# Skills

铁律 9:Skill YAML 是契约,行为变更 = YAML 改 + version bump(v1.0 → v1.1)。

## 目录约定

| 路径 | 内容 |
|------|------|
| **`playbooks/`** | 可执行 **`*.yaml`** |
| **`md_skills/`** | **`*.md`** 知识包 |

根目录平铺仍兼容；新文件请放入子目录。环境变量见 `app.services.skill_loader`（`SKILLS_PLAYBOOKS_SUBDIR` 等）。

## YAML 与 MD（ADR-022）

- **YAML**：编排执行。
- **MD**：`md_knowledge_refs` 关联 `md_skills/` 下正文；主规范示例 `md_skills/SKILL_xhs-note-creator.md`。

## V1 必上(2 个 hero)

- [`playbooks/short_video.yaml`](playbooks/short_video.yaml)
- [`playbooks/ecommerce_detail_image.yaml`](playbooks/ecommerce_detail_image.yaml)

## 校验

每个 Skill YAML 必须通过 `python -m skill_validator <file>`(Sprint 4 实现)。
