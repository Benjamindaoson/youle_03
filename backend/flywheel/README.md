# 数据飞轮 4 类信号 pipeline(ADR-011)

铁律 15:任何修改 task 完成路径的 PR 必须保留 4 类信号沉淀,否则 CI 失败。

| # | 信号 | 存储 | 用途 | 子目录 |
|---|------|------|------|------|
| 1 | 工作流完整轨迹 | Qdrant + OSS | RAG 增强主编排意图理解 | `ingestion/` |
| 2 | 用户偏好向量 | Postgres pgvector(256 维)| 候选选项动态排序 | `preference_embedder/` |
| 3 | 失败 → Reflexion | Postgres prompt_improvement_candidates | 改进 prompt(人审)| `reflexion/` |
| 4 | 高满意度 → Skill 草稿 | Postgres skill_drafts | 创作者飞轮(V1.5)| `skill_drafter/` |

每个 pipeline 都从 Redis Stream `flywheel:signals` 消费,各自处理后写入对应存储。
