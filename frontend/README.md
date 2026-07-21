# Frontend (Next.js 15 + Tailwind v4 + Zustand)

## 起步

```bash
pnpm install
pnpm dev          # http://localhost:3000

# 后端 OpenAPI 启动后,生成 API 类型:
pnpm gen:api
```

## 视觉规范(ARCHITECTURE.md §6.4)

- 唯一强调色:微信绿 `#07C160`
- 讨论群浅蓝头像 + 蓝色「讨论」徽章;工作群浅绿 + 微信绿「工作」徽章
- **无 emoji** — 用 `lucide-react` 图标(铁律)

## 关键交互

- 三栏布局(左导航 / 中聊天 / 右执行流)
- HITL 审核组件 3 个:`ScriptApproval` / `ImageSelection` / `VideoFinalReview`
- 模式切换 chip(Plan / Ask / Auto)
- 群成员栏:主会话 7 角色 / 普通群 5 角色
- WS 自动重连,事件路由到 Zustand store

## V1 终审

仅 [接受][微调][取消],**无回滚按钮**(中断 C 是 V2 范围)。
