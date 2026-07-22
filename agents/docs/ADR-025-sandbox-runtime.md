# ADR-025: Sandbox Task Runtime

**状态**: Skeleton(本地 provider 落地;e2b 适配器骨架;Firecracker 留给 S3)
**日期**: 2026-05-09
**关联**: ADR-026(browser_use / code_executor MCP)

## 结论

引入 `agents._common.sandbox` 抽象,让 task 可以申请独立 sandbox 跑代码 / 浏览器 / 文件操作:

- **Provider 接口**(Protocol):`SandboxProvider.acquire / release / healthy`
- **Sandbox 实例**(Protocol):`exec / python / write_file / read_file / list_dir / snapshot / close`
- **本次 S1 落地**:
  - `LocalSandboxProvider` - subprocess + tempdir,**dev/CI 用**
  - `E2BSandboxProvider` - e2b.dev SaaS 适配器骨架(SDK 未装时 graceful 抛 SandboxUnavailable)
  - `SandboxManager` - 进程级单例,按 `SANDBOX_PROVIDER` 环境变量选 provider
- **后续**:S3 加 `FirecrackerSandboxProvider`(自托管 microVM),加真池化与预热

## 背景

Manus 拉开身位的核心:**每个任务拿到属于它的虚拟机**。Agent 可以写文件、跑 Python、装包、操作浏览器,行为像人在工作台前。

我们的现状:Worker 是无状态进程,每个 step 处理完就忘 — 想做"用户上传 CSV 让我清洗 + 出图"这类任务,只能靠手写 handler。Sandbox 是这一切的基础设施。

## 决策

### 1. Protocol-based,不强制继承

`SandboxProvider` 与 `Sandbox` 都是 `typing.Protocol` — provider 实现者可以选继承 `_SandboxBase`,也可以自己写 — 只要满足接口。

理由:
- e2b SDK 已经有自己的 Sandbox 类型,我们用 adapter 包装比强行继承自然
- Firecracker(S3)行为差异更大,不强行套壳

### 2. 三个 provider 分层

| Provider | 隔离强度 | 适用 |
|---|---|---|
| `local` | tempdir + subprocess + timeout | dev / CI / 单测 |
| `e2b` | 真 microVM(SaaS,e2b.dev)| **production 起步** |
| `firecracker`(S3)| 真 microVM(自托管)| 高规模 production |

`local` provider **不是真隔离** — 进程逃逸是可能的。document 上明确写"仅 dev"。

### 3. e2b 适配器用 lazy import

```python
def _try_import_e2b():
    try:
        from e2b_code_interpreter import Sandbox as E2BSdkSandbox
        return E2BSdkSandbox
    except ImportError:
        return None
```

SDK 不在 → `acquire` 抛 `SandboxUnavailable`,**不让 import 阶段崩**。
agents 包默认不强依赖 50MB 的 e2b SDK — production 部署清单加一行 install 即可。

### 4. 预算硬约束

每个 sandbox 在 acquire 时设:
- `wall_clock_budget_s`(默认 600s)
- `max_stdout_bytes`(默认 4MB)

超出 → `SandboxBudgetExceeded`。这是防止恶意 / 失控代码占用资源。

### 5. 不池化(S1)

`acquire` 每次产 fresh sandbox。S3 的真池化需要:
- 启动期预热 N 个空 sandbox
- 用完后镜像回滚 + 复用
- 健康检查 + 死亡替换

S1 不做的理由:e2b SaaS 自己有池化;local 启动 sandbox 几乎零成本;Firecracker 才需要这个,而 Firecracker 是 S3 的事。

## 模块结构

```
agents/agents/_common/sandbox/
├── __init__.py
├── provider.py            # Protocol + ExecResult + SandboxBudgetExceeded + SandboxUnavailable
├── provider_local.py      # LocalSandboxProvider + LocalSandbox
├── provider_e2b.py        # E2BSandboxProvider + E2BSandbox(适配器骨架)
└── manager.py             # SandboxManager + get_default_manager + session() ctxmgr
```

## 配置

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `SANDBOX_PROVIDER` | `local` | provider 选择:`local` / `e2b` |
| `LOCAL_SANDBOX_ROOT` | `${TMPDIR}/haole-sandbox` | 本地 sandbox 工作目录 |
| `LOCAL_SANDBOX_PYTHON` | `python` | 本地 python 解释器路径 |
| `E2B_API_KEY` | - | e2b SaaS API key |

## API 用法

```python
from agents._common.sandbox import get_default_manager

mgr = get_default_manager()
async with mgr.session(task_id="t-1", wall_clock_budget_s=120) as sb:
    await sb.write_file("data.csv", csv_text)
    r = await sb.python("""
import pandas as pd
df = pd.read_csv('data.csv')
print(df.describe().to_json())
""", timeout_s=30)
    if r.ok():
        process(r.stdout)
```

## 与 ADR / 铁律兼容性

| ADR / 铁律 | 兼容 | 说明 |
|---|---|---|
| ADR-001-rev(4 Worker)| ✓ | sandbox 是 worker 内的工具,不改进程模型 |
| ADR-002(Worker 不互调)| ✓ | sandbox 也不互调 |
| ADR-009(MCP-first)| 协同 | ADR-026 的 code_executor / browser_use MCP 通过 sandbox 跑 |
| 铁律 4(产物用引用)| ✓ | sandbox 内产物显式 read_file 后落 OSS,不进 LangGraph state |

## 测试

`agents/tests/unit/test_sandbox.py`:
- Protocol 兼容性
- 生命周期(acquire / release / session ctxmgr)
- python / exec / timeout / stdout 截断
- 文件 IO(write/read 文本 / 二进制 / max_bytes)
- 关闭幂等 / 关闭后操作抛 budget exceeded
- E2BSandboxProvider 在 SDK 未装时抛 SandboxUnavailable
- Manager 默认 local + 未知 provider silent fallback

注:`test_python_executes` 在 python 解释器不可达时 `pytest.skip`(沙箱环境)。

## 风险

| 风险 | 缓解 |
|---|---|
| local provider 不真隔离 → 误用到 production | doc 显式标记"仅 dev";SANDBOX_PROVIDER 默认 `local` 但 production 配置应改 e2b |
| e2b SDK API 在不同版本不兼容 | 适配器内 try/except 包所有 SDK 调用,挂 → ExecResult.error;production 上线前需 pin SDK 版本 |
| sandbox 泄漏(forget release)| `session()` ctxmgr 是推荐路径,出 with 块强制 release |
| 预算被超 | `SandboxBudgetExceeded` 是真异常,调用方需要 catch |

## S3 后续

- `provider_firecracker.py` - 自托管 microVM
- 池化:启动期预热 N 个,用完镜像回滚
- snapshot 真镜像(目前只是 metadata)→ 长任务跨日恢复
- 资源限制(CPU / RAM / 磁盘 quota)
