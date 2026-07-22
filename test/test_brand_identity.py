from __future__ import annotations

from pathlib import Path
import re
import subprocess


ASCII_RETIRED = re.compile("you" + "le", re.IGNORECASE)
CHINESE_RETIRED = "\u6709" + "\u4e86"
ROOT = Path(__file__).resolve().parents[1]


def find_retired_markers() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=False,
    )
    offenders: list[str] = []
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        path = raw_path.decode("utf-8")
        if ASCII_RETIRED.search(path) or CHINESE_RETIRED in path:
            offenders.append(path)
            continue
        try:
            content = (ROOT / path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if ASCII_RETIRED.search(content) or CHINESE_RETIRED in content:
            offenders.append(path)
    return offenders


def test_tracked_files_have_only_the_active_brand() -> None:
    assert find_retired_markers() == []
