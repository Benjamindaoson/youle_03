"""Plan JSON schema(ADR-019)。

Plan 是 Planner Agent 的产出,**结构上是 Skill YAML 的子集** —
为的是 `dynamic_compiler.to_skill_yaml(plan)` 能直接喂给现有
`compiler.build_state_graph()`,复用全部下游基建(节点工厂、HITL、
failure_handling、router、finalize、checkpointer)。

设计原则:
1. **Plan 是数据,不是代码** — LLM 产 JSON,引擎执行。
2. **shape 与 Skill YAML 对齐** — 不引入新概念,downstream 零改动。
3. **可校验** — `compile_to_dag` 已经做了环/缺失 dep/重复 step_id 校验,
   plan 翻成 skill_yaml 后会被同样校验,不需要重写。
4. **可序列化** — 整个 Plan 落 `task.parameters.dynamic_plan`,
   checkpoint 含 plan = 复现可信。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 仅允许这 4 个 worker(ADR-001-rev / ADR-002 边界)
PlanAgentId = Literal["agent_1", "agent_2", "agent_3", "agent_4"]

# Persona 是 worker 之上的逻辑层(S3 升级,这里先留扩展点)
KNOWN_PERSONAS = {
    "default",
    "researcher",
    "critic",
    "art_director",
    "editor",
    "fact_checker",
    "seo_specialist",
    "compliance",
}


class PlanValidationError(ValueError):
    """Plan 静态校验错误(早 fail,避免劣质 plan 进入 runner)。"""


class HITLGateSpec(BaseModel):
    """与 Skill YAML 的 hitl_gate 同 shape。"""

    type: str = "quality_review"
    timeout_seconds: int | None = None
    actions: list[str] | None = None
    auto_approve_if_user_offline: bool | None = None


class PlanStep(BaseModel):
    """单个 step — 与 Skill YAML workflow item 同字段(子集)。"""

    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(..., min_length=1, max_length=64)
    agent: PlanAgentId
    task_type: str = Field(..., min_length=1)
    persona: str = "default"
    depends_on: list[str] = Field(default_factory=list)
    timeout: int = Field(default=120, ge=1, le=3600)

    #: Jinja2 渲染前的 prompt 模板;运行期由 compiler._make_step_node 注入
    #: collected_fields + step_results 做渲染。
    prompt_template: str = ""

    #: 静态输入(非模板字段)
    inputs: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    routing_hints: dict[str, Any] = Field(default_factory=dict)

    #: MCP tool whitelist,由 ReAct Worker 在循环里使用
    mcp_tools: list[str] = Field(default_factory=list)

    #: HITL gate(可选)
    hitl_gate: HITLGateSpec | None = None

    #: budget — Planner 给单 step 的 token 上限,react_runner 应尊重
    #: (S1 阶段先存不强制,S3 接 ReAct 时硬约束)
    budget_tokens: int | None = None

    #: 期望产物的简单 schema(描述性,不强校验)
    expected_artifact: str | None = None

    @field_validator("persona")
    @classmethod
    def _persona_known_or_default(cls, v: str) -> str:
        # 不强校验未知 persona — Planner 可能创新,但记下来便于审计
        return v or "default"


class Plan(BaseModel):
    """Planner 产出的完整执行计划。"""

    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(..., min_length=1, max_length=64)
    rationale: str = Field(default="", max_length=2000)
    steps: list[PlanStep] = Field(..., min_length=1, max_length=20)

    #: 主产物 step_id(对应 Skill YAML 的 delivery.primary_artifact)
    primary_artifact: str | None = None

    #: 失败重试策略(对应 Skill YAML 的 failure_handling 顶层)
    failure_handling: dict[str, Any] = Field(default_factory=dict)

    #: 元数据 — 便于审计和飞轮信号
    source: Literal["planner", "replanner"] = "planner"
    cognitive_model: str | None = None
    estimated_cost_usd: float | None = None
    estimated_duration_s: int | None = None

    @field_validator("steps")
    @classmethod
    def _step_ids_unique(cls, v: list[PlanStep]) -> list[PlanStep]:
        seen: set[str] = set()
        for s in v:
            if s.step_id in seen:
                raise PlanValidationError(f"duplicate step_id: {s.step_id!r}")
            seen.add(s.step_id)
        return v

    def validate_deps(self) -> None:
        """补充校验:depends_on 引用都要存在。

        compile_to_dag 之后会再做一次环检测,这里只查未声明引用 —
        早 fail 减少进入 runner 的污染。
        """
        valid = {s.step_id for s in self.steps}
        for s in self.steps:
            for d in s.depends_on:
                if d not in valid:
                    raise PlanValidationError(
                        f"step {s.step_id!r} depends on undefined step {d!r}"
                    )
        if self.primary_artifact and self.primary_artifact not in valid:
            raise PlanValidationError(
                f"primary_artifact {self.primary_artifact!r} not in steps"
            )

    def to_skill_yaml(self) -> dict[str, Any]:
        """翻译为 `compiler.build_state_graph` 能消化的 skill_yaml dict。

        这是 Plan 与 LangGraph 编排层之间的唯一桥 — shape 必须与
        `agents/skills/*.yaml` 解析后的 dict 完全一致,否则下游会出错。
        """
        workflow: list[dict[str, Any]] = []
        for s in self.steps:
            item: dict[str, Any] = {
                "step_id": s.step_id,
                "agent": s.agent,
                "task_type": s.task_type,
                "depends_on": list(s.depends_on),
                "timeout": s.timeout,
                "prompt_template": s.prompt_template,
                "inputs": dict(s.inputs),
                "parameters": dict(s.parameters),
                "routing_hints": dict(s.routing_hints),
                "mcp_tools": list(s.mcp_tools),
            }
            if s.hitl_gate is not None:
                item["hitl_gate"] = s.hitl_gate.model_dump(exclude_none=True)
            # persona / budget_tokens / expected_artifact 是 ADR-019 新增字段,
            # 现有 compiler 不读,通过 parameters 的命名空间下传,react_runner 可见
            item["parameters"].setdefault("_planner", {})
            item["parameters"]["_planner"].update(
                {
                    "persona": s.persona,
                    "budget_tokens": s.budget_tokens,
                    "expected_artifact": s.expected_artifact,
                    "plan_id": self.plan_id,
                }
            )
            workflow.append(item)

        return {
            # 合成 skill_id — 留下"这是动态 plan"的痕迹,不与现有 skills 冲突
            "skill_id": f"dynamic-{self.plan_id}",
            "version": "dynamic-1.0",
            "name": f"Dynamic Plan {self.plan_id}",
            "description": self.rationale[:500],
            "workflow": workflow,
            "delivery": (
                {"primary_artifact": self.primary_artifact}
                if self.primary_artifact
                else {}
            ),
            "failure_handling": dict(self.failure_handling),
            # 飞轮 / 审计标记
            "_dynamic": True,
            "_planner_meta": {
                "plan_id": self.plan_id,
                "source": self.source,
                "cognitive_model": self.cognitive_model,
                "rationale": self.rationale,
            },
        }
