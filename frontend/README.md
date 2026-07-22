# youle-mas frontend

Next.js 15 / React 19 正式前端。生产路径连接 FastAPI typed API，并通过 Bearer SSE 消费 canonical `UserEvent`；mock 只有在 `NEXT_PUBLIC_MOCK_MODE=true` 时启用。

```bash
pnpm install --frozen-lockfile
pnpm dev
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm test:e2e
```

后端运行在 `http://localhost:8000` 时更新 OpenAPI 类型：

```bash
pnpm gen:api
```

主要边界：

- `lib/client.ts`：JWT、结构化错误和 generated-schema API。
- `lib/sse.ts`：frame、回放游标、去重、重连和 store 更新。
- `stores/`：纯客户端展示状态；不执行 Agent 编排。
- `app/market/`：Skill 搜索、详情、安装、启用和停用。
- `e2e/`：无密钥浏览器场景；真实短视频长任务保留为显式 skip。

视觉强调色为微信绿 `#07C160`，图标使用 `lucide-react`。HITL V1 提供接受/微调/取消，不提供回滚。
