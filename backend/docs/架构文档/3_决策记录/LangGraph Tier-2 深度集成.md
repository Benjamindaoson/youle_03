# LangGraph Tier-2 深度集成 — 设计与迁移方案

> **状态**:Design / 待评审
> **作者**:Claude Code
> **关联**:PR #6 已落地 Tier-1 (RetryPolicy + Cache backend + recursion 兜底)
> **预估**:Tier-2 整体 2 sprint(~2 周),可分三个独立 PR 增量上线

---

## 1. 背景

PR #6 已经接入了 LangGraph 1.1 的 **Tier-1 韧性能力**:节点级 RetryPolicy、Cache backend、recursion_limit + GraphRecursionError 兜底。零架构风险、当天落地、立即兑现铁律 #12 第一层兜底。

但 LangGraph 还有三块"用了能砍代码 / 提质量"的能力**目前没用**,本文档把它们的设计与迁移路径写清楚,作为后续 PR 的依据:

| 能力 | 当前替代实现 | Tier-2 改造价值 |
|------|------------|----------------|
| `BaseStore` + `AsyncPostgresStore` | 手写飞轮(`youle/flywheel`) + Qdrant 集成 | 砍掉一套自研代码,获得标准 namespace 检索 + TTL + 向量索引 |
| `Runtime.context` 注入 | step 节点 closure 捕获 `dispatcher` / `result_waiter` | 可测试性大幅提升,mock 不用 rebuild graph |
| per-task_type `CachePolicy` + 自定义 `key_func` | PR #6 只接了 cache backend,没具体 cache_policy | 真正吃到 web_search / image_describe 等幂等调用红利 |

这三件**互不依赖**,可独立 PR 渐进上线。

---

## 2. Tier-2.1 — BaseStore 替手写飞轮偏好向量

### 2.1 当前状态

铁律 #15 要求 4 类飞轮信号沉淀:**工作流轨迹 / 偏好向量 / Reflexion / Skill 草稿**。当前实现:

- `youle/flywheel/` 自写一套 dispatcher
- `youle/backend/app/services/flywheel.py` 内部用 Redis Streams `flywheel:signals` 落事件
- 偏好向量目前**没有**真正的向量检索(只是落事件,不能按相似度查"这个用户喜欢什么风格的 BGM")

### 2.2 LangGraph 1.1 提供的 Store

```
langgraph.store.base.BaseStore
langgraph.store.postgres.aio.AsyncPostgresStore
  - PostgresIndexConfig    # 向量索引(语义检索)
  - TTLConfig              # 偏好可过期
  - SearchOp               # 余弦相似度 search
  - 命名空间嵌套           # ("user", user_id, "preferences", ...)
```

完全对应"按用户的偏好向量做语义检索"的需求。

### 2.3 目标设计

```python
# 启动时(checkpointer 同源升级)
from langgraph.store.postgres.aio import AsyncPostgresStore, PostgresIndexConfig

store = await AsyncPostgresStore.from_conn_string(
    DATABASE_URL,
    index=PostgresIndexConfig(
        dims=1536,
        embed=embed_with_openrouter,  # 经 LiteLLM 走 text-embedding 模型
    ),
    ttl=TTLConfig(default_ttl=60 * 60 * 24 * 90),  # 偏好 90 天
).__aenter__()

# graph 编译时注入
graph = builder.compile(checkpointer=saver, store=store, cache=_CACHE)

# 节点内取用
from langgraph.config import get_store

async def _bgm_select_node(state):
    store = get_store()
    # 写入用户决策(用户选了哪首 BGM)
    await store.aput(
        ("user", state["user_id"], "preferences", "bgm_style"),
        key=str(uuid4()),
        value={"mood": "warm", "title": "...", "feedback_score": 5},
    )
    # 检索这个用户的偏好,辅助 LLM 选片
    hits = await store.asearch(
        ("user", state["user_id"], "preferences", "bgm_style"),
        query=script_text[:200],  # 用脚本主旨作 query embedding
        limit=5,
    )
```

### 2.4 迁移路径(3 步,每步独立 PR)

#### Step 1:Store 上线 + 迁 _flywheel_preference_

- 新增 `langgraph_runner/store_factory.py`(对应 `checkpointer.py`)— 统一 init / close
- `app/main.py` lifespan:`store = await init_store(...)`
- `_build_compiled` 加 `store=` 入参
- `flywheel.py.emit_preference()` 改成同时写 store(双写,先观察 1 周)

#### Step 2:迁检索路径

- `bgm_select.py` / `image_generate.py` 把"读用户历史偏好"路径切到 `store.asearch`
- 老 Qdrant 检索保留作 fallback(`feature_flag=use_langgraph_store`)

#### Step 3:撤掉双写 + 删旧 Qdrant 集成

- 监控指标 1 周稳定(命中率、相似度分布、TTL 失效)后切单写
- 删 `youle/flywheel/qdrant_client.py` 等老代码

### 2.5 风险

| 风险 | 缓解 |
|-----|------|
| Embedding 调用增加 LiteLLM 成本 | 只对**用户决策**(数量级 ~10/任务)做嵌入,不对每条工作流轨迹 |
| Postgres 向量索引性能 | langgraph_store 走 pgvector — phase-1 已下线,需要先把 pgvector 加回来(开 ADR 单独议) |
| 双写一致性 | Step 1-2 期间双写,任一失败都不阻塞主路径,只发 metric 告警 |

### 2.6 工作量

- Step 1:1 天
- Step 2:1 天
- Step 3:0.5 天 + 1 周观察期
- **合计**:~2-3 天纯开发 + 1 周稳定观察

---

## 3. Tier-2.2 — Runtime.context 注入 dispatcher / waiter

### 3.1 当前痛点

`compiler._make_step_node` 是个 closure 工厂,捕获 `dispatcher` 和 `result_waiter`:

```python
def _make_step_node(step_def, *, dispatcher, result_waiter):
    sid = step_def["step_id"]
    async def _node(state):
        ...
        await dispatcher(agent_task)        # closure 捕获
        result = await result_waiter(...)   # closure 捕获
    return _node
```

这导致:
1. **测试 mock 麻烦**:每次换 dispatcher 必须 `build_state_graph(...)` 重建 — 把 graph 编译成本带进单测
2. **配置不可在运行时切换**:同一进程不能根据 conversation 切换 dispatcher(例如灰度路由)
3. **closure 捕获污染日志**:`_node` 的 repr 里包含 closure 变量

### 3.2 LangGraph Runtime API

```python
from dataclasses import dataclass
from langgraph.runtime import Runtime
from langgraph.config import get_runtime

@dataclass
class GraphContext:
    dispatcher: Callable[[AgentTask], Awaitable[None]]
    result_waiter: Callable[[str, str, int], Awaitable[Any]]

# 节点内
async def _node(state):
    runtime: Runtime[GraphContext] = get_runtime()
    await runtime.context.dispatcher(agent_task)

# 编译时无需传依赖,build_state_graph 不再吃 dispatcher / waiter
builder = StateGraph(TaskState, context_schema=GraphContext)
graph = builder.compile(checkpointer=saver)

# 调用时注入
await graph.ainvoke(
    initial_state,
    config={
        "configurable": {"thread_id": tid},
        "context": GraphContext(dispatcher=real_dispatch, result_waiter=real_wait),
    },
)
```

### 3.3 迁移路径(单 PR)

1. 在 `langgraph_runner/state.py`(或新文件 `context.py`)定义 `GraphContext` dataclass
2. `compiler.build_state_graph` 签名:**保留**当前 `dispatcher / result_waiter` 入参作为兼容期(标 `DEPRECATED`),**但内部**不再传给 `_make_step_node` — 取而代之 `_make_step_node` 内部 `get_runtime()` 取
3. `runner._build_compiled` / `start` / `resume` / `rollback_to_step` 调用时把 context 传 config
4. 单测 mock:不用 rebuild graph,直接传不同 context 的 config 即可
5. 收敛期(1 PR + 1 周观察)后删 `dispatcher` / `result_waiter` 入参

### 3.4 风险

| 风险 | 缓解 |
|-----|------|
| 未声明 `context_schema=` 时 `get_runtime()` 返回 default runtime | 在 `_build_compiled` 强制声明 schema,启动期加 assertion |
| time-travel 重放时 context 丢失 | runtime context 是**运行期**注入,不进 checkpoint —— 对的;但要确认 rollback_to_step 路径每次重 invoke 都重新传 context,不能依赖前一次的 |
| 兼容期 deprecated 入参用错 | 加 `DeprecationWarning`,CI grep 检查不再有新调用方传 |

### 3.5 工作量

~1.5 天(1 天改 + 0.5 天测)。

---

## 4. Tier-2.3 — per-task_type CachePolicy + 自定义 key_func

### 4.1 当前状态

PR #6 接了 cache backend(`compile(cache=InMemoryCache())`),但**没给任何 step 配 cache_policy**,所以**还没有任何节点缓存生效**。原因:LangGraph 默认 `key_func=default_cache_key` 会 hash 整个 state(含 `task_id`),跨 task 永远 miss,毫无缓存价值。

### 4.2 目标:按 task_type 配自定义 key_func

#### 4.2.1 缓存白名单(只这些 task_type 配 cache,其他保持原行为)

| task_type | TTL | key_func 哈希什么 |
|-----------|-----|-----------------|
| `web_search` | 1 h | `inputs["query"]` |
| `image_describe` | 7 d | `inputs["_upstream"]["image"]`(OSS ref) |
| `summarization` | 1 d | `inputs["text_ref"]` + `parameters["style"]` |
| `version_compare` | 30 d | 两个 ref(版本对) |
| `style_extract` | 7 d | `inputs["image_ref"]` |

**不缓存**:`long_writing` / `image_generate` / `tts_generate` / 一切 video — 创意任务,同 prompt 应当出多样性。

#### 4.2.2 设计:cacheable 由 task_type 注册表控制

```python
# compiler.py 内
CACHEABLE: dict[str, CachePolicy] = {
    "web_search": CachePolicy(
        ttl=3600,
        key_func=lambda state: _hash_inputs(state, fields=("query",)),
    ),
    "image_describe": CachePolicy(
        ttl=7 * 86400,
        key_func=lambda state: _hash_upstream(state, ref_key="image"),
    ),
    # ...
}

def _hash_inputs(state, *, fields):
    # 从 state 里抽出该 step 的 inputs(由 _make_step_node 渲染前的 raw fields)
    # 回 deterministic hash 字符串
    ...

# add_node 时
cache_policy = CACHEABLE.get(step_def["task_type"])
builder.add_node(
    f"step_{step_def['step_id']}",
    _make_step_node(...),
    retry_policy=STEP_RETRY_POLICY,
    cache_policy=cache_policy,  # None 也合法 = 不缓存
)
```

### 4.3 多 worker 缓存共享(prod blocker)

PR #6 的 `_CACHE = InMemoryCache()` 在多 worker 场景**进程间不共享** — dev 单机 OK,prod K8s 多 pod 会大量 miss。Tier-2.3 落地前必须解决:

#### 选项

| 方案 | 复杂度 | 推荐度 |
|------|--------|--------|
| `langgraph.cache.sqlite.SqliteCache` | 极低 | ⭐ NFS 共享 SQLite 不是好主意,跳过 |
| 自定义 `BaseCache` 用 Redis backend | 中 | ⭐⭐⭐ 复用项目已有 Redis,~150 行代码 |
| 直接接 LangGraph Platform `langgraph_sdk` | 高 | V1-P2 才考虑 |

**推荐方案**:实现 `RedisCache(BaseCache)`,key 用 namespace 隔离 cache vs Redis Streams 命名空间。

```python
class RedisCache(BaseCache[bytes]):
    def __init__(self, redis_url: str, namespace: str = "lg:cache:"):
        self._redis = aioredis.from_url(redis_url)
        self._ns = namespace
    async def aget(self, keys): ...
    async def aset(self, pairs): ...
    async def aclear(self, namespaces=None): ...
```

### 4.4 迁移路径

依赖 Tier-2.2 完成(因为 cache 与 Runtime context 都在 graph compile 路径,合一起改更清爽)。

1. 实现 `RedisCache` + 单测
2. `runner._CACHE` 切到 RedisCache(env 切换:dev=`InMemoryCache`,staging/prod=`RedisCache`)
3. 加 `CACHEABLE` 注册表 + key_func 工具
4. 给 5 个白名单 task_type 接上 cache_policy
5. 增量观察命中率(metric: `lg.cache.hit_count` / `lg.cache.miss_count`),按 task_type 调优 TTL

### 4.5 风险

| 风险 | 缓解 |
|-----|------|
| key_func 哈希不一致(Skill YAML 改了 prompt 但 cache 仍命中老结果) | 在 key_func 里**也哈希 skill_version**,Skill bump version → cache 自动失效 |
| 多用户隔离:用户 A 的 web_search 不应该让用户 B 命中 | key_func 哈希 user_id —— 但 web_search 的 query 与 user 无关,反而希望跨 user 共享省钱;按业务决策(默认共享,敏感场景 user_id 进 key) |
| cache poisoning(失败结果被缓存) | LangGraph 自带:节点抛异常时不写 cache,只缓存正常返回 |

### 4.6 工作量

- RedisCache 实现 + 测:1 天
- 5 个 key_func + cache_policy 接入:1 天
- 命中率观察 + 调 TTL:1 周(被动)
- **合计**:~2 天纯开发 + 1 周观察

---

## 5. 整体排期与依赖

```
Tier-2.2 (Runtime.context)  ─┐
                              ├─→  Tier-2.3 (per-step cache_policy)
Tier-2.1 (BaseStore)        ─┘     需要先解决多-worker cache (RedisCache)
       │
       └─→ 依赖 pgvector 加回 phase-1 (单独 ADR)
```

**推荐顺序**:Tier-2.2(无依赖)→ Tier-2.3(技术上无强依赖,但代码合一起改更清爽)→ Tier-2.1(需要 pgvector ADR 先开)。

| Tier | 工作量(纯开发) | 风险 | 收益 |
|------|----------------|------|------|
| 2.2 Runtime.context | 1.5 天 | 低 | 中(可测试性) |
| 2.3 per-step cache | 2 天 | 中(多 worker) | **高**(钱) |
| 2.1 BaseStore | 2-3 天 | 中(pgvector 依赖) | **高**(砍一套自写代码) |

总计 ~6-7 天纯开发 + 1-2 周稳定观察。

---

## 6. 不做的事(明确划界)

- `create_react_agent` / `ToolNode` 替 HR/财务经理 — V1-P2 范围(铁律 #18)
- `langgraph.func.@entrypoint` 改写简单 Skill — 价值低,不动 StateGraph 主线
- `stream_mode="custom"` + `get_stream_writer` 重写 WS 事件 — V1-P1,单独 PR
- LangGraph Platform / SDK — V2 自托管平台讨论时再起

---

## 7. 决策点(评审需明确)

1. **是否同意 Tier-2.1 把 pgvector 加回 phase-1**?(替代方案:用外部 Qdrant,但要维护两套)
2. **cache 跨用户共享策略**:`web_search` 的同 query 跨用户共享是否合规?(隐私 vs 钱)
3. **三件 PR 的合入顺序**和 sprint 归属。

---

> **下一步**:在评审通过后,按"Tier-2.2 → Tier-2.3 → Tier-2.1"顺序起独立 PR,每个 PR 内附本文档对应章节作为 design rationale。
