"""MD Skill 加载器 — Anthropic / Kimi 兼容(ADR-022)。

# 角色
解析单个 SKILL.md 文件,产 `MDSkill` 对象。**渐进式加载**:
  - name + description + when_to_use:常驻(轻量,< 1KB / skill)
  - body:按需加载(可能几 KB)
  - scripts:文件路径,真正调用时再读

# 与 Skill Playbook(YAML)的关系
- MD Skill = **知识包**:Planner 把它注入 prompt,告诉下游 worker 该怎么做
- YAML Playbook = **可执行工作流**:compiler 直接编译成 LangGraph
- 两者在 SkillRegistry 下统一索引,但**用法完全不同**(见 ADR-022)。

# 兼容性
直接读 Anthropic Claude Code / Kimi K2 的 SKILL.md 格式,不需要任何转换:

```yaml
---
name: xhs-note-creator
description: "小红书笔记的写作风格、合规红线、爆款句式与排版规范。
              当用户要写小红书 / 种草文 / 探店文时使用。"
---

# 小红书笔记规范
## 风格
...
```

可选扩展字段(我们的私有约定,不破坏 Anthropic 兼容):
  - `when_to_use`:触发条件的更结构化描述(单独一行,便于 Planner 路由)
  - `required_tools`:list of MCP URIs,声明本 skill 需要的工具白名单
  - `scripts`:list of relative paths,可调脚本(S3 接 sandbox 后真正可执行)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import yaml

log = structlog.get_logger(__name__)

#: SKILL.md 大小硬上限 — 防止误读巨文件吃内存
SKILL_MD_MAX_BYTES = int(os.getenv("SKILL_MD_MAX_BYTES", str(256 * 1024)))


class SkillLoadError(ValueError):
    """SKILL.md 解析失败。"""


@dataclass
class MDSkill:
    """单个 MD Skill 的内存表示。

    设计:**name + description + when_to_use 永远加载**(轻量索引面);
    body 通过 `load_body()` 按需读盘 — Anthropic 的 progressive disclosure 模式。
    """

    skill_id: str
    name: str
    description: str
    source_path: Path

    when_to_use: str = ""
    required_tools: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    raw_frontmatter: dict[str, Any] = field(default_factory=dict)

    #: body 缓存(load_body 第一次调用后填),size 受 SKILL_MD_MAX_BYTES 控
    _body_cache: str | None = None

    # ─── 渐进式加载 ───
    def load_body(self) -> str:
        """读取并缓存 body。多次调用零开销。"""
        if self._body_cache is not None:
            return self._body_cache
        try:
            raw = self.source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            log.warning("skill.body_read_fail", skill=self.skill_id, err=str(e)[:200])
            self._body_cache = ""
            return ""
        # 剥 frontmatter
        body = _strip_frontmatter(raw)
        # 硬截断
        if len(body.encode("utf-8")) > SKILL_MD_MAX_BYTES:
            log.warning(
                "skill.body_truncated",
                skill=self.skill_id,
                size_bytes=len(body.encode("utf-8")),
                cap=SKILL_MD_MAX_BYTES,
            )
            body = body[:SKILL_MD_MAX_BYTES]
        self._body_cache = body
        return body

    def summary_block(self) -> str:
        """给 Planner index 用的一行摘要 — name + description(截断)。"""
        desc = (self.description or "").strip().replace("\n", " ")[:200]
        return f"- {self.skill_id} ({self.name}): {desc}"

    def to_planner_dict(self) -> dict[str, Any]:
        """给 episode_retrieval.summarize_available_skills() 兼容的形态。"""
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "when_to_use": self.when_to_use,
            "required_tools": list(self.required_tools),
            "kind": "md_skill",
        }


# ─────────────────────────────────────────────────────────────────
# 解析
# ─────────────────────────────────────────────────────────────────
_FRONTMATTER_DELIM = "---"


def parse_md_skill(path: Path) -> MDSkill:
    """从单个 .md 文件构造 MDSkill。

    Raises:
        SkillLoadError:文件不存在 / 无 frontmatter / frontmatter 必填字段缺失
    """
    if not path.exists() or not path.is_file():
        raise SkillLoadError(f"SKILL.md not found: {path}")

    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise SkillLoadError(f"unable to read {path}: {e}") from e

    fm, _body = _split_frontmatter(raw)
    if fm is None:
        raise SkillLoadError(f"no YAML frontmatter found in {path}")

    try:
        meta = yaml.safe_load(fm) or {}
    except yaml.YAMLError as e:
        raise SkillLoadError(f"invalid frontmatter YAML in {path}: {e}") from e

    if not isinstance(meta, dict):
        raise SkillLoadError(f"frontmatter must be a YAML mapping, got {type(meta).__name__}")

    name = str(meta.get("name") or "").strip()
    description = str(meta.get("description") or "").strip()
    if not name:
        raise SkillLoadError(f"frontmatter.name is required in {path}")
    if not description:
        # 不强制 — Anthropic 的某些 skills 描述放在 body 里;但我们要求至少一行
        log.warning("skill.no_description", path=str(path))

    skill_id = _derive_skill_id(path, name)

    return MDSkill(
        skill_id=skill_id,
        name=name,
        description=description,
        source_path=path,
        when_to_use=str(meta.get("when_to_use") or "").strip(),
        required_tools=_normalize_str_list(meta.get("required_tools")),
        scripts=_normalize_str_list(meta.get("scripts")),
        raw_frontmatter=dict(meta),
    )


def parse_md_skill_from_text(*, text: str, source_path: Path | None = None) -> MDSkill:
    """从内存中的字符串解析(测试用)。"""
    fm, _body = _split_frontmatter(text)
    if fm is None:
        raise SkillLoadError("no YAML frontmatter")
    try:
        meta = yaml.safe_load(fm) or {}
    except yaml.YAMLError as e:
        raise SkillLoadError(f"invalid frontmatter YAML: {e}") from e
    if not isinstance(meta, dict):
        raise SkillLoadError("frontmatter must be a mapping")
    name = str(meta.get("name") or "").strip()
    desc = str(meta.get("description") or "").strip()
    if not name:
        raise SkillLoadError("frontmatter.name is required")
    sp = source_path or Path("<memory>")
    return MDSkill(
        skill_id=_derive_skill_id(sp, name),
        name=name,
        description=desc,
        source_path=sp,
        when_to_use=str(meta.get("when_to_use") or "").strip(),
        required_tools=_normalize_str_list(meta.get("required_tools")),
        scripts=_normalize_str_list(meta.get("scripts")),
        raw_frontmatter=dict(meta),
    )


# ─────────────────────────────────────────────────────────────────
# 内部工具
# ─────────────────────────────────────────────────────────────────
def _split_frontmatter(text: str) -> tuple[str | None, str]:
    """切分 frontmatter 与 body。

    返回 (frontmatter_text, body_text)。无 frontmatter 时第一项为 None。
    """
    s = text.lstrip("﻿")  # BOM
    if not s.startswith(_FRONTMATTER_DELIM):
        return None, text
    # 找下一个 ---,跳过第一行
    rest = s[len(_FRONTMATTER_DELIM):]
    end = rest.find(f"\n{_FRONTMATTER_DELIM}")
    if end == -1:
        return None, text
    fm = rest[:end].lstrip("\n")
    body = rest[end + len(_FRONTMATTER_DELIM) + 1 :].lstrip("\n")
    return fm, body


def _strip_frontmatter(text: str) -> str:
    """只要 body — 给 load_body() 用。"""
    _, body = _split_frontmatter(text)
    return body


def _derive_skill_id(path: Path, name: str) -> str:
    """skill_id 优先用 frontmatter.name,异常情况用 filename(不含扩展名,标准化)。

    标准化:转小写、空格转连字符、剥前缀 `SKILL_` / `SKILL ` / `SKILL.`。
    """
    candidate = (name or path.stem).strip()
    candidate = candidate.lower().replace(" ", "-").replace("_", "-")
    # 剥 "skill-" 前缀,避免 SKILL_xhs-note-creator.md 变成 skill-xhs-note-creator
    if candidate.startswith("skill-"):
        candidate = candidate[len("skill-") :]
    if candidate == "skill":
        # SKILL.md without name → 用文件目录名兜底
        candidate = path.parent.name.lower() or "unnamed"
    return candidate or path.stem.lower()


def _normalize_str_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return []
