# 4 个分任务 Agent 实现指南

**版本**:v3.0(锁定 ADR-001-rev / ADR-002 / ADR-005-rev / ADR-009 / ADR-010 / ADR-011 / ADR-013 / ADR-015)
**日期**:2026-05-05
**面向**:智能体团队 / 后端工程师
**地位**:Agent 1-4 实现的唯一来源。

**v3.0 关键变更**:
- 🔄 **Agent 编号反向**(ADR-001-rev):Agent 2=文档 / Agent 3=图 / Agent 4=影音
- 🔄 **本指南章节顺序按新编号重排**:Agent 1 → Agent 2(文档) → Agent 3(图) → Agent 4(影音)
- 🔄 V1 hero SKU 回归:**反诈视频 + 电商详情图**(ADR-012 废弃)
- ✨ Agent 拟人化(ADR-015):每 Agent emit 表情 + 状态变化
- 保留:MCP-first(ADR-009)、HITL(ADR-010)、飞轮(ADR-011)

---

## ⚠️ 关键变更说明(必读)

### ADR-001-rev:Agent 编号反向锁定(v3.0)

| 编号 | 角色名 | 能力域 | 队列 |
|------|--------|--------|------|
| **Agent 1** | 研究员 / 文案师 | 文字与语言 | `agent_tasks:text` |
| **Agent 2** | **文档专员** | 办公文档(Office)| `agent_tasks:document` |
| **Agent 3** | **设计师** | 图像 | `agent_tasks:image` |
| **Agent 4** | **影音师** | 视频与音频 | `agent_tasks:av` |

### ADR-002:Agent 不主动跨调其他 Agent

- `call_other_agent` 永久 `NotImplementedError`
- 跨能力步骤在 Skill YAML 显式拆步

### ADR-009(v2.0 新增):MCP-first 架构

- **所有外部工具走 MCP server**(Tavily / Playwright / FFmpeg / PIL / python-pptx 等)
- Agent handler 通过 `mcp_client.call_tool()` 调用,不直接 import 工具 SDK
- **生成式模型**(GPT-Image-2 / Veo-3 / Volcengine TTS 等)走 LiteLLM,**不**走 MCP
- 7 个 V1 MCP server:`mcp-search` / `mcp-image-tools` / `mcp-video-tools` / `mcp-audio-tools` / `mcp-document-tools` / `mcp-oss` / `mcp-platform-publish`(V1.5)
- 详细:[MCP 集成方案](../3_决策记录/MCP 集成方案.md)

### ADR-011(v2.0 新增):飞轮信号

- Agent handler 完成 / 失败时 emit 信号
- 元数据完整:`cost_usd / duration_ms / model_used / mcp_calls`
- 失败时附带 `failure_mode` 给 Reflexion pipeline 用

---

## 📑 v3.0 章节索引(按 Agent ID 查找)

> 本文档章节按"内容创作链路"顺序排列(文字→图→影音→文档),与 Agent 编号顺序略有错位。按 Agent ID 查找:

| Agent ID | 角色 | 队列 | 章节 |
|---------|------|-----|------|
| Agent 1 | 研究员/文案师(文字)| `agent_tasks:text` | §二 |
| **Agent 2** | **文档专员(办公文档)** | `agent_tasks:document` | **§五** |
| **Agent 3** | **设计师(图)** | `agent_tasks:image` | **§三** |
| **Agent 4** | **影音师(视频音频)** | `agent_tasks:av` | **§四** |

---

## 一、通用框架(所有 Agent 共享)

### 1.1 定位

4 个分任务 Agent 是真正干活的执行者。每个 Agent 是**独立的微服务**,用 Docker 部署,通过 Redis Streams 接收任务、返回结果。

**核心约束**:

- Agent 不知全局,只知道自己的当下任务
- Agent 之间不直接对话,不互相 @
- Agent **不主动跨调其他 Agent**(ADR-002)
- 主编排 Agent 是唯一调度者
- 每个 Agent 有明确边界,超出能力必须返错(不硬撑)
- Agent 内部按 task_type 分发到不同 handler

### 1.2 通用架构

```
Agent 服务进程(Docker 容器)
├── 任务消费者(从 Redis Streams 读任务)
├── 任务路由器(根据 task_type 分发)
├── Handler 池(每种 task_type 一个)
├── 工具集(这个 Agent 能用的所有工具)
├── 模型路由调用层(走 L2 路由表)
├── 失败处理器(重试 / 备用 / 降级)
└── 结果发送器(写 Redis 结果队列)
```

### 1.3 通用任务消息格式(AgentTask)

主编排发给 Agent 的任务:

```yaml
AgentTask:
  task_id: 全局唯一
  step_id: 步骤标识
  agent_id: agent_1 / agent_2 / agent_3 / agent_4
  task_type: long_writing / image_generate / video_compose / 等
  scenario: anti_fraud / ecommerce_detail / 等
  
  prompt: 已渲染好的完整 prompt 文本
  
  inputs:
    - artifact_id: xxx
      type: text / image / video / structured
      reference: oss://path
  
  parameters:
    temperature: 0.7
    max_tokens: 4000
    stream: true
    custom_params: {...}
  
  routing_hints:
    primary: 主力模型
    fallback: 备用模型列表
    language: zh
    cost_priority: low / medium / high
  
  output_format:
    type: text / image / video / document
    schema: {...}
  
  callback:
    result_queue: agent_results:task_id_step_id
    timeout_seconds: 300
```

### 1.4 通用结果消息格式(AgentResult)

```yaml
AgentResult:
  task_id: 同上
  step_id: 同上
  status: success / failed / partial / pending_external
  
  output:
    artifact_id: 新生成
    type: text / image / video / document
    reference: oss://path
    metadata:
      tokens_used: 1234
      cost_usd: 0.045
      duration_ms: 2300
      model_used: kimi-k2
  
  error:  # 失败时
    type: timeout / api_error / quality_failure / out_of_scope
    message: 友好错误消息
    retry_count: 0
    suggested_action: fallback / user_input / skip
```

### 1.5 通用消费者循环

```python
async def consume_tasks(queue_name: str, consumer_group: str):
    
    try:
        await redis.xgroup_create(queue_name, consumer_group, mkstream=True)
    except ResponseError:
        pass
    
    while True:
        try:
            messages = await redis.xreadgroup(
                consumer_group,
                consumer_name=f"worker-{os.getpid()}",
                streams={queue_name: ">"},
                count=1,
                block=5000
            )
            
            if not messages:
                continue
            
            for stream, message_list in messages:
                for message_id, data in message_list:
                    task = AgentTask(**msgpack.unpackb(data["task"]))
                    
                    try:
                        result = await process_task(task)
                        await publish_result(task, result)
                        await redis.xack(queue_name, consumer_group, message_id)
                    except Exception as e:
                        await handle_task_failure(task, e, message_id)
        
        except Exception as e:
            logger.error(f"Consumer error: {e}")
            await asyncio.sleep(1)
```

### 1.6 通用任务处理流程

每个 Agent 的 `process_task` 都遵循相同流程:

```python
async def process_task(task: AgentTask) -> AgentResult:
    
    # 1. 边界检查
    if task.task_type not in SUPPORTED_TASK_TYPES:
        return AgentResult(
            status="failed",
            error=Error(
                type="out_of_scope",
                message=f"我是 {AGENT_NAME},不支持 {task.task_type}",
                suggested_action="reassign"
            )
        )
    
    # 2. 路由到对应 handler
    handler = HANDLERS[task.task_type]
    
    # 3. 选模型(走 L2 路由表)
    model = await router.select_model(
        task_type=task.task_type,
        routing_hints=task.routing_hints
    )
    
    # 4. 执行 handler
    try:
        result = await handler(task, model)
    except TransientError:
        result = await handler(task, model)  # 重试 1 次
    except PermanentError as e:
        return AgentResult(status="failed", error=Error(...))
    
    # 5. 质量校验
    if task.output_format.schema:
        if not validate_quality(result):
            fallback_model = router.get_fallback(model)
            result = await handler(task, fallback_model)
    
    # 6. 上传产物到 OSS
    artifact_ref = await upload_to_oss(
        content=result.content,
        path=f"artifacts/{task.task_id}/{task.step_id}/output.{ext}"
    )
    
    # 7. 写入 artifacts 表
    artifact_id = await create_artifact(
        task_id=task.task_id,
        step_id=task.step_id,
        type=task.output_format.type,
        reference=artifact_ref,
        metadata=result.metadata
    )
    
    # 8. 返回结果
    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="success",
        output=Output(
            artifact_id=artifact_id,
            type=task.output_format.type,
            reference=artifact_ref,
            metadata=result.metadata
        )
    )
```

### 1.7 通用失败处理

```python
async def handle_task_failure(task, error, message_id):
    
    retry_count = task.metadata.get("retry_count", 0) + 1
    
    if retry_count <= 3 and is_transient_error(error):
        await asyncio.sleep(2 ** retry_count)
        task.metadata["retry_count"] = retry_count
        await publish_task(task)
        await redis.xack(queue_name, consumer_group, message_id)
        return
    
    result = AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="failed",
        error=Error(
            type=type(error).__name__,
            message=str(error),
            retry_count=retry_count
        )
    )
    await publish_result(task, result)
    await redis.xack(queue_name, consumer_group, message_id)
    
    await redis.xadd(
        f"agent_tasks_dlq:{task.agent_id}",
        {"task": msgpack.packb(task.to_dict()), "error": str(error)}
    )
```

### 1.8 ADR-002 防御性编程:禁用 `call_other_agent`

```python
# agent_common/cross_call.py
def call_other_agent(*args, **kwargs):
    """
    Disabled per ADR-002: Agents must NOT directly call other agents.
    Express cross-agent dependencies as explicit Skill workflow steps;
    let main orchestrator (LangGraph) schedule them.
    """
    raise NotImplementedError(
        "Direct cross-agent calls are forbidden (ADR-002). "
        "Add a separate step to the Skill YAML."
    )
```

任何遗留代码引用 `call_other_agent` 都会立即失败。

### 1.9 通用部署配置

每个 Agent 服务:

- Docker 容器(Python 3.12-slim)
- 独立进程,水平可扩展
- 资源:2 核 4G(Agent 1/4)/ 4 核 8G(Agent 2/3)
- 队列:`agent_tasks:{agent_id}`
- 健康检查:`/health` 端点

### 1.10 通用监控指标

每个 Agent 必须暴露:

- 任务接收量、完成量、失败量
- P50/P95/P99 延迟
- 错误率(按类型分)
- 模型调用成本(累计)
- 队列积压数

---

## 二、Agent 1:研究员 / 文案师(文字)

### 2.1 职责

处理所有文字与语言相关任务。在用户视角分两个角色:

- **研究员**:做调研、搜索、数据收集
- **文案师**:做写作、文案、脚本

技术上是同一个 Agent 1 服务,队列 `agent_tasks:text`。

### 2.2 支持的 task_type

```python
SUPPORTED_TASK_TYPES = {
    # 写作类
    "short_writing",         # 短文(标题、口播稿、文案)
    "long_writing",          # 长文(公众号、报告、长篇分析)
    "structured_writing",    # 结构化(大纲、提案、PPT 大纲)
    
    # 阅读理解类
    "summarization",         # 摘要
    "extraction",            # 信息提取
    "analysis",              # 分析推理
    
    # 研究类
    "web_search",            # 联网搜索
    "web_scrape",            # 网页抓取
    "data_organize",         # 数据整理
    
    # 翻译类
    "translation",           # 翻译
    "polish",                # 润色
    
    # 澄清辅助
    "version_compare",       # 生成 3 个版本供用户对比(澄清形式 4)
}
```

### 2.3 模型路由(摘要,完整请看 [模型路由表 §3](../4_附录/模型路由表.md))

| task_type | 主力模型 | 备用 1 | 备用 2 |
|-----------|---------|--------|--------|
| short_writing | deepseek-v4-flash | deepseek-v4-pro | claude-haiku-4-5 |
| long_writing | kimi-k2 | deepseek-v4-pro | claude-sonnet-4-6 |
| structured_writing | deepseek-v4-pro | kimi-k2 | claude-sonnet-4-6 |
| analysis | claude-sonnet-4-6 | deepseek-v4-pro | gpt-5 |
| web_search | claude-sonnet-4-6 | gpt-5 | - |
| web_scrape | (无 LLM,纯工具)| - | - |

### 2.4 工具集

```python
TOOLS = {
    "search_engine": TavilyAPI / BingAPI,
    "web_scraper": Playwright + httpx,
    "data_processor": pandas,
    "code_interpreter": (V2),
    "llm_judge": (内部用 Sonnet 评质量),
}
```

### 2.5 关键 Handler:long_writing

```python
async def long_writing_handler(task: AgentTask, model) -> AgentResult:
    
    messages = [
        {"role": "system", "content": LONG_WRITING_SYSTEM_PROMPT},
        {"role": "user", "content": task.prompt}
    ]
    
    full_text = ""
    async for chunk in model.stream(messages, **task.parameters):
        full_text += chunk
        await emit_streaming_event(
            task_id=task.task_id,
            step_id=task.step_id,
            chunk=chunk,
            total_so_far_words=len(full_text)
        )
    
    if task.output_format.schema:
        validation = validate_schema(full_text, task.output_format.schema)
        if not validation.passed:
            return await retry_with_correction(task, validation.errors)
    
    artifact_ref = await upload_to_oss(
        content=full_text,
        path=f"artifacts/{task.task_id}/{task.step_id}/output.md"
    )
    
    return AgentResult(
        ...
        output=Output(
            type="text",
            reference=artifact_ref,
            metadata={
                "word_count": len(full_text),
                "model_used": model.id,
                "cost_usd": model.last_cost,
                "duration_ms": model.last_duration
            }
        )
    )
```

### 2.6 关键 Handler:web_search

```python
async def web_search_handler(task: AgentTask, model) -> AgentResult:
    messages = [{"role": "user", "content": task.prompt}]
    
    response = await model.acompletion(
        messages=messages,
        tools=[
            {"name": "web_search", "parameters": {"query": "string"}},
            {"name": "web_fetch", "parameters": {"url": "string"}}
        ]
    )
    
    while response.tool_calls:
        for tool_call in response.tool_calls:
            if tool_call.name == "web_search":
                results = await tavily.search(tool_call.args["query"])
            elif tool_call.name == "web_fetch":
                results = await playwright.fetch(tool_call.args["url"])
            messages.append({"role": "tool", "content": results})
        response = await model.acompletion(messages=messages, tools=[...])
    
    if task.output_format.type == "structured":
        xlsx_data = parse_to_xlsx(response.content)
        artifact_ref = await save_xlsx_to_oss(xlsx_data, task)
    else:
        artifact_ref = await upload_to_oss(response.content, ...)
    
    return AgentResult(...)
```

### 2.7 短视频场景的关键 Handler(v2.0,hero SKU)

#### 2.7.1 short_video_research(知识科普 / 热点 / 测评 类型才走)

```python
async def short_video_research_handler(task: AgentTask, model) -> AgentResult:
    """走 mcp-search 的 web_search + web_fetch"""
    
    # LLM 生成搜索 query
    query_response = await router.complete(
        task_type="short_video_research",
        messages=[
            {"role": "system", "content": SHORT_VIDEO_RESEARCH_PROMPT},
            {"role": "user", "content": task.prompt}
        ],
        tools=await mcp_client.list_tools_as_openai_format("search"),  # MCP 工具转换为 OpenAI tool 格式
        routing_hints=task.routing_hints
    )
    
    # 处理 tool calls
    while query_response.tool_calls:
        for tc in query_response.tool_calls:
            result = await mcp_client.call_tool(
                server="search",
                tool=tc.name,                # web_search / web_fetch
                arguments=tc.arguments
            )
            # 把 tool result 加回对话
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
        
        query_response = await router.complete(...)
    
    # 整理为 markdown
    research_md = query_response.content
    
    artifact_ref = await mcp_client.call_tool(
        server="oss",
        tool="upload_bytes",
        arguments={"path": ..., "content": research_md.encode()}
    )
    
    # 飞轮信号(ADR-011)
    await flywheel_emitter.on_step_completed(
        task=task,
        metadata={
            "cost_usd": query_response.cost,
            "duration_ms": query_response.duration_ms,
            "model_used": query_response.model,
            "mcp_calls": [{"server": "search", "tool": tc.name} for tc in all_tool_calls]
        }
    )
    
    return AgentResult(...)
```

#### 2.7.2 short_video_script(脚本生成,3 个版本)

```python
async def short_video_script_handler(task: AgentTask, model) -> AgentResult:
    """根据 Skill prompt + 用户需求,一次生成 3 个差异化版本"""
    
    response = await router.complete(
        task_type="short_video_script",
        messages=[
            {"role": "system", "content": SHORT_VIDEO_SCRIPT_PROMPT},
            {"role": "user", "content": task.prompt}     # 已渲染好,含 platform / type / style
        ],
        response_format={"type": "json_object"},
        routing_hints={"primary": "deepseek-v4-pro"}
    )
    
    versions = json.loads(response.content)["versions"]
    # 校验 schema:必须 3 个版本,各有 label/title/script/estimated_duration
    
    # 上传产物(JSON)
    artifact_ref = await mcp_client.call_tool(
        server="oss", tool="upload_bytes",
        arguments={"path": ..., "content": json.dumps(versions, ensure_ascii=False).encode()}
    )
    
    return AgentResult(
        ...,
        output=Output(
            type="structured",
            reference=artifact_ref,
            metadata={
                "version_count": 3,
                "platform": task.parameters["platform"],
                "type": task.parameters["type"],
                "preview_for_hitl": [{"label": v["label"], "title": v["title"]} for v in versions]
            }
        )
    )
```

注意:**这个 handler 的产物会触发 HITL gate(version_select)**,主编排把 `preview_for_hitl` 推给前端展示。


### 2.8 边界检查

```python
def check_boundary(task: AgentTask) -> Optional[Error]:
    if task.task_type in ["image_generate", "image_edit"]:
        return Error("我是文字 Agent,请让设计师处理图片任务")
    if task.task_type in ["video_compose", "tts_generate"]:
        return Error("我是文字 Agent,请让影音师处理视频音频任务")
    if task.task_type in ["pptx_create", "xlsx_create", "docx_create"]:
        return Error("我是文字 Agent,请让文档专员处理办公文档任务")
    return None
```

### 2.9 部署

- 容器:`agent-text`
- 资源:2 核 4G,水平扩展(初始 2 实例)
- 队列:`agent_tasks:text`
- 工具依赖:Tavily API key、Playwright

---

## 三、Agent 3:设计师(图)

> v3.0 ADR-001-rev:本节描述的"设计师"是 **Agent 3**(原 v2.0 是 Agent 2)。下文所有 `agent_2` 引用应理解为 `agent_3`。

### 3.1 职责

处理一切跟"图"相关的事:生成、理解、编辑、风格管理。队列 `agent_tasks:image`。

### 3.2 支持的 task_type

```python
SUPPORTED_TASK_TYPES = {
    # 生成类
    "image_generate",        # 文生图
    "image_edit",            # 图生图(基于参考图)
    "image_compose",         # 多图合成
    "batch_generate",        # 批量生成(关键:风格一致性)
    
    # 理解类
    "image_describe",        # 图片描述
    "image_classify",        # 图片分类
    "image_quality_check",   # 质量评估
    "image_ocr",             # OCR
    
    # 编辑类
    "image_inpaint",         # 局部重绘
    "image_outpaint",        # 扩图
    "image_enhance",         # 画质增强
    "background_remove",     # 抠图
    "image_download",        # 从 URL 下载图片(短视频研究类场景用)
    
    # 风格类
    "style_extract",         # 从参考图提取风格
    "style_transfer",        # 风格迁移
}
```

### 3.3 模型路由(摘要)

| task_type | 主力模型 | 备用 1 | 备用 2 |
|-----------|---------|--------|--------|
| image_generate(真实)| gpt-image-2 | seedream-3 | midjourney-v7 |
| image_generate(卡通)| nano-banana-2 | seedream-3 | midjourney-v7 |
| image_generate(中国风)| kling-image | seedream-3 | - |
| image_edit | gpt-image-2 | seedream-3 | - |
| image_describe | claude-sonnet-vision | gpt-5-vision | qwen-vl |
| image_quality_check | gpt-5-vision | claude-sonnet-vision | - |
| background_remove | (rembg 工具)| - | - |
| image_enhance | (Real-ESRGAN 工具)| - | - |

完整路由请看 [模型路由表 §4](../4_附录/模型路由表.md)。

### 3.4 工具集

```python
TOOLS = {
    "PIL": 基础图像处理,
    "OpenCV": 高级图像处理,
    "rembg": 抠图,
    "Real-ESRGAN": 超分辨率,
    "image_downloader": httpx + 图片格式校验,
}
```

### 3.5 关键 Handler:batch_generate(电商详情图场景)

电商详情图需要 5 张图保持视觉一致——这是 Agent 2 的核心能力。

**关键策略**:**第一张作为后续 4 张的视觉锚点**。

```python
async def batch_generate_handler(task: AgentTask, model) -> AgentResult:
    
    image_specs = task.parameters["image_specs"]
    style_strength = task.parameters.get("style_strength", 0.7)
    
    # 1. 第一张:从纯文本 prompt 生成
    first_image = await model.generate(
        prompt=image_specs[0].prompt,
        size=image_specs[0].size
    )
    first_ref = await upload_to_oss(first_image, ...)
    
    # 2. 后续图:用第一张作为 reference
    async def generate_with_anchor(spec):
        return await model.generate(
            prompt=spec.prompt,
            reference_image=first_image,  # 视觉锚点
            style_strength=style_strength,
            size=spec.size
        )
    
    semaphore = asyncio.Semaphore(3)
    async def limited_generate(spec):
        async with semaphore:
            return await generate_with_anchor(spec)
    
    later_results = await asyncio.gather(
        *[limited_generate(spec) for spec in image_specs[1:]],
        return_exceptions=True
    )
    
    final_images = [first_image]
    for i, result in enumerate(later_results):
        if isinstance(result, Exception):
            retry = await generate_with_anchor(image_specs[i + 1])
            final_images.append(retry)
        else:
            final_images.append(result)
    
    artifact_refs = await asyncio.gather(*[
        upload_to_oss(img, ...) for img in final_images
    ])
    
    return AgentResult(
        ...
        output=Output(
            type="image_collection",
            references=artifact_refs,
            metadata={
                "count": len(final_images),
                "anchor_image": artifact_refs[0],
                "style_strength": style_strength
            }
        )
    )
```

### 3.6 关键 Handler:image_download(短视频研究素材场景)

知识科普 / 测评类短视频在研究阶段拿到带图 URL,Agent 2 负责下载并质检。

```python
async def image_download_handler(task: AgentTask, model) -> AgentResult:
    
    # 输入:Agent 1 产出的 xlsx,主编排已渲染好 URL 列表注入 prompt
    urls = parse_urls_from_prompt(task.prompt)
    
    async def download_one(url, idx):
        try:
            response = await httpx.get(url, timeout=10)
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                return None
            
            filename = f"case_{idx:02d}.jpg"
            artifact_ref = await upload_to_oss(
                content=response.content,
                path=f"artifacts/{task.task_id}/{task.step_id}/{filename}"
            )
            return artifact_ref
        except Exception as e:
            logger.error(f"Download failed: {url}, {e}")
            return None
    
    results = await asyncio.gather(*[
        download_one(url, i) for i, url in enumerate(urls)
    ])
    
    successful_refs = [r for r in results if r is not None]
    
    if task.parameters.get("check_quality", False):
        successful_refs = await filter_low_quality_images(successful_refs)
    
    return AgentResult(
        ...
        output=Output(
            type="image_collection",
            references=successful_refs,
            metadata={
                "total_urls": len(urls),
                "successful": len(successful_refs),
                "failed": len(urls) - len(successful_refs)
            }
        )
    )
```

### 3.7 关键 Handler:image_quality_check

```python
async def image_quality_check_handler(task: AgentTask, model) -> AgentResult:
    
    image_ref = task.inputs[0].reference
    
    response = await model.acompletion(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": """
                    评估这张图的质量,输出 JSON:
                    {
                        "resolution_ok": true/false,
                        "clarity_ok": true/false,
                        "style_match": 0.0-1.0,
                        "subject_clear": true/false,
                        "overall_score": 0.0-1.0,
                        "issues": ["问题列表"]
                    }
                    """},
                    {"type": "image_url", "image_url": image_ref}
                ]
            }
        ]
    )
    
    quality = json.loads(response.content)
    
    if quality["overall_score"] < 0.7:
        return AgentResult(
            status="quality_failure",
            error=Error(
                type="quality_failure",
                message=f"质量不达标:{quality['issues']}",
                suggested_action="regenerate"
            )
        )
    
    return AgentResult(
        status="success",
        output=Output(type="quality_report", metadata=quality)
    )
```

### 3.8 边界检查

```python
def check_boundary(task: AgentTask) -> Optional[Error]:
    if task.task_type in ["short_writing", "long_writing"]:
        return Error("我是设计师,文字内容请让文案师处理")
    if task.task_type in ["video_compose", "text_to_video"]:
        return Error("我是设计师,视频请让影音师处理")
    if task.task_type in ["pptx_create"]:
        return Error("我是设计师,PPT 请让文档专员处理")
    return None
```

### 3.9 部署

- 容器:`agent-image`
- 资源:4 核 8G(图像处理重)
- 队列:`agent_tasks:image`
- 工具依赖:PIL、OpenCV、rembg、Real-ESRGAN

---

## 四、Agent 4:影音师(视频与音频)

> v3.0 ADR-001-rev:本节描述的"影音师"是 **Agent 4**(原 v2.0 是 Agent 3)。下文所有 `agent_3` 引用应理解为 `agent_4`。

### 4.1 职责

处理一切跟"视频和音频"相关的事:视频生成、视频编辑、TTS、BGM、字幕。队列 `agent_tasks:av`。

**特殊性**:视频合成是 5-10 分钟的长任务,**通过 Celery 异步执行**(V1)/Temporal(V2 升级)。

### 4.2 支持的 task_type

```python
SUPPORTED_TASK_TYPES = {
    # 视频生成
    "text_to_video",         # 文生视频(短片段)
    "image_to_video",        # 图生视频
    "video_compose",         # 视频合成(长任务,Celery)
    
    # 视频理解
    "video_describe",        # 视频描述
    "video_extract_frames",  # 关键帧提取
    "audio_extract",         # 音轨提取
    
    # 视频编辑
    "video_cut",             # 剪辑
    "subtitle_generate",     # 字幕生成
    "subtitle_add",          # 加字幕
    "bgm_add",               # 加 BGM
    "transition_apply",      # 加转场
    
    # 音频处理
    "tts_generate",          # TTS 配音
    "audio_to_text",         # Whisper 语音识别
    "bgm_select",            # BGM 选择(从素材库匹配情绪)
}
```

### 4.3 模型路由(摘要)

| task_type | 主力模型 | 备用 1 | 备用 2 |
|-----------|---------|--------|--------|
| text_to_video | veo-3 | seedance-2 | kling-2 |
| image_to_video | seedance-2 | kling-2 | veo-3 |
| video_compose | (FFmpeg + MoviePy 工具)| - | - |
| tts_generate | volcengine-tts | aliyun-tts | elevenlabs |
| audio_to_text | whisper-v3 | aliyun-asr | - |
| video_describe | gpt-5-vision | claude-sonnet-vision | - |
| bgm_select | (素材库匹配,无 LLM)| - | - |

### 4.4 工具集

```python
TOOLS = {
    "FFmpeg": 视频处理核心,
    "MoviePy": Python 视频封装,
    "Whisper": 语音识别,
    "BGM 素材库": 预置 BGM(分情绪标签),
    "字幕对齐算法": 自研 + Whisper 时间戳,
}
```

### 4.5 关键 Handler:video_compose(长任务)

视频合成是短视频 hero SKU 的最后一步,涉及 TTS + 图生视频片段拼接 + 字幕对齐 + BGM 混音 + 终输出,5-10 分钟。

**实现方式**:Agent 3 立即提交到 Celery,**返回 pending_external 状态**,Celery 完成后回调 LangGraph。

```python
async def video_compose_handler(task: AgentTask, model) -> AgentResult:
    
    # 校验所有输入(脚本、图片、BGM 是否齐全)
    required_inputs = ["script", "images", "bgm"]
    for req in required_inputs:
        if not has_input(task, req):
            return AgentResult(
                status="failed",
                error=Error(type="missing_input", message=f"缺少 {req}")
            )
    
    celery_payload = {
        "task_id": task.task_id,
        "step_id": task.step_id,
        "script_ref": get_input(task, "script").reference,
        "images_refs": [inp.reference for inp in get_inputs(task, "images")],
        "bgm_ref": get_input(task, "bgm").reference,
        "voice": task.parameters.get("voice", "female_warm"),
        "duration": task.parameters.get("duration", 60),
        "callback_queue": task.callback.result_queue
    }
    
    workflow_id = f"video_compose_{task.task_id}_{task.step_id}"
    celery_app.send_task(
        "video_compose_workflow",
        args=[celery_payload],
        task_id=workflow_id
    )
    
    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="pending_external",
        external_workflow_id=workflow_id
    )
```

### 4.6 Celery 任务定义(video_compose_workflow)

```python
@celery_app.task(bind=True, name="video_compose_workflow")
def video_compose_workflow(self, payload):
    
    try:
        # 步骤 1:TTS 生成
        tts_audio = generate_tts(
            text=load_from_oss(payload["script_ref"]).read_text(),
            voice=payload["voice"]
        )
        
        # 步骤 2:字幕生成与对齐
        subtitle = generate_subtitle(
            audio=tts_audio,
            script=load_from_oss(payload["script_ref"])
        )
        
        # 步骤 3:图片转视频片段(并行)
        with ThreadPoolExecutor(max_workers=3) as executor:
            video_segments = list(executor.map(
                lambda img_ref: image_to_video_segment(img_ref, duration=10),
                payload["images_refs"]
            ))
        
        # 步骤 4:视频拼接 + BGM + 字幕
        final_video = compose_video(
            segments=video_segments,
            audio=tts_audio,
            bgm=load_from_oss(payload["bgm_ref"]),
            subtitle=subtitle,
            target_duration=payload["duration"]
        )
        
        # 步骤 5:质量校验 + 上传
        quality = check_video_quality(final_video)
        if not quality["passed"]:
            raise QualityFailure(quality["issues"])
        
        artifact_ref = upload_to_oss(
            final_video,
            path=f"artifacts/{payload['task_id']}/{payload['step_id']}/output.mp4"
        )
        
        notify_langgraph_complete(
            task_id=payload["task_id"],
            step_id=payload["step_id"],
            result={
                "type": "video",
                "reference": artifact_ref,
                "metadata": {
                    "duration": payload["duration"],
                    "resolution": "1080p",
                    "file_size": os.path.getsize(final_video)
                }
            },
            callback_queue=payload["callback_queue"]
        )
    
    except Exception as e:
        notify_langgraph_failed(
            task_id=payload["task_id"],
            step_id=payload["step_id"],
            error=str(e),
            callback_queue=payload["callback_queue"]
        )
        raise
```

### 4.7 关键工具:compose_video(MoviePy)

```python
def compose_video(segments, audio, bgm, subtitle, target_duration):
    from moviepy.editor import (
        VideoFileClip, AudioFileClip, CompositeAudioClip,
        TextClip, CompositeVideoClip, concatenate_videoclips
    )
    
    clips = [VideoFileClip(seg) for seg in segments]
    video = concatenate_videoclips(clips, method="compose")
    
    if video.duration > target_duration:
        video = video.subclip(0, target_duration)
    
    voice = AudioFileClip(audio)
    bgm_clip = AudioFileClip(bgm).volumex(0.3)
    final_audio = CompositeAudioClip([voice, bgm_clip])
    video = video.set_audio(final_audio)
    
    subtitle_clips = []
    for sub in subtitle:
        txt_clip = TextClip(
            sub.text,
            fontsize=48,
            color="white",
            font="PingFang-SC",
            stroke_color="black",
            stroke_width=2
        ).set_position(("center", 0.85), relative=True).set_duration(sub.duration).set_start(sub.start)
        subtitle_clips.append(txt_clip)
    
    video = CompositeVideoClip([video] + subtitle_clips)
    
    output_path = f"/tmp/{uuid()}.mp4"
    video.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=30,
        preset="medium",
        bitrate="4000k"
    )
    
    return output_path
```

### 4.8 关键 Handler:tts_generate

```python
async def tts_generate_handler(task: AgentTask, model) -> AgentResult:
    
    text = task.prompt
    voice = task.parameters.get("voice", "female_warm")
    speed = task.parameters.get("speed", 1.0)
    
    audio_data = await model.tts(
        text=text,
        voice=voice,
        speed=speed,
        format="mp3",
        sample_rate=24000
    )
    
    artifact_ref = await upload_to_oss(
        content=audio_data,
        path=f"artifacts/{task.task_id}/{task.step_id}/voice.mp3"
    )
    
    return AgentResult(
        ...
        output=Output(
            type="audio",
            reference=artifact_ref,
            metadata={
                "duration_seconds": len(audio_data) / 24000,
                "voice": voice,
                "format": "mp3"
            }
        )
    )
```

### 4.9 关键 Handler:bgm_select

不调 LLM,基于情绪标签从素材库匹配:

```python
async def bgm_select_handler(task: AgentTask, model) -> AgentResult:
    
    mood = task.parameters.get("mood", "warning")
    duration = task.parameters.get("duration", 60)
    
    bgm_candidates = await db.query(
        "SELECT * FROM bgm_library WHERE mood = ? AND duration >= ?",
        [mood, duration]
    )
    
    if not bgm_candidates:
        bgm = await db.query("SELECT * FROM bgm_library WHERE mood = 'neutral' LIMIT 1")
    else:
        bgm = min(bgm_candidates, key=lambda b: b.usage_count)
    
    await db.execute("UPDATE bgm_library SET usage_count = usage_count + 1 WHERE id = ?", [bgm.id])
    
    return AgentResult(
        ...
        output=Output(
            type="audio",
            reference=bgm.oss_ref,
            metadata={
                "title": bgm.title,
                "mood": bgm.mood,
                "duration": bgm.duration,
                "license": bgm.license
            }
        )
    )
```

### 4.10 边界检查

```python
def check_boundary(task: AgentTask) -> Optional[Error]:
    if task.task_type in ["short_writing", "long_writing"]:
        return Error("我是影音师,纯文字请让文案师处理")
    if task.task_type in ["image_generate", "image_edit"]:
        return Error("我是影音师,单图生成请让设计师处理")
    if task.task_type in ["pptx_create"]:
        return Error("我是影音师,PPT 请让文档专员处理")
    return None
```

### 4.11 部署

- 容器:`agent-av`(av = audio + video)
- 资源:4 核 8G(视频处理重)
- 队列:`agent_tasks:av`
- 工具依赖:FFmpeg、MoviePy、Whisper
- Celery worker:`video_compose_worker` × 2-4 实例
- Celery 队列:`video_tasks`(独立队列,避免阻塞短任务)

---

## 五、Agent 2:文档专员(办公文档)

> v3.0 ADR-001-rev:本节描述的"文档专员"是 **Agent 2**(原 v2.0 是 Agent 4)。下文所有 `agent_4` 引用应理解为 `agent_2`。

### 5.1 职责

处理 Office 文档(PPT、Excel、Word、PDF)+ 长图拼接(电商详情图终步)。队列 `agent_tasks:document`。

技术核心:**Python 库的封装**。**所有需要文字/图片内容的步骤,在 Skill YAML 里显式拆为前置步骤**(ADR-002),Agent 4 只接收已就绪的 inputs,不主动跨调。

### 5.2 支持的 task_type

```python
SUPPORTED_TASK_TYPES = {
    # PPT
    "pptx_assemble",         # PPT 组装(接收 outline + images,组装)
    "pptx_modify",           # PPT 修改
    "pptx_extract",          # PPT 内容提取
    
    # Excel
    "xlsx_assemble",         # Excel 组装(接收数据,生成表格)
    "xlsx_read",             # Excel 读取
    "xlsx_chart",            # Excel 图表
    "xlsx_format",           # Excel 格式化
    
    # Word
    "docx_assemble",         # Word 组装
    "docx_modify",           # Word 修改
    "docx_extract",          # Word 内容提取
    
    # PDF
    "pdf_extract",           # PDF 文字/表格提取
    "pdf_create",            # PDF 生成
    "pdf_watermark",         # PDF 水印
    "pdf_ocr",               # 扫描 OCR
    
    # 长图拼接(电商详情图场景)
    "image_concat_long",     # 长图垂直拼接
}
```

> **命名变更**:原 `pptx_create` 改名 `pptx_assemble`,以语义明确"Agent 4 只组装,不创作内容"。其它 `*_create` 同样改为 `*_assemble`。

### 5.3 模型路由

Agent 4 大部分任务**不需要 LLM**(纯 Python 库操作)。极少数 LLM 用途:

| task_type | 模型 | 用途 |
|-----------|------|------|
| pdf_ocr | Tesseract / 阿里云 OCR | 扫描识别 |
| xlsx_assemble(含轻量整理)| deepseek-v4-flash | 数据清洗 |

### 5.4 工具集

```python
TOOLS = {
    "python-pptx": pptx 库,
    "openpyxl": Excel 操作,
    "python-docx": Word 操作,
    "PyPDF2": PDF 处理,
    "pdfplumber": PDF 表格提取,
    "pandas": 数据处理,
    "matplotlib": 图表生成,
    "PIL": 图像拼接(长图),
    "tesseract": OCR,
}
```

### 5.5 关键 Handler:pptx_assemble(ADR-002 重写)

> **本节是 ADR-002 的核心示例:Agent 4 只组装,不主动跨调。**

输入由 Skill workflow 上游步骤提供:

```yaml
# Skill YAML(节选)
workflow:
  - step_id: ppt_outline
    agent: agent_1                # Agent 1 写大纲
    task_type: structured_writing
  
  - step_id: ppt_images
    agent: agent_2                # Agent 2 生成配图
    depends_on: [ppt_outline]
    task_type: image_generate
  
  - step_id: ppt_assemble
    agent: agent_4                # Agent 4 仅组装
    depends_on: [ppt_outline, ppt_images]
    task_type: pptx_assemble
    inputs:
      outline: "{{ppt_outline.output}}"     # 上游产物
      images:  "{{ppt_images.output}}"      # 上游产物
```

Handler 实现:

```python
async def pptx_assemble_handler(task: AgentTask, model) -> AgentResult:
    
    # 1. 解析参数
    style = task.parameters.get("style", "business")
    
    # 2. 直接读取上游产物(主编排已经把它们注入 task.inputs)
    outline = parse_outline(get_input(task, "outline"))     # 已经是 Agent 1 的产物
    images = get_inputs(task, "images")                     # 已经是 Agent 2 的产物列表
    
    # ⚠️ 注意:这里没有 call_other_agent。所有需要的内容都通过 inputs 传入。
    
    # 3. 用 python-pptx 组装
    prs = Presentation()
    apply_template(prs, style)
    
    for i, slide_def in enumerate(outline.slides):
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = slide_def.title
        body = slide.placeholders[1]
        body.text_frame.text = slide_def.content
        
        if i < len(images):
            slide.shapes.add_picture(
                images[i].reference,
                left=Inches(5), top=Inches(2),
                width=Inches(4)
            )
    
    output_path = f"/tmp/{task.task_id}.pptx"
    prs.save(output_path)
    
    artifact_ref = await upload_to_oss(output_path, ...)
    
    return AgentResult(
        ...
        output=Output(
            type="document",
            reference=artifact_ref,
            metadata={
                "page_count": len(outline.slides),
                "file_size": os.path.getsize(output_path),
                "style": style
            }
        )
    )
```

### 5.6 关键 Handler:image_concat_long(电商详情图场景)

```python
async def image_concat_long_handler(task: AgentTask, model) -> AgentResult:
    
    images = []
    for inp in task.inputs:
        img_data = await download_from_oss(inp.reference)
        images.append(Image.open(BytesIO(img_data)))
    
    total_width = max(img.width for img in images)
    total_height = sum(img.height for img in images)
    
    long_image = Image.new("RGB", (total_width, total_height), color="white")
    y_offset = 0
    for img in images:
        x_offset = (total_width - img.width) // 2
        long_image.paste(img, (x_offset, y_offset))
        y_offset += img.height
    
    output_path = f"/tmp/{task.task_id}_long.jpg"
    long_image.save(output_path, "JPEG", quality=90, optimize=True)
    
    artifact_ref = await upload_to_oss(output_path, ...)
    
    return AgentResult(
        ...
        output=Output(
            type="image",
            reference=artifact_ref,
            metadata={
                "width": total_width,
                "height": total_height,
                "segment_count": len(images)
            }
        )
    )
```

### 5.7 边界检查

```python
def check_boundary(task: AgentTask) -> Optional[Error]:
    if task.task_type in ["short_writing", "long_writing"]:
        return Error("我是文档专员,纯文字内容请让文案师处理")
    if task.task_type in ["image_generate", "image_edit"]:
        return Error("我是文档专员,图片生成请让设计师处理")
    if task.task_type in ["video_compose"]:
        return Error("我是文档专员,视频请让影音师处理")
    return None
```

### 5.8 部署

- 容器:`agent-document`
- 资源:2 核 4G(纯 Python 库,不重)
- 队列:`agent_tasks:document`
- 工具依赖:python-pptx、openpyxl、python-docx、PIL、Tesseract

---

## 六、4 个 Agent 对比速查(v3.0 ADR-001-rev)

| 维度 | Agent 1 文字 | **Agent 2 文档** | **Agent 3 图** | **Agent 4 影音** |
|------|------------|-----------|------------|------------|
| 用户视角名 | 研究员/文案师 | 文档专员 | 设计师 | 影音师 |
| 主要 LLM | DeepSeek/Kimi/Sonnet | (大部分不调 LLM)| GPT-Image-2/Seedream | Veo/Seedance/Kling |
| 调用频次 | 高 | 中 | 中-高 | 低(视频任务) |
| 单次延迟 | 5-30s | 5-60s | 5-60s | 30s-10min |
| 单次成本 | $0.01-0.5 | $0.10-0.50 | $0.05-0.20 | $0.30-2.0 |
| 长任务 | 否 | 否 | 否 | **是**(视频合成)|
| 跨 Agent 调用 | **否(ADR-002)** | **否(ADR-002)** | **否(ADR-002)** | **否(ADR-002)** |
| 部署队列 | agent_tasks:text | agent_tasks:document | agent_tasks:image | agent_tasks:av |

---

## 七、典型场景的 Agent 协作

### 7.1 反诈视频制作(5 步,~8 分钟,V1 hero SKU)

> v3.0:V1 hero 回归反诈视频(ADR-012 废弃)。短视频制作降级为 V1.5 Skill 市场。

```
T+0      主编排 → Agent 1(研究员)调研 → 输出 xlsx(含案例 + 图片 URL)
T+30     主编排 → Agent 1(文案师)写脚本 → 输出 docx
         ↓ HITL gate(脚本审核)— 用户选 A/B/C 或要求重写(中断 C)
T+60     主编排 → Agent 1 + Agent 3(设计师)下载并处理图片 → 5 张配图
         ↓ HITL gate(画面审核)— 用户挑选 / 重生成单张
T+90     主编排 → Agent 4(影音师)bgm_select → 输出 BGM 引用
T+120    主编排 → Agent 4(影音师)video_compose(Celery 异步)
         → 5-10 分钟后输出 mp4
         ↓ HITL gate(终审)— 用户接受 / 调字幕 / 回到第 N 步重做(中断 C)
T+8min   最终交付:mp4 + xlsx + docx + 5 张配图 + mp3
```

### 7.2 电商详情图制作(6 步,~100 秒)

```
T+0    用户上传商品图 + 卖点
T+5    主编排 → Agent 3(设计师)风格分析 → 输出风格指引
T+15   主编排 → Agent 1 写文案(5 段)→ 输出 5 段文案
T+30   主编排 → Agent 3 批量生成 5 张分段图(第 1 张为锚点)→ 输出 5 张图
       ↓ HITL gate(可重生成单张)
T+90   主编排 → Agent 2(文档专员)长图拼接 → 输出 1 张长图
T+95   主编排 → Agent 3 质量校验 → 输出 OK
T+100  最终交付:1 张精美的电商详情长图
```

### 7.3 PPT 制作(ADR-002 标准范式,V1.5)

```
T+0    主编排 → Agent 1(structured_writing)写大纲 → outline.json
T+15   主编排 → Agent 3(image_generate × N,并行)生成配图 → image_collection
T+45   主编排 → Agent 2(pptx_assemble)只组装 → output.pptx
       ↑ Agent 2 不调 Agent 1/3,所有 inputs 由主编排注入
```

---

## 七.5 v3.0 新增:支持 Agent(HR + 财务经理)实现要点

> 详见 ADR-013。**HR / 财务经理不是独立微服务**——它们是主编排在主会话场景下,用不同 system prompt 渲染的回复。

### HR

- 触发:用户在主会话说"我应该用什么 Agent 处理这件事" / "我想给 Agent 进修(V2)" / "我想加新 Skill" / "我要成为创作者"(V2)
- 实现:意图理解器输出 `intent_type=team_management` → 主编排调 LiteLLM(L1)用 `HR_SYSTEM_PROMPT`
- 不消费 agent_tasks 队列(不是分任务 Agent)
- 出现位置:**仅主会话**(`mode=main_session`)

### 财务经理

- 触发:用户在主会话说"还剩多少配额" / "升级一下" / "本月账单"
- 实现:意图理解器输出 `intent_type=quota_query | subscription_management` → 主编排调 LiteLLM(L1)用 `FINANCE_SYSTEM_PROMPT`,**附加调 QuotaService 拿数据**
- 出现位置:**仅主会话**

### system prompts 见

`docs/4_附录/系统 Prompt 全集.md` §7(用户面文案库,新增 HR/财务经理章节)

---

## 七.6 v3.0 新增:Agent 拟人化(ADR-015)

每个分任务 Agent 实现要支持:

### 表情 emit

任务关键节点 emit 表情(由主编排 Agent 互动编排器驱动):

```python
# Agent handler 完成时返回 emotion 提示
return AgentResult(
    ...,
    metadata={
        ...,
        "emotion_hint": "happy",   # happy / proud / thinking / frustrated / sad
        "trigger": "task_completed"
    }
)
```

主编排收到后调用 `emit_emoji(agent_id, emotion)` 推到群里(严肃 Skill 关闭)。

### 工作状态自动转换

Agent 进程在以下时刻调 `update_agent_status` API:

- 接到任务 → `working`
- 任务结束 → `idle`
- 30 分钟无任务 → 后台任务自动改 `fishing`

```python
# agents/_common/consumer.py
async def consume_loop(...):
    while True:
        msg = await redis.xreadgroup(...)
        if msg:
            await update_agent_status(user_id, AGENT_ID, "working")
            try:
                result = await process_task(...)
            finally:
                await update_agent_status(user_id, AGENT_ID, "idle")
```

### Agent 间互动

Agent 自身**不**主动发互动消息——这由**主编排的 Agent 互动编排器**(子模块 9)在派活时统一生成。详见 `docs/2_工程实现/主编排 Agent 实现指南.md §九.8`。

---

## 八、所有 Agent 必须遵守的工程原则

1. **Agent 之间不互相 @,不直接对话**——只通过队列
2. **Agent 不主动跨调其他 Agent**(ADR-002)——任何跨能力步骤必须在 Skill YAML 里显式拆出
3. **超出能力必须返错**,不硬撑
4. **所有产物上传 OSS**,返回 artifact_id
5. **元数据完整**(成本、耗时、模型)
6. **失败有 3 层兜底**:重试 → 备用模型 → 用户介入
7. **长任务用 Celery,不阻塞 Agent 进程**
8. **流式输出**(长文、视频生成进度)
9. **质量校验**(可选,但推荐)
10. **统一的 AgentTask / AgentResult 格式**
11. **`call_other_agent` 函数永久禁用**(防御性 NotImplementedError)

---

## 九、相关文档

- [主编排 Agent 实现指南](主编排 Agent 实现指南.md) — 主编排端的派活机制
- [模型路由表](../4_附录/模型路由表.md) — L2 执行层路由完整表
- [Skill YAML 模板](../3_决策记录/Skill YAML 模板.md) — 短视频/电商/PPT 三个示例
- [MCP 集成方案](../3_决策记录/MCP 集成方案.md) — Agent ↔ MCP 调用范式
- [数据飞轮设计](../3_决策记录/数据飞轮设计.md) — 信号沉淀
- [开放问题与决议](../3_决策记录/开放问题与决议.md) — ADR-001、ADR-002 决议详情
