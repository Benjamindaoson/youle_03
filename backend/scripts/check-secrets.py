#!/usr/bin/env python3
"""Reject tracked environment files and high-confidence credential patterns."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_ENV_NAMES = {".env.example", ".env.sample", ".env.template"}
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[opusr]_[A-Za-z0-9]{36,255}\b"),
    "OpenAI-style key": re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}\b"),
}
KNOWN_SYNTHETIC_VALUES = {
    "sk-ant-api03-AAAAAAAAAAAA1234567890abcdef",
    "sk-ant-api03-AAAAAAAAAAAA1234567890abcdefXYZ",
    "sk-proj-abcdef1234567890",
    "sk-proj-abcdefABCDEF1234567890XYZ",
}


def _tracked_files() -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
    )
    return [ROOT / item.decode("utf-8") for item in output.split(b"\0") if item]


def main() -> int:
    violations: list[str] = []
    for path in _tracked_files():
        name = path.name.lower()
        if name == ".env" or (name.startswith(".env.") and name not in ALLOWED_ENV_NAMES):
            violations.append(f"tracked environment file: {path.relative_to(ROOT)}")
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for label, pattern in SECRET_PATTERNS.items():
            matches = [match.group(0) for match in pattern.finditer(text)]
            if any(value not in KNOWN_SYNTHETIC_VALUES for value in matches):
                violations.append(f"{label} pattern: {path.relative_to(ROOT)}")

    if violations:
        for violation in violations:
            print(f"ERROR: {violation}")
        return 1
    print("OK: no tracked env files or high-confidence secrets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
