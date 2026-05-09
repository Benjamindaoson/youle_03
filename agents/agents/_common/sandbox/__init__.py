"""Sandbox Task Runtime(ADR-025)。

每个 task 可申请一个独立 sandbox,用于:
  - 在隔离环境里跑 code_executor MCP(I 阶段)
  - browser_use MCP 的 session(登录态、cookies、下载)
  - 临时文件 + OSS 双向同步
  - 长任务暂停 / 恢复(快照 sandbox 状态)

# Provider 抽象
默认提供两个 provider:
  - `local`:subprocess + tempdir,**无真实隔离**,仅 dev / CI 用
  - `e2b`:e2b.dev SaaS sandbox(产线推荐起步)
S2 升级:`firecracker` provider(自托管 microVM)

# 选择
通过 `SANDBOX_PROVIDER` 环境变量(`local` / `e2b`)选择。未指定 → `local`。

# Graceful
provider 不可用(SDK 未装 / API key 缺失 / 服务挂)→ raise
`SandboxUnavailable`,调用方可降级到 no-sandbox 路径。
"""

from agents._common.sandbox.provider import (
    ExecResult,
    Sandbox,
    SandboxBudgetExceeded,
    SandboxProvider,
    SandboxUnavailable,
)
from agents._common.sandbox.manager import (
    SandboxManager,
    get_default_manager,
)

__all__ = [
    "ExecResult",
    "Sandbox",
    "SandboxBudgetExceeded",
    "SandboxManager",
    "SandboxProvider",
    "SandboxUnavailable",
    "get_default_manager",
]
