"""qdrant_client + episode_retrieval 联合测试(ADR-011 / ADR-019 C 阶段)。

LITELLM_MOCK=true → embed_text 返回 None → search_episodes 直接返回 []。
所有 Qdrant 网络调用通过 monkeypatch 替换,**不连任何外部服务**。
"""

from __future__ import annotations


from agents._common import qdrant_client as qc
from agents.orchestrator_agent.planner.episode_retrieval import (
    Episode,
)


# ─── qdrant_client 单元 ───
async def test_search_returns_empty_when_embed_fails(monkeypatch) -> None:
    """LITELLM_MOCK 默认 true → embed_text 返回 None → 短路返回 []。"""

    async def _fake_embed(text):
        return None

    monkeypatch.setattr(qc, "embed_text", _fake_embed)

    out = await qc.search_episodes(query_text="搜什么都行", top_k=5)
    assert out == []


async def test_search_handles_qdrant_unreachable(monkeypatch) -> None:
    """嵌入成功 + Qdrant 挂 → 不抛,返回 []。"""

    async def _fake_embed(text):
        return [0.0] * 8

    class _FakeClient:
        async def post(self, *args, **kwargs):
            raise ConnectionError("qdrant down")

    monkeypatch.setattr(qc, "embed_text", _fake_embed)
    monkeypatch.setattr(qc, "_get_client", lambda: _FakeClient())

    out = await qc.search_episodes(query_text="x", user_id="u-test", top_k=5)
    assert out == []


async def test_search_returns_empty_without_user_id(monkeypatch) -> None:
    async def _fake_embed(text):
        return [0.0] * 8

    monkeypatch.setattr(qc, "embed_text", _fake_embed)
    out = await qc.search_episodes(query_text="x", user_id=None, top_k=5)
    assert out == []


async def test_search_returns_404_collection_missing(monkeypatch) -> None:
    """collection 不存在 → 警告 + 空列表。"""

    async def _fake_embed(text):
        return [0.0] * 8

    class _Resp:
        status_code = 404

        def raise_for_status(self):  # 不应被调到
            raise AssertionError("不该被调")

        def json(self):
            return {}

    class _FakeClient:
        async def post(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr(qc, "embed_text", _fake_embed)
    monkeypatch.setattr(qc, "_get_client", lambda: _FakeClient())

    out = await qc.search_episodes(query_text="x", user_id="u-test", top_k=5)
    assert out == []


async def test_search_parses_real_qdrant_shape(monkeypatch) -> None:
    """伪造一个标准 Qdrant search 响应,验证 EpisodePayload 反序列化。"""

    async def _fake_embed(text):
        return [0.1] * 8

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "result": [
                    {
                        "id": 1,
                        "score": 0.92,
                        "payload": {
                            "task_id": "t-1",
                            "user_request": "做反诈视频",
                            "plan_summary": "research → script → video",
                            "outcome": "success",
                            "user_rating": 0.95,
                            "duration_s": 320,
                            "cost_usd": 0.045,
                        },
                    },
                    {
                        "id": 2,
                        "score": 0.81,
                        "payload": {
                            "task_id": "t-2",
                            "user_request": "做小红书笔记",
                            "plan_summary": "write → image",
                            "outcome": "success",
                        },
                    },
                ]
            }

    class _FakeClient:
        async def post(self, path, json=None, **_):
            assert "points/search" in path
            assert json["limit"] == 3
            return _Resp()

    monkeypatch.setattr(qc, "embed_text", _fake_embed)
    monkeypatch.setattr(qc, "_get_client", lambda: _FakeClient())

    out = await qc.search_episodes(query_text="x", user_id="u-1", top_k=3)
    assert len(out) == 2
    assert out[0].task_id == "t-1"
    assert out[0].outcome == "success"
    assert out[0].user_rating == 0.95
    assert out[0].score == 0.92
    # 第二条的 nullable 字段
    assert out[1].user_rating is None
    assert out[1].duration_s is None


async def test_healthcheck_unreachable_returns_false(monkeypatch) -> None:
    class _FakeClient:
        async def get(self, *args, **kwargs):
            raise ConnectionError("nope")

    monkeypatch.setattr(qc, "_get_client", lambda: _FakeClient())
    assert (await qc.healthcheck()) is False


# ─── episode_retrieval 桥接层 ───
async def test_episode_retrieval_disabled_returns_empty(monkeypatch) -> None:
    """ENABLE_EPISODE_RETRIEVAL=false(默认)→ 空列表,不调 Qdrant。"""
    monkeypatch.setenv("ENABLE_EPISODE_RETRIEVAL", "false")
    # reload 让模块级常量生效
    import importlib

    import agents.orchestrator_agent.planner.episode_retrieval as er

    importlib.reload(er)

    called = {"n": 0}

    async def _spy_search(**kwargs):
        called["n"] += 1
        return []

    monkeypatch.setattr(er, "_qdrant_search_episodes", _spy_search)

    out = await er.retrieve_similar_episodes(user_request="x", user_id="u")
    assert out == []
    assert called["n"] == 0  # 被 flag 短路,根本没调 Qdrant


async def test_episode_retrieval_enabled_calls_qdrant(monkeypatch) -> None:
    """flag on + Qdrant 返回 1 条 → Episode 列表长度 1。"""
    monkeypatch.setenv("ENABLE_EPISODE_RETRIEVAL", "true")
    import importlib

    import agents.orchestrator_agent.planner.episode_retrieval as er

    importlib.reload(er)
    EpisodeCls = er.Episode

    async def _fake_search(**kwargs):
        # qdrant_client 已经把 hit 转成 EpisodePayload
        return [
            qc.EpisodePayload(
                task_id="t-mock",
                user_request="prior request",
                plan_summary="a→b",
                outcome="success",
                user_rating=0.9,
                duration_s=100,
                cost_usd=0.01,
                score=0.8,
            )
        ]

    monkeypatch.setattr(er, "_qdrant_search_episodes", _fake_search)

    out = await er.retrieve_similar_episodes(user_request="新请求", user_id="u-1")
    assert len(out) == 1
    assert isinstance(out[0], EpisodeCls)
    assert out[0].task_id == "t-mock"
    assert out[0].outcome == "success"


async def test_episode_retrieval_skips_blank_user(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_EPISODE_RETRIEVAL", "true")
    import importlib

    import agents.orchestrator_agent.planner.episode_retrieval as er

    importlib.reload(er)

    called = {"n": 0}

    async def _spy(**kwargs):
        called["n"] += 1
        return []

    monkeypatch.setattr(er, "_qdrant_search_episodes", _spy)
    assert await er.retrieve_similar_episodes(user_request="new", user_id="  ") == []
    assert called["n"] == 0


async def test_retrieve_format_episodes_for_prompt() -> None:
    """to_prompt_block 不会因 None rating 崩。"""
    from agents.orchestrator_agent.planner.episode_retrieval import (
        format_episodes_for_prompt,
    )

    eps = [
        Episode(
            task_id="t",
            user_request="req",
            plan_summary="plan",
            outcome="success",
            user_rating=None,
            duration_s=None,
            cost_usd=None,
        )
    ]
    block = format_episodes_for_prompt(eps)
    assert "rating=N/A" in block
    assert "req" in block
