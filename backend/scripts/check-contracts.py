#!/usr/bin/env python3
"""Fail fast when the repository's architecture and transport contracts drift."""

from __future__ import annotations

import argparse
import ast
import importlib
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
AGENTS_ROOT = ROOT / "agents"
for source_root in (BACKEND_ROOT, AGENTS_ROOT):
    sys.path.insert(0, str(source_root))

PRODUCTION_ROOTS = (
    BACKEND_ROOT / "app",
    AGENTS_ROOT / "agents",
    AGENTS_ROOT / "mcp_servers",
)
AGENT_MODULES = (
    "agents.text_agent.main",
    "agents.document_agent.main",
    "agents.image_agent.main",
    "agents.av_agent.main",
    "agents.orchestrator_agent.langgraph_runner.runner",
)


class ContractError(RuntimeError):
    """One or more repository contracts are inconsistent."""


def _strip_schema_annotations(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_schema_annotations(item)
            for key, item in value.items()
            if key not in {"description", "title"}
        }
    if isinstance(value, list):
        return [_strip_schema_annotations(item) for item in value]
    return value


def _import_runtime_modules() -> list[str]:
    errors: list[str] = []
    modules = list(AGENT_MODULES)
    modules.extend(
        f"mcp_servers.{path.parent.name}.server"
        for path in sorted((AGENTS_ROOT / "mcp_servers").glob("*/server.py"))
    )
    for module_name in modules:
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - report every broken service together
            errors.append(f"cannot import {module_name}: {type(exc).__name__}: {exc}")
    return errors


def _check_agent_schema_parity() -> list[str]:
    from agents._common.protocol import AgentResult as WorkerAgentResult
    from agents._common.protocol import AgentTask as WorkerAgentTask

    from app.schemas.agent import AgentResult as BackendAgentResult
    from app.schemas.agent import AgentTask as BackendAgentTask

    errors: list[str] = []
    for name, backend_model, worker_model in (
        ("AgentTask", BackendAgentTask, WorkerAgentTask),
        ("AgentResult", BackendAgentResult, WorkerAgentResult),
    ):
        backend_schema = _strip_schema_annotations(backend_model.model_json_schema())
        worker_schema = _strip_schema_annotations(worker_model.model_json_schema())
        if backend_schema != worker_schema:
            errors.append(f"backend/Agent {name} schemas have drifted")
    return errors


def _check_skill_playbooks() -> list[str]:
    from agents.orchestrator_agent.task_compiler import DAGCompileError, compile_to_dag

    errors: list[str] = []
    seen: dict[str, Path] = {}
    playbooks = sorted((BACKEND_ROOT / "skills" / "playbooks").glob("*.y*ml"))
    if not playbooks:
        return ["no Skill YAML playbooks found"]

    for path in playbooks:
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            errors.append(f"invalid YAML {path.relative_to(ROOT)}: {exc}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"{path.relative_to(ROOT)} must contain a YAML mapping")
            continue
        skill_id = str(payload.get("skill_id") or "").strip()
        if not skill_id:
            errors.append(f"{path.relative_to(ROOT)} has no skill_id")
            continue
        if skill_id in seen:
            errors.append(
                f"duplicate skill_id {skill_id!r}: {seen[skill_id].name} and {path.name}"
            )
        seen[skill_id] = path
        if not payload.get("version"):
            errors.append(f"{path.relative_to(ROOT)} has no version")
        try:
            compile_to_dag(payload)
        except (DAGCompileError, TypeError, ValueError) as exc:
            errors.append(f"cannot compile {path.relative_to(ROOT)}: {exc}")
        for step in payload.get("workflow") or []:
            for uri in step.get("mcp_tools") or []:
                if not isinstance(uri, str) or not uri.startswith("mcp://"):
                    errors.append(f"{path.name} contains invalid MCP URI {uri!r}")
    return errors


def _python_files() -> list[Path]:
    return [
        path
        for root in PRODUCTION_ROOTS
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    ]


def _check_forbidden_code_patterns() -> list[str]:
    errors: list[str] = []
    forbidden_import_roots = {"openai", "anthropic"}
    for path in _python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append(f"cannot parse {path.relative_to(ROOT)}: {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".", 1)[0] in forbidden_import_roots:
                        errors.append(f"direct provider import in {path.relative_to(ROOT)}:{node.lineno}")
            elif isinstance(node, ast.ImportFrom):
                module_root = (node.module or "").split(".", 1)[0]
                if module_root in forbidden_import_roots:
                    errors.append(f"direct provider import in {path.relative_to(ROOT)}:{node.lineno}")
            elif isinstance(node, ast.Call):
                called = node.func
                name = called.id if isinstance(called, ast.Name) else (
                    called.attr if isinstance(called, ast.Attribute) else ""
                )
                if name in {"OpenAI", "Anthropic", "call_other_agent"}:
                    errors.append(
                        f"forbidden call {name} in {path.relative_to(ROOT)}:{node.lineno}"
                    )
                if name == "create_all":
                    errors.append(
                        f"runtime schema creation in {path.relative_to(ROOT)}:{node.lineno}; use Alembic"
                    )
    return errors


def _check_single_architecture() -> list[str]:
    errors: list[str] = []
    required = ("backend/app", "backend/alembic", "agents/agents", "agents/mcp_servers")
    for relative in required:
        if not (ROOT / relative).is_dir():
            errors.append(f"required architecture root is missing: {relative}")
    forbidden = ("src/backend", "haole/backend", "backend/src/backend", "legacy_backend")
    for relative in forbidden:
        if (ROOT / relative).exists():
            errors.append(f"duplicate backend architecture found: {relative}")
    return errors


def _check_frontend_event_contract() -> list[str]:
    """Require the frontend to consume the backend-generated event schema."""
    from app.schemas.events import EventType

    errors: list[str] = []
    generated_path = ROOT / "frontend" / "lib" / "api-types.ts"
    adapter_path = ROOT / "frontend" / "lib" / "ws-events.ts"
    if not generated_path.is_file():
        return ["generated frontend OpenAPI types are missing: frontend/lib/api-types.ts"]
    if not adapter_path.is_file():
        return ["frontend event type adapter is missing: frontend/lib/ws-events.ts"]

    generated = generated_path.read_text(encoding="utf-8")
    adapter = adapter_path.read_text(encoding="utf-8")
    for event_type in EventType:
        if f'"{event_type.value}"' not in generated:
            errors.append(
                f"frontend generated EventType is missing {event_type.value!r}"
            )
    if "UserEvent:" not in generated:
        errors.append("frontend generated OpenAPI types do not contain UserEvent")
    if "components['schemas']['EventType']" not in adapter:
        errors.append("frontend EventType does not reference generated OpenAPI components")
    if "components['schemas']['UserEvent']" not in adapter:
        errors.append("frontend UserEvent does not reference generated OpenAPI components")
    if "export type EventType = '" in adapter or 'export type EventType = "' in adapter:
        errors.append("frontend contains a handwritten EventType union")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--imports-only",
        action="store_true",
        help="only import every Agent and MCP service",
    )
    args = parser.parse_args()

    errors = _import_runtime_modules()
    if not args.imports_only:
        errors.extend(_check_agent_schema_parity())
        errors.extend(_check_skill_playbooks())
        errors.extend(_check_forbidden_code_patterns())
        errors.extend(_check_single_architecture())
        errors.extend(_check_frontend_event_contract())

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise ContractError(f"{len(errors)} contract violation(s)")

    mode = "runtime imports" if args.imports_only else "repository contracts"
    print(f"OK: {mode} verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
