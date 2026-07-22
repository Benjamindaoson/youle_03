"""黄金任务集加载(ADR-027)。

# Golden 文件格式(YAML)
```yaml
case_id: short_video_basic
description: 短视频 happy path
tags: [video, hero]
input:
  user_request: 给我做一个城市漫游短视频
  collected_fields:
    主题: 城市漫游
    风格: 治愈向
    受众: 都市白领
    时长: 60s
expected:
  must_have_steps: [research, script, image_process, bgm, video_compose]
  must_have_artifact_types: [text, image_collection, video]
  primary_artifact_step: video_compose
  max_total_cost_usd: 10.0
  max_p95_duration_s: 600
  must_pass_critic: false              # 这条 case 不强制 critic 过
budget:
  total_cost_usd: 8.0
  total_duration_s: 480
```

字段都是可选的(case_id / input.user_request 必填),`expected.*` 给指标
打分用,`budget.*` 给硬上限用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import yaml

log = structlog.get_logger(__name__)


class SuiteLoadError(ValueError):
    """fixture 解析失败。"""


@dataclass
class EvalCase:
    """单个评测 case。"""

    case_id: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    user_request: str = ""
    collected_fields: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] = field(default_factory=dict)
    budget: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None

    @classmethod
    def from_yaml_dict(
        cls, data: dict[str, Any], *, source_path: Path | None = None
    ) -> "EvalCase":
        if not isinstance(data, dict):
            raise SuiteLoadError("eval case must be a YAML mapping")
        case_id = str(data.get("case_id") or "").strip()
        if not case_id:
            raise SuiteLoadError("eval case missing case_id")
        inp = data.get("input") or {}
        if not isinstance(inp, dict):
            raise SuiteLoadError(f"{case_id}: input must be a mapping")
        user_request = str(inp.get("user_request") or "").strip()
        if not user_request:
            raise SuiteLoadError(f"{case_id}: input.user_request is required")
        return cls(
            case_id=case_id,
            description=str(data.get("description") or "")[:500],
            tags=[str(t) for t in (data.get("tags") or [])],
            user_request=user_request,
            collected_fields=dict(inp.get("collected_fields") or {}),
            expected=dict(data.get("expected") or {}),
            budget=dict(data.get("budget") or {}),
            source_path=source_path,
        )


@dataclass
class EvalSuite:
    """一组 case。"""

    name: str
    cases: list[EvalCase] = field(default_factory=list)
    source_dir: Path | None = None

    @classmethod
    def from_directory(cls, directory: Path | str) -> "EvalSuite":
        d = Path(directory).expanduser().resolve()
        suite = cls(name=d.name, source_dir=d)
        if not d.exists() or not d.is_dir():
            log.warning("eval.suite.dir_missing", dir=str(d))
            return suite

        for p in sorted(d.iterdir()):
            if not p.is_file() or p.suffix.lower() not in {".yaml", ".yml"}:
                continue
            try:
                raw = p.read_text(encoding="utf-8")
                data = yaml.safe_load(raw)
            except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
                log.warning("eval.case.parse_fail", path=str(p), err=str(e)[:200])
                continue
            try:
                case = EvalCase.from_yaml_dict(data, source_path=p)
            except SuiteLoadError as e:
                log.warning("eval.case.invalid", path=str(p), err=str(e)[:200])
                continue
            suite.cases.append(case)

        log.info(
            "eval.suite.loaded",
            dir=str(d),
            n_cases=len(suite.cases),
        )
        return suite

    def filter_by_tag(self, tag: str) -> "EvalSuite":
        sub = EvalSuite(name=f"{self.name}:{tag}", source_dir=self.source_dir)
        sub.cases = [c for c in self.cases if tag in c.tags]
        return sub

    def by_id(self, case_id: str) -> EvalCase | None:
        for c in self.cases:
            if c.case_id == case_id:
                return c
        return None
