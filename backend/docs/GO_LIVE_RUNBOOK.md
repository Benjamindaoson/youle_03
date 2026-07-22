# 「haole」V1 上线 Runbook

> Sprint 6 acceptance:**短视频 ≥ 10 次 + 电商详情图 ≥ 5 次,smoke 全绿才算达标。**
>
> 本文档是上线总指挥的操作脚本。每一步前**先确认**,出问题立刻按"回滚"路径走。

---

## 0. 预检(D-1 上午)

```bash
# 在仓库根
bash backend/scripts/preflight.sh staging
# 退出码 0 才往下走;1 = 必须修;2 = 警告评估
```

预检会检查:secrets 齐全 / 无 mock 残留 / Alembic head / 黑名单 / 单测 / Skill HITL gate / K8s manifest / Grafana。

---

## 1. 镜像构建(D-1 下午,自动)

打 tag 触发:

```bash
git tag v0.1.0 && git push origin v0.1.0
```

GitHub Actions [release.yml](../.github/workflows/release.yml) 会:
1. 构建 5 个镜像(backend / agent / mcp / frontend / celery-video)
2. push 到 GHCR
3. 自动 deploy → staging
4. 跑 smoke(短视频 3 次 + 详情 1 次)

**通过条件**:5 个镜像全绿 + staging smoke 全绿。

---

## 2. 真 API 切换验证(D-1 晚)

在 staging 上跑:

```bash
# 装好真凭证(临时 export,不要 commit)
export LITELLM_URL=https://litellm.haole.example.com
export LITELLM_MASTER_KEY=...
export TAVILY_API_KEY=...
export ALIYUN_OSS_ACCESS_KEY_ID=...
export ALIYUN_OSS_ACCESS_KEY_SECRET=...
export ALIYUN_OSS_BUCKET=haole-prod
export VOLCENGINE_TTS_APPID=...
export VOLCENGINE_TTS_TOKEN=...
export SENTRY_DSN=...

python backend/scripts/verify-real-apis.py
```

每项 ✓ 才算就绪。**有 ✗ 不能往 prod 推。**

---

## 3. Prod 部署(D-day,人工触发)

### 3.1 流量灰度准备

- [ ] 确认 DNS 可灰度切换(Aliyun DNS 或 Cloudflare Page Rule)
- [ ] 确认 Ingress 可加 `weight` 注解
- [ ] **回滚开关**:旧 prod 环境保持运行,新 prod 跑同一 ingress 但权重 0

### 3.2 数据库迁移

```bash
# 在仓库根目录,确认 prod kubeconfig 已加载
kubectl --context=prod -n haole apply -f deploy/production/k8s/jobs/db-migrate.yaml
kubectl --context=prod -n haole wait --for=condition=complete job/db-migrate --timeout=10m
kubectl --context=prod -n haole logs job/db-migrate
```

确认 `Running upgrade ... -> head` 在日志末尾。

### 3.3 触发 prod deploy

GitHub Actions `release.yml` workflow_dispatch,选 `prod`。

或手动:

```bash
cd deploy/production/k8s
sed -i 's/newTag: .*/newTag: v0.1.0/g' kustomization.yaml
kubectl --context=prod apply -k . -n haole --record
```

### 3.4 Rollout 等待

```bash
for d in backend agent-text agent-document agent-image agent-av frontend \
         heartbeat-consumer reflexion-runner ingestion-runner \
         celery-worker-video litellm-proxy; do
  kubectl --context=prod -n haole rollout status deploy/$d --timeout=10m
done
```

---

## 4. Acceptance(D-day 下午)

### 4.1 Sprint 6 必过项

```bash
BASE_URL=https://haole.example.com \
JWT_TOKEN=$(cat /tmp/prod-smoke-jwt) \
python backend/scripts/smoke-prod.py --short-video 10 --detail 5
```

判定:
- 成功率 = 100%(15/15)→ 上线达标
- 任何一次失败 → **不上线**,走 4.4 回滚

### 4.2 大盘验证

打开 Grafana:`https://grafana.example.com/d/haole-v1-slo`

肉眼检查:
- 意图理解 p95 < 1.5s ✓
- Agent 队列积压 ≈ 0 ✓
- 视频任务成功率 = 100% ✓
- DLQ 全 0 ✓
- HITL 未关闭门 ≤ 测试期产生数 ✓

### 4.3 用户路径手测(2 个真账号)

- [ ] 注册新用户 → 看到首次进入流程(总裁助理 / HR / 财务经理 依次入群)
- [ ] 主会话发"做短视频" → 自动 Auto + 走完 3 道 HITL gate + 拿到 mp4
- [ ] 短视频群里 @ 设计师 → 单独私聊设计师 → 完成一次小任务
- [ ] 切到 Plan 模式 → 不消耗任务配额(财务经理不弹超限)
- [ ] 长时间不操作 → Agent 状态变 "摸鱼中"
- [ ] DevTools 网络 → kill WS → 看到自动重连(应当 3-5 秒内连回来)

### 4.4 回滚(任何一项不过)

```bash
# 镜像 tag 回退
cd deploy/production/k8s
sed -i 's/newTag: .*/newTag: v0.0.x-LAST-GOOD/g' kustomization.yaml
kubectl --context=prod apply -k . -n haole

# DB 迁移回滚(需提前确认 alembic downgrade 路径安全)
kubectl --context=prod -n haole exec -it deploy/backend -- alembic downgrade -1
```

---

## 5. 上线后(D+1 ~ D+7)

### D+1
- [ ] Sentry 收件箱:0 critical / 0 high
- [ ] Grafana DLQ 全 0
- [ ] 短视频 24h 累计 50+ 次,成功率 ≥ 95%

### D+3
- [ ] Reflexion 候选 ≥ 5 条(说明失败信号正常沉淀)
- [ ] 偏好向量 ≥ 100 条(ingestion runner 在工作)

### D+7
- [ ] 跑离线 Skill 草稿统计:有 ≥ 3 条 user_satisfaction=5 的轨迹
- [ ] 配额超限率 < 5%(否则财务经理对话太烦人,需调档)

---

## 6. 应急联系

- **on-call**:by rotation,Sentry 告警直推
- **DB 紧急**:DBA 群组,备份恢复 RTO < 30min
- **LiteLLM 故障**:切到 mock 模式应急 → `kubectl set env deploy/backend LITELLM_MOCK=true`

---

## 7. Sprint 6 acceptance 自检清单(对齐 CLAUDE.md §4.6)

| acceptance 条目 | 状态 | 证据 |
|---|---|---|
| 真实 LiteLLM + 真 Tavily / volcengine / 阿里云 OSS 跑通 | ⬜ | `verify-real-apis.py` 输出全绿 |
| K8s manifest 部署到 staging | ⬜ | `kubectl rollout status` 全部 OK |
| Grafana 大盘上线 | ⬜ | `haole-v1-slo` dashboard 可访问 + 4 大指标有数据 |
| E2E 跑 10 次短视频 + 5 次电商详情图,全绿 | ⬜ | `smoke-prod.py` 输出 15/15 成功 |

四项全部勾完 → 正式上线公告。

