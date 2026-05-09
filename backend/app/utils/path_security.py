"""Shared path validation helpers.

Adapted from hermes-agent (MIT) © Nous Research — ``tools/path_security.py``.
Trimmed to just the two helpers we actually call.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def validate_within_dir(path: Path, root: Path) -> Optional[str]:
    """Ensure *path* resolves to a location within *root*.

    Returns an error message string if validation fails, or ``None`` if the
    path is safe.  Uses ``Path.resolve()`` to follow symlinks and normalise
    ``..`` components.

    Usage::

        error = validate_within_dir(user_path, allowed_root)
        if error:
            raise HTTPException(400, error)
    """
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
        resolved.relative_to(root_resolved)
    except (ValueError, OSError) as exc:
        return f"Path escapes allowed directory: {exc}"
    return None


def has_traversal_component(path_str: str) -> bool:
    """Return True if *path_str* contains ``..`` traversal components.

    Cheap pre-flight before doing full resolution against an allow-listed
    root; combine with :func:`validate_within_dir` for the authoritative check.
    """
    parts = Path(path_str).parts
    return ".." in parts
