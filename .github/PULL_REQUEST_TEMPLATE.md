## 改了什么

<!-- 对应 ADR / Skill / Sprint -->

## Acceptance criteria(对齐 CLAUDE.md §4)

- [ ] 不命中代码模式黑名单(§3)
- [ ] 至少 1 个 happy case test
- [ ] `ruff check .` 通过
- [ ] `mypy app/` 通过
- [ ] 飞轮信号沉淀点保留(ADR-011)
- [ ] HITL gate 合规(若任务路径有改动,ADR-010)
- [ ] Skill YAML 行为变更已 bump version

## 怎么验证

```bash
# 命令 / 截图
```

## 配套文档更新

- [ ] CLAUDE.md / docs/ARCHITECTURE.md / docs/CONSTITUTION.md
- [ ] OpenAPI → 前端 `pnpm gen:api` 重跑(若 schemas 改了)
