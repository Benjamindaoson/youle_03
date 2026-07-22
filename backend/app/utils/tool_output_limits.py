"""Configurable tool-output truncation limits.

Adapted from hermes-agent (MIT) © Nous Research — ``tools/tool_output_limits.py``.

Centralises tool-output caps so terminal / file / agent-result handlers can
read consistent thresholds.  Defaults match the upstream values; override
via env vars (no config-file dependency, unlike the upstream module which
read ``hermes_cli.config``).

Env vars:
    HAOLE_TOOL_OUTPUT_MAX_BYTES        terminal stdout/stderr cap (chars)
    HAOLE_TOOL_OUTPUT_MAX_LINES        read_file pagination + truncation cap
    HAOLE_TOOL_OUTPUT_MAX_LINE_LENGTH  per-line length cap
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_MAX_BYTES = 50_000
DEFAULT_MAX_LINES = 2_000
DEFAULT_MAX_LINE_LENGTH = 2_000


def _coerce_positive_int(value: Any, default: int) -> int:
    """Return ``value`` as a positive int, or ``default`` on any issue."""
    try:
        iv = int(value)
    except (TypeError, ValueError):
        return default
    if iv <= 0:
        return default
    return iv


def get_tool_output_limits() -> dict[str, int]:
    """Return resolved tool-output limits.

    Keys: ``max_bytes``, ``max_lines``, ``max_line_length``.  Missing or
    invalid env values fall through to the ``DEFAULT_*`` constants.  Never
    raises.
    """
    return {
        "max_bytes": _coerce_positive_int(
            os.getenv("HAOLE_TOOL_OUTPUT_MAX_BYTES"), DEFAULT_MAX_BYTES
        ),
        "max_lines": _coerce_positive_int(
            os.getenv("HAOLE_TOOL_OUTPUT_MAX_LINES"), DEFAULT_MAX_LINES
        ),
        "max_line_length": _coerce_positive_int(
            os.getenv("HAOLE_TOOL_OUTPUT_MAX_LINE_LENGTH"),
            DEFAULT_MAX_LINE_LENGTH,
        ),
    }


def get_max_bytes() -> int:
    return get_tool_output_limits()["max_bytes"]


def get_max_lines() -> int:
    return get_tool_output_limits()["max_lines"]


def get_max_line_length() -> int:
    return get_tool_output_limits()["max_line_length"]
