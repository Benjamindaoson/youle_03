"""GET /api/conversations/{id}/members 计算逻辑单测。"""

from __future__ import annotations

from app.api.conversations import _MAIN_SESSION_ROLES, _members_for_mode


def test_main_session_has_seven_roles() -> None:
    members = _members_for_mode("main_session")
    assert len(members) == 7
    assert "ceo_assistant" in members
    assert "hr" in members
    assert "finance_manager" in members
    for i in range(1, 5):
        assert f"agent_{i}" in members


def test_group_has_five_roles_no_hr_finance() -> None:
    """铁律 18:HR / 财务经理仅主会话。"""
    members = _members_for_mode("group")
    assert len(members) == 5
    assert "hr" not in members
    assert "finance_manager" not in members
    assert "ceo_assistant" in members


def test_private_chat_has_one_role() -> None:
    assert _members_for_mode("private_chat", private_chat_agent_id="agent_3") == ["agent_3"]


def test_private_chat_default_to_ceo() -> None:
    assert _members_for_mode("private_chat") == ["ceo_assistant"]


def test_main_session_roles_constant_stable() -> None:
    """对齐 ADR-001-rev:agent_1=text, 2=document, 3=image, 4=av(显示顺序固定)。"""
    expected = (
        "ceo_assistant",
        "agent_1",
        "agent_2",
        "agent_3",
        "agent_4",
        "hr",
        "finance_manager",
    )
    assert expected == _MAIN_SESSION_ROLES
