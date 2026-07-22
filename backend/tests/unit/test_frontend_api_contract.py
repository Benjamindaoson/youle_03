"""Routes used by the Next.js client must exist in the FastAPI OpenAPI contract."""

from __future__ import annotations

from app.main import app

FRONTEND_ROUTES = {
    ("post", "/api/auth/sms/send"),
    ("post", "/api/auth/login"),
    ("post", "/api/auth/local-guest"),
    ("get", "/api/conversations"),
    ("post", "/api/conversations"),
    ("get", "/api/conversations/{conversation_id}/members"),
    ("get", "/api/conversations/{conversation_id}/messages"),
    ("post", "/api/conversations/{conversation_id}/messages"),
    ("get", "/api/conversations/{conversation_id}/events"),
    ("post", "/api/conversations/{conversation_id}/switch-work-mode"),
    ("post", "/api/conversations/private-chat/{agent_id}"),
    ("get", "/api/materials"),
    ("post", "/api/materials"),
    ("delete", "/api/materials/{material_id}"),
    ("get", "/api/prompts"),
    ("post", "/api/prompts"),
    ("delete", "/api/prompts/{prompt_id}"),
    ("get", "/api/skills"),
    ("get", "/api/skills/mine"),
    ("get", "/api/skills/{skill_id}"),
    ("post", "/api/skills/{skill_id}/install"),
    ("post", "/api/skills/{skill_id}/enable"),
    ("post", "/api/skills/{skill_id}/disable"),
    ("get", "/api/artifacts"),
    ("get", "/api/profile/me"),
    ("patch", "/api/profile/me"),
    ("get", "/api/profile/me/stats"),
    ("get", "/api/quota/me"),
    ("post", "/api/tasks/{task_id}/hitl_gates/{gate_id}/approve"),
    ("post", "/api/tasks/{task_id}/hitl_gates/{gate_id}/modify"),
    ("post", "/api/tasks/{task_id}/hitl_gates/{gate_id}/cancel"),
}

FRONTEND_JSON_SCHEMAS = {
    ("post", "/api/auth/login"): ("TokenResponse", "SmsLoginRequest"),
    ("post", "/api/auth/local-guest"): ("TokenResponse", None),
    ("post", "/api/conversations"): ("ConversationOut", "ConversationCreate"),
    ("post", "/api/conversations/{conversation_id}/messages"): (
        "SendMessageResponse",
        "SendMessageRequest",
    ),
    ("post", "/api/materials"): ("MaterialOut", "MaterialIn"),
    ("post", "/api/prompts"): ("PromptOut", "PromptIn"),
    ("patch", "/api/profile/me"): ("ProfileOut", "ProfilePatch"),
    ("post", "/api/tasks/{task_id}/hitl_gates/{gate_id}/approve"): (
        None,
        "ApproveBody",
    ),
    ("post", "/api/tasks/{task_id}/hitl_gates/{gate_id}/modify"): (
        None,
        "ModifyBody",
    ),
    ("post", "/api/tasks/{task_id}/hitl_gates/{gate_id}/cancel"): (
        None,
        "CancelBody",
    ),
}


def _schema_name(schema: dict[str, object]) -> str | None:
    ref = schema.get("$ref")
    return str(ref).rsplit("/", 1)[-1] if ref else None


def test_every_frontend_route_exists_with_the_expected_method() -> None:
    paths = app.openapi()["paths"]
    missing = sorted(
        (method, path)
        for method, path in FRONTEND_ROUTES
        if path not in paths or method not in paths[path]
    )

    assert missing == []


def test_frontend_mutations_keep_the_expected_json_schemas() -> None:
    paths = app.openapi()["paths"]
    mismatches: list[tuple[str, str, str, str | None, str | None]] = []
    for (method, path), (response_name, request_name) in FRONTEND_JSON_SCHEMAS.items():
        operation = paths[path][method]
        request_schema = (
            operation.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        success = next(
            value
            for code, value in operation["responses"].items()
            if str(code).startswith("2")
        )
        response_schema = (
            success.get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        actual = (_schema_name(response_schema), _schema_name(request_schema))
        expected = (response_name, request_name)
        if actual != expected:
            mismatches.append((method, path, "response/request", *actual))

    assert mismatches == []
