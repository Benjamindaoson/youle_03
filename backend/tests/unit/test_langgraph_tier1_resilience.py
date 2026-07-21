"""LangGraph Tier-1 韧性能力单测(铁律 #12 第一层兜底)。

覆盖 Tier-1 三件套:
1. 节点级 RetryPolicy — 网络/瞬态异常自动重试 3 次(指数退避)
2. LangGraph compile(cache=...) API — 需要时可在 compile 层传入 InMemoryCache(主任务 runner 未挂载模块级单例)
3. recursion_limit 显式 + GraphRecursionError 捕获 — 防止 graph 死循环静默卡死

测试方式:
- 不跑真 graph,直接断言 LangGraph 接口被正确接入
- 用 mock dispatcher / waiter 跑一个最小 step 验证 retry 行为
- 显式构造一个会 RecursionError 的图,验证 runner 兜底
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from agents.orchestrator_agent.langgraph_runner import compiler as lg_compiler
from agents.orchestrator_agent.langgraph_runner import runner as lg_runner
from agents.orchestrator_agent.langgraph_runner import runner_compiled_cache as lg_compiled_cache
from langgraph.cache.memory import InMemoryCache
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy


# ─────────────────────────────────────────────────────────────────
# 1. RetryPolicy 接入
# ─────────────────────────────────────────────────────────────────
def test_step_retry_policy_constants_are_set() -> None:
    """compiler.STEP_RETRY_POLICY 用作 add_node(retry_policy=...)。"""
    rp = lg_compiler.STEP_RETRY_POLICY
    assert isinstance(rp, RetryPolicy)
    assert rp.max_attempts == 3
    assert rp.initial_interval == 2.0
    assert rp.backoff_factor == 2.0
    assert rp.jitter is True


def test_build_state_graph_attaches_retry_policy_to_step_nodes() -> None:
    """build_state_graph() 给每个 step 节点都挂 retry_policy。"""
    skill_yaml = {
        "skill_id": "test_retry",
        "version": "1.0",
        "workflow": [
            {"step_id": "s1", "agent": "agent_1", "task_type": "web_search"},
            {
                "step_id": "s2",
                "agent": "agent_2",
                "task_type": "long_writing",
                "depends_on": ["s1"],
            },
        ],
    }

    async def _dispatcher(_):
        pass

    async def _waiter(*_a, **_k):
        return None

    builder = lg_compiler.build_state_graph(
        skill_yaml, dispatcher=_dispatcher, result_waiter=_waiter
    )
    # StateGraph.nodes 是 dict[str, StateNodeSpec]
    for sid in ("step_s1", "step_s2"):
        spec = builder.nodes[sid]
        # spec 上挂的 retry_policy 应当与 STEP_RETRY_POLICY 一致
        retry = getattr(spec, "retry_policy", None)
        assert retry is not None, f"{sid} 缺 retry_policy"
        # RetryPolicy 是 NamedTuple,本身就是 tuple — 直接断言字段
        assert isinstance(retry, RetryPolicy), f"{sid} retry_policy 类型错: {type(retry)}"
        assert retry.max_attempts == 3
        assert retry.initial_interval == 2.0


@pytest.mark.asyncio
async def test_retry_policy_actually_retries_transient_failure() -> None:
    """跑一个最小 graph 验证瞬态异常确实被 retry。

    构造一个节点:前 2 次抛 RuntimeError("network blip"),第 3 次成功。
    用 STEP_RETRY_POLICY 挂上去,期望 graph 最终 ok 并记录 3 次调用。
    """
    calls = {"n": 0}

    async def _flaky_node(state: dict[str, Any]) -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("network blip")
        return {"step_results": {"s1": {"status": "completed"}}}

    builder = StateGraph(dict)
    builder.add_node(
        "flaky",
        _flaky_node,
        retry_policy=RetryPolicy(
            max_attempts=3,
            initial_interval=0.01,
            backoff_factor=1.0,
            jitter=False,
            retry_on=(RuntimeError,),
        ),
    )
    builder.add_edge(START, "flaky")
    builder.add_edge("flaky", END)
    graph = builder.compile()
    out = await graph.ainvoke({})
    assert calls["n"] == 3
    assert out.get("step_results", {}).get("s1", {}).get("status") == "completed"


# ─────────────────────────────────────────────────────────────────
# 2. Cache backend 接入
# ─────────────────────────────────────────────────────────────────
def test_runner_exposes_compiled_graph_cache_alias() -> None:
    """runner._COMPILED_CACHE 与 runner_compiled_cache.COMPILED_GRAPH_CACHE 为同一 dict。"""
    assert lg_runner._COMPILED_CACHE is lg_compiled_cache.COMPILED_GRAPH_CACHE


def test_compile_accepts_cache_parameter_smoke() -> None:
    """smoke:StateGraph.compile(cache=...) 在当前 langgraph 版本可用。"""
    builder = StateGraph(dict)

    async def _node(state):  # noqa: ARG001
        return {}

    builder.add_node("n", _node)
    builder.add_edge(START, "n")
    builder.add_edge("n", END)
    # 同时传 checkpointer + cache 应当 ok
    graph = builder.compile(checkpointer=InMemorySaver(), cache=InMemoryCache())
    assert graph is not None


# ─────────────────────────────────────────────────────────────────
# 3. recursion_limit + GraphRecursionError
# ─────────────────────────────────────────────────────────────────
def test_recursion_limit_constant_is_50() -> None:
    """runner.GRAPH_RECURSION_LIMIT 显式设到 50,防 V1.5 嵌套撞默认 25。"""
    assert lg_runner.GRAPH_RECURSION_LIMIT == 50


@pytest.mark.asyncio
async def test_graph_recursion_error_is_raised_when_limit_hit() -> None:
    """超过 recursion_limit 时 LangGraph 抛 GraphRecursionError(对齐我们的捕获)。

    构造一个永远循环的图 (a → b → a → ...) 用低 limit,期望抛 GraphRecursionError。
    runner._run_until_pause 的捕获逻辑就是依赖这个异常类型。
    """

    async def _a(state):  # noqa: ARG001
        return {}

    async def _b(state):  # noqa: ARG001
        return {}

    builder = StateGraph(dict)
    builder.add_node("a", _a)
    builder.add_node("b", _b)
    builder.add_edge(START, "a")
    builder.add_edge("a", "b")
    builder.add_edge("b", "a")  # 形成回路
    graph = builder.compile()

    with pytest.raises(GraphRecursionError):
        await asyncio.wait_for(
            graph.ainvoke({}, config={"recursion_limit": 5}),
            timeout=5.0,
        )


def test_runner_imports_recursion_error_class() -> None:
    """runner.py 必须 import GraphRecursionError 以便 except 命中。"""
    assert hasattr(lg_runner, "GraphRecursionError")
    # 同源同 class
    from langgraph.errors import GraphRecursionError as _SourceErr

    assert lg_runner.GraphRecursionError is _SourceErr
