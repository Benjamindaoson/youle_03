# Third-Party Notices

审计日期：2026-07-21。

## 项目许可证状态

在本次整合锁定的四个来源提交中，仓库根目录均未发现 `LICENSE`、`COPYING` 或 `NOTICE`：

- `Benjamindaoson/youle_03@14815ee`
- `Benjamindaoson/youle01@d5f84ab`
- `Benjamindaoson/oye-mas@6ff181a`
- `Benjamindaoson/youle-agno@43f86e2`

本文件不替仓库所有者授予 `youle-mas` 整体许可证，也不应被解释为四个来源仓库的许可声明。项目所有者需要另行确认并添加根许可证。

### Benjamindaoson/youle_03

- 来源：https://github.com/Benjamindaoson/youle_03/tree/14815ee
- 许可证：来源提交未提供项目级许可证。
- 使用位置：本项目 Git 主干，以及 `backend/`、`agents/`、`test/`、基础设施和工程脚本的原始基线。
- 是否修改：是。
- 修改范围：修复基线缺陷；扩展事件、OTP、Skill、API、迁移、测试与 CI。旧 migration 保持追加式历史，未改为第二套架构。

### Benjamindaoson/youle01

- 来源：https://github.com/Benjamindaoson/youle01/tree/d5f84ab
- 许可证：来源提交未提供项目级许可证。
- 使用位置：`frontend/app/website/` 的产品页面方向，以及根前端中的群聊、员工私聊和团队化展示细节。
- 是否修改：是。
- 修改范围：只迁移非重复的 UI/产品表达，重写数据接入和文案；没有复制其后端、conductor、重复 store 或 SQLite 路径。

### Benjamindaoson/oye-mas

- 来源：https://github.com/Benjamindaoson/oye-mas/tree/6ff181a
- 许可证：来源提交未提供项目级许可证。
- 使用位置：根 `frontend/` 的 Next.js 应用基线、群内多 Agent 交互、Skill 市场和浏览器测试场景。
- 是否修改：是。
- 修改范围：迁移后改为真实 API 默认、显式 mock、统一消息状态、SSE/UserEvent、Skill 生命周期和 OpenAPI 类型；没有迁移其旧后端/Agent 副本。

### Benjamindaoson/youle-agno

- 来源：https://github.com/Benjamindaoson/youle-agno/tree/43f86e2
- 许可证：来源提交未提供项目级许可证。
- 使用位置：`backend/app/services/event_bus.py`、SSE/事件测试和 OTP 增量行为的设计参考。
- 是否修改：是，按 `youle_03` 模型与任务边界重新实现。
- 修改范围：采用每用户队列、Redis 分发、本地 fallback、heartbeat/replay 和一次性 OTP 的经过测试思路；没有复制 Agno Team、第二套鉴权、第二套模型或 `src/backend`。

## hermes-agent

- 项目：`NousResearch/hermes-agent`
- 来源：https://github.com/NousResearch/hermes-agent
- 许可证：MIT
- Copyright：© 2025 Nous Research
- 使用位置：`backend/app/utils/` 中带 Hermes 文件头的工具、`agents/agents/_common/think_scrubber.py`、`backend/skills/md_skills/hermes/`
- 修改：适配本项目类型、日志、配置和安全边界；Skill 卡片经筛选并用于 Planner/Critic/Persona 知识引用。

所有派生源文件继续保留原始来源文件头。Hermes Skill 卡片还标注了它们自身引用的上游项目，见下文。

## obra/superpowers

- 项目：`obra/superpowers`
- 来源：https://github.com/obra/superpowers
- 许可证：MIT
- Copyright：© 2025 Jesse Vincent
- 使用位置：经 hermes-agent 改编的 `SKILL_writing-plans.md`、`SKILL_systematic-debugging.md`、`SKILL_test-driven-development.md`、`SKILL_subagent-driven-development.md`、`SKILL_requesting-code-review.md`
- 修改：由 hermes-agent 改写为其工程工作流，本仓库保留上游说明并作为知识卡片使用。

## gsd-build/get-shit-done

- 项目：`gsd-build/get-shit-done`
- 来源：https://github.com/gsd-build/get-shit-done
- 许可证：MIT
- Copyright：© 2025 Lex Christopherson
- 使用位置：经 hermes-agent 改编的 `SKILL_spike.md`，以及 `SKILL_subagent-driven-development.md` 中明确标注的参考段落
- 修改：由 hermes-agent 改写，本仓库保留嵌入的来源说明。

## MIT License Text

The following license terms apply to the MIT-licensed third-party components identified above. The applicable copyright holder is the holder listed in that component's section.

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Contributor instruction

不得删除上述文件中的 attribution、license、copyright、author 或来源字段。新增第三方代码时，请在本文件补充项目、链接、许可证、使用位置和修改范围。
