# 主编排 Agent 实现指南

**版本**:v3.0(锁定 ADR-001-rev / ADR-013 / ADR-014 / ADR-015 / ADR-016)
**日期**:2026-05-05
**面向**:后端 / 智能体团队工程师
**地位**:主编排实现的唯一来源。原理与流程请看 [主编排原理与流程](../1_原理篇/主编排原理与流程.md)。

**v3.0 关键变更**:
- ✨ Agent 编号反向(ADR-001-rev):AGENT_QUEUE_MAP 重排
- ✨ 子模块从 8 升到 **9**(新增 Agent 互动编排器,ADR-015)
- ✨ 模式管理器改三模式(Plan / Ask / Auto,ADR-014)
- ✨ 主会话支持 HR + 财务经理 角色(ADR-013)
- ✨ Agent 互动消息生成机制(派活时编排"研究员 @文案师..." 这类对话)

---

## 一、定位

主编排 Agent(在用户面前叫"**总裁助理**")是系统的**大脑**和**唯一调度者**。

**核心约束**:

- 不直接产出内容(不写文案、不画图、不剪视频)
- 是 LangGraph 进程内的 Node 群,**不是独立微服务**
- 每个用户只有一个主编排,跟着用户走(主会话 + 所有群)
- 主力模型用 **deepseek-v4-flash**,备用 **Claude Haiku 4.5**
- **是唯一派活方**——Agent 1-4 之间不互相派活(ADR-002)

---

## 二、内部 9 个子模块

| 子模块 | 是否调 LLM | 模型(主/备)| 上下文 | 延迟 | 成本/次 |
|--------|-----------|-------------|--------|------|---------|
| 1. 意图理解器 | 调 | deepseek-v4-flash / Haiku | 1500 tokens | 300ms | $0.0002 |
| 2. Skill 匹配器 | 99% 不调 | (兜底)Flash / Haiku | 0 / 1500 | 5-30ms / 600ms | $0 / $0.0002 |
| 3. 输入校验器 | 不调 | - | 0 | 1ms | $0 |
| 4. 澄清生成器 | 大部分不调 | (V4 形式)Kimi K2 | 0 / 1000 | 1ms / 3-5s | $0 / $0.001 |
| 5. 任务编排器 | 不调 | - | 0 | 50-200ms | $0 |
| 6. 中断处理器 | 调 | deepseek-v4-flash / Haiku | 1500 tokens | 300ms | $0.0002 |
| **7. 三模式管理器**(v3.0)| 调(brief)| deepseek-v4-flash / Haiku | 1000 tokens | 300ms | $0.0002 |
| 8. HITL 网关管理器 | 半 | (用户决定解析)Flash | 800 tokens | 200ms | $0.0001 |
| **9. Agent 互动编排器**(v3.0,ADR-015)| 调 | Flash | 600 tokens | 200ms | $0.0001 |

**单任务总成本**:$0.001-$0.003(15 次调用)
**单次调用响应**:< 1 秒

**关键设计**:所有 LLM 调用**通过模型路由层**(LiteLLM + 自定义路由表),不直接调 API。路由层根据健康度自动切换模型(主力宕机时切备用)。详见 [模型路由表](../4_附录/模型路由表.md)。

---

## 三、子模块 1:意图理解器

### 3.1 输入

- 用户最新消息
- 最近 3 条对话历史
- 当前会话元数据(群类型、装备的 Skill 列表)

### 3.2 输出 schema

```json
{
  "intent_type": "create_task | modify_task | query | feedback | chitchat | meta | back_to_discuss | ready_to_work",
  "domain": "text | image | video | document | mixed | null",
  "scenario": "short_video | ecommerce_detail | ... | null",
  "entities": {"字段名": "字段值或 null"},
  "confidence": 0.0
}
```

### 3.3 系统 Prompt

```
你是「有了」的总裁助理,负责理解用户意图。

输出字段:
- intent_type: create_task / modify_task / query / feedback / chitchat / meta / back_to_discuss / ready_to_work
- domain: text / image / video / document / mixed
- scenario: 从给定列表选(如 short_video / ecommerce_detail)
- entities: 从消息中提取的字段值(JSON 对象)
- confidence: 0.0-1.0

规则:
- 用户消息模糊时,domain 可以填,scenario 留空
- entities 中,用户没明确提到的字段填 null,不要猜
- 不确定意图时 confidence 低于 0.7,等待澄清
- 必须严格输出 JSON,不要任何其他文字

群类型: {group_type}
群模式: {conversation_mode}  (main_session / discuss / work / private_chat)
装备的 Skill: {available_skills}
最近 3 条对话: {recent_messages}
用户最新消息: {user_message}
```

### 3.4 实现

```python
async def understand_intent(state: TaskState) -> Intent:
    
    context = {
        "group_type": state.conversation.group_type,
        "conversation_mode": state.conversation.mode,
        "available_skills": [
            {"id": s.id, "name": s.name, "scenario": s.scenario}
            for s in state.conversation.equipped_skills
        ],
        "recent_messages": state.messages[-3:],
        "user_message": state.messages[-1].content
    }
    
    prompt = render_template(INTENT_PROMPT, context)
    
    # 通过路由层 L1 调用,主 deepseek-v4-flash,备 Haiku
    response = await router.complete(
        task_type="intent_understanding",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        timeout=2,
        max_tokens=500,
        routing_hints={
            "primary": "deepseek-v4-flash",
            "fallback": ["claude-haiku-4-5"],
            "language": "zh"
        }
    )
    
    try:
        intent = Intent.model_validate_json(response.content)
    except ValidationError:
        return await retry_understand_intent(state)
    
    return intent
```

### 3.5 失败处理

- JSON 解析失败 → 重试 1 次
- 仍失败 → 返回 fallback intent,触发澄清"我没听明白,你想做什么? [视频] [图片] [文章] [文档]"
- 主模型超时 → 路由层自动切 Haiku

### 3.6 测试用例

| 用户消息 | 期望输出 |
|----------|---------|
| "做短视频,2026 投资理财案例" | `intent_type=create_task, scenario=short_video, entities={year:2026, content_type:investment}, confidence=0.95` |
| "我想做点东西" | `intent_type=create_task, domain=null, scenario=null, confidence=0.4` |
| "等等,案例换成城市漫游"(任务进行中)| `intent_type=modify_task, entities={content_type:telecom}, confidence=0.93` |
| "今天天气真好" | `intent_type=chitchat, confidence=0.95` |
| "等下,我觉得方向不对要重新想"(工作群)| `intent_type=back_to_discuss, confidence=0.92` |
| "差不多了开始做吧"(讨论群)| `intent_type=ready_to_work, confidence=0.90` |

---

## 四、子模块 2:Skill 匹配器

### 4.1 三层检索

#### 第 1 层:关键词检索(SQL,5-30ms,0 tokens)

```python
def keyword_match(user_message, intent, user_id):
    keywords = jieba_tokenize(user_message)
    if intent.scenario:
        keywords.append(intent.scenario)
    
    sql = """
    SELECT skill_id, name,
        cardinality(ARRAY(SELECT unnest(keywords) INTERSECT SELECT unnest(%s))) as match_count
    FROM skills
    WHERE keywords && %s
      AND skill_id IN (SELECT skill_id FROM user_skill_visibility WHERE user_id = %s)
      AND NOT (anti_signals && %s)
    ORDER BY match_count DESC LIMIT 5
    """
    
    results = db.execute(sql, [keywords, keywords, user_id, keywords])
    
    if results and results[0].match_count >= 2:
        return results[0].skill_id
    return None
```

#### 第 2 层:语义向量检索(pgvector,30-50ms,0 tokens)

```python
async def semantic_match(user_message, user_id):
    query_vec = await bge_m3.embed(user_message)
    
    sql = """
    SELECT skill_id, 1 - (description_vec <=> %s) as similarity
    FROM skill_embeddings
    WHERE skill_id IN (SELECT skill_id FROM user_skill_visibility WHERE user_id = %s)
    ORDER BY description_vec <=> %s LIMIT 5
    """
    
    results = db.execute(sql, [query_vec, user_id, query_vec])
    
    if results and results[0].similarity >= 0.85:
        return results[0].skill_id
    return None
```

#### 第 3 层:LLM 兜底(deepseek-v4-flash,600-800ms,$0.0002)

```python
async def llm_match(user_message, intent, user_id):
    candidates = get_top_candidates(user_id, limit=10)
    candidates_brief = [
        {"id": s.id, "name": s.name, "description": s.description[:50]}
        for s in candidates
    ]
    
    prompt = f"""
    用户消息:"{user_message}"
    用户意图:{intent.model_dump_json()}
    候选 Skill:{json.dumps(candidates_brief, ensure_ascii=False)}
    
    判断哪个 Skill 最匹配。如果都不匹配,返回 null。
    输出 JSON: {{"skill_id": "xxx", "confidence": 0.0-1.0}}
    """
    
    response = await router.complete(
        task_type="skill_matching",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        timeout=2,
        routing_hints={
            "primary": "deepseek-v4-flash",
            "fallback": ["claude-haiku-4-5"]
        }
    )
    
    result = json.loads(response.content)
    if result.get("skill_id") and result.get("confidence", 0) >= 0.7:
        return result["skill_id"], result["confidence"]
    return None
```

### 4.2 调度流程

```python
async def match_skill(state: TaskState) -> Optional[Skill]:
    user_message = state.messages[-1].content
    intent = state.user_inputs.intent
    user_id = state.user_id
    
    skill_id = keyword_match(user_message, intent, user_id)
    if skill_id:
        return load_skill(skill_id)
    
    skill_id = await semantic_match(user_message, user_id)
    if skill_id:
        return load_skill(skill_id)
    
    result = await llm_match(user_message, intent, user_id)
    if result:
        return load_skill(result[0])
    
    return None
```

### 4.3 找不到匹配

返回 Top 3 候选给用户确认:

```python
async def ask_user_to_pick_skill(state):
    candidates = get_top_3_candidates(state.user_id, state.messages[-1].content)
    
    await emit_clarification({
        "type": "single_select",
        "question": "我不太确定你想做什么,是这几个吗?",
        "options": [{"label": s.name, "value": s.id} for s in candidates]
                   + [{"label": "都不是", "value": "none"}]
    })
```

### 4.4 群内 Skill 限制

如果用户在"短视频群"里说"做小红书笔记"——这个群没装备小红书 Skill。

```python
if matched_skill.id not in state.conversation.equipped_skills:
    await emit_message({
        "content": "这个群是短视频专用,你想做小红书笔记的话,我帮你新建一个群?",
        "options": ["新建小红书群", "继续在这个群做短视频", "取消"]
    })
```

---

## 五、子模块 3:输入校验器

### 5.1 实现(纯程序)

```python
def validate_inputs(
    skill: Skill,
    intent: Intent,
    user_prefs: UserPreferences,
    brief: Optional[Brief] = None,  # 来自 ContextPool(讨论群衍生工作群时)
) -> ValidationResult:
    filled = {}
    missing = []
    
    for field in skill.inputs_schema:
        # 优先级 1: 用户消息里提到了
        if field.name in intent.entities and intent.entities[field.name] is not None:
            filled[field.name] = intent.entities[field.name]
        
        # 优先级 2: Brief 里有(讨论群已聊过)
        elif brief and field.name in brief.字段:
            filled[field.name] = brief.字段[field.name]
        
        # 优先级 3: 偏好库可信度足够
        elif field.name in user_prefs and user_prefs[field.name].confidence >= 1.0:
            filled[field.name] = user_prefs[field.name].value
        
        # 优先级 4: 选填字段用默认值
        elif not field.required:
            filled[field.name] = field.default
        
        # 必填且找不到 → 缺失
        else:
            missing.append(field)
    
    return ValidationResult(filled=filled, missing=missing)
```

### 5.2 偏好可信度阈值

| 用户行为 | 偏好可信度 | 处理 |
|---------|-----------|------|
| 第 1 次选某值 | 0.3 | 不影响下次询问 |
| 连续 2 次同选 | 0.7 | 仍要问,但选项默认值用偏好值 |
| 连续 3 次同选 | 1.0 | **自动套用,不再问** |

只有可信度 ≥ 1.0 才自动套用。

---

## 六、子模块 4:澄清生成器

### 6.1 4 种澄清形式

详见 [主编排原理与流程 §7](../1_原理篇/主编排原理与流程.md#七子模块-4意图澄清)。

### 6.2 实现

```python
async def generate_clarification(missing_fields: list, state: TaskState) -> Optional[Clarification]:
    
    if len(missing_fields) == 0:
        return None
    
    if len(missing_fields) == 1:
        return await _generate_single_field(missing_fields[0], state)
    
    if len(missing_fields) <= 3:
        return _generate_combined_question(missing_fields)
    
    # 超过 3 个,拆 2 轮,先问最关键的 2 个
    return _generate_combined_question(missing_fields[:2])


async def _generate_single_field(field, state):
    if field.clarification_form == "single_select":
        return Clarification(type="single_select", field=field.name, options=field.options)
    
    elif field.clarification_form == "image_compare":
        return Clarification(type="image_compare", field=field.name, preview_images=field.preview_images)
    
    elif field.clarification_form == "version_compare":
        # 走标准 Agent 派活流程,不是主编排自己调
        agent_task = build_version_generate_task(state, field, count=field.generate_count)
        await publish_to_queue("agent_tasks:text", agent_task)
        versions = await wait_for_result(agent_task.callback.result_queue, timeout=10)
        return Clarification(type="version_compare", field=field.name, versions=versions)
```

### 6.3 用户回答处理

```python
@router.post("/api/tasks/{task_id}/answer-clarification")
async def answer_clarification(task_id: str, payload: dict):
    
    field_name = payload["field_name"]
    value = payload["value"]
    
    await langgraph_api.update_state(
        thread_id=task_id,
        values={"user_inputs.collected_fields": {field_name: value}}
    )
    
    state = await load_state(task_id)
    result = validate_inputs(state.skill, state.user_inputs.intent, state.user_prefs, state.brief)
    
    if result.missing:
        clarification = await generate_clarification(result.missing, state)
        await emit_clarification(clarification)
    else:
        await langgraph_api.resume(thread_id=task_id)
```

---

## 七、子模块 5:任务编排器

### 7.1 编译过程(只做一次,缓存)

```
Skill YAML
    ↓
Parser 解析为内存对象
    ↓
为每个 step 创建 LangGraph Node
    ↓
根据 depends_on 创建 Edges
    ↓
编译为可执行 StateGraph
    ↓
绑定 PostgreSQL checkpointer
    ↓
缓存到 Redis(key = skill_id + version)
```

### 7.2 Node 函数模板

每个 Skill 步骤变成一个 LangGraph Node:

```python
async def make_step_node(step: WorkflowStep):
    async def node_function(state: TaskState) -> dict:
        
        # 1. 状态前置检查
        if state.status != "executing":
            return {}
        
        # 2. 渲染 prompt
        prompt = render_prompt(
            template=step.prompt_template,
            collected_fields=state.user_inputs.collected_fields,
            artifacts=state.artifacts
        )
        
        # 3. 准备 AgentTask
        agent_task = AgentTask(
            task_id=state.task_id,
            step_id=step.step_id,
            agent_id=step.agent,           # "agent_1" / "agent_2" / "agent_3" / "agent_4"
            task_type=step.task_type,
            prompt=prompt,
            inputs=resolve_inputs(step.inputs, state),
            parameters=step.parameters,
            routing_hints=step.routing_hints,
            output_format=step.output_format,
            callback={
                "result_queue": f"agent_results:{state.task_id}_{step.step_id}",
                "timeout_seconds": step.timeout
            }
        )
        
        # 4. 通知前端
        await emit_ws_event("step_started", {
            "step_id": step.step_id,
            "agent_id": step.agent
        })
        
        # 5. 提交到 Agent 队列(ADR-001-rev v3.0 反向锁定)
        queue_name = AGENT_QUEUE_MAP[step.agent]
        # AGENT_QUEUE_MAP = {
        #   "agent_1": "agent_tasks:text",
        #   "agent_2": "agent_tasks:document",   # v3.0 改:文档
        #   "agent_3": "agent_tasks:image",       # v3.0 改:图
        #   "agent_4": "agent_tasks:av"           # v3.0 改:影音
        # }
        await publish_to_queue(queue=queue_name, task=agent_task)
        
        # 6. 等待结果(异步)
        try:
            result = await wait_for_result(
                queue=agent_task.callback.result_queue,
                timeout=step.timeout
            )
        except TimeoutError:
            return await handle_step_failure(step, "timeout", state)
        
        # 7. 失败处理
        if result.status == "failed":
            return await handle_step_failure(step, result.error, state)
        
        # 8. 质量校验(可选)
        if step.quality_check:
            if not validate_quality(result, step.quality_check):
                return await handle_quality_failure(step, result, state)
        
        # 9. 把产物加入 state(用引用)
        new_artifact = Artifact(
            artifact_id=result.output.artifact_id,
            step_id=step.step_id,
            type=result.output.type,
            reference=result.output.reference,
            metadata=result.output.metadata
        )
        
        # 10. 通知前端
        await emit_ws_event("step_completed", {
            "step_id": step.step_id,
            "artifact": new_artifact.to_preview()
        })
        
        emit_metric_event("step_completed", {...})
        
        return {
            "artifacts": state.artifacts + [new_artifact],
            "workflow.completed_steps": [...] + [step.step_id]
        }
    
    return node_function
```

### 7.3 Prompt 渲染(纯程序)

```python
def render_prompt(template: str, collected_fields: dict, artifacts: list) -> str:
    
    context = {
        **collected_fields,
        **{
            f"{art.step_id}.output": load_artifact_for_prompt(art)
            for art in artifacts
        }
    }
    
    return Template(template).render(**context)


def load_artifact_for_prompt(artifact: Artifact):
    if artifact.type == "text":
        return load_from_oss(artifact.reference).read_text()
    elif artifact.type in ("image", "video"):
        return artifact.reference  # OSS URL
    elif artifact.type == "structured":
        return {
            "summary": artifact.metadata.get("summary"),
            "reference": artifact.reference
        }
```

### 7.4 派给哪个 Agent

由 Skill 的 `agent` 字段直接指定。**主编排不需要"判断"**:

```yaml
workflow:
  - {step_id: research, agent: agent_1}
  - {step_id: script, agent: agent_1, depends_on: [research]}
  - {step_id: image_process, agent: agent_3, depends_on: [research]}   # 图(ADR-001-rev v3.0)
  - {step_id: bgm, agent: agent_4, depends_on: [script]}                # 影音(ADR-001-rev v3.0)
  - {step_id: video_compose, agent: agent_4, depends_on: [script, image_process, bgm]}
```

### 7.5 并行执行

LangGraph 自动识别可并行节点(没有相互依赖的)。**不需要 Skill 定义里写"哪些可以并行"**,LangGraph 拓扑调度自动处理。

### 7.6 跨能力步骤(ADR-002)

⚠️ **Agent 不主动跨调其他 Agent**。Agent 4 做 PPT 时需要文字大纲 + 配图,**必须在 Skill YAML 里显式拆出 step**:

```yaml
workflow:
  - {step_id: ppt_outline, agent: agent_1, task_type: structured_writing}
  - {step_id: ppt_images, agent: agent_3, depends_on: [ppt_outline]}    # 图(v3.0:Agent 3)
  - {step_id: ppt_assemble, agent: agent_2, depends_on: [ppt_outline, ppt_images]}    # 文档(v3.0:Agent 2)
```

**主编排是唯一调度者,Agent 之间只通过产物传递数据。**

---

## 八、子模块 6:中断处理器

### 8.1 处理流程

```
新用户消息
    ↓
检测 task.status == "executing"
    ↓
调用中断分类器(deepseek-v4-flash)
    ↓
得到中断类型 A-H + 影响范围
    ↓
派发到对应 handler
    ↓
操作 LangGraph state(update_state / resume / cancel)
    ↓
通知前端 + 回复用户
```

### 8.2 中断分类输出

```json
{
  "category": "C",
  "confidence": 0.88,
  "affected_fields": ["content_type"],
  "affected_steps": ["research", "script", "image_process"],
  "intent_summary": "用户想把内容类型从投资理财改成城市漫游"
}
```

### 8.3 8 类中断处理

| 类型 | 含义 | 处理方式 | V1 |
|------|------|---------|----|
| A | 补充信息 | graph.update_state + invoke 继续 | ✓ |
| B | 微调当前 | 取消当前节点 + 改 prompt + 重启 | ✓ |
| C | 修改参数 | 依赖图回滚 + 重做受影响步骤 | V2 |
| D | 改方向 | 当前 graph 标 abandoned + 创建新 graph | V2 |
| E | 暂停 | task.status = paused | ✓ |
| F | 取消 | task.status = cancelled,24h 后清理 | ✓ |
| G | 闲聊 | 不动 graph,直接回复 | ✓ |
| H | 反馈 | 写事件流,可能转 B | ✓ |

### 8.4 实现(以 A 类为例)

```python
async def handle_interrupt_A(message, classification, state):
    """A 类:补充信息"""
    
    new_fields = await extract_fields_from_message(message, state.skill)
    
    await langgraph_api.update_state(
        thread_id=state.task_id,
        values={
            "user_inputs.collected_fields": {
                **state.user_inputs.collected_fields,
                **new_fields
            }
        }
    )
    
    current_step = get_current_running_step(state)
    if current_step and any(
        f in current_step.prompt_template_vars 
        for f in new_fields
    ):
        await restart_step(state, current_step.step_id)
    
    summary = format_changes_summary(new_fields)
    await send_assistant_message(state.task_id, f"好的,已记录:{summary}")
```

### 8.5 关键约束

- **置信度 < 0.7 时不直接处理**,先让用户确认意图("你是想暂停这个任务吗?")
- **永远先回复用户**,再操作 graph
- **中断处理本身不能被中断**

---

## 九、子模块 7:模式管理器

### 9.1 派发逻辑

```python
class ModeManager:
    async def handle_user_message(self, message: Message, conversation: Conversation):
        if conversation.mode == "main_session":
            return await self._handle_main_session(message, conversation)
        elif conversation.mode == "discuss":
            return await self._handle_discuss_mode(message, conversation)
        elif conversation.mode == "work":
            return await self._handle_work_mode(message, conversation)
        elif conversation.mode == "private_chat":
            return await self._handle_private_chat(message, conversation)
```

### 9.2 主会话:用户元操作的入口

```python
async def _handle_main_session(self, message, conversation):
    intent = await intent_understander.understand(message, conversation)
    
    if intent.intent_type == "create_task":
        user_prefs = await user_pref_service.get(conversation.user_id)
        default_mode = user_prefs.get("default_mode")
        
        # 偏好已沉淀(confidence=1.0),跳过模式选择
        if default_mode and default_mode.confidence >= 1.0:
            if default_mode.value == "discuss":
                await self._create_discuss_group(message, intent)
            elif default_mode.value == "work":
                skill = await skill_matcher.match(intent)
                await self._create_work_group(message, intent, skill)
        else:
            await self._ask_mode_choice(message, intent, conversation)
    elif intent.intent_type == "query":
        await self._handle_cross_group_query(message, conversation)
    elif intent.intent_type == "meta":
        await self._handle_meta_op(message, conversation)
```

### 9.3 讨论模式

```python
async def _handle_discuss_mode(self, message, conversation):
    intent = await intent_understander.understand(message, conversation)
    
    # 1. 用户主动"开始制作"
    if intent.intent_type == "ready_to_work":
        await self._propose_create_work_group(conversation)
        return
    
    # 2. 派活给 Agent 1 / Agent 2(讨论群只装这两个)
    if intent.needs_research:
        await self._call_researcher(message, conversation)
    elif intent.needs_reference_image:
        await self._call_designer_for_reference(message, conversation)
    else:
        await self._reply_with_guidance(message, conversation)
    
    # 3. 后台异步:更新 brief(防抖批量)
    await brief_scheduler.schedule_update(
        pool_id=conversation.context_pool_id,
        new_message=message.content,
        conversation_id=conversation.id
    )
```

### 9.4 干活模式

```python
async def _handle_work_mode(self, message, conversation):
    if conversation.has_running_task():
        await interrupt_handler.handle(message, conversation)
        return
    
    intent = await intent_understander.understand(message, conversation)
    if intent.intent_type == "back_to_discuss":
        await self._propose_back_to_discuss(message, conversation)
        return
    
    pool = await context_pool_service.get(conversation.context_pool_id)
    
    skill = await skill_matcher.match(intent, conversation)
    validation = input_validator.validate(
        skill, intent, pool.user_preferences_snapshot, brief=pool.brief
    )
    
    if validation.missing:
        clarification = await clarification_generator.generate(validation.missing)
        await chat_service.send_clarification(conversation.id, clarification)
    else:
        await orchestrator.start_workflow(
            conversation=conversation,
            skill=skill,
            inputs=validation.filled
        )
```

### 9.5 Brief 更新(防抖批量)

```python
async def schedule_brief_update(pool_id, new_message, conversation_id):
    """
    触发条件(满足任一即更新):
    1. 用户停顿 5 秒(打字结束防抖)
    2. 累计 3 条新消息未更新
    3. 用户主动点 [总结一下]
    4. 总裁助理被 @ 时强制更新
    """
    counter = await redis.incr(f"brief_pending:{pool_id}")
    
    if counter >= 3:
        await _do_update(pool_id, conversation_id)
        await redis.delete(f"brief_pending:{pool_id}")
    else:
        # 5 秒防抖
        await scheduler.schedule_once(
            f"brief_debounce:{pool_id}",
            delay=5,
            callback=lambda: _do_update(pool_id, conversation_id)
        )
```

详细 brief 维护逻辑见 [两种模式技术实现](两种模式技术实现.md)。

---

## 九.5 子模块 8:HITL 网关管理器(v2.0,ADR-010)

### 9.5.1 触发

任务编排器在执行某 step 完成后,如果该 step 的 Skill YAML 声明了 `hitl_gate`,主编排:

1. 不立即推进到下一 step
2. 把 LangGraph state 标 `status = waiting_hitl`
3. 创建 `hitl_gates` 表记录
4. WS 推 `hitl_gate_opened` 事件给前端
5. 等待用户响应

### 9.5.2 实现

```python
class HITLGateManager:
    
    async def open_gate(self, task_id, step_id, gate_config, artifact):
        gate = HITLGate(
            id=uuid4(),
            task_id=task_id,
            step_id=step_id,
            gate_type=gate_config.type,        # version_select / quality_review / final_approval
            opened_at=now(),
            preview_artifact_id=artifact.id,
            timeout_seconds=gate_config.timeout_seconds,
        )
        await db.save(gate)
        
        # 暂停 LangGraph
        await langgraph_api.update_state(
            thread_id=task_id,
            values={"status": "waiting_hitl", "current_gate_id": gate.id}
        )
        
        # 通知前端
        await emit_to_user(
            user_id=task.user_id,
            event={
                "type": "hitl_gate_opened",
                "task_id": task_id,
                "gate": gate.to_dict(),
                "preview_artifact": artifact.to_preview()
            }
        )
        
        # 启动超时定时器
        asyncio.create_task(self._handle_timeout(gate, gate_config))
    
    async def resolve_gate(self, task_id, gate_id, resolution: HITLResolution):
        """用户响应后调用"""
        gate = await db.get(HITLGate, id=gate_id)
        gate.closed_at = now()
        gate.resolution = resolution.action       # approved / modified / rolled_back / timeout
        gate.user_choice = resolution.payload
        await db.save(gate)
        
        if resolution.action == "approved":
            # 推进下一 step
            await langgraph_api.update_state(thread_id=task_id, values={"status": "executing"})
            await langgraph_api.invoke(thread_id=task_id, resume_from_next=True)
        
        elif resolution.action == "modified":
            # 转中断 B(微调当前 step)
            await interrupt_handler.handle_B(task_id, modification=resolution.payload)
        
        elif resolution.action == "rolled_back":
            # 转中断 C(回滚)
            await interrupt_handler.handle_C(task_id, target_step=resolution.payload["target_step"])
```

### 9.5.3 中断 C 实现(回滚)

```python
async def handle_interrupt_C(task_id, target_step: str):
    """V1 必须实现(ADR-010)"""
    
    state = await langgraph_api.get_state(task_id)
    skill = await load_skill(state.skill_id)
    
    # 1. 计算受影响 step(target_step 及其下游)
    affected_steps = compute_downstream_steps(skill.workflow, target_step)
    
    # 2. 把受影响 step 的产物加版本号(不删除,便于对比)
    for step_id in affected_steps:
        existing_artifact = state.artifacts.get(step_id)
        if existing_artifact:
            await mark_artifact_as_old_version(existing_artifact.id)
    
    # 3. 标记 step 为 invalidated
    await langgraph_api.update_state(
        thread_id=task_id,
        values={
            "workflow.invalidated_steps": affected_steps,
            "rollback_target": target_step,
            "rollback_count": state.rollback_count + 1,
            "status": "executing"
        }
    )
    
    # 4. 通知用户
    await chat_service.send_assistant_message(
        conversation_id=state.conversation_id,
        content=ROLLBACK_CONFIRMATION_TEMPLATE.format(
            target_step_human_name=skill.workflow[target_step].human_name,
            kept_steps=...,
            redo_steps=...,
            estimated_minutes=...
        )
    )
    
    # 5. 推 WS 事件
    await emit_to_user(state.user_id, {"type": "rollback_started", ...})
    
    # 6. 从 target_step 重启
    await langgraph_api.invoke(thread_id=task_id, resume_from=target_step)
```

### 9.5.4 旧产物保留(用于对比)

回滚时不删除旧产物:

- 数据库 `artifacts` 表加列 `version INT DEFAULT 1`
- 同 `(task_id, step_id)` 重复产物,version 递增
- 前端可显示"对比 v1 vs v2"

---

## 九.6 数据飞轮信号沉淀(v2.0,ADR-011)

任务编排器在 step 完成 / 任务结束时,**必须** emit 4 类信号:

```python
# app/services/flywheel.py
class FlywheelEmitter:
    
    async def on_step_completed(self, task: Task, step: Step):
        # 信号 2:用户偏好向量更新(如该 step 涉及用户选择)
        if step.had_user_choice:
            await self._update_preference_vec(task.user_id, step.user_choice)
    
    async def on_task_completed(self, task: Task):
        # 信号 1:工作流轨迹 → Qdrant
        await self._emit_workflow_trace(task)
        
        # 信号 4:高满意度 → Skill 草稿
        if task.user_satisfaction >= 4 and self._is_novel(task):
            await self._emit_skill_draft(task)
    
    async def on_task_failed(self, task: Task, failure: Failure):
        # 信号 3:Reflexion
        await self._emit_failure_for_reflexion(task, failure)
    
    async def on_user_negative_feedback(self, task: Task, feedback: Feedback):
        # 信号 3:Reflexion(用户主动反馈不满意)
        if feedback.satisfaction <= 2:
            await self._emit_failure_for_reflexion(task, Failure.from_feedback(feedback))
```

**所有 step 完成 / 任务结束的代码路径必须经过此 emitter,CI 检查 PR 必有信号沉淀**。

详细见 [数据飞轮设计](../3_决策记录/数据飞轮设计.md)。

---

## 九.7 MCP 客户端集成(v2.0,ADR-009)

主编排不直接调外部工具,但需要决定**让 Agent 用哪些 MCP 工具**:

```python
# agents/orchestrator_agent/task_compiler.py(节选)

async def build_agent_task(state, step):
    # ...(原有逻辑)
    
    # v2.0:把 Skill 声明的 mcp_tools 注入 AgentTask
    agent_task = AgentTask(
        ...,
        mcp_tools=[
            MCPToolRef.parse(uri) for uri in step.mcp_tools  # mcp://search/web_search
        ],
        hitl_gate=step.hitl_gate,                            # v2.0
    )
    
    return agent_task
```

Agent 端按 `mcp_tools` 用 LiteLLM 的 tool use 调用。详细见 [MCP 集成方案](../3_决策记录/MCP 集成方案.md)。

---

## 九.7 子模块 7 升级:三模式管理器(v3.0,ADR-014)

### 9.7.1 派发逻辑(三模式)

```python
class ModeManager:
    async def handle_user_message(self, message, conversation):
        if conversation.mode == "main_session":
            return await self._handle_main_session(message, conversation)
        elif conversation.mode == "private_chat":
            return await self._handle_private_chat(message, conversation)
        else:  # group
            return await self._dispatch_by_work_mode(message, conversation)
    
    async def _dispatch_by_work_mode(self, message, conversation):
        if conversation.work_mode == "plan":
            return await self._handle_plan(message, conversation)
        elif conversation.work_mode == "ask":
            return await self._handle_ask(message, conversation)
        elif conversation.work_mode == "auto":
            return await self._handle_auto(message, conversation)
```

### 9.7.2 模式切换(API + 隐式触发)

```python
async def switch_work_mode(conversation_id, target: str, triggered_by: str):
    conv = await load_conversation(conversation_id)
    old_mode = conv.work_mode
    
    # 写入 mode_switch_log
    await db.insert("mode_switch_log", {
        "conversation_id": conv.id,
        "from_mode": old_mode,
        "to_mode": target,
        "triggered_by": triggered_by
    })
    
    # 更新 conversation
    conv.work_mode = target
    await db.save(conv)
    
    # 推系统消息
    await chat_service.send_system_message(
        conv.id,
        f"─── 总裁助理 切到 {MODE_DISPLAY[target]} ───"
    )
    
    # WS 推前端
    await emit_to_user(conv.user_id, {
        "type": "work_mode_changed",
        "conversation_id": str(conv.id),
        "from": old_mode,
        "to": target
    })
```

### 9.7.3 隐式触发(意图理解里识别)

意图理解器输出 `intent_type` 增加:

- `switch_to_auto`("开干"、"就这么做")
- `switch_to_plan`("等等我再想想"、"先讨论下")
- `temp_ask`("顺便问下"、"我有个问题")  ← 不切模式,临时 Ask 一次

`_handle_auto` 内部检测到 `temp_ask` 时,**不切模式**,只走单轮 Ask 应答,主任务不受影响。

---

## 九.8 子模块 9:Agent 互动编排器(v3.0,ADR-015)

### 9.8.1 职责

在派活给某个 Agent 之前,**生成"前一个 Agent 把任务交接给当前 Agent"的对话消息**,让用户视角看起来像真公司工作群。

### 9.8.2 实现

```python
class AgentInteractionOrchestrator:
    
    async def emit_handoff(self, from_agent, to_agent, context, conversation_id):
        """生成前 Agent → 后 Agent 的交接消息"""
        
        # 调 LLM 生成自然的"交接对话"(很短,< 50 字)
        prompt = f"""
        {from_agent.role_name} 刚完成 {context.from_task},现在要交给 {to_agent.role_name} 做 {context.to_task}。
        生成一条简短的交接消息(50 字内),含 @{to_agent.role_name},口吻自然、有公司感。
        """
        msg = await router.complete(
            task_type="agent_interaction",
            messages=[{"role": "user", "content": prompt}],
            routing_hints={"primary": "deepseek-v4-flash"}
        )
        
        # 推到群里(role = from_agent)
        await chat_service.send_agent_message(
            conversation_id=conversation_id,
            role=from_agent.id,
            content=msg.content,
            metadata={"interaction_type": "handoff"}
        )
    
    async def emit_emoji(self, agent_id, emotion: str, conversation_id):
        """关键节点 emit 表情"""
        if await is_serious_skill(conversation_id):
            return  # 严肃场景不出表情
        
        emoji_asset = await get_emoji_asset(agent_id, emotion)
        await chat_service.send_agent_message(
            conversation_id=conversation_id,
            role=agent_id,
            content=None,
            content_type="emoji",
            metadata={"emoji_asset": emoji_asset, "emotion": emotion}
        )
```

### 9.8.3 触发节点

| 节点 | 行为 |
|------|------|
| Skill step 切换 | emit_handoff(from_agent, to_agent) |
| Agent 完成 step | emit_emoji(agent_id, "happy") |
| Agent 失败 | emit_emoji(agent_id, "frustrated") |
| 用户表扬 | emit_emoji(agent_id, "proud") |
| 用户批评 | emit_emoji(agent_id, "sad") |

### 9.8.4 工作状态显示

每个 Agent 有 `agent_status` 表项(`(user_id, agent_id) → status`):

```python
async def update_agent_status(user_id, agent_id, status):
    await db.upsert("agent_status", {
        "user_id": user_id, "agent_id": agent_id,
        "status": status,    # working / idle / fishing / training
        "last_active_at": now()
    })
    await emit_to_user(user_id, {
        "type": "agent_status_changed",
        "agent_id": agent_id, "status": status
    })

# 状态自动转换
# - 派活 → working
# - 任务结束 → idle
# - idle 30 分钟 → fishing
```

---

## 九.9 主会话支持 Agent(v3.0,ADR-013)

主会话(`conversations.mode = main_session`)额外支持 2 个角色:

- **HR**:管理 AI 团队
- **财务经理**:管订阅、配额、成本

### 9.9.1 意图分类

意图理解器在主会话下增加识别:

- `team_management` → 派给 HR
- `quota_query` / `subscription_management` → 派给 财务经理

### 9.9.2 实现

HR 和财务经理**不是独立 Agent 微服务**——他们是主编排在主会话里调用 LiteLLM 时,**用不同的 system prompt 渲染回复**:

```python
async def _handle_main_session_team_management(message, conversation):
    response = await router.complete(
        task_type="team_management",
        messages=[
            {"role": "system", "content": HR_SYSTEM_PROMPT},
            {"role": "user", "content": message.content}
        ]
    )
    await chat_service.send_agent_message(
        conversation.id,
        role="hr",
        content=response.content
    )
```

### 9.9.3 群成员栏

主会话顶部群成员栏显示 7 个角色:总裁助理 + 4 分任务 Agent + HR + 财务经理。其他群只显示 5 个(总裁助理 + 4 分任务 Agent)。

---

## 十、整体流程示例

用户在短视频群说:"做短视频,2026 投资理财"

```
T+0       用户发消息
T+0.1     [意图理解] deepseek-v4-flash,300ms,1500 tokens,$0.0002
          输出:intent_type=create_task, scenario=short_video,
                entities={year:2026, content_type:investment}, confidence=0.95
T+0.4     [Skill 匹配] L1 关键词命中,5ms,0 tokens
          输出:skill_id=short_video, confidence=0.95
T+0.41    [输入校验] 纯程序,1ms
          输出:filled={年份, 内容类型, 时长}, missing=[受众]
T+0.42    [澄清生成] 纯程序(单字段单选)
          输出:选择题"受众? [城市老人] [农村老人] [都覆盖]"
T+0.5     推送给前端

[等用户选择...]

T+10      用户点 [城市老人]
T+10.1    [输入校验] 重新校验,字段全齐
T+10.15   [任务编排] 加载 Skill workflow,编译为 LangGraph
T+10.2    主编排回复:"任务开始,研究员先调研..."
T+10.3    启动 research 节点,渲染 prompt,提交 agent_tasks:text 队列
[Agent 1 开始执行,用户看到右栏更新...]
```

---

## 十一、性能与成本汇总

| 子模块 | LLM 调用 | 上下文 | 延迟 | 成本/任务 |
|--------|---------|--------|------|----------|
| 意图理解 | deepseek-v4-flash | 1500 tokens | 300ms | $0.0002 |
| Skill 匹配 | 99% 不调,1% 调 | 0 / 1500 | 5-30ms / 600ms | $0 / $0.0002 |
| 输入校验 | 不调 | 0 | 1ms | $0 |
| 澄清生成 | 大部分不调 | 0 / 1000 | 1ms / 3-5s | $0 / $0.001 |
| 任务编排 | 不调 | 0 | 50-200ms | $0 |
| 中断处理 | deepseek-v4-flash | 1500 tokens | 300ms | $0.0002 |
| 模式管理 | deepseek-v4-flash | 1000 tokens | 300ms | $0.0002 |

**主编排单任务总成本**:$0.001-$0.003(15 次调用)
**主编排单次调用响应**:< 1 秒

---

## 十二、相关文档

- [4 个分任务 Agent 实现指南](4 个分任务 Agent 实现指南.md) — Agent 1-4 实现
- [两种模式技术实现](两种模式技术实现.md) — 数据模型 + ConversationService + ContextPoolService
- [模型路由表](../4_附录/模型路由表.md) — L1+L2 两层路由
- [Skill YAML 模板](../3_决策记录/Skill YAML 模板.md) — Skill 定义示例
- [开放问题与决议](../3_决策记录/开放问题与决议.md) — 所有 ADR
