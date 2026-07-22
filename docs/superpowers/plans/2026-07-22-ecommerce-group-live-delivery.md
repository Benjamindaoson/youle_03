# 电商专业群真实交付 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 将现有 ecommerce_detail_image 从 mock 工作流改造成同一专业群内、每次图片调用均经用户确认的国内模型真实交付链路。

**Architecture:** 保持一个 LangGraph 编排器、一个群聊与既有四个专业 Agent。编排器在 Agent 3 的图片任务派发前发出可审计的 image_generation_confirmation 中断；批准后才允许调用火山方舟 Seedream，失败即在群内失败，不重试、不换模型。Agent 2 直接复用本地 Pillow 拼接函数，避免为详情长图额外启动 MCP/Docker 服务。

**Tech Stack:** FastAPI、SQLAlchemy、LangGraph、Redis Streams、Pydantic、httpx、Pillow、Next.js、React、Vitest、pytest。

## Global Constraints

- 电商仅是现有群聊中的专业能力：不新增页面、会话类型、Agent 或第二编排器。
- 电商群成员固定为 ceo_assistant、agent_1、agent_2、agent_3；不得包含 agent_4、hr、finance_manager。
- 任何图片模型调用（首次、批量、单张重生、补图）都必须先显示并由用户批准精确数量；不得按金额或数量自动批准。
- 电商真实路径只使用 DeepSeek 文本、火山方舟 Seedream 图片、Pillow 拼接；不能自动重试、不能自动切换到海外模型。
- 没有 ARK_API_KEY 时不伪造成功：显式失败且不产生模型调用。默认本地 core 继续使用 mock，真实调用须显式选择 live profile。
- 不新增运行时依赖；详情长图拼接不得要求额外 Docker/MCP 进程。

---

## File Structure

- backend/app/api/conversations.py — 为电商 skill 返回专属群成员。
- agents/agents/orchestrator_agent/langgraph_runner/compiler_step_node.py — 支持 before_dispatch HITL，且先闸门后派发。
- backend/skills/playbooks/ecommerce_detail_image.yaml — 唯一的确认优先工作流。
- agents/agents/image_agent/handlers/ark_seedream.py — 火山方舟原生图片接口的一次性适配器。
- agents/agents/image_agent/handlers/batch_generate.py — 电商指定图片提供商分支。
- agents/agents/document_agent/main.py、handlers/image_concat_long.py、mcp_servers/image_tools/server.py — Agent 2 的真实 Pillow 拼接，不依赖 HTTP sidecar。
- frontend/components/chat/PendingInteractions.tsx — 群聊里的精确数量确认卡片。
- frontend/lib/agents.ts、GroupMembers.tsx、MentionPopover.tsx — 电商四成员群的显示。
- deploy/production/.env.ecommerce.example、deploy/production/README.md — mock/live 分层。

### Task 1: 锁定电商专业群成员

**Files:**
- Modify: backend/app/api/conversations.py:241-296
- Modify: backend/tests/unit/test_conversation_members.py
- Modify: frontend/lib/agents.ts, frontend/components/chat/GroupMembers.tsx, frontend/components/chat/MentionPopover.tsx
- Create: frontend/lib/agents.test.ts

**Interfaces:** Produces _members_for_mode(mode, skill_id=None, private_chat_agent_id=None) -> list[str] and ECOMMERCE_GROUP_ROLES.

- [ ] **Step 1: Write failing tests**

~~~python
def test_ecommerce_group_excludes_av_hr_and_finance() -> None:
    members = _members_for_mode("group", skill_id="ecommerce_detail_image")
    assert members == ["ceo_assistant", "agent_1", "agent_2", "agent_3"]
~~~

~~~ts
expect(ECOMMERCE_GROUP_ROLES).toEqual(['ceo_assistant', 'agent_1', 'agent_2', 'agent_3']);
~~~

- [ ] **Step 2: Run it to verify failure**

Run: ..\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_conversation_members.py::test_ecommerce_group_excludes_av_hr_and_finance -v

Expected: FAIL because _members_for_mode does not accept skill_id.

- [ ] **Step 3: Implement minimal rule**

~~~python
_ECOMMERCE_GROUP_ROLES = ("ceo_assistant", "agent_1", "agent_2", "agent_3")

def _members_for_mode(mode: str, *, skill_id: str | None = None,
                      private_chat_agent_id: str | None = None) -> list[str]:
    if mode == "group" and skill_id == "ecommerce_detail_image":
        return list(_ECOMMERCE_GROUP_ROLES)
    if mode == "group":
        return list(_GROUP_ROLES)
    # preserve main_session and private_chat branches
~~~

Pass skill_id=conv.skill_id in list_members. Backend members remain authoritative; frontend uses the same four-role set only while API members have not loaded.

- [ ] **Step 4: Verify and commit**

Run: ..\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_conversation_members.py -v; pnpm --dir frontend test -- agents.test.ts

~~~powershell
git add backend/app/api/conversations.py backend/tests/unit/test_conversation_members.py frontend/lib/agents.ts frontend/lib/agents.test.ts frontend/components/chat/GroupMembers.tsx frontend/components/chat/MentionPopover.tsx
git commit -m "feat: scope ecommerce specialist group"
~~~

### Task 2: 将图片确认为派发前硬闸门

**Files:**
- Modify: agents/agents/orchestrator_agent/langgraph_runner/compiler_step_node.py:45-205,429-466
- Modify: agents/agents/orchestrator_agent/langgraph_runner/runner.py:588-692
- Create: agents/tests/unit/orchestrator_agent/test_compiler_step_node.py

**Interfaces:** Consumes hitl_gate with type image_generation_confirmation and phase before_dispatch. Produces preview metadata image_count, model, estimated_cost_cny_per_image, and requires_exact_count_confirmation.

- [ ] **Step 1: Write failing pre-dispatch test**

~~~python
async def test_image_confirmation_interrupts_before_dispatch(monkeypatch) -> None:
    dispatched: list[AgentTask] = []
    node = make_step_node(
        {"step_id": "segment_images", "agent": "agent_3", "task_type": "batch_generate",
         "parameters": {"count": 3, "confirmation": {"model": "doubao-seedream-4-0-250828"}},
         "hitl_gate": {"type": "image_generation_confirmation", "phase": "before_dispatch"}},
        dispatcher=lambda task: dispatched.append(task), result_waiter=AsyncMock(),
    )
    with pytest.raises(GraphInterrupt):
        await node(state_for("segment_images"))
    assert dispatched == []
~~~

- [ ] **Step 2: Run it to verify failure**

Run: ..\.venv\Scripts\python.exe -m pytest agents/tests/unit/orchestrator_agent/test_compiler_step_node.py::test_image_confirmation_interrupts_before_dispatch -v

Expected: FAIL because dispatch currently happens before interrupt().

- [ ] **Step 3: Implement pre-dispatch interrupt and exact count validation**

Insert after parameter rendering and before AgentTask construction:

~~~python
if has_gate and gate_cfg.get("phase") == "before_dispatch":
    confirmation = dict(parameters_tpl.get("confirmation") or {})
    expected_count = int(parameters_tpl.get("count") or len(parameters_tpl.get("image_specs") or []))
    decision = interrupt({
        "kind": "hitl_gate", "step_id": sid,
        "gate_type": gate_cfg.get("type", "image_generation_confirmation"),
        "task_id": state["task_id"], "agent_id": agent_id,
        "preview_artifact_metadata": {**confirmation, "image_count": expected_count,
                                      "requires_exact_count_confirmation": True},
    })
    chosen_count = (decision.get("user_choice") or {}).get("confirmed_image_count")
    if decision.get("resolution") != "approved" or chosen_count != expected_count:
        return {"final_status": "failed", "failure_reason": "image_generation_not_confirmed"}
~~~

HAOLE_AUTO_APPROVE_HITL must never apply to this gate. Emit preview metadata from _open_hitl_for_interrupt even with no artifact reference.

- [ ] **Step 4: Add approved/cancel/mismatched-count tests**

~~~python
async def test_approved_image_confirmation_dispatches_once() -> None:
    decision = {"resolution": "approved", "user_choice": {"confirmed_image_count": 3}}
    # monkeypatch interrupt to return decision
    await node(state_for("segment_images"))
    assert len(dispatched) == 1
    assert dispatched[0].parameters["count"] == 3
~~~

- [ ] **Step 5: Verify and commit**

Run: ..\.venv\Scripts\python.exe -m pytest agents/tests/unit/orchestrator_agent/test_compiler_step_node.py -v

~~~powershell
git add agents/agents/orchestrator_agent/langgraph_runner/compiler_step_node.py agents/agents/orchestrator_agent/langgraph_runner/runner.py agents/tests/unit/orchestrator_agent/test_compiler_step_node.py
git commit -m "feat: require image approval before dispatch"
~~~

### Task 3: 固化唯一的确认优先 playbook

**Files:**
- Modify: backend/skills/playbooks/ecommerce_detail_image.yaml
- Delete: agents/skills/playbooks/ecommerce_detail_image.yaml
- Modify: backend/tests/unit/test_skill_loader.py and backend/tests/integration/test_short_video_e2e.py

**Interfaces:** segment_images exposes count: 5 and routing hints provider: ark_seedream, no_retry: true, no_fallback: true.

- [ ] **Step 1: Write failing assertion**

~~~python
def test_ecommerce_image_step_requires_exact_pre_dispatch_confirmation() -> None:
    step = {s["step_id"]: s for s in load_skill_by_id("ecommerce_detail_image")["workflow"]}["segment_images"]
    assert step["hitl_gate"]["phase"] == "before_dispatch"
    assert step["hitl_gate"]["type"] == "image_generation_confirmation"
    assert step["parameters"]["count"] == 5
    assert step["routing_hints"]["provider"] == "ark_seedream"
    assert step["routing_hints"]["no_retry"] is True
    assert step["routing_hints"]["no_fallback"] is True
~~~

- [ ] **Step 2: Run it to verify failure**

Run: ..\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_skill_loader.py::test_ecommerce_image_step_requires_exact_pre_dispatch_confirmation -v

Expected: FAIL because the existing gate is post-generation and uses generic fallback.

- [ ] **Step 3: Replace stale segment and quality path**

~~~yaml
parameters:
  count: 5
  confirmation:
    model: doubao-seedream-4-0-250828
    provider: 火山方舟
    estimated_cost_cny_per_image: 0.20
routing_hints:
  provider: ark_seedream
  model: doubao-seedream-4-0-250828
  no_retry: true
  no_fallback: true
hitl_gate:
  type: image_generation_confirmation
  phase: before_dispatch
  actions: [approve, cancel]
~~~

Retain style_analysis, copy_writing, segment_images, long_concat. Remove automatic segment retry, unregistered image_quality_react, and automatic regeneration. Use DeepSeek for copy with no_fallback true. Prove backend/skills/playbooks is canonical, then delete the duplicate agents playbook.

- [ ] **Step 4: Verify and commit**

Run: ..\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_skill_loader.py backend/tests/integration/test_short_video_e2e.py -v

~~~powershell
git add backend/skills/playbooks/ecommerce_detail_image.yaml backend/tests/unit/test_skill_loader.py backend/tests/integration/test_short_video_e2e.py
git rm agents/skills/playbooks/ecommerce_detail_image.yaml
git commit -m "feat: make ecommerce playbook confirmation-first"
~~~

### Task 4: 接入一次性火山方舟 Seedream 请求

**Files:**
- Create: agents/agents/image_agent/handlers/ark_seedream.py
- Modify: agents/agents/image_agent/handlers/batch_generate.py:39-213
- Create: agents/tests/unit/image_agent/test_ark_seedream.py
- Modify: agents/tests/unit/image_agent/test_batch_generate.py

**Interfaces:** generate_seedream_image(prompt: str, size: str, reference_images: list[str] | None = None) -> SeedreamImageResult. The adapter POSTs once to https://ark.cn-beijing.volces.com/api/v3/images/generations and never retries or falls back.

- [ ] **Step 1: Write failing provider tests**

~~~python
async def test_seedream_posts_one_native_generation_request(respx_mock) -> None:
    route = respx_mock.post("https://ark.cn-beijing.volces.com/api/v3/images/generations").mock(
        return_value=httpx.Response(200, json={"model": "doubao-seedream-4-0-250828", "data": [{"url": "https://img.example/a.jpg"}]})
    )
    result = await generate_seedream_image(prompt="保温杯", size="2K")
    assert result.url == "https://img.example/a.jpg"
    assert route.call_count == 1

async def test_seedream_without_key_fails_before_network(monkeypatch) -> None:
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    with pytest.raises(ArkSeedreamConfigurationError):
        await generate_seedream_image(prompt="保温杯", size="2K")
~~~

- [ ] **Step 2: Run it to verify failure**

Run: ..\.venv\Scripts\python.exe -m pytest agents/tests/unit/image_agent/test_ark_seedream.py -v

Expected: FAIL because no native provider adapter exists.

- [ ] **Step 3: Implement one-shot adapter**

~~~python
async def generate_seedream_image(*, prompt: str, size: str,
                                  reference_images: list[str] | None = None) -> SeedreamImageResult:
    api_key = os.getenv("ARK_API_KEY", "").strip()
    if not api_key:
        raise ArkSeedreamConfigurationError("ARK_API_KEY is required for ecommerce live images")
    payload = {
        "model": os.getenv("ECOMMERCE_SEEDREAM_MODEL", "doubao-seedream-4-0-250828"),
        "prompt": prompt, "size": size, "response_format": "url",
        "sequential_image_generation": "disabled", "stream": False, "watermark": True,
    }
    if reference_images:
        payload["image"] = reference_images
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0)) as client:
        response = await client.post(ARK_IMAGE_GENERATIONS_URL, json=payload,
                                     headers={"Authorization": f"Bearer {api_key}"})
        response.raise_for_status()
    return SeedreamImageResult.from_response(response.json())
~~~

For provider == ark_seedream, batch_generate_handler invokes this adapter exactly once per requested image spec and normalizes its returned URL. On exception return AgentResult(status=failed, error_detail={reason: ark_seedream_failed}); do not call llm.complete and do not send replacement work.

- [ ] **Step 4: Add exact-count batch test**

~~~python
async def test_ecommerce_batch_uses_seedream_once_per_confirmed_image(monkeypatch) -> None:
    calls = AsyncMock(side_effect=[seedream_result("a"), seedream_result("b")])
    monkeypatch.setattr(ark_seedream, "generate_seedream_image", calls)
    result = await batch_generate_handler(ecommerce_task(count=2))
    assert result.status == "completed"
    assert calls.await_count == 2
~~~

- [ ] **Step 5: Verify and commit**

Run: ..\.venv\Scripts\python.exe -m pytest agents/tests/unit/image_agent/test_ark_seedream.py agents/tests/unit/image_agent/test_batch_generate.py -v

~~~powershell
git add agents/agents/image_agent/handlers/ark_seedream.py agents/agents/image_agent/handlers/batch_generate.py agents/tests/unit/image_agent/test_ark_seedream.py agents/tests/unit/image_agent/test_batch_generate.py
git commit -m "feat: add confirmed Ark Seedream ecommerce images"
~~~

### Task 5: 让 Agent 2 直接运行 Pillow 长图拼接

**Files:**
- Modify: agents/mcp_servers/image_tools/server.py:22-119
- Modify: agents/agents/document_agent/handlers/image_concat_long.py:12-48
- Modify: agents/agents/document_agent/main.py:7-17
- Create: agents/tests/unit/document_agent/test_image_concat_long.py

**Interfaces:** concat_long_local(images: list[str], direction: str = vertical) -> str. Agent 2 handler registry contains image_concat_long.

- [ ] **Step 1: Write failing registration and input tests**

~~~python
def test_document_agent_registers_long_image_concat() -> None:
    assert _build_handlers()["image_concat_long"] is image_concat_long_handler

async def test_concat_reads_upstream_image_refs(monkeypatch) -> None:
    monkeypatch.setattr(handler_module, "concat_long_local", AsyncMock(return_value="oss://haole-dev/long.png"))
    result = await image_concat_long_handler(task_with_images(["oss://a.png", "oss://b.png"]))
    assert result.output.reference == "oss://haole-dev/long.png"
~~~

- [ ] **Step 2: Run it to verify failure**

Run: ..\.venv\Scripts\python.exe -m pytest agents/tests/unit/document_agent/test_image_concat_long.py -v

Expected: FAIL because Agent 2 has no handler registration and uses external MCP.

- [ ] **Step 3: Extract and call direct local function**

~~~python
async def concat_long_local(images: list[str], direction: str = "vertical") -> str:
    result = await concat_long({"images": images, "direction": direction})
    if result.get("error") or result.get("_mock"):
        raise RuntimeError(result.get("error", "image concat failed"))
    return str(result["oss_ref"])
~~~

Refactor the existing Pillow/OSS logic behind this function, make Agent 2 accept a list, {image_refs: [...]}, or upstream metadata image_refs, and return explicit failed AgentResult on error. Register only this handler in a _build_handlers function.

- [ ] **Step 4: Verify and commit**

Run: ..\.venv\Scripts\python.exe -m pytest agents/tests/unit/document_agent/test_image_concat_long.py -v

~~~powershell
git add agents/mcp_servers/image_tools/server.py agents/agents/document_agent/main.py agents/agents/document_agent/handlers/image_concat_long.py agents/tests/unit/document_agent/test_image_concat_long.py
git commit -m "fix: run ecommerce long-image concat in document worker"
~~~

### Task 6: 在现有群聊中显示精确数量确认

**Files:**
- Modify: frontend/components/chat/PendingInteractions.tsx
- Create: frontend/components/chat/PendingInteractions.test.tsx
- Modify: frontend/stores/hitl.ts only if metadata type is narrower than Record<string, unknown>.

**Interfaces:** Consumes hitl_gate_opened with gate_type image_generation_confirmation and preview metadata. Produces approval payload {user_choice:{confirmed_image_count:number}}.

- [ ] **Step 1: Write failing component test**

~~~tsx
render(<PendingGate gate={imageGate({ image_count: 5, model: 'doubao-seedream-4-0-250828', estimated_cost_cny_per_image: 0.2 })} />)
expect(screen.getByText('确认生成 5 张图片')).toBeInTheDocument()
await user.click(screen.getByRole('button', { name: '确认并生成 5 张' }))
expect(api).toHaveBeenCalledWith(expect.objectContaining({ user_choice: { confirmed_image_count: 5 } }))
~~~

- [ ] **Step 2: Run it to verify failure**

Run: pnpm --dir frontend test -- PendingInteractions.test.tsx

Expected: FAIL because generic gates do not display/post exact count.

- [ ] **Step 3: Add narrow card branch**

~~~tsx
const isImageConfirmation = gate.gate_type === 'image_generation_confirmation';
const count = Number(gate.preview_artifact?.metadata?.image_count ?? 0);
const approvePayload = isImageConfirmation
  ? { user_choice: { confirmed_image_count: count } }
  : { user_choice: {} };
~~~

Render provider/model/per-image estimate and total for this gate. Its only actions are 确认并生成 {count} 张 and 取消本次生成; preserve generic approval/cancel UI for other gates.

- [ ] **Step 4: Verify and commit**

Run: pnpm --dir frontend test -- PendingInteractions.test.tsx; pnpm --dir frontend lint; pnpm --dir frontend typecheck

~~~powershell
git add frontend/components/chat/PendingInteractions.tsx frontend/components/chat/PendingInteractions.test.tsx frontend/stores/hitl.ts
git commit -m "feat: show exact image confirmation in group chat"
~~~

### Task 7: 配置、端到端验证与交付

**Files:**
- Create: deploy/production/.env.ecommerce.example
- Modify: deploy/production/README.md and README.md
- Modify: frontend/e2e/ecommerce-detail-image.spec.ts
- Modify: backend/scripts/smoke-prod.py only to require RUN_LIVE_ECOMMERCE_SMOKE=true before paid live image requests.

**Interfaces:** Consumes ARK_API_KEY, ECOMMERCE_SEEDREAM_MODEL, DEEPSEEK_API_KEY, RUN_LIVE_ECOMMERCE_SMOKE. Produces explicit zero-cost mock core versus owner-enabled live ecommerce profile.

- [ ] **Step 1: Write failing browser assertion**

~~~ts
await expect(page.getByText('确认生成 5 张图片')).toBeVisible();
await expect(page.getByRole('button', { name: '确认并生成 5 张' })).toBeVisible();
~~~

- [ ] **Step 2: Run it to verify failure**

Run: pnpm --dir frontend exec playwright test e2e/ecommerce-detail-image.spec.ts --project=chromium

Expected: FAIL until the server emits pre-dispatch confirmation.

- [ ] **Step 3: Add non-secret live profile**

~~~dotenv
LITELLM_MOCK=false
DEEPSEEK_API_KEY=
ARK_API_KEY=
ECOMMERCE_SEEDREAM_MODEL=doubao-seedream-4-0-250828
RUN_LIVE_ECOMMERCE_SMOKE=false
~~~

Document that scripts/core.ps1 start is a zero-cost mock demo, no image API call occurs until exact-count approval, and live smoke is opt-in because it spends owner credits.

- [ ] **Step 4: Run complete offline verification**

~~~powershell
..\.venv\Scripts\python.exe -m pytest backend/tests/unit backend/tests/integration -q
..\.venv\Scripts\python.exe -m pytest agents/tests/unit -q
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm --dir frontend build
~~~

Expected: all offline checks PASS.

- [ ] **Step 5: Start and smoke-test local core**

Run: .\scripts\core.ps1 start; open http://127.0.0.1:3000/; enter an ecommerce group and verify four members plus confirmation card. Do not click paid live generation without the owner's credentials.

- [ ] **Step 6: Commit and push after review**

~~~powershell
git add deploy/production/.env.ecommerce.example deploy/production/README.md README.md frontend/e2e/ecommerce-detail-image.spec.ts backend/scripts/smoke-prod.py
git commit -m "docs: document confirmed domestic ecommerce delivery"
git push origin main
~~~

## Self-Review

- Task 1 implements confirmed group roles.
- Task 2 implements the mandatory pre-call confirmation invariant.
- Task 3 removes duplicate/stub/automatic-retry workflow behavior.
- Task 4 supplies the one-shot Chinese image provider.
- Task 5 supplies real Agent 2 long-image delivery without a sidecar.
- Task 6 exposes confirmation in the existing group UI.
- Task 7 documents cost boundaries and verifies offline/local behavior.

