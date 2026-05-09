# Hermes 借用的 SKILL 卡片

来源:[hermes-agent](https://github.com/NousResearch/hermes-agent)(MIT © Nous Research)

挑选的高复用提示词卡片(均为通用的工程方法论,不绑定具体框架),供 youle_mas
的 Planner / Critic / Persona 在编排时引用。

| 文件 | 何时触发 |
|------|----------|
| `SKILL_plan.md` | 用户说"先想清楚再做"/任务拆解前 |
| `SKILL_writing-plans.md` | 写实施计划文档时 |
| `SKILL_systematic-debugging.md` | 报错复现 / Bug 定位 |
| `SKILL_test-driven-development.md` | 写测试或要求 TDD 时 |
| `SKILL_spike.md` | 不确定的探索任务,先做 spike |
| `SKILL_subagent-driven-development.md` | 需要并行子智能体时 |
| `SKILL_requesting-code-review.md` | 提交前自检 / 触发 review |

如需修改,请保留顶部的属性来源说明并同步上游(若仍需对齐)。
