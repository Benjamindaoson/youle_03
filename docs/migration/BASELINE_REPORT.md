# Youle MAS 主干基线报告

审计日期：2026-07-21  
唯一主干：`youle_03@14815ee`  
审计分支：`codex/youle-mas-consolidation`

## 结论

`youle_03` 可以作为唯一主干，但当前提交不是全绿基线。Python 模块可以完整编译，Docker Compose 配置和 Alembic 迁移链有效；后端已有 243 个测试通过。阻塞项是主干自带的 8 个后端测试失败、Agent 测试包导入错误、203 个 Ruff 问题，以及仓库根目录缺少 README 所描述的 `frontend/`。这些问题都发生在业务迁移之前，后续将用独立的“基线修复”提交处理，避免把既有缺陷误归因于四库整合。

本机 Docker Desktop 守护进程没有运行，所以 PostgreSQL/Redis 的容器内运行验证和 `alembic upgrade head` 实际执行暂时属于环境阻塞；迁移历史与 Compose 静态配置已验证。

## 工具与环境

| 项目 | 检测结果 |
| --- | --- |
| 操作系统/终端 | Windows / PowerShell |
| Python | `3.12.10` |
| Python 项目环境 | 仓库根目录 `.venv`，使用 `uv` 创建；未向全局解释器安装项目依赖 |
| uv | `0.11.29` |
| Node.js | `v24.16.0`；高于目标 CI 的 Node 20，最终 CI 仍固定 Node 20 |
| pnpm | `11.9.0`；高于目标 CI 的 pnpm 9，最终仓库通过 `packageManager`/Corepack 固定版本 |
| Docker Compose | `v5.3.0` |
| OpenSpec | `1.6.0` |

依赖安装命令：

```powershell
uv venv --python 3.12 .venv
uv pip install --python .\.venv\Scripts\python.exe -e '.\backend[dev]' -e '.\agents[dev]' -e '.\agents\mcp_servers'
```

首次依赖下载因 PyPI 连接重置而超时；原命令重试后成功，共安装 158 个包。该问题归类为一次性网络环境问题，不是代码缺陷。

## 验证结果

| 检查 | 命令 | 结果 | 分类 |
| --- | --- | --- | --- |
| 全仓 Ruff | `.venv\Scripts\ruff.exe check .` | 失败：203 个问题，其中 182 个可自动修复 | 主干代码质量缺陷 |
| 根目录 pytest | `.venv\Scripts\pytest.exe` | 失败：收集 544 项时被 `agents.mcp_servers` 导入错误中断 | 主干测试包路径缺陷 |
| 后端 pytest | `cd backend; ..\.venv\Scripts\pytest.exe tests` | 243 通过、8 失败、2 跳过，共 253 项 | 主干代码/测试漂移 |
| Agent pytest | `cd agents; ..\.venv\Scripts\pytest.exe tests` | 收集 185 项时有 1 个导入错误，未进入执行 | 主干测试包路径缺陷 |
| Python 编译 | `.venv\Scripts\python.exe -m compileall backend agents` | 通过 | 已验证 |
| Alembic 迁移历史 | `cd backend; ..\.venv\Scripts\alembic.exe history` | 通过：`base -> 0001 -> 0002 -> 0003 -> 0004 (head)` | 已验证 |
| Alembic 实际升级 | `cd backend; ..\.venv\Scripts\alembic.exe upgrade head` | 失败：PostgreSQL 连接被拒绝，`WinError 1225` | 环境阻塞；Docker 守护进程未运行 |
| 根前端存在性 | `Test-Path frontend/package.json` | 失败：`frontend/` 不存在 | 主干缺失功能；README 与仓库不一致 |
| Compose 静态配置 | `docker compose -f backend/infrastructure/docker-compose.yml -f backend/infrastructure/docker-compose.mock.yml config --quiet` | 通过 | 已验证 |
| Docker 守护进程 | `docker version` | 失败：Docker Desktop Linux engine named pipe 不存在 | 环境阻塞 |

## 后端失败明细

| 失败组 | 数量 | 根因初判 | 处理原则 |
| --- | ---: | --- | --- |
| 反欺诈/电商 Skill 编译 | 2 | 编译阶段用 StrictUndefined 渲染了运行阶段才产生的 `research`/`style_analysis` 输出 | 修复编译器对步骤输出引用的处理并补回归测试 |
| Redis Consumer 超时测试 | 1 | 测试替换 `asyncio.wait_for` 后又递归调用已替换对象 | 修正测试夹具，不改变生产超时语义 |
| 头像确认测试 | 2 | 测试 mock 目标与当前对象存储签名/调用位置漂移 | 按实际边界修复 mock 或实现，并验证上传流程 |
| 配额服务测试 | 3 | 异步 `session.execute` 使用了不可 await 的 `MagicMock` | 改用异步 mock，保留生产查询语义 |

## Agent 测试收集失败

`agents/tests/unit/test_browser_use_mcp.py` 从 `agents.mcp_servers` 导入，但生产代码、Docker 启动命令和集成文档使用的是命名空间包 `mcp_servers.*`。这是测试导入路径与运行时包布局不一致，后续基线修复将统一为实际运行路径并增加 CI import smoke check。

## 风险与后续门禁

- 先提交本报告、迁移矩阵和 OpenSpec，不改业务代码。
- 随后的基线修复单独提交，并要求 Ruff、后端测试、Agent 测试和 compileall 通过。
- 只有基线绿灯后才接入 EventBus/SSE、OTP、Skill 生命周期和正式前端。
- 最终必须在可用 Docker 环境上补跑全量 Alembic、PostgreSQL/Redis、后端、Worker、MCP、前端和无 Key mock E2E。若当前机器始终没有 Docker 守护进程，最终报告会明确列为未验证，不会伪报成功。

## 基线修复结果

基线报告提交后，既有失败用独立修复提交处理，未混入四库迁移功能：

| 检查 | 修复后结果 |
| --- | --- |
| 全仓 Ruff | 通过：`All checks passed!` |
| 后端 pytest | 252 通过、2 跳过；共 254 项 |
| Agent pytest | 188 通过、2 跳过；共 190 项 |
| 根目录 Agent handler/Live 套件 | 31 通过、75 按显式 live 条件跳过；共 106 项 |
| Python compileall | 通过 |

根目录原有 `*live*.py` 和数据库工作流测试以前会在没有外部依赖时直接等待真实 LLM、Redis 或 PostgreSQL。它们现在保留原测试体，仅增加 `YOULE_RUN_LIVE_TESTS=1` 的显式 opt-in 门禁；默认执行的 31 个无外部依赖 handler 契约测试仍全部运行。后续新增的无 Key mock E2E 不使用该 live 门禁。
