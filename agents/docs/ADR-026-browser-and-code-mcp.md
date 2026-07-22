# ADR-026: browser_use 与 code_executor MCP servers

**状态**: Skeleton(I 阶段已落地;production 上线还需依赖安装 + 配置)
**日期**: 2026-05-09
**关联**: ADR-009(MCP-first)、ADR-025(Sandbox Runtime)

## 结论

新增两个 MCP servers,把工具集从"内容生产垂直域"扩展到"通用执行器":

| Server | 工具 | 实现 | production 依赖 |
|---|---|---|---|
| `mcp-browser-use` | navigate / click / fill / extract_text / extract_links / screenshot / wait_for / close | Playwright + Chromium | `pip install playwright` + `playwright install chromium` |
| `mcp-code-executor` | python_exec / shell_exec / write_file / read_file / list_dir / install_package | 转发到 ADR-025 SandboxManager | `SANDBOX_PROVIDER=e2b` + `E2B_API_KEY`(production) |

## 背景

S 档目标的 12 项升级里第 4 条:**通用执行器三件套**(browser / code / files)。
没有这些,Agent 只能做"我们 handler 写过的"事;有了它们,Agent 可以做
"用户上传 CSV 让我清洗 + 出图"、"帮我抓抖音热榜"、"读这个 PDF 提取表格" 之类的开放任务。

## 决策

### 1. 都按 MCP 部署,与既有 7 个 MCP server 同模式

复用 `mcp_servers/_shared/http_app.py` 的 `make_app` — 工具是
`async def name(arguments: dict) -> dict`,自动注册成 `POST /tools/<name>`。
worker 端的 `react_runner._build_tools` / `_merged_mcp_uris` 已经通过
`mcp://browser_use/*` / `mcp://code_executor/*` 把它们暴露给 ReAct LLM,**零改动**
就能被 plan 引用。

ADR-021 的 Step Persona 控制谁能调:
- `researcher`:可调 `mcp://search/*` + `mcp://browser_use/extract_text`(S2 加 patten)
- `default`:全开
- `critic`:全黑(本来就拒所有 MCP)

### 2. browser_use 用 Playwright + 进程级 session

S1 用进程级单 session 跑(`_browser` / `_page` 全局),好处:
- 跨多次工具调用保持登录态、cookies、当前页
- 实现简单

代价:**多任务并发会冲突**(两个 task 抢一个 page)。production 上线前必须改成
per-task session(配合 ADR-025,把 browser 跑在 sandbox 里)。S2 改造点。

### 3. code_executor 转发到 SandboxManager

不直接 `subprocess.run`,所有执行都通过 `agents._common.sandbox` 走。这样:
- 隔离强度由 provider 决定(local 弱 / e2b 强 / Firecracker S3)
- 切换隔离方案零代码改动 — 改 `SANDBOX_PROVIDER` 即可
- 预算硬约束(timeout / stdout 字节)在 sandbox 层统一执行

code_executor 按调用参数中的 `task_id` 复用独立 sandbox，任务之间不共享文件或执行状态。
进程内最多保留 `CODE_EXECUTOR_MAX_SESSIONS` 个会话（默认 4），超出时释放最久未使用的会话；
任务完成后可调用 `close_session` 主动释放。

### 4. install_package 默认禁,白名单可配

```bash
CODE_EXECUTOR_ALLOW_PIP=true     # 显式开启
CODE_EXECUTOR_PIP_WHITELIST=pandas,numpy,pillow,requests,beautifulsoup4,lxml,openpyxl,python-dateutil
```

为什么默认禁:
- agent 自由 pip install = 攻击面
- 白名单覆盖 90% 数据处理需求

S3 的 sandbox 镜像里预装这些常用包,S2 阶段允许动态安装但锁白名单。

### 5. Graceful 设计

| 故障 | 行为 |
|---|---|
| Playwright 未装 | 工具返回 `{"error": "Playwright 未安装..."}`,不让 server 崩 |
| Sandbox provider 不可用 | 返回 `{"error": "sandbox unavailable: ..."}` |
| 超时 | 返回 `{"timed_out": true, ...}`,不抛 |
| 字节超限 | 返回 `{"truncated": true, ...}`,带截断后内容 |

任何工具都**永不向上抛 5xx**,始终返回 dict — Agent 端 ReAct 看到 error 字段会自己 fallback。

## 模块结构

```
agents/mcp_servers/
├── browser_use/
│   ├── __init__.py
│   └── server.py           # FastAPI app(make_app)+ 8 个工具
├── code_executor/
│   ├── __init__.py
│   └── server.py           # FastAPI app + 7 个工具(转发到 SandboxManager)
└── _shared/http_app.py     # 不动
```

## 配置

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `BROWSER_HEADLESS` | `true` | Playwright 无头模式 |
| `BROWSER_DEFAULT_TIMEOUT_MS` | `15000` | navigate / click / wait 默认超时 |
| `BROWSER_USER_AGENT` | `Mozilla/5.0 (compatible; YouleAgent/1.0)` | UA |
| `CODE_EXECUTOR_DEFAULT_TIMEOUT_S` | `60` | python_exec / shell_exec 默认超时 |
| `CODE_EXECUTOR_MAX_SESSIONS` | `4` | 进程内最多保留的 task sandbox 数量 |
| `CODE_EXECUTOR_ALLOW_PIP` | `false` | 是否开启 install_package |
| `CODE_EXECUTOR_PIP_WHITELIST` | `pandas,numpy,...` | 允许的包列表(逗号分隔) |
| `SANDBOX_PROVIDER` | `local` | code_executor 用 — 见 ADR-025 |

## 与 ADR / 铁律兼容性

| ADR / 铁律 | 兼容 | 说明 |
|---|---|---|
| ADR-002(Worker 不互调)| ✓ | 都是 worker 调 MCP,worker 边界不变 |
| ADR-009(MCP-first)| ✓ | 严格遵守 |
| ADR-021(Step Persona)| 协同 | researcher 可调 browser,critic 不可 |
| ADR-025(Sandbox)| 协同 | code_executor 转发到 sandbox |

## 测试

`agents/tests/unit/`:
- `test_browser_use_mcp.py`:输入校验 + Playwright 未装时 graceful
- `test_code_executor_mcp.py`:python_exec / shell_exec / write+read 文本+二进制 / list_dir / install_package 白名单

不真测真浏览器 — Playwright + Chromium 二进制不在测试镜像里,production 部署
时需独立 smoke。

## V1 部署约束(决策)

### 1. 单副本部署(concurrency=1)

browser_use 仍是进程级单 session；code_executor 已按 `task_id` 隔离 sandbox，但会话映射仍在单进程内存中。
**V1 部署明确要求**:

```yaml
# K8s deployment(production)
mcp-browser-use:
  replicas: 1               # 不可超过 1
  port: 7008
mcp-code-executor:
  replicas: 1               # 不可超过 1
  port: 7009
```

`__main__` 块已写死 `workers=1`,部署侧需要在 K8s 上锁 `replicas: 1` 直到 S2
改成 per-task session/sandbox 后才解锁横向扩展。

实际负载:V1 的 browser/code 类任务量极少(主流量是短视频 + 详情图,不走这两条),
单副本足够。

### 2. 鉴权依赖网络隔离(决策)

V1 **不加 service-to-service token**,理由:

- 与现有 7 个 MCP server 一致(它们也都没鉴权)
- 全部部署在 K8s 同一 namespace,通过 NetworkPolicy 限制只有 worker pod 可达
- 加 token middleware 会让 9 个 server 同时改,工作量不匹配 V1 收益

S2 的触发条件(任一命中即引入 token):
- 跨集群部署(MCP 与 worker 不在同一 cluster)
- 合规审计要求 service-to-service auth
- 任何一个 MCP server 暴露到 namespace 外

接入点单点修改:[mcp_servers/_shared/http_app.py](../mcp_servers/_shared/http_app.py) 加 middleware,所有 server 自动生效。

## 风险

| 风险 | 缓解 |
|---|---|
| Agent 通过 browser 访问恶意网站 | S2 加 URL 白名单 / 黑名单(`BROWSER_URL_ALLOW`)+ 监控 |
| Agent pip install 恶意包 | `ALLOW_PIP=false` + 白名单 |
| browser session 跨 task 串档 | **V1 单副本部署兜住**;S2 改 per-task session 后允许横向扩 |
| code_executor sandbox 跨 task 串档 | 按必填 `task_id` 隔离，并提供 `close_session` 释放 |
| sandbox 用 local provider 上 production | ADR-025 文档明确;部署清单卡 `SANDBOX_PROVIDER=e2b` |
| 截图返回 base64 体积大 | screenshot 默认非 full_page;调用方拿到 base64 应及时落 OSS |
| MCP server 暴露到 K8s 集群外 | V1 不允许;NetworkPolicy 拦截 |

## S2 后续

- per-task browser session(配合 ADR-025 的 task_id → sandbox 映射)
- code_executor 会话映射迁移到外部协调层后再启用多副本
- browser 加 URL 白/黑名单 + 监控
- pip install 白名单滚动维护 + 每周扫描镜像漏洞
