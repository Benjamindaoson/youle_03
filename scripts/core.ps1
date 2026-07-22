param(
    [ValidateSet('setup', 'start', 'stop', 'status')]
    [string]$Action = 'start',
    [int]$BackendPort = 8001,
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$RuntimeDir = Join-Path $Root '.runtime'
$PidFile = Join-Path $RuntimeDir 'core-processes.json'
$ComposeFile = Join-Path $Root 'compose.core.yml'
$Python = Join-Path $Root '.venv\Scripts\python.exe'

function Invoke-Checked([string]$Program, [string[]]$Arguments, [string]$WorkingDirectory = $Root) {
    Push-Location $WorkingDirectory
    try {
        & $Program @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed ($LASTEXITCODE): $Program $($Arguments -join ' ')"
        }
    }
    finally {
        Pop-Location
    }
}

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function Test-Port([int]$Port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Find-FreePort([int]$Preferred) {
    $Port = $Preferred
    while (Test-Port $Port) { $Port++ }
    return $Port
}

function Initialize-Core {
    Assert-Command 'docker'
    Assert-Command 'uv'
    Assert-Command 'pnpm'
    $env:PYTHONUTF8 = '1'
    $env:DEBUG = 'false'
    $env:LITELLM_MOCK = 'true'
    $env:LOCAL_GUEST_ACCESS = 'true'

    if (-not (Test-Path (Join-Path $Root '.env'))) {
        Copy-Item (Join-Path $Root '.env.example') (Join-Path $Root '.env')
    }

    Invoke-Checked 'docker' @('compose', '-f', $ComposeFile, 'up', '-d', '--wait')
    Invoke-Checked 'uv' @('sync', '--locked', '--all-packages', '--all-extras')
    Invoke-Checked 'pnpm' @('--dir', 'frontend', 'install', '--frozen-lockfile')
    Invoke-Checked 'uv' @('run', 'alembic', 'upgrade', 'head') (Join-Path $Root 'backend')
    Invoke-Checked 'uv' @('run', 'python', 'scripts/bootstrap-skills.py') (Join-Path $Root 'backend')
}

function Read-CoreProcesses {
    if (-not (Test-Path $PidFile)) { return $null }
    return Get-Content $PidFile -Raw | ConvertFrom-Json
}

function Test-OwnedProcess([int]$ProcessId, [string]$Name) {
    $Process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if (-not $Process -or -not $Process.CommandLine) { return $false }
    if ($Process.CommandLine.IndexOf($Root, [StringComparison]::OrdinalIgnoreCase) -lt 0) { return $false }
    $Marker = switch ($Name) {
        'backend' { 'app.run' }
        'agent' { 'agents.core_worker' }
        'frontend' { 'next' }
        default { return $false }
    }
    return $Process.CommandLine.IndexOf($Marker, [StringComparison]::OrdinalIgnoreCase) -ge 0
}

function Show-CoreStatus {
    $State = Read-CoreProcesses
    if (-not $State) {
        Write-Host 'Core application processes have not been started.'
        return
    }
    foreach ($Name in @('backend', 'agent', 'frontend')) {
        $Id = [int]$State.$Name
        $Running = Test-OwnedProcess $Id $Name
        Write-Host ("{0,-9} pid={1,-7} {2}" -f $Name, $Id, $(if ($Running) { 'running' } else { 'stopped' }))
    }
    Write-Host "Backend: http://127.0.0.1:$($State.backend_port)"
    Write-Host "Frontend: http://127.0.0.1:$($State.frontend_port)"
}

function Start-Core {
    if (-not (Test-Path $Python)) {
        throw 'Project .venv is missing. Run: .\scripts\core.ps1 setup'
    }
    Assert-Command 'pnpm'
    Assert-Command 'docker'
    New-Item -ItemType Directory -Force $RuntimeDir | Out-Null

    $Existing = Read-CoreProcesses
    if ($Existing) {
        $Owned = @('backend', 'agent', 'frontend') | Where-Object {
            Test-OwnedProcess ([int]$Existing.$_) $_
        }
        if ($Owned.Count -eq 3) {
            throw 'Core is already running. Use status or stop first.'
        }
        # A build or a crashed dev server can leave only part of the core
        # alive. Restart the owned remainder instead of leaving users with an
        # unusable state and a misleading "already running" error.
        if ($Owned.Count -gt 0) { Stop-Core }
        else { Remove-Item $PidFile -ErrorAction SilentlyContinue }
    }

    $BackendPort = Find-FreePort $BackendPort
    $FrontendPort = Find-FreePort $FrontendPort
    Invoke-Checked 'docker' @('compose', '-f', $ComposeFile, 'up', '-d', '--wait')
    $env:LITELLM_MOCK = 'true'
    $env:LOCAL_GUEST_ACCESS = 'true'
    $env:DEBUG = 'false'
    $env:PYTHONUTF8 = '1'
    $env:REDIS_URL = 'redis://127.0.0.1:6379/0'
    $env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:$BackendPort"
    $env:NEXT_PUBLIC_LOCAL_GUEST_ACCESS = 'true'

    $Backend = Start-Process -FilePath $Python -ArgumentList @('-m', 'app.run', '--host', '127.0.0.1', '--port', $BackendPort) -WorkingDirectory (Join-Path $Root 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $RuntimeDir 'backend.log') -RedirectStandardError (Join-Path $RuntimeDir 'backend.error.log')
    $Agent = Start-Process -FilePath $Python -ArgumentList @('-m', 'agents.core_worker') -WorkingDirectory $Root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $RuntimeDir 'agent.log') -RedirectStandardError (Join-Path $RuntimeDir 'agent.error.log')
    $Node = (Get-Command node).Source
    $Next = Join-Path $Root 'frontend\node_modules\next\dist\bin\next'
    $Frontend = Start-Process -FilePath $Node -ArgumentList @($Next, 'dev', '--hostname', '127.0.0.1', '--port', $FrontendPort) -WorkingDirectory (Join-Path $Root 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $RuntimeDir 'frontend.log') -RedirectStandardError (Join-Path $RuntimeDir 'frontend.error.log')

    @{
        backend = $Backend.Id
        agent = $Agent.Id
        frontend = $Frontend.Id
        backend_port = $BackendPort
        frontend_port = $FrontendPort
    } | ConvertTo-Json | Set-Content -Encoding utf8 $PidFile

    try {
        $Deadline = (Get-Date).AddSeconds(45)
        do {
            try {
                $Health = Invoke-RestMethod "http://127.0.0.1:$BackendPort/ready" -TimeoutSec 2
                if ($Health.status -eq 'ok') { break }
            }
            catch { Start-Sleep -Milliseconds 500 }
        } while ((Get-Date) -lt $Deadline)

        if ((Get-Date) -ge $Deadline) {
            throw "Backend did not become ready. See $RuntimeDir\backend.error.log"
        }
        if (-not (Test-OwnedProcess $Agent.Id 'agent')) {
            throw "Agent worker stopped during startup. See $RuntimeDir\agent.error.log"
        }
        if (-not (Test-OwnedProcess $Frontend.Id 'frontend')) {
            throw "Frontend stopped during startup. See $RuntimeDir\frontend.error.log"
        }
        Show-CoreStatus
    }
    catch {
        Stop-Core
        throw
    }
}

function Stop-ProcessTree([int]$RootProcessId) {
    $Children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$RootProcessId" -ErrorAction SilentlyContinue
    foreach ($Child in $Children) {
        Stop-ProcessTree ([int]$Child.ProcessId)
    }
    Stop-Process -Id $RootProcessId -ErrorAction SilentlyContinue
}

function Stop-Core {
    $State = Read-CoreProcesses
    if (-not $State) { return }
    foreach ($Name in @('backend', 'agent', 'frontend')) {
        $Id = [int]$State.$Name
        if (Test-OwnedProcess $Id $Name) { Stop-ProcessTree $Id }
    }
    Remove-Item $PidFile -ErrorAction SilentlyContinue
}

switch ($Action) {
    'setup' { Initialize-Core }
    'start' { Start-Core }
    'stop' { Stop-Core }
    'status' { Show-CoreStatus }
}
