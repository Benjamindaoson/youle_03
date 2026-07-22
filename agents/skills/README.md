# Skills

铁律 9:Skill YAML 是契约,行为变更 = YAML 改 + version bump(v1.0 → v1.1)。

## 目录约定

| 路径 | 内容 |
|------|------|
| **`playbooks/`** | 可执行 **`*.yaml`** Playbook（LangGraph 编排） |
| **`md_skills/`** | **`*.md`** 知识包（frontmatter + 正文；文件名 `SKILL_*.md` 等） |
| 本文件 `README.md` | 不参与索引 |

根目录下的 `*.yaml` / `*.md` 仍会被 **SkillRegistry** / **load_skill_by_id** 扫描（迁移兼容），新内容请放入上表子目录。

环境变量（可选）: `SKILLS_DIR`（skills 根）、`SKILLS_PLAYBOOKS_SUBDIR`、`SKILLS_MD_SUBDIR`。

## YAML 与 MD（ADR-022）

- **Playbook YAML**：`workflow` 被编译进 LangGraph 执行。
- **MD Skill**：摘要给 Planner；若 YAML 顶层写了 `md_knowledge_refs`（如 `xhs-note-creator`），执行时把 `md_skills` 里对应 MD **正文**注入各步 LLM user 前缀。

小红书主规范：`md_skills/SKILL_xhs-note-creator.md`；`playbooks/xiaohongshu_carousel_note.yaml` 与 `playbooks/xhs_article.yaml` 已挂载该 ref。

## V1 必上(2 个 hero)

- [`playbooks/short_video.yaml`](playbooks/short_video.yaml)
- [`playbooks/ecommerce_detail_image.yaml`](playbooks/ecommerce_detail_image.yaml)

## 校验

每个 Skill YAML 必须通过 `python -m skill_validator <file>`(Sprint 4 实现)。
