"""Repository delivery workflows are blocking and cover every shipped subsystem."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_ci_requires_all_blocking_jobs_and_commands() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    for job in ("backend-ci:", "agents-ci:", "frontend-ci:", "contract-ci:"):
        assert job in workflow

    for command in (
        "ruff check .",
        "python -m compileall",
        "pytest tests",
        "alembic upgrade head",
        "pnpm install --frozen-lockfile",
        "pnpm lint",
        "pnpm typecheck",
        "pnpm test",
        "pnpm build",
        "backend/scripts/check-contracts.py",
    ):
        assert command in workflow

    assert "continue-on-error" not in workflow
    assert "Detect frontend" not in workflow
    assert "|| pnpm install" not in workflow
    assert "|| echo" not in workflow


def test_security_workflow_is_blocking_and_audits_both_ecosystems() -> None:
    workflow = (ROOT / ".github/workflows/security.yml").read_text(encoding="utf-8")

    for command in ("gitleaks", "pip-audit", "pnpm audit"):
        assert command in workflow
    assert "continue-on-error" not in workflow
    assert "check-secrets.py" in workflow


def test_active_product_copy_has_no_fraud_specific_positioning() -> None:
    roots = (
        ROOT / "backend" / "app",
        ROOT / "backend" / "skills",
        ROOT / "backend" / "scripts",
        ROOT / "agents" / "agents",
        ROOT / "agents" / "mcp_servers",
        ROOT / "agents" / "skills",
        ROOT / "frontend",
    )
    files = [ROOT / "README.md", ROOT / "GETTING_STARTED.md", ROOT / "Makefile"]
    suffixes = {".md", ".py", ".ts", ".tsx", ".yaml", ".yml"}
    files.extend(
        path
        for root in roots
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in suffixes
        and "node_modules" not in path.parts
        and ".next" not in path.parts
    )

    forbidden = ("fraud", "scam", "反诈", "防诈骗", "反欺诈", "诈骗", "骗局", "96110")
    offenders = [
        str(path.relative_to(ROOT))
        for path in files
        if any(token in path.read_text(encoding="utf-8").lower() for token in forbidden)
    ]

    assert offenders == []


def test_removed_video_skill_is_hidden_for_existing_databases() -> None:
    migration = (
        ROOT
        / "backend"
        / "alembic"
        / "versions"
        / "20260722_0007_retire_legacy_video_skill.py"
    ).read_text(encoding="utf-8")

    assert "status = 'archived'" in migration
    assert "visibility = 'private'" in migration


def test_windows_alembic_commands_run_from_backend_directory() -> None:
    docs = "\n".join(
        (ROOT / name).read_text(encoding="utf-8")
        for name in ("README.md", "CONTRIBUTING.md")
    )

    assert "-c backend/alembic.ini" not in docs


def test_mock_demo_never_forces_live_llm_mode() -> None:
    script = (ROOT / "test" / "run_short_video_real_workflow.py").read_text(
        encoding="utf-8"
    )
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert 'os.environ["LITELLM_MOCK"] = "false"' not in script
    assert "LITELLM_MOCK=true" in makefile
