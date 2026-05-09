# Skill YAML 模板

**版本**:v3.0(对齐 ADR-001-rev / ADR-002 / ADR-009 / ADR-010)
**日期**:2026-05-05
**面向**:Skill 设计者 / 平台运营 / 工程团队
**地位**:Skill YAML 的标准格式 + 三个完整示例(**反诈视频** / 电商详情图 / PPT 制作)。

**v3.0 关键变更**:
- 🔄 Agent 编号反向(ADR-001-rev):agent_2=文档 / agent_3=图 / agent_4=影音
- 🔄 V1 hero 回归反诈视频(ADR-012 废弃)
- 保留:`hitl_gate` 字段(ADR-010)/ `mcp_tools` / `mcp_calls`(ADR-009)/ `skip_if`
- 保留:task_type `pptx_assemble`(ADR-002)

---

## 一、Skill YAML 顶层结构(以反诈视频制作为例)

```yaml
# 元数据
skill_id: anti_fraud_video
name: 反诈视频制作
version: 1.0
description: 自动制作 30-90 秒反诈短视频,适合社区宣传、抖音投放
domain: video
scenario: anti_fraud
creator: platform                # platform / user_<uuid>
visibility: public               # public / subscribed / private
created_at: 2026-05-04
updated_at: 2026-05-05

# 触发关键词
keywords:
  - 反诈
  - 防诈骗
  - 防骗视频
  - 反诈视频
anti_signals:                    # 包含这些词时不命中
  - 真人出镜
  - 直播
  - 长视频

# 输入字段定义
inputs_schema:
  - name: 年份
    type: number
    required: true
    default: 2026
    options: [2024, 2025, 2026]
  - name: 骗局类型
    type: enum
    required: true
    options: [电信诈骗, 投资理财, 网恋诈骗, 网络洗钱]
    clarification_form: single_select
  - name: 受众
    type: enum
    required: true
    options: [城市老人, 农村老人, 都覆盖]
    default: 都覆盖
    clarification_form: single_select
  - name: 时长
    type: enum
    required: false
    options: [30s, 60s, 90s]
    default: 60s

# 工作流步骤(LangGraph DAG,v3.0 编号)
workflow:
  - step_id: research                   # 案例调研
    agent: agent_1                      # 文字
    task_type: web_search
    mcp_tools: [mcp://search/web_search, mcp://search/web_fetch]    # ADR-009
    # ...

  - step_id: script                      # 脚本生成
    agent: agent_1                      # 文字
    task_type: long_writing
    depends_on: [research]
    hitl_gate:                           # ADR-010 HITL gate
      type: version_select
    # ...

  - step_id: image_process               # 图片下载与处理
    agent: agent_3                      # v3.0 图(原 v2 是 agent_2)
    task_type: image_download
    depends_on: [research]
    hitl_gate:
      type: quality_review
    # ...

  - step_id: bgm                         # 配乐
    agent: agent_4                      # v3.0 影音(原 v2 是 agent_3)
    task_type: bgm_select
    depends_on: [script]

  - step_id: video_compose               # 自动剪辑
    agent: agent_4                      # v3.0 影音
    task_type: video_compose
    depends_on: [script, image_process, bgm]
    timeout: 600

  - step_id: final_review                # 终审 + 中断 C 入口
    agent: orchestrator
    task_type: hitl_only
    depends_on: [video_compose]
    hitl_gate:
      type: final_approval
      actions:
        - {label: "接受", action: approve}
        - {label: "回到第 2 步重写脚本", action: rollback, target_step: script}
        - {label: "回到第 3 步重做图片", action: rollback, target_step: image_process}

# 失败处理
failure_handling:
  research:
    on_timeout: retry_once
    on_failure: ask_user_to_provide_links
  script:
    on_timeout: switch_to_fallback_model
    on_failure: ask_user_to_simplify
  video_compose:
    on_timeout: notify_user_long_running
    on_failure: ask_user_to_retry

# 最终交付
delivery:
  primary_artifact: video_compose
  bundled_artifacts: [research, script, image_process, bgm]
  user_message_template: |
    ✅ 任务完成!共耗时 {{duration}}。
    主成品:反诈视频(mp4),时长 {{时长}}
    附带:调研表 / 脚本 / 配图 / 配乐
```

---

## 二、字段语义详解

### 2.1 元数据

| 字段 | 必填 | 说明 |
|------|-----|------|
| `skill_id` | ✅ | 全局唯一,蛇形命名 |
| `name` | ✅ | 用户面展示名 |
| `version` | ✅ | 用于编译缓存 key |
| `domain` | ✅ | text / image / video / document / mixed |
| `scenario` | ✅ | 与意图理解的 `scenario` 对齐 |
| `creator` | ✅ | platform / user_<uuid> |
| `visibility` | ✅ | public / subscribed / private |

### 2.2 触发关键词

- `keywords`:命中即加分
- `anti_signals`:命中即排除

匹配逻辑:`keywords && user_keywords AND NOT (anti_signals && user_keywords)`

### 2.3 输入字段(inputs_schema)

| 字段 | 说明 |
|------|------|
| `name` | 字段名(中英文均可,Jinja2 变量名)|
| `type` | number / text / enum / boolean / image_ref |
| `required` | true(必填) / false(选填) |
| `default` | 选填字段的默认值 |
| `options` | enum 类型的选项 |
| `clarification_form` | single_select / image_compare / version_compare |
| `preview_images` | image_compare 时的预置图列表 |
| `generate_count` | version_compare 时生成几个版本 |

### 2.4 工作流步骤(workflow)

| 字段 | 说明 |
|------|------|
| `step_id` | 步骤名,Jinja2 引用产物时用作 key |
| `agent` | agent_1 / agent_2 / agent_3 / agent_4(ADR-001)|
| `task_type` | 必须在该 Agent 的 SUPPORTED_TASK_TYPES 内 |
| `depends_on` | 上游 step_id 列表;LangGraph 自动并行无依赖步骤 |
| `timeout` | 超时秒数 |
| `prompt_template` | Jinja2 模板,主编排渲染后传给 Agent |
| `inputs` | 显式声明上游产物注入(见 ADR-002 PPT 例子)|
| `parameters` | 传给 Agent handler 的额外参数 |
| `routing_hints` | L2 模型路由提示(主备模型)|
| `output_format` | type + schema(用于质量校验)|
| `quality_check` | 自动质检规则 |

### 2.5 失败处理(failure_handling)

每步可定义:

- `on_timeout`:retry_once / switch_to_fallback_model / notify_user_long_running
- `on_failure`:ask_user_to_provide_links / ask_user_to_simplify / ask_user_to_retry / abort

---

## 三、示例 1:反诈视频制作(V1 hero SKU,v3.0 回归)

```yaml
skill_id: anti_fraud_video
name: 反诈视频制作
version: 1.0
description: 自动制作 30-90 秒反诈短视频,适合社区宣传、抖音投放
domain: video
scenario: anti_fraud
creator: platform
visibility: public
created_at: 2026-05-04
updated_at: 2026-05-05

keywords:
  - 反诈
  - 防诈骗
  - 防骗视频
  - 反诈视频
  - anti_fraud
anti_signals:
  - 真人出镜
  - 直播
  - 长视频

inputs_schema:
  - name: 年份
    type: number
    required: true
    default: 2026
    clarification_form: single_select
    options: [2024, 2025, 2026]
  - name: 骗局类型
    type: enum
    required: true
    options: [电信诈骗, 投资理财, 网恋诈骗, 网络洗钱]
    clarification_form: single_select
  - name: 受众
    type: enum
    required: true
    options: [城市老人, 农村老人, 都覆盖]
    default: 都覆盖
    clarification_form: single_select
  - name: 时长
    type: enum
    required: false
    options: [30s, 60s, 90s]
    default: 60s
    clarification_form: single_select
  - name: 开头钩子
    type: text
    required: false
    clarification_form: version_compare
    generate_count: 3

workflow:
  # ━━━ 第 1 步:案例调研 ━━━
  - step_id: research
    agent: agent_1                       # 文字
    task_type: web_search
    timeout: 120
    mcp_tools:
      - mcp://search/web_search
      - mcp://search/web_fetch
    prompt_template: |
      给我 10 条 {{年份}} 涉及 {{骗局类型}}、传销、网络洗钱的案件新闻,
      并且罗列涉案金额、新闻简介 50 字。
      标题要有夸张感,模仿抖音标题。
      给我新闻来源网址。
      生成 excel 表格。
      只要有图片的来源。
      对于有图片的新闻来源,记录图片 URL 到 excel 表格单独一列。
      (图片下载由后续步骤的 Agent 3 设计师负责)
    output_format:
      type: structured                   # xlsx
      schema:
        columns: [标题, 摘要, 涉案金额, 来源URL, 图片URL]
    routing_hints:
      primary: deepseek-v4-pro
      fallback: [claude-sonnet-4-6]
    quality_check:
      min_rows: 5

  # ━━━ 第 2 步:脚本生成 + HITL gate ━━━
  - step_id: script
    agent: agent_1                       # 文字
    task_type: long_writing
    depends_on: [research]
    timeout: 60
    prompt_template: |
      基于 {{research.output}} 撰写一段反诈视频脚本,
      针对 {{受众}} 受众,时长 {{时长}}。
      开头钩子参考:{{开头钩子}}
      要求:开头有钩子、中间有案例、结尾呼吁警惕。
    output_format:
      type: text
    routing_hints:
      primary: kimi-k2
      fallback: [deepseek-v4-pro, claude-sonnet-4-6]
    hitl_gate:
      type: version_select
      timeout_seconds: 600
      auto_approve_if_user_offline: false

  # ━━━ 第 3 步:图片处理(下载+质检)+ HITL gate ━━━
  - step_id: image_process
    agent: agent_3                       # v3.0 设计师(原 v2 是 agent_2)
    task_type: image_download
    depends_on: [research]
    timeout: 120
    parameters:
      check_quality: true
    prompt_template: |
      从 {{research.output.图片URL}} 下载图片,
      过滤无效与低质,保留至少 5 张供视频合成使用。
    output_format:
      type: image_collection
    hitl_gate:
      type: quality_review
      actions: [approve, regenerate_single, replace_with_upload]

  # ━━━ 第 4 步:配乐选择 ━━━
  - step_id: bgm
    agent: agent_4                       # v3.0 影音(原 v2 是 agent_3)
    task_type: bgm_select
    depends_on: [script]
    timeout: 5
    parameters:
      mood: warning
      duration_field: 时长
    output_format:
      type: audio

  # ━━━ 第 5 步:视频合成(Celery 异步)+ 终审 ━━━
  - step_id: video_compose
    agent: agent_4                       # v3.0 影音
    task_type: video_compose
    depends_on: [script, image_process, bgm]
    timeout: 600
    inputs:
      script: "{{script.output}}"
      images: "{{image_process.output}}"
      bgm:    "{{bgm.output}}"
    parameters:
      voice: female_warm
      duration_field: 时长
    output_format:
      type: video
    quality_check:
      min_resolution: 1080p
      max_silence_seconds: 2
    hitl_gate:
      type: final_approval
      timeout_seconds: 1800
      actions:
        - {label: "接受,发布", action: approve, default: true}
        - {label: "调字幕样式", action: modify, target_step: video_compose}
        - {label: "换 BGM", action: modify, target_step: bgm}
        - {label: "回到第 2 步重写脚本", action: rollback, target_step: script}
        - {label: "回到第 3 步重做图片", action: rollback, target_step: image_process}

failure_handling:
  research:
    on_timeout: retry_once
    on_failure: ask_user_to_provide_links
  script:
    on_timeout: switch_to_fallback_model
    on_failure: ask_user_to_simplify
  video_compose:
    on_timeout: notify_user_long_running
    on_failure: ask_user_to_retry

delivery:
  primary_artifact: video_compose
  bundled_artifacts: [research, script, image_process, bgm]
  user_message_template: |
    ✅ 任务完成!共耗时 {{duration}}。
    主成品:反诈视频(mp4),时长 {{时长}}
    附带:调研表 / 脚本 / 配图 / 配乐
```

**关键设计**:

- **5 步 DAG,3 道 HITL gate**(脚本审 / 配图审 / 终审)
- v3.0 Agent 编号:**Agent 1 文字 → Agent 3 图 → Agent 4 影音**
- `research` 输出 xlsx 含图片 URL,**Agent 3 设计师**负责下载(ADR-002:不在 Agent 1 内做下载)
- `video_compose` 走 Celery 异步(Agent 4 内部决定)
- 终审支持中断 C(回滚到第 2 / 第 3 步)

## 四、示例 2:电商详情图制作

```yaml
skill_id: ecommerce_detail_image
name: 电商详情图制作
version: 1.0
description: 基于商品图 + 卖点 + 风格,生成 1 张精美的电商详情长图
domain: image
scenario: ecommerce_detail
creator: platform
visibility: public

keywords:
  - 电商详情图
  - 商品详情
  - 长图
  - 详情页
anti_signals:
  - 视频
  - 海报

inputs_schema:
  - name: 商品图
    type: image_ref
    required: true
    clarification_form: image_upload     # 让用户上传
  - name: 卖点
    type: text
    required: true
  - name: 受众
    type: enum
    required: true
    options: [城市妈妈, 都市白领, Z 世代, 银发族, 都覆盖]
    clarification_form: single_select
  - name: 风格
    type: enum
    required: true
    options: [自然质朴, 简约现代, 暖色家居, 科技感, 朴朴风, 自定义]
    clarification_form: image_compare
    preview_images:
      - oss://samples/style_natural.jpg
      - oss://samples/style_minimal.jpg
      - oss://samples/style_warm.jpg
      - oss://samples/style_tech.jpg
      - oss://samples/style_pupu.jpg

workflow:
  - step_id: style_analysis
    agent: agent_3                       # v3.0 ADR-001-rev:图 = Agent 3
    task_type: style_extract
    timeout: 30
    inputs:
      reference: "{{商品图}}"
    prompt_template: |
      分析这个商品图的视觉特征,
      结合用户偏好风格 "{{风格}}" 输出风格指引。
      包含:配色、构图、字体、氛围。
    output_format:
      type: structured

  - step_id: copy_writing
    agent: agent_1
    task_type: long_writing
    depends_on: [style_analysis]
    timeout: 30
    prompt_template: |
      基于风格指引 {{style_analysis.output}}
      和商品卖点 {{卖点}},
      为 {{受众}} 写 5 段电商详情图文案,每段 30-50 字。
      要求:第 1 段是主标题(吸引点),后 4 段层层递进。
    output_format:
      type: structured                   # 5 段独立
    routing_hints:
      primary: deepseek-v4-pro
      fallback: [kimi-k2]

  - step_id: segment_images
    agent: agent_3                       # v3.0:图 = Agent 3
    task_type: batch_generate
    depends_on: [style_analysis, copy_writing]
    timeout: 90
    parameters:
      image_specs:                       # 5 张分段图,第 1 张为视觉锚点
        - {prompt: "{{copy_writing.output[0]}}", size: "1080x720"}
        - {prompt: "{{copy_writing.output[1]}}", size: "1080x720"}
        - {prompt: "{{copy_writing.output[2]}}", size: "1080x720"}
        - {prompt: "{{copy_writing.output[3]}}", size: "1080x720"}
        - {prompt: "{{copy_writing.output[4]}}", size: "1080x720"}
      style_strength: 0.7                # 锚定第 1 张
    output_format:
      type: image_collection

  - step_id: long_concat
    agent: agent_2                       # v3.0 ADR-001-rev:文档 = Agent 2(长图拼接)
    task_type: image_concat_long
    depends_on: [segment_images]
    timeout: 30
    inputs: "{{segment_images.output}}"
    output_format:
      type: image

  - step_id: quality_check
    agent: agent_3                       # v3.0:图 = Agent 3
    task_type: image_quality_check
    depends_on: [long_concat]
    timeout: 20
    inputs:
      reference: "{{long_concat.output}}"
    output_format:
      type: quality_report
    quality_check:
      min_overall_score: 0.7

failure_handling:
  segment_images:
    on_failure: retry_with_different_anchor
  quality_check:
    on_quality_failure: regenerate_segments

delivery:
  primary_artifact: long_concat
  bundled_artifacts: [copy_writing, segment_images]
```

**关键设计**:
- 第 1 张分段图作为视觉锚点(`style_strength: 0.7`),保证 5 张风格一致
- 长图拼接归 **Agent 2 文档专员**(v3.0 ADR-001-rev),它做的就是"组装多个图片成一个文档级产物"
- 质检不达标自动重生成

---

## 五、示例 3:PPT 制作(ADR-002 标准范式)

```yaml
skill_id: ppt_create
name: PPT 制作
version: 1.0
description: 基于主题生成 15-20 页商务/学术 PPT,含大纲 + 配图
domain: document
scenario: ppt_create
creator: platform
visibility: public

keywords:
  - PPT
  - 演示文稿
  - 幻灯片
  - 提案
anti_signals:
  - Word
  - PDF

inputs_schema:
  - name: 主题
    type: text
    required: true
  - name: 风格
    type: enum
    required: true
    options: [商务, 学术, 科技, 极简]
    default: 商务
    clarification_form: single_select
  - name: 页数
    type: number
    required: false
    default: 15
  - name: 受众
    type: enum
    required: false
    options: [客户, 投资人, 学者, 内部团队]
    default: 内部团队

workflow:
  # ━━━ ADR-002 关键示例:PPT 制作显式拆为 3 步 ━━━
  
  - step_id: ppt_outline
    agent: agent_1                       # 文字 → 写大纲
    task_type: structured_writing
    timeout: 60
    prompt_template: |
      为「{{主题}}」生成 PPT 大纲,共 {{页数}} 页。
      面向 {{受众}}。
      每页输出:
      - title: 页面标题
      - content: 正文要点(3-5 条)
      - image_description: 建议配图描述(用于让设计师生成图)
      返回 JSON 数组。
    output_format:
      type: structured
      schema:
        type: array
        items:
          type: object
          properties:
            title: string
            content: string
            image_description: string
    routing_hints:
      primary: deepseek-v4-pro

  - step_id: ppt_images
    agent: agent_3                       # v3.0:图 → 批量生成配图
    task_type: batch_generate
    depends_on: [ppt_outline]
    timeout: 120
    parameters:
      style_strength: 0.6                # 全 PPT 风格统一
      image_specs_from: "{{ppt_outline.output[*].image_description}}"
    output_format:
      type: image_collection

  - step_id: ppt_assemble
    agent: agent_2                       # v3.0:文档 → 仅组装
    task_type: pptx_assemble             # 注:不是 pptx_create(ADR-002)
    depends_on: [ppt_outline, ppt_images]
    timeout: 30
    inputs:
      outline: "{{ppt_outline.output}}"
      images:  "{{ppt_images.output}}"
    parameters:
      style: "{{风格}}"
    output_format:
      type: document                     # .pptx

failure_handling:
  ppt_outline:
    on_failure: ask_user_to_simplify
  ppt_images:
    on_failure: skip_image_use_placeholder

delivery:
  primary_artifact: ppt_assemble
  bundled_artifacts: [ppt_outline, ppt_images]
```

**关键设计(对应 ADR-002)**:

- ❌ Agent 4 内部**没有** `call_other_agent("agent_1", ...)` 跨调
- ✅ 跨能力被显式拆为 3 个 step,LangGraph 编排
- ✅ Agent 4 的 `pptx_assemble` 只做组装(`python-pptx` 插入文字 + 图片)
- ✅ `task_type` 从 `pptx_create` 改名 `pptx_assemble`,语义清晰

---

## 六、Skill YAML 编写注意事项

### 6.1 Jinja2 变量引用

模板内可引用:

| 引用 | 含义 | 例子 |
|------|------|------|
| `{{字段名}}` | 用户输入字段 | `{{受众}}` |
| `{{step_id.output}}` | 上游产物全文 | `{{research.output}}` |
| `{{step_id.output[index]}}` | 数组产物某项 | `{{copy_writing.output[0]}}` |
| `{{step_id.output.字段}}` | 结构化产物某字段 | `{{research.output.图片URL}}` |
| `{{step_id.output[*].字段}}` | 数组所有项的某字段(JMESPath)| `{{ppt_outline.output[*].image_description}}` |

### 6.2 产物类型与渲染策略

主编排根据产物 `type` 决定如何注入 prompt:

| type | 注入策略 |
|------|---------|
| `text` | 全文嵌入 |
| `structured` | 摘要 + OSS 引用 |
| `image` | OSS URL,Agent 自己加载 |
| `image_collection` | URL 列表 |
| `video` | OSS URL |
| `audio` | OSS URL |
| `document` | OSS URL + 元数据(页数等)|

### 6.3 Agent 选择速查(ADR-001)

| 任务类型 | 用哪个 Agent |
|---------|------------|
| 写文案 / 调研 / 翻译 | Agent 1 |
| 单图生成 / 批量生成 / 图编辑 | Agent 2 |
| 视频生成 / 视频合成 / TTS / BGM / 字幕 | Agent 3 |
| PPT / Excel / Word / PDF / 长图拼接 | Agent 4 |

### 6.4 跨能力步骤(ADR-002)

**绝对不要**让 Agent 内部调其他 Agent。永远用 Skill YAML 显式拆步:

```yaml
# 错误模式(已禁用)
# Agent 4 的 pptx_create 内部调 Agent 1 + Agent 2

# 正确模式
- {step_id: outline, agent: agent_1, ...}
- {step_id: images, agent: agent_3, depends_on: [outline]}      # v3.0:图 = Agent 3
- {step_id: assemble, agent: agent_2, depends_on: [outline, images]}  # v3.0:文档 = Agent 2
```

### 6.5 性能与成本

- LangGraph 自动并行无依赖步骤(无需 Skill 标注)
- 长任务(视频合成)在 Agent 内走 Celery,主编排立即拿到 `pending_external` 状态
- 单 Skill 单任务总成本估算:
  - 反诈视频:$0.5-2.0(主要是视频生成)
  - 电商详情图:$0.1-0.3
  - PPT 制作:$0.2-0.5

---

## 七、Skill 编译与缓存

主编排首次加载 Skill YAML 时:

1. Parser 解析为内存对象
2. 按 `workflow` 创建 LangGraph Node
3. 按 `depends_on` 创建 Edges
4. 编译为 StateGraph
5. **缓存到 Redis**(`key = skill_id + version`)

后续同一 Skill 直接走缓存,只重新渲染 prompt(纯程序操作)。

---

## 八、用户不写 Skill YAML

- 用户在群里**只说自然语言**,主编排自动匹配 Skill
- 创作者通过"成为 Skill 创作者"流程(V2),由总裁助理**自动从工作流总结生成 YAML**
- 创作者可在 AI 学院里审核、编辑后发布,平台审核通过后上线技能市场

---

## 九、相关文档

- [4 个分任务 Agent 实现指南](../2_工程实现/4 个分任务 Agent 实现指南.md) — 各 Agent 的 task_type 列表
- [模型路由表](../4_附录/模型路由表.md) — routing_hints 可填的模型
- [开放问题与决议](开放问题与决议.md) — ADR-001 / ADR-002
