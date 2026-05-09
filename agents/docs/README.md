# agents/docs — 智能体模块的本地 ADR

本目录是 **agents 包内部**的架构决策记录。
全仓库级 ADR 仍在 `backend/docs/`(ADR-001..018)— 那些是跨模块决策。

ADR-019 起的智能化升级序列:
- [ADR-019](./ADR-019-dynamic-planner.md):Planner Agent 与动态规划路径
- [ADR-020](./ADR-020-critic-loop.md):Critic Loop —— 创作 step 后自动评审 + 重试
- [ADR-021](./ADR-021-step-persona.md):Step Persona —— 能力维度的 worker 上层人格
- [ADR-022](./ADR-022-md-skills-and-episodes.md):MD Skills 一等公民 + Episode 召回
- [ADR-023](./ADR-023-critique-reflexion-bridge.md):Critique → Reflexion 桥接(写飞轮)
- [ADR-024](./ADR-024-s2-integration.md):S2 集成路径(Planner / Critique-Signal / 飞轮闭环)
- [ADR-025](./ADR-025-sandbox-runtime.md):Sandbox Task Runtime(Local / e2b / Firecracker)
- [ADR-026](./ADR-026-browser-and-code-mcp.md):browser_use + code_executor MCP servers
- [ADR-027](./ADR-027-eval-harness.md):Eval 评测体系(Golden Suite + Runner)

升级路线图见 `UPGRADE_TO_S_TIER.md`(若存在)或与作者沟通。
