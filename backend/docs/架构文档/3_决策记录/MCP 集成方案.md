# MCP 集成方案

**版本**:v3.0(对应 ADR-009;Agent 编号同步 ADR-001-rev)
**日期**:2026-05-05
**面向**:智能体团队 / 后端工程师 / Skill 创作者
**地位**:工具集成的唯一标准。任何引入新工具都按本文档走。

**v3.0 关键变更**:
- 🔄 文档内 `agent_2` / `agent_3` / `agent_4` 引用按 ADR-001-rev 反向同步
- 保留:7 个 V1 MCP server / Agent 端集成范式 / Skill YAML 引用

---

## 一、为什么 MCP

### 1.1 背景

到 2026 年,Anthropic 的 **Model Context Protocol(MCP)** 已成为 agent 工具集成的事实标准。Claude Code、Cursor、Anthropic Claude Desktop、ChatGPT Operator 等都已采纳;社区 MCP server 涵盖 Linear、Notion、Slack、GitHub、Figma、Brave Search、Filesystem、Postgres 等数十种工具。

### 1.2 v1.0 的问题

之前架构里,工具直接写死在 Agent handler 里(Tavily SDK / FFmpeg subprocess / python-pptx 等)。问题:

1. **接入新工具成本高**——每个 Agent 改 handler 代码
2. **不能复用社区生态**——MCP server 写好了,我们重新造轮子
3. **Skill 创作飞轮卡住**——创作者无法用标准协议引用工具
4. **调试 / 审计 / 限流不统一**——每个工具自己实现

### 1.3 决议(ADR-009)

**所有外部工具一律以 MCP server 形式暴露,Agent handler 作为 MCP client 调用。**

例外:**生成式模型走 LiteLLM**(GPT-Image-2 / Veo-3 / Volcengine TTS 等)。"工具" vs "模型"分界线:

- 工具:确定性 / 副作用 / 调用 → 走 MCP
- 模型:概率性 / 内容生成 / 调用 → 走 LiteLLM

---

## 二、MCP 协议速览

### 2.1 核心概念

MCP 是基于 JSON-RPC 2.0 的协议,定义 Client 与 Server 之间的:

- **Tools**:server 暴露的可调用函数(`tools/list` 列出 / `tools/call` 调用)
- **Resources**:server 暴露的可读资源(文件 / 数据库表 / API endpoint)
- **Prompts**:server 提供的可复用 prompt 模板
- **Sampling**(双向):server 反过来可请求 client(LLM)生成内容

### 2.2 传输

V1 用两种:

- **stdio**:本地 server,Python/Node 子进程
- **HTTP+SSE**:远程 server,K8s 部署

V2 评估:**Streamable HTTP**(MCP 0.6+ 推荐)

### 2.3 SDK

| 语言 | 包 |
|------|-----|
| Python | `mcp` (官方) |
| TypeScript | `@modelcontextprotocol/sdk` (官方) |
| Go | `mcp-go`(社区)|

---

## 三、V1 的 7 个 MCP server

| Server | 实现 | 协议 | tools 数 |
|--------|------|------|---------|
| `mcp-search` | Python | stdio + HTTP | 2 |
| `mcp-image-tools` | Python | stdio + HTTP | 4 |
| `mcp-video-tools` | Python | HTTP(GPU 节点)| 3 |
| `mcp-audio-tools` | Python | HTTP | 3 |
| `mcp-document-tools` | Python | stdio + HTTP | 5 |
| `mcp-oss` | Python | stdio | 3 |
| `mcp-platform-publish`(V1.5)| TypeScript | HTTP | 3 |

### 3.1 mcp-search

```python
# mcp_servers/search/server.py
from mcp.server import Server
from mcp.server.stdio import stdio_server
import httpx

server = Server("mcp-search")

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="web_search",
            description="使用 Tavily 在网上搜索",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索 query"},
                    "max_results": {"type": "integer", "default": 5},
                    "lang": {"type": "string", "default": "zh"}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="web_fetch",
            description="抓取 URL 内容,渲染 JS",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "render_js": {"type": "boolean", "default": True}
                },
                "required": ["url"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "web_search":
        return await tavily_search(**arguments)
    elif name == "web_fetch":
        return await playwright_fetch(**arguments)

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, ...)
```

### 3.2 mcp-image-tools

tools:
- `bg_remove`(rembg)
- `enhance`(Real-ESRGAN)
- `concat_long`(PIL 长图拼接)
- `quality_check`(调用 vision model 评估)

### 3.3 mcp-video-tools

tools:
- `compose`(FFmpeg + MoviePy 视频合成,内部调用 Celery)
- `extract_frames`(关键帧)
- `subtitle_align`(faster-whisper)

⚠️ **GPU 节点部署**,资源大,启动慢,用 HTTP 模式 + 持久化进程。

### 3.4 mcp-audio-tools

tools:
- `tts`(走 LiteLLM 调 Volcengine,这里是包装,实际生成走 LLM 路由)
- `asr`(faster-whisper 自托管)
- `bgm_match`(从 bgm_library 表匹配)

### 3.5 mcp-document-tools

tools:
- `pptx_assemble`
- `xlsx_assemble`
- `docx_assemble`
- `pdf_extract`
- `pdf_ocr`(Tesseract / 阿里云 OCR)

### 3.6 mcp-oss

tools:
- `upload_bytes`
- `download_bytes`
- `sign_url`(生成预签名 URL)

### 3.7 mcp-platform-publish(V1.5)

tools:
- `douyin_publish`(抖音开放平台 API)
- `xhs_publish`(小红书 API,V1.5 评估开放程度)
- `wechat_publish`(视频号 API)

---

## 四、Agent 端集成

### 4.1 通用 MCP Client

```python
# agents/_common/mcp_client.py
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
import asyncio

class MCPClientPool:
    """
    单例,持有所有 MCP server 的连接池。
    Agent handler 通过 call_tool() 调用,自动路由到正确的 server。
    """
    
    def __init__(self):
        self._sessions: dict[str, ClientSession] = {}
    
    async def init(self, server_configs: list[ServerConfig]):
        for cfg in server_configs:
            if cfg.transport == "stdio":
                read, write = await stdio_client(cfg.command, cfg.args)
            else:
                read, write = await sse_client(cfg.url)
            
            session = ClientSession(read, write)
            await session.initialize()
            self._sessions[cfg.name] = session
    
    async def call_tool(self, server: str, tool: str, arguments: dict):
        session = self._sessions[server]
        result = await session.call_tool(name=tool, arguments=arguments)
        if result.isError:
            raise MCPToolError(result.content[0].text)
        return result.content
    
    async def list_tools(self, server: str):
        session = self._sessions[server]
        return await session.list_tools()
    
    async def close(self):
        for session in self._sessions.values():
            await session.close()


# 全局单例
mcp_client = MCPClientPool()
```

启动时初始化:

```python
# agents/text_agent/main.py
from agents._common.mcp_client import mcp_client

async def main():
    await mcp_client.init([
        ServerConfig(name="search", transport="stdio", command="python", args=["-m", "mcp_servers.search"]),
        ServerConfig(name="oss", transport="stdio", command="python", args=["-m", "mcp_servers.oss"]),
    ])
    
    await consume_tasks("agent_tasks:text")
```

### 4.2 Handler 调用范式

```python
# agents/text_agent/handlers/web_search.py
from agents._common.mcp_client import mcp_client

async def web_search_handler(task, model):
    # 1. 让 LLM 生成搜索 query
    query_response = await router.complete(
        task_type="search_query_generation",
        messages=[{"role": "user", "content": task.prompt}]
    )
    query = parse_query(query_response)
    
    # 2. 通过 MCP 调用搜索工具
    results = await mcp_client.call_tool(
        server="search",
        tool="web_search",
        arguments={"query": query, "max_results": 10, "lang": "zh"}
    )
    
    # 3. LLM 整理结果
    summary = await router.complete(
        task_type="search_result_summarization",
        messages=[{"role": "user", "content": build_prompt(task.prompt, results)}]
    )
    
    # 4. 上传到 OSS(也走 MCP)
    artifact_ref = await mcp_client.call_tool(
        server="oss",
        tool="upload_bytes",
        arguments={
            "path": f"artifacts/{task.task_id}/{task.step_id}/output.md",
            "content": summary.encode()
        }
    )
    
    return AgentResult(...)
```

---

## 五、Skill YAML 引用 MCP

### 5.1 简单引用

Skill YAML 的 step 可以直接列出可用 MCP tool:

```yaml
- step_id: research
  agent: agent_1
  task_type: web_search
  mcp_tools:
    - mcp://search/web_search
    - mcp://search/web_fetch
  prompt_template: |
    研究主题:{{主题}}
    使用搜索工具查找最新信息,整理为 markdown。
```

主编排把这个传给 Agent 1 时,会让 LLM 看到 tools/list,LLM 自主决定调哪个。

### 5.2 显式调用(高级)

如果 Skill 作者想显式控制 MCP 调用顺序:

```yaml
- step_id: download_images
  agent: agent_3                       # v3.0 ADR-001-rev:图 = Agent 3
  task_type: image_download
  mcp_calls:
    - tool: mcp://oss/sign_url
      arguments:
        path: "{{previous_step.image_url}}"
      result_var: signed_url
    - tool: mcp://image-tools/quality_check
      arguments:
        url: "{{signed_url}}"
      result_var: quality
  prompt_template: |
    根据 quality_check 结果({{quality}}),决定是否需要 enhance。
```

---

## 六、社区 MCP server 复用

V2 可以接入 Anthropic 维护的 MCP server 仓库:

| server | 用途 |
|--------|------|
| `@modelcontextprotocol/server-filesystem` | 用户素材库(本地)|
| `@modelcontextprotocol/server-postgres` | 让 Agent 1 能查内部数据库 |
| `@modelcontextprotocol/server-github` | V2 代码 Skill |
| `@modelcontextprotocol/server-slack` | 团队版协作 |
| `@modelcontextprotocol/server-brave-search` | Tavily 备用 |
| 飞书 MCP server(社区) | 团队版集成 |
| 钉钉 MCP server(待开发) | 团队版集成 |

V1 不主动接入,但**架构留好接口**,V2 一键启用。

---

## 七、部署

### 7.1 dev 环境

`docker-compose.yml` 加入:

```yaml
mcp_search:
  build: ./mcp_servers/search
  environment:
    TAVILY_API_KEY: ${TAVILY_API_KEY}
  # stdio 模式时不需要端口

mcp_video_tools:
  build: ./mcp_servers/video_tools
  ports: ["8001:8001"]
  deploy:
    resources:
      reservations:
        devices: [{driver: nvidia, count: 1, capabilities: [gpu]}]
```

### 7.2 prod K8s

每个 MCP server 独立 Deployment:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-video-tools
spec:
  replicas: 2
  template:
    spec:
      nodeSelector:
        gpu: "true"
      containers:
      - name: mcp-server
        image: youle/mcp-video-tools:v1.0
        resources:
          limits: {nvidia.com/gpu: 1, memory: 8Gi}
        ports: [{containerPort: 8001}]
        livenessProbe:
          httpGet: {path: /health, port: 8001}
```

Agent 配置 MCP client 指向 K8s Service:

```python
ServerConfig(name="video-tools", transport="sse", url="http://mcp-video-tools.default.svc.cluster.local:8001/sse")
```

### 7.3 MCP Gateway(可选,V1.5)

部署一个 thin proxy,所有 MCP 调用过它:

- 统一审计日志
- 统一限流
- 统一鉴权(server 级 + tool 级)
- 统一 metrics(每个 tool 调用次数 / 延迟 / 错误率)

V1 不做,V1.5 评估。

---

## 八、错误处理

### 8.1 MCP server 不可用

```python
try:
    result = await mcp_client.call_tool(server="search", tool="web_search", arguments=args)
except MCPServerUnavailable:
    # 路由到 fallback server(如果配置了)
    fallback = settings.mcp_fallbacks.get("search")
    if fallback:
        result = await mcp_client.call_tool(server=fallback, tool="web_search", arguments=args)
    else:
        return AgentResult(status="failed", error=Error(type="mcp_unavailable", ...))
```

### 8.2 MCP tool 调用失败

LLM 调用工具失败时,应该:

1. 给 LLM 看错误,让它决定重试或换 tool
2. 重试上限 3 次
3. 仍失败 → 返回用户

### 8.3 MCP 工具版本变更

Skill YAML 引用 MCP tool 不带版本(MCP 协议保证向后兼容):

- 工具增加可选参数 → 兼容
- 工具减少必填参数 → 兼容(给 default)
- 工具改名 → 不兼容(此时 tool 必须改名,旧 tool 保留 deprecated)

---

## 九、测试

### 9.1 单元测试(MCP server)

```python
# mcp_servers/search/tests/test_server.py
import pytest
from mcp.client.session import ClientSession

@pytest.fixture
async def search_client():
    # 起本地 stdio server
    ...

async def test_web_search(search_client):
    result = await search_client.call_tool("web_search", {"query": "test"})
    assert result.content[0].type == "text"
```

### 9.2 集成测试(Agent ↔ MCP)

```python
@pytest.mark.integration
async def test_agent1_research_via_mcp(mock_mcp_search, agent_text_consumer):
    # 模拟 MCP server 返回固定结果
    mock_mcp_search.expect_call("web_search").return_value([...])
    
    # 发任务
    task = build_task(...)
    result = await agent_text_consumer.process(task)
    
    assert result.status == "success"
```

### 9.3 CI 集成

```yaml
# .github/workflows/ci.yml
- name: Run MCP integration tests
  run: pytest tests/integration/mcp/
```

---

## 十、迁移路径(从 v1.0 直连工具到 v2.0 MCP)

由于本次是 v2.0 重写,V1 直接走 MCP-first,**不存在迁移历史代码的问题**。

但 V2 评估时:

- 现有自建 MCP server 是否可换成社区版本(更稳定)
- 是否引入 MCP Gateway
- 是否升级到 Streamable HTTP

---

## 十一、相关文档

- [4 个分任务 Agent 实现指南](../2_工程实现/4 个分任务 Agent 实现指南.md) — Agent handler 调用范式
- [Skill YAML 模板](Skill YAML 模板.md) — `mcp_tools` / `mcp_calls` 字段
- [开放问题与决议 ADR-009](开放问题与决议.md#adr-009)
- [V1 工程基建清单](../5_工程基建/V1 工程基建清单.md) — MCP server 部署
