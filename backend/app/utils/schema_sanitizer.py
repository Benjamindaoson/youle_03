"""Sanitize tool JSON schemas for broad LLM-backend compatibility.

Adapted from hermes-agent (MIT) © Nous Research — ``tools/schema_sanitizer.py``.

Some inference backends (notably llama.cpp's ``json-schema-to-grammar``
converter, OpenAI's strict Codex backend) reject schema shapes that
Anthropic / OpenRouter / most cloud providers silently accept.  This
walker fixes the known-hostile constructs in-place on a deep copy.

Failure modes addressed:
  - ``{"type": "object"}`` with no ``properties`` — rejected by
    grammar converters that can't constrain a free-form object.
  - Bare-string schema values (``"object"`` instead of a dict) from
    malformed MCP server output.
  - ``"type": ["string", "null"]`` array types — many parsers only accept
    a single string ``type``.
  - ``anyOf`` / ``oneOf`` nullable unions for optional fields (common
    Pydantic / MCP shape).  Anthropic rejects null branches at the top
    of ``input_schema``; collapse them.
  - Top-level combinators (``anyOf``, ``oneOf``, ``allOf``, ``enum``,
    ``not``) — strict Codex backend rejects these.
  - Unconstrained ``additionalProperties`` on objects with empty
    properties.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)


def sanitize_tool_schemas(tools: list[dict]) -> list[dict]:
    """Return a deep copy of *tools* with each tool's parameter schema sanitized.

    Input is OpenAI-format:
    ``[{"type": "function", "function": {"name": ..., "parameters": {...}}}]``
    """
    if not tools:
        return tools
    return [_sanitize_single_tool(tool) for tool in tools]


def _sanitize_single_tool(tool: dict) -> dict:
    out = copy.deepcopy(tool)
    fn = out.get("function") if isinstance(out, dict) else None
    if not isinstance(fn, dict):
        return out

    params = fn.get("parameters")
    if not isinstance(params, dict):
        fn["parameters"] = {"type": "object", "properties": {}}
        return out

    fn["parameters"] = _sanitize_node(params, path=fn.get("name", "<tool>"))
    top = fn["parameters"]
    if not isinstance(top, dict):
        fn["parameters"] = {"type": "object", "properties": {}}
    else:
        if top.get("type") != "object":
            top["type"] = "object"
        if "properties" not in top or not isinstance(top.get("properties"), dict):
            top["properties"] = {}
    fn["parameters"] = strip_nullable_unions(fn["parameters"], keep_nullable_hint=True)
    fn["parameters"] = _strip_top_level_combinators(
        fn["parameters"], path=fn.get("name", "<tool>"),
    )
    return out


_TOP_LEVEL_FORBIDDEN_KEYS = ("allOf", "anyOf", "oneOf", "enum", "not")


def _strip_top_level_combinators(params: dict, *, path: str = "<tool>") -> dict:
    if not isinstance(params, dict):
        return params
    out = dict(params)
    for key in _TOP_LEVEL_FORBIDDEN_KEYS:
        if key in out:
            logger.debug(
                "schema_sanitizer[%s]: stripped top-level %r combinator "
                "from tool parameters (strict-backend compat)",
                path, key,
            )
            out.pop(key, None)
    return out


def strip_nullable_unions(
    schema: Any,
    *,
    keep_nullable_hint: bool = True,
) -> Any:
    """Collapse ``anyOf`` / ``oneOf`` nullable unions to the non-null branch.

    MCP / Pydantic optional fields commonly arrive as::

        {"anyOf": [{"type": "string"}, {"type": "null"}], "default": null}

    Anthropic's tool input-schema validator rejects the null branch.  Tool
    optionality is already represented by the parent's ``required`` array,
    so we collapse to the single non-null variant.  Metadata (``title``,
    ``description``, ``default``, ``examples``) on the outer union node is
    carried over to the replacement.
    """
    if isinstance(schema, list):
        return [
            strip_nullable_unions(item, keep_nullable_hint=keep_nullable_hint)
            for item in schema
        ]
    if not isinstance(schema, dict):
        return schema

    stripped = {
        k: strip_nullable_unions(v, keep_nullable_hint=keep_nullable_hint)
        for k, v in schema.items()
    }
    for key in ("anyOf", "oneOf"):
        variants = stripped.get(key)
        if not isinstance(variants, list):
            continue
        non_null = [
            item for item in variants
            if not (isinstance(item, dict) and item.get("type") == "null")
        ]
        if len(non_null) == 1 and len(non_null) != len(variants):
            replacement = dict(non_null[0]) if isinstance(non_null[0], dict) else {}
            if keep_nullable_hint:
                replacement.setdefault("nullable", True)
            for meta_key in ("title", "description", "default", "examples"):
                if meta_key in stripped and meta_key not in replacement:
                    replacement[meta_key] = stripped[meta_key]
            return strip_nullable_unions(
                replacement, keep_nullable_hint=keep_nullable_hint,
            )
    return stripped


def _sanitize_node(node: Any, path: str) -> Any:
    if isinstance(node, str):
        if node in {"object", "string", "number", "integer", "boolean", "array", "null"}:
            logger.debug(
                "schema_sanitizer[%s]: replacing bare-string schema %r "
                "with {'type': %r}",
                path, node, node,
            )
            return {"type": node} if node != "object" else {
                "type": "object", "properties": {},
            }
        logger.debug(
            "schema_sanitizer[%s]: replacing non-schema string %r "
            "with empty object schema", path, node,
        )
        return {"type": "object", "properties": {}}

    if isinstance(node, list):
        return [_sanitize_node(item, f"{path}[{i}]") for i, item in enumerate(node)]

    if not isinstance(node, dict):
        return node

    out: dict = {}
    for key, value in node.items():
        if key == "type" and isinstance(value, list):
            non_null = [t for t in value if t != "null"]
            if len(non_null) == 1 and isinstance(non_null[0], str):
                out["type"] = non_null[0]
                if "null" in value:
                    out.setdefault("nullable", True)
                continue
            first_str = next(
                (t for t in value if isinstance(t, str) and t != "null"), None,
            )
            if first_str:
                out["type"] = first_str
                continue
            out["type"] = "object"
            continue

        if key in {"properties", "$defs", "definitions"} and isinstance(value, dict):
            out[key] = {
                sub_k: _sanitize_node(sub_v, f"{path}.{key}.{sub_k}")
                for sub_k, sub_v in value.items()
            }
        elif key in {"items", "additionalProperties"}:
            if isinstance(value, bool):
                out[key] = value
            else:
                out[key] = _sanitize_node(value, f"{path}.{key}")
        elif key in {"anyOf", "oneOf", "allOf"} and isinstance(value, list):
            out[key] = [
                _sanitize_node(item, f"{path}.{key}[{i}]")
                for i, item in enumerate(value)
            ]
        elif key in {"required", "enum", "examples"}:
            # Sibling keywords whose VALUES are not schemas — pass through.
            out[key] = (
                copy.deepcopy(value) if isinstance(value, (list, dict)) else value
            )
        else:
            out[key] = (
                _sanitize_node(value, f"{path}.{key}")
                if isinstance(value, (dict, list)) else value
            )

    if out.get("type") == "object" and not isinstance(out.get("properties"), dict):
        out["properties"] = {}

    if out.get("type") == "object" and isinstance(out.get("required"), list):
        props = out.get("properties") or {}
        valid = [r for r in out["required"] if isinstance(r, str) and r in props]
        if not valid:
            out.pop("required", None)
        elif len(valid) != len(out["required"]):
            out["required"] = valid

    return out


# =============================================================================
# Reactive strip — only when a backend rejects pattern/format keywords
# =============================================================================

_STRIP_ON_RECOVERY_KEYS = frozenset({"pattern", "format"})


def strip_pattern_and_format(tools: list[dict]) -> tuple[list[dict], int]:
    """Strip ``pattern`` and ``format`` from tool schemas.

    Reactive: invoke only after a backend rejects a schema with a
    grammar-parse error (llama.cpp can't compile most ECMAScript regex
    classes / format values).  Cloud providers accept these keywords as
    prompting hints, so we keep them in the default and only strip on demand.

    The strip operates only on siblings of ``type`` — a property literally
    named ``pattern`` (e.g. ``search_files.pattern``) is preserved because
    property names live inside the ``properties`` dict.
    """
    if not tools:
        return tools, 0

    stripped = 0

    def _walk(node: Any) -> None:
        nonlocal stripped
        if isinstance(node, dict):
            is_schema_node = (
                "type" in node or "anyOf" in node or "oneOf" in node or "allOf" in node
            )
            for key in list(node.keys()):
                if is_schema_node and key in _STRIP_ON_RECOVERY_KEYS:
                    node.pop(key, None)
                    stripped += 1
                    continue
                _walk(node[key])
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    for tool in tools:
        fn = tool.get("function") if isinstance(tool, dict) else None
        if isinstance(fn, dict):
            params = fn.get("parameters")
            if isinstance(params, dict):
                _walk(params)

    if stripped:
        logger.info(
            "schema_sanitizer: stripped %d pattern/format keyword(s) from "
            "tool schemas (grammar-parse recovery)",
            stripped,
        )
    return tools, stripped
