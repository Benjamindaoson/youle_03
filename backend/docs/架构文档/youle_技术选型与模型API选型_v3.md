# 「有了」技术选型与模型 API 选型文档

**版本**:V3.0(基于 7 角色团队 + 三种工作模式 + Agent 拟人化)
**日期**:2026-05-04
**面向**:技术负责人 / AI 工程师 / 后端 / DevOps / 采购
**用途**:工程团队进行技术采购、对接、配置时的实操手册

---

# 第 1 章 选型总览

## 1.1 选型原则

V1 阶段的选型遵循 5 个原则:

**1. 成熟优先,不追新**:用经过大规模验证的方案,V1 不试验性技术
**2. 中文优先**:面向中国 SMB 用户,中文场景能力是首要考虑
**3. 国内主备**:主力用国内模型,海外作 fallback
**4. 简单可控**:V1 阶段不上 K8s、Temporal、Kafka
**5. 按需接入**:V1 只接 V1 用得上的模型,V1.5 加新场景时再加

## 1.2 V1 vs V1.5 模型接入策略

**核心原则**:**用得上才接,接得越多稳定性测试成本越高**。

V1 阶段只做 2 个 Skill(反诈视频 + 电商详情图),实际用到的文本场景:
- 短文写作(脚本、文案)
- 信息提取、摘要
- web_search(调研)
- 图片描述、风格分析

V1.5 阶段加小红书 / 公众号 / 抖音 / PPT 等 Skill,才需要长文模型和爆款风格模型。

## 1.3 关键决策一览

| 类别 | V1 阶段选型 | V1.5 / V2 升级 |
|---|---|---|
| 编排引擎 | LangGraph | 不变 |
| 长任务 | Celery + Redis | V2 升级 Temporal |
| 消息队列 | Redis Streams | V2 视情况 Kafka |
| 数据库 | PostgreSQL 16 + pgvector | 不变,加分区 |
| 缓存 | Redis 7.x | 不变,加分片 |
| 对象存储 | OSS / S3 | 不变 |
| 后端框架 | FastAPI | 不变 |
| 前端框架 | Next.js 15 | 不变 |
| 容器化 | Docker + Docker Compose | V2 升级 K8s |
| 模型路由 | LiteLLM + 自定义 | 不变 |
| 主力轻 LLM | DeepSeek-V4-Flash | 不变 |
| 主力推理 / web_search | Claude Sonnet 4.6 | 不变 |
| Fallback 轻量 | Claude Haiku 4.5 | 不变 |
| 深度兜底 | GPT-5 | 不变 |
| 主力图片(真实) | GPT Image 2 | 不变 |
| 主力图片(批量) | Seedream 3 | 不变 |
| 主力视频(文生) | (V1 不接) | V1.5:Veo 3 |
| 主力视频(图生) | (V1 不接) | V1.5:Seedance 2 |
| TTS | 火山引擎 TTS | 不变 |
| ASR | Whisper v3 | 不变 |
| **长文主力(V1.5)** | (V1 不用) | DeepSeek-V4-Pro |
| **创意备用(V1.5)** | (V1 不用) | Kimi K2 |
| **抖音/小红书风格(V1.5)** | (V1 不用) | 豆包 Pro |

---

# 第 2 章 基础设施选型

## 2.1 数据库:PostgreSQL 16 + pgvector

**选型**:阿里云 RDS PostgreSQL 16(高可用版)+ pgvector 0.7 扩展

**用途**:
- 业务数据(users / conversations / messages / artifacts)
- Brief 数据(Plan 模式产出)
- LangGraph state 持久化
- Skill 元数据
- 向量检索(Skill 匹配第 2 层)
- 模型路由规则 + 健康度

**版本**:PostgreSQL 16(2026 年主流稳定版)

**部署**:V1 1 主 1 从(同城),V2 1 主 N 从

**规格**:4 核 16G(V1 起步)

**关键扩展**:pgvector 0.7+、pg_partman(V2)、pg_stat_statements

---

## 2.2 缓存:Redis 7.x

**选型**:阿里云 Redis 7.0 企业版(集群版)

**用途**:消息队列(Streams)、实时状态、分布式锁、限流、Skill 编译缓存

**版本**:Redis 7.2+

**部署**:V1 Sentinel 模式,V2 Cluster 模式

**规格**:4G 内存(V1 起步)

---

## 2.3 对象存储:阿里云 OSS

**选型**:阿里云 OSS 标准存储

**用途**:用户上传素材、Agent 产物、系统预置资源(BGM、参考图、表情包)

**预算**:V1 阶段约 ¥200/月(1TB 起步)

---

## 2.4 容器与部署

**容器**:Docker 24+
**编排(V1)**:Docker Compose
**编排(V2)**:Kubernetes(阿里云 ACK)
**镜像仓库**:阿里云容器镜像服务 ACR

---

## 2.5 网络与安全

**域名 + DNS**:阿里云域名服务
**SSL 证书**:阿里云 SSL 证书
**负载均衡**:阿里云 SLB 标准型
**WAF**:阿里云 WAF
**DDoS 防护**:阿里云 DDoS 基础防护

---

# 第 3 章 应用框架选型

## 3.1 编排引擎:LangGraph

**选型**:LangGraph 0.2+
**用途**:主编排 Agent 的内核
**Checkpointer**:PostgresSaver
**风险**:深度绑定 LangChain 生态,V2 切换成本高

## 3.2 长任务执行:Celery

**选型(V1)**:Celery 5.4 + Redis broker + Redis backend
**用途**:Agent 4 的视频合成(5-10 分钟)
**升级 Temporal 触发条件**:视频任务日均 > 1000

## 3.3 消息队列:Redis Streams

**选型**:Redis 7.x 内置 Streams
**队列设计**:
- agent_tasks:text(Agent 1)
- agent_tasks:document(Agent 2)
- agent_tasks:image(Agent 3)
- agent_tasks:video(Agent 4)
- (HR / 财务经理不接队列,直接 API)

## 3.4 后端框架:FastAPI

**选型**:FastAPI 0.110+ + Python 3.12
**ORM**:SQLAlchemy 2.0
**ASGI**:Uvicorn + Gunicorn

## 3.5 前端框架:Next.js 15

**选型**:Next.js 15 + TypeScript + Tailwind 4 + shadcn/ui + Zustand
**包管理**:pnpm
**构建**:Turbopack

---

# 第 4 章 Agent 选型与配置

## 4.1 Agent 总览

系统共 7 个 Agent:

| Agent | 用户视角名 | 部署形态 | 实例数 | 资源 |
|---|---|---|---|---|
| 主编排 Agent | 总裁助理 | LangGraph 进程内 | 3 | 4 核 8G |
| Agent 1 | 研究员/文案师 | 独立微服务 | 2 | 2 核 4G |
| Agent 2 | 文档专员 | 独立微服务 | 2 | 2 核 4G |
| Agent 3 | 设计师 | 独立微服务 | 3 | 4 核 8G |
| Agent 4 | 影音师 | 独立微服务 | 2 | 4 核 8G |
| 支持 Agent A | HR | 独立微服务 | 1 | 2 核 4G |
| 支持 Agent B | 财务经理 | 独立微服务 | 1 | 2 核 4G |
| Celery Worker | (无,后台) | Celery 进程 | 2 | 4 核 8G |

## 4.2 主编排 Agent

**部署形态**:LangGraph 进程内的 Node 群,不是独立微服务

**内部分 8 个子模块**:
- 意图理解器
- 模式管理器
- Skill 匹配器
- 输入校验器
- 澄清生成器
- 任务编排器
- 中断处理器
- **互动编排器**(新)

**关键依赖**:LangGraph 0.2+、LiteLLM、pgvector、jieba、BGE-M3

**水平扩展**:按 user_id 一致性哈希分片

---

## 4.3 Agent 1:研究员/文案师(文字 + 工具调用)

**职责**:文字与语言相关任务,以及工具调用(联网搜索、网页抓取、数据收集)

**V1 阶段支持的 task_type**:

| task_type | 说明 | 主力模型 | 备用 |
|---|---|---|---|
| short_writing | 短文(脚本、文案、口播) | DeepSeek-V4-Flash | Haiku 4.5 |
| summarization | 摘要 | DeepSeek-V4-Flash | Haiku 4.5 |
| extraction | 信息提取 | DeepSeek-V4-Flash | Haiku 4.5 |
| analysis | 分析推理 | Claude Sonnet 4.6 | GPT-5 |
| web_search | 联网搜索(tool use) | Claude Sonnet 4.6 | GPT-5 |
| web_scrape | 网页抓取 | (Playwright,无 LLM) | - |
| data_organize | 数据整理 | Claude Sonnet 4.6 | DeepSeek-V4-Flash |

**V1.5 阶段新增**:
- long_writing(公众号长文):DeepSeek-V4-Pro 主力
- long_writing(creative):Kimi K2 主力
- short_writing(xiaohongshu):豆包 Pro 主力
- short_writing(douyin):豆包 Pro 主力
- structured_writing(大纲、提案):Sonnet 4.6 主力
- translation:DeepSeek-V4-Pro 主力
- polish

**工具集**:Tavily Search API、Playwright、httpx、pandas

**资源**:2 核 4G

---

## 4.4 Agent 2:文档专员(办公文档)

**职责**:Office 文档(PPT、Excel、Word、PDF) + 图像组装(长图垂直拼接)

**V1 阶段支持的 task_type**:

| task_type | 说明 | 是否调 LLM |
|---|---|---|
| xlsx_create | Excel 生成 | 部分(Sonnet 整理数据) |
| xlsx_read | Excel 读取 | 否 |
| xlsx_format | Excel 格式化 | 否 |
| docx_create | Word 生成 | 否(跨调 Agent 1) |
| docx_modify | Word 修改 | 否 |
| pdf_extract | PDF 提取 | 否 |
| **image_concat_long** | **长图垂直拼接(电商详情图核心)** | 否(用 PIL) |

**V1.5 阶段新增**:
- pptx_create(跨调 Agent 1+3)
- pptx_modify、pptx_extract
- xlsx_chart
- docx_extract
- pdf_create、pdf_watermark、pdf_ocr

**工具集**:python-pptx、openpyxl、python-docx、PyPDF2、pdfplumber、pandas、Pillow、Tesseract

**特殊能力**:跨 Agent 调用——做 PPT 时调 Agent 1 写大纲、调 Agent 3 生成配图(V1.5)

**资源**:2 核 4G(纯 Python 库,不重)

**关键备注**:Agent 2 大部分任务**不调 LLM**,主要是 Python 库的封装

---

## 4.5 Agent 3:设计师(图)

**职责**:图像生成、理解、编辑、风格管理

**V1 阶段支持的 task_type**:

| task_type | 说明 | 主力模型 | 备用 |
|---|---|---|---|
| image_generate(真实) | 真实风格图 | GPT Image 2 | Seedream 3 |
| **batch_generate** | **批量生成(风格一致)** | Seedream 3 | GPT Image 2 |
| image_describe | 图片描述 | Claude Sonnet Vision | GPT-5 Vision |
| image_quality_check | 质量评估 | GPT-5 Vision | Sonnet Vision |
| image_download | 从 URL 下载 | (httpx) | - |
| image_compose | 多图合成 | (PIL,无 LLM) | - |
| image_ocr | OCR | (Tesseract) | - |

**V1.5 阶段新增**:
- image_generate(卡通):Nano Banana 2
- image_generate(中国风):Kling Image
- image_edit、image_inpaint、image_outpaint
- image_classify、image_enhance、background_remove
- style_extract、style_transfer

**工具集**:Pillow、OpenCV、httpx,调用 GPT Image 2 / Seedream 3 / Vision 模型

**关键能力:批量生成的风格一致性**——第 1 张作为视觉锚点,后续以这张为参考保持风格统一(电商详情图核心)

**资源**:4 核 8G(图像处理重)

---

## 4.6 Agent 4:影音师(视频与音频)

**职责**:视频生成、视频编辑、TTS、BGM、字幕、音频处理

**V1 阶段支持的 task_type**(反诈视频场景):

| task_type | 说明 | 主力 | 备用 | 是否长任务 |
|---|---|---|---|---|
| **video_compose** | **视频合成(端到端)** | (FFmpeg + MoviePy) | - | **是** |
| tts_generate | TTS 配音 | 火山引擎 TTS | 阿里云 TTS | 否 |
| audio_to_text | 语音识别 | Whisper v3 | 阿里云 ASR | 否 |
| bgm_select | BGM 选择 | (素材库匹配) | - | 否 |
| subtitle_generate | 字幕生成 | (Whisper + 时间戳) | - | 否 |
| subtitle_add | 加字幕 | (MoviePy) | - | 否 |
| bgm_add | 加 BGM | (MoviePy) | - | 否 |

**V1.5 阶段新增**:
- text_to_video:Veo 3 主力(长任务)
- image_to_video:Seedance 2 主力(长任务)
- video_describe、video_extract_frames、audio_extract
- video_cut、transition_apply

**工具集**:FFmpeg 6.0+、MoviePy 1.0+、Whisper v3、火山引擎 TTS SDK、BGM 素材库

**特殊能力:长任务异步执行**——视频合成 5-10 分钟通过 Celery 异步

**资源**:4 核 8G(视频处理重)
**Celery worker**:独立部署 2-4 个实例

**关键备注**:V1 的反诈视频用现成图 + TTS + BGM 拼成视频(不调 Veo/Seedance),V1.5 才需要文生/图生视频模型。

---

## 4.7 HR Agent(支持 Agent A)

**职责**:管理用户的 AI 团队

**核心场景**:
- 给用户推荐合适的 Agent("我应该用什么 Agent 处理这件事")
- 引导用户加 Skill 到自己的库
- 引导 Agent 进修(V2)
- 引导用户成为 Skill 创作者(V2)
- 解释 Agent 的能力边界

**部署**:独立微服务(agent-hr)
**资源**:2 核 4G
**模型**:DeepSeek-V4-Flash 主 + Haiku 备
**调用方式**:不接队列任务,直接 API 响应

**与分任务 Agent 的区别**:
- 不接 Redis Streams 任务队列
- 不参与 Skill 工作流执行
- 直接通过 API 收到主编排转发的消息
- 直接读业务数据库

**支持的 task_type**:hr_consultation(对话式咨询)

---

## 4.8 财务经理 Agent(支持 Agent B)

**职责**:管订阅、配额、成本

**核心场景**:
- 回答用户问"还剩多少配额"
- 主动提醒"本月已用 80%"
- 处理升级、续费请求
- 月度账单总结
- 解释计费规则

**部署**:独立微服务(agent-finance)
**资源**:2 核 4G
**模型**:DeepSeek-V4-Flash
**调用方式**:同 HR

**关键数据来源**:user_subscriptions 表、events 表(成本)、缓存的实时配额

**支持的 task_type**:finance_consultation(对话式咨询)

---

# 第 5 章 大模型 API 选型

## 5.1 选型策略

**主备双活**:每个场景定义主力模型 + 1-2 个备用模型

**国内主力 + 海外兜底**:
- 主力用国产模型(成本/延迟优势)
- 海外作为 fallback(稳定性兜底)

**按场景分模型**:
- 不同 task_type 用不同模型
- 同一 task_type 在不同 scenario 也可能用不同模型

**自动切换**:模型不健康时自动 fallback

**按需接入**:V1 用得上才接,V1.5 加新场景时再接

---

## 5.2 V1 阶段必接的文本模型(共 4 个)

### 5.2.1 DeepSeek-V4-Flash(主力轻量,V1 必接)

| 参数 | 值 |
|---|---|
| 总参数 | 284B |
| 激活参数 | 13B |
| 上下文 | 1M tokens |
| 速度 | 200-400ms |
| 价格(输入) | ¥1/M tokens |
| 价格(输出) | ¥4/M tokens |
| API 端点 | https://api.deepseek.com/v1/chat/completions |
| 接入方式 | OpenAI 兼容 |

**用途**:
- 主编排意图理解
- Skill 匹配 LLM 兜底
- 中断分类
- Brief 维护(Plan 模式)
- 互动消息生成
- 短文写作
- 摘要、信息提取
- HR / 财务经理对话

**为什么主力**:中文场景能力强、国内调用延迟低、价格便宜、1M 上下文

---

### 5.2.2 Claude Sonnet 4.6(主力推理,V1 必接)

| 参数 | 值 |
|---|---|
| 上下文 | 200K tokens |
| 速度 | 1-3s |
| 价格(输入) | ¥21/M tokens |
| 价格(输出) | ¥105/M tokens |
| API 端点 | https://api.anthropic.com/v1/messages |
| 接入方式 | Anthropic SDK / LiteLLM |

**用途**:
- 复杂分析推理
- 联网搜索(tool use 强)— **反诈视频调研**
- 数据整理(xlsx 输出)
- 图片描述、风格分析、质量评估(Vision)
- 跨调用 PPT 大纲生成(V1.5)

**为什么必接**:Tool use 业界顶尖、推理能力强、视觉理解能力(同 API)

**注意**:价格高,只在必要场景用

---

### 5.2.3 Claude Haiku 4.5(Fallback 轻量,V1 必接)

| 参数 | 值 |
|---|---|
| 上下文 | 200K tokens |
| 速度 | 500-800ms |
| 价格(输入) | ¥6/M tokens |
| 价格(输出) | ¥30/M tokens |

**用途**:
- 意图理解 fallback
- Skill 匹配 LLM 兜底 fallback
- 短文写作 fallback

**为什么作 fallback**:海外稳定性高、跟 DeepSeek-V4-Flash 用法相似(可平替)、跟 Sonnet 同 API key

---

### 5.2.4 GPT-5(深度兜底,V1 必接)

| 参数 | 值 |
|---|---|
| 上下文 | 256K tokens |
| 价格(输入) | ¥28/M tokens |
| 价格(输出) | ¥140/M tokens |

**用途**:
- 极端 fallback
- web_search 二级 fallback
- 视觉理解 fallback
- **image_quality_check 主力**(GPT-5 Vision 视觉评估强)

**为什么必接**:最后一道防线、Vision 能力强(质量校验)、不主力但不能没有

---

## 5.3 V1.5 阶段新增的文本模型(共 3 个)

### 5.3.1 DeepSeek-V4-Pro(主力长文,V1.5 加)

**用途(V1.5)**:公众号长文主力、结构化写作、翻译主力、数据整理便宜方案

**为什么 V1.5 加**:V1 阶段没有长文场景

**为什么主力长文用 V4-Pro 不用 Kimi K2**:价格便宜 6 倍、中文长文质量已经够好

### 5.3.2 Kimi K2(创意备用,V1.5 加)

**用途(V1.5)**:文学性创意类长文、DeepSeek-V4-Pro 的备用

### 5.3.3 豆包 Pro(抖音/小红书风格,V1.5 加)

**用途(V1.5)**:小红书爆款笔记主力、抖音口播脚本主力

**关键备注**:V1.5 上线时要做 A/B 测试,验证豆包 Pro 在小红书/抖音场景是否真的优于其他

---

## 5.4 图像生成模型

### 5.4.1 GPT Image 2(主力真实图,V1 必接)

| 参数 | 值 |
|---|---|
| 风格 | 真实、高质量 |
| 速度 | 5-15s |
| 价格 | ~¥0.5/张 |

**用途**:V1.5 高质量真实风格商品图、局部重绘、扩图
**V1 用途**:反诈视频配图(辅助,主要靠下载)

---

### 5.4.2 Seedream 3(批量主力,V1 必接)

| 参数 | 值 |
|---|---|
| 风格 | 通用,中英文 prompt |
| 速度 | 3-8s |
| 价格 | ~¥0.2/张 |

**用途**:**电商详情图分段图(批量生成,核心)**、通用图片生成

**为什么用于批量**:reference_image 参数支持好、风格保持能力强、价格便宜

---

### 5.4.3 V1.5 加:Nano Banana 2(卡通)

**用途**:卡通插画、儿童内容配图

### 5.4.4 V1.5 加:Kling Image(中国风)

**用途**:中国风、国潮设计、传统元素图

---

## 5.5 视觉理解(Vision)

### Claude Sonnet Vision(V1 必接,与文本同 API)

**用途**:图片描述(电商详情图风格分析)、风格分析、质量评估

### GPT-5 Vision(V1 必接,与文本同 API)

**用途**:image_quality_check 主力、Sonnet Vision 的 fallback

### V1.5 加:Qwen-VL(国产备用)

---

## 5.6 视频生成模型

### V1 阶段不接外部视频生成模型

V1 的反诈视频用**现成图 + TTS + BGM 拼成视频**(MoviePy + FFmpeg),不需要文生/图生视频模型。

省掉的接入:Veo 3、Seedance 2、Kling 2

**理由**:反诈视频场景下现成案例图比生成视频更真实可信、Veo/Seedance 单次成本 ¥3-5/秒、V1 阶段验证产品方向比追求高质量视频生成重要

### V1.5 加:Veo 3(文生视频主力)
### V1.5 加:Seedance 2(图生视频主力)
### V1.5 加:Kling 2(国产备用)

---

## 5.7 语音模型

### 5.7.1 火山引擎 TTS(主力中文,V1 必接)

| 参数 | 值 |
|---|---|
| 音色数量 | 100+ |
| 速度 | < 1s |
| 价格 | ~¥10/万字符 |

**用途**:反诈视频配音(主力)

### 5.7.2 阿里云 TTS(备用,V1 必接)

### 5.7.3 Whisper v3(语音识别,V1 必接)

| 价格 | OpenAI API ~¥0.04/分钟 |
|---|---|

**部署方式**:V1 用 OpenAI API,V2 自部署 faster-whisper

### 5.7.4 阿里云 ASR(国产备用,V1 必接)

---

## 5.8 Embedding 模型

### BGE-M3(主力,V1 必接)

| 参数 | 值 |
|---|---|
| 维度 | 1024 |
| 部署 | 自部署 / API |
| 价格 | 自部署成本 ¥500/月 GPU |

**用途**:Skill 描述向量化、用户消息向量化(检索)

**部署方式**:V1 用 GPU 实例自部署,FastAPI 包装

---

# 第 6 章 模型路由表

## 6.1 V1 阶段路由配置(基于 Agent 职责修正版)

```yaml
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 主编排相关
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- task_type: intent_understanding
  scenario: "*"
  primary: deepseek-v4-flash
  fallback_1: claude-haiku-4-5

- task_type: skill_matching
  scenario: "*"
  primary: deepseek-v4-flash  # 仅 LLM 兜底层
  fallback_1: claude-haiku-4-5

- task_type: brief_update      # Plan 模式
  scenario: "*"
  primary: deepseek-v4-flash
  fallback_1: claude-haiku-4-5

- task_type: agent_interaction_message  # 互动消息生成
  scenario: "*"
  primary: deepseek-v4-flash
  fallback_1: claude-haiku-4-5

- task_type: interrupt_classification
  scenario: "*"
  primary: deepseek-v4-flash
  fallback_1: claude-haiku-4-5

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Agent 1 文字
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- task_type: short_writing
  scenario: anti_fraud
  primary: deepseek-v4-flash
  fallback_1: claude-haiku-4-5
  fallback_2: gpt-5

- task_type: short_writing
  scenario: ecommerce
  primary: deepseek-v4-flash
  fallback_1: claude-haiku-4-5

- task_type: summarization
  scenario: "*"
  primary: deepseek-v4-flash
  fallback_1: claude-haiku-4-5

- task_type: extraction
  scenario: "*"
  primary: deepseek-v4-flash
  fallback_1: claude-haiku-4-5

- task_type: analysis
  scenario: "*"
  primary: claude-sonnet-4-6
  fallback_1: gpt-5
  fallback_2: deepseek-v4-flash

- task_type: web_search
  scenario: "*"
  primary: claude-sonnet-4-6
  fallback_1: gpt-5

- task_type: data_organize
  scenario: "*"
  primary: claude-sonnet-4-6
  fallback_1: deepseek-v4-flash

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Agent 2 文档(职责修正:从原 Agent 4 改来)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- task_type: image_concat_long  # 长图垂直拼接
  scenario: "*"
  primary: pillow_internal      # PIL 程序

- task_type: xlsx_create
  scenario: "*"
  primary: claude-sonnet-4-6    # 数据整理时
  fallback_1: deepseek-v4-flash

- task_type: docx_create
  scenario: "*"
  primary: python_docx_internal

- task_type: pdf_extract
  scenario: "*"
  primary: pdfplumber_internal

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Agent 3 图(职责修正:从原 Agent 2 改来)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- task_type: image_generate
  scenario: realistic
  primary: gpt-image-2
  fallback_1: seedream-3

- task_type: batch_generate
  scenario: ecommerce
  primary: seedream-3
  fallback_1: gpt-image-2
  routing_hints:
    style_consistency: high

- task_type: image_describe
  scenario: "*"
  primary: claude-sonnet-vision
  fallback_1: gpt-5-vision

- task_type: image_quality_check
  scenario: "*"
  primary: gpt-5-vision
  fallback_1: claude-sonnet-vision

- task_type: image_download
  scenario: "*"
  primary: httpx_internal

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Agent 4 视频(职责修正:从原 Agent 3 改来)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- task_type: video_compose
  scenario: "*"
  primary: ffmpeg_internal
  routing_hints:
    long_task: true

- task_type: tts_generate
  scenario: "*"
  primary: volcengine-tts
  fallback_1: aliyun-tts

- task_type: audio_to_text
  scenario: "*"
  primary: whisper-v3
  fallback_1: aliyun-asr

- task_type: bgm_select
  scenario: "*"
  primary: internal_match

- task_type: subtitle_generate
  scenario: "*"
  primary: whisper-v3            # 时间戳

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 支持 Agent
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- task_type: hr_consultation
  scenario: "*"
  primary: deepseek-v4-flash
  fallback_1: claude-haiku-4-5

- task_type: finance_consultation
  scenario: "*"
  primary: deepseek-v4-flash
  fallback_1: claude-haiku-4-5
```

## 6.2 V1.5 阶段新增路由

```yaml
# 长文场景
- task_type: long_writing
  scenario: gongzhonghao
  primary: deepseek-v4-pro
  fallback_1: kimi-k2
  fallback_2: claude-sonnet-4-6

- task_type: long_writing
  scenario: creative
  primary: kimi-k2
  fallback_1: deepseek-v4-pro

# 抖音/小红书场景
- task_type: short_writing
  scenario: xiaohongshu
  primary: doubao-pro
  fallback_1: deepseek-v4-flash

- task_type: short_writing
  scenario: douyin
  primary: doubao-pro
  fallback_1: deepseek-v4-flash

# 视频生成
- task_type: text_to_video
  scenario: "*"
  primary: veo-3
  fallback_1: seedance-2
  routing_hints:
    long_task: true

- task_type: image_to_video
  scenario: "*"
  primary: seedance-2
  fallback_1: kling-2

# V1.5 图像
- task_type: image_generate
  scenario: cartoon
  primary: nano-banana-2
  fallback_1: seedream-3

- task_type: image_generate
  scenario: chinese_style
  primary: kling-image
  fallback_1: seedream-3
```

## 6.3 路由决策优先级

(同 V2 文档)

## 6.4 健康度评估

(同 V2 文档)

---

# 第 7 章 第三方服务清单

## 7.1 V1 阶段必接的服务(共 11 个)

### LLM 类(4 个文本 + 共享 Vision)
| 优先级 | 服务商 | 模型 | 用途 |
|---|---|---|---|
| P0 | DeepSeek | v4-flash | 主力轻量 |
| P0 | Anthropic | Sonnet 4.6 | web_search、分析、图片理解 |
| P0 | Anthropic | Haiku 4.5 | Fallback 轻量 |
| P0 | OpenAI | GPT-5 | 深度兜底 + Vision 质量评估 |

注:Vision 跟文本同 API key,不算单独接入。

### 图像生成(2 个)
| 优先级 | 服务商 | 模型 | 用途 |
|---|---|---|---|
| P0 | OpenAI | GPT Image 2 | 真实风格图 |
| P0 | 字节豆包 | Seedream 3 | 批量生成(电商详情图) |

### 工具服务(1 个)
| 优先级 | 服务商 | 用途 |
|---|---|---|
| P0 | Tavily | Web Search(反诈视频调研) |

### 语音(3 个)
| 优先级 | 服务商 | 用途 |
|---|---|---|
| P0 | 火山引擎 TTS | 中文配音主力 |
| P0 | 阿里云 TTS | 备用 |
| P0 | OpenAI | Whisper v3(语音识别) |
| P1 | 阿里云 ASR | Whisper 备用 |

### Embedding(1 个,自部署)
| 优先级 | 模型 | 部署方式 |
|---|---|---|
| P0 | BGE-M3 | 自部署(GPU 实例) |

### 内容安全(1 个)
| 优先级 | 服务商 | 用途 |
|---|---|---|
| P1 | 阿里云内容安全 | 输入输出审核 |

**V1 阶段服务接入总数:11 个**

---

## 7.2 V1.5 阶段新增的服务(共 7 个)

### LLM 类(3 个)
- DeepSeek-V4-Pro(长文主力)
- Kimi K2(创意备用)
- 豆包 Pro(抖音/小红书风格)

### 图像生成(2 个)
- Nano Banana 2(卡通)
- Kling Image(中国风)

### 视频生成(2 个)
- Veo 3(文生视频)
- Seedance 2(图生视频)

**V1.5 阶段累计服务接入:18 个**

---

## 7.3 商务合作建议

V1 阶段优先签订企业合作的 API:
- DeepSeek
- Anthropic(Sonnet/Haiku 共享配额)
- 字节火山方舟(Seedream + 豆包 + Seedance + 火山 TTS 同生态)
- OpenAI(GPT + GPT Image 2 + Whisper 同 API key)

V1 阶段 API 账号管理:
- 火山方舟一个账号即可覆盖 Seedream + TTS(V1.5 加豆包/Seedance 同账号)
- Anthropic 一个 API key 同时调 Sonnet + Haiku
- OpenAI 一个 API key 同时调 GPT-5 + GPT Image 2 + Whisper

---

# 第 8 章 V1 阶段成本测算

## 8.1 单任务成本估算

### 反诈视频任务(单次)

| 步骤 | Agent | 模型 | 成本 |
|---|---|---|---|
| 案例调研 | Agent 1 | Sonnet 4.6 + Tavily | ¥1.5 |
| 脚本生成 | Agent 1 | DeepSeek-V4-Flash | ¥0.02 |
| **图片处理** | **Agent 3**(职责修正) | (下载 + PIL) | ¥0 |
| **配乐 + TTS** | **Agent 4**(职责修正) | 火山引擎 TTS + 素材库 | ¥0.5 |
| 字幕生成 | Agent 4 | Whisper API | ¥0.04 |
| **视频合成** | **Agent 4**(职责修正) | (FFmpeg + MoviePy) | ¥0(自建) |
| 主编排成本 | - | DeepSeek-V4-Flash × 15 次 | ¥0.05 |
| **小计** | | | **¥2.11** |

### 电商详情图任务(单次)

| 步骤 | Agent | 模型 | 成本 |
|---|---|---|---|
| **风格分析** | **Agent 3**(职责修正) | Sonnet Vision | ¥0.1 |
| 文案撰写 | Agent 1 | DeepSeek-V4-Flash | ¥0.02 |
| **分段图生成** | **Agent 3**(职责修正) | Seedream 3(5 张) | ¥1.0 |
| **长图拼接** | **Agent 2**(职责修正) | (PIL) | ¥0 |
| **质量校验** | **Agent 3**(职责修正) | GPT-5 Vision | ¥0.2 |
| 主编排成本 | - | DeepSeek-V4-Flash × 12 次 | ¥0.04 |
| **小计** | | | **¥1.36** |

## 8.2 月度成本估算

假设 V1 阶段 1000 DAU,人均 2 个任务/天:

| 项目 | 数量/月 | 单价 | 月成本 |
|---|---|---|---|
| 反诈视频任务 | 30000 | ¥2.11 | ¥63300 |
| 电商详情图任务 | 30000 | ¥1.36 | ¥40800 |
| Plan/Ask 模式 token | 1000000 个用户消息 | ¥0.001 | ¥1000 |
| HR/财务经理对话 | 200000 次 | ¥0.005 | ¥1000 |
| 基础设施 | - | - | ¥23500 |
| **总计** | | | **¥129600** |

按 1 美元 = ¥7.2 估算,约 **$18000/月**。

## 8.3 单用户经济模型

| 项 | 值 |
|---|---|
| ARPU(个人版) | ¥99/月 |
| 平均每用户任务/月 | 50 次(订阅个人版) |
| LLM 成本 | ¥30/月 |
| 基础设施分摊 | ¥10/月 |
| 单用户毛利 | ¥59/月 |
| 毛利率 | 60% |

## 8.4 成本优化策略

**短期(V1)**:
- 优先用便宜模型(DeepSeek-V4-Flash 主力)
- 严格用户配额
- 缓存 Skill 编译结果
- 流式输出避免重试
- web_search 调研结果缓存

**中期(V1.5)**:
- 长文用 DeepSeek-V4-Pro 而不是 Kimi K2
- 自部署 Whisper、BGE-M3、rembg 降本
- 智能缓存

---

# 第 9 章 接入与对接清单

## 9.1 V1 接入 Checklist(11 个服务)

### V1 接入顺序建议

**第 1 周**:接基础大模型
1. DeepSeek-V4-Flash
2. Anthropic(Sonnet + Haiku 同 API key)
3. OpenAI(GPT-5 + GPT Image 2 + Whisper 同 API key)

**第 2 周**:接专项服务
4. Tavily(Web Search)
5. Seedream 3(火山方舟)
6. 火山引擎 TTS(同账号)

**第 3 周**:接备用 + 自部署
7. 阿里云 TTS / ASR
8. BGE-M3(自部署 GPU 实例)
9. 阿里云内容安全

---

## 9.2 V1.5 接入 Checklist(7 个新服务)

V1.5 触发条件:V1 上线后 3 个月,准备加新 Skill 时。

**长文相关 Skill 上线前**:
- DeepSeek-V4-Pro(同 V4-Flash API key)
- Kimi K2(月之暗面账号)

**抖音/小红书 Skill 上线前**:
- 豆包 Pro(火山方舟,跟 Seedream 同账号)

**视频生成 Skill 上线前**:
- Veo 3(Google Cloud)
- Seedance 2(火山方舟)

**专业图像 Skill 上线前**:
- Nano Banana 2
- Kling Image

---

# 第 10 章 V2 演进路径

## 10.1 V1 → V1.5 升级清单

**触发条件**:V1 上线后 3 个月,准备加新 Skill

**升级动作**:
- 接入 7 个新模型
- 新增路由规则
- 训练运营团队对新场景的 A/B 测试

## 10.2 V1.5 → V2 升级清单

**触发条件**:V1.5 上线后 6 个月,流量上升

**升级动作**:
- Celery → Temporal
- Docker Compose → K8s
- Redis Streams → Kafka
- PostgreSQL 加分区
- 自部署 Whisper / rembg 降本

## 10.3 V3 远期(12+ 月)

- 自研垂直小模型
- 多 Region 部署
- 边缘计算节点

## 10.4 不可逆决策的留意

(同前文)

---

# 附录:快速对接参考

## A. LiteLLM 配置示例(V1 阶段,YAML)

```yaml
model_list:
  # V1 必接 - DeepSeek
  - model_name: deepseek-v4-flash
    litellm_params:
      model: deepseek/deepseek-v4-flash
      api_key: os.environ/DEEPSEEK_API_KEY
      api_base: https://api.deepseek.com/v1
  
  # V1 必接 - Anthropic
  - model_name: claude-sonnet-4-6
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY
  
  - model_name: claude-haiku-4-5
    litellm_params:
      model: anthropic/claude-haiku-4-5
      api_key: os.environ/ANTHROPIC_API_KEY
  
  # V1 必接 - OpenAI
  - model_name: gpt-5
    litellm_params:
      model: openai/gpt-5
      api_key: os.environ/OPENAI_API_KEY
  
  - model_name: gpt-image-2
    litellm_params:
      model: openai/gpt-image-2
      api_key: os.environ/OPENAI_API_KEY
  
  # V1 必接 - 字节火山方舟
  - model_name: seedream-3
    litellm_params:
      model: bytedance/seedream-3
      api_key: os.environ/VOLCENGINE_API_KEY
      api_base: https://ark.cn-beijing.volces.com/api/v3
  
  # V1.5 加 - 长文场景
  - model_name: deepseek-v4-pro
    litellm_params:
      model: deepseek/deepseek-v4-pro
      api_key: os.environ/DEEPSEEK_API_KEY
      api_base: https://api.deepseek.com/v1
  
  - model_name: kimi-k2
    litellm_params:
      model: openai/kimi-k2
      api_key: os.environ/KIMI_API_KEY
      api_base: https://api.moonshot.cn/v1
  
  # V1.5 加 - 抖音/小红书
  - model_name: doubao-pro
    litellm_params:
      model: bytedance/doubao-pro
      api_key: os.environ/VOLCENGINE_API_KEY
      api_base: https://ark.cn-beijing.volces.com/api/v3

router_settings:
  routing_strategy: usage-based-routing-v2
  fallbacks: ...

litellm_settings:
  set_verbose: false
  drop_params: true
  cache: true
  cache_params:
    type: redis
```

## B. 各供应商关键文档链接

| 供应商 | 文档 |
|---|---|
| DeepSeek | https://platform.deepseek.com/api-docs |
| Anthropic | https://docs.anthropic.com |
| OpenAI | https://platform.openai.com/docs |
| 火山方舟(字节) | https://www.volcengine.com/docs/82379 |
| 火山引擎 TTS | https://www.volcengine.com/docs/6561 |
| 月之暗面(Kimi) | https://platform.moonshot.cn/docs |
| 阿里云 | https://help.aliyun.com |
| Google Cloud(Veo) | https://cloud.google.com/vertex-ai |
| 快手可灵 | https://klingai.com/docs |
| LiteLLM | https://docs.litellm.ai |
| LangGraph | https://langchain-ai.github.io/langgraph |

## C. 应急预案

(同前文)

---

# 文档说明

**关键决策汇总**:

### V1 阶段(立即接入,11 个服务)

**文本 LLM(4 个)**:
- DeepSeek-V4-Flash(主力轻量)
- Claude Sonnet 4.6(主力推理 + web_search)
- Claude Haiku 4.5(Fallback 轻量)
- GPT-5(深度兜底 + Vision 质量评估)

**图像生成(2 个)**:
- GPT Image 2(真实风格)
- Seedream 3(批量生成,电商详情图)

**语音(3 个)**:
- 火山引擎 TTS(主力)
- 阿里云 TTS(备用)
- Whisper v3(语音识别,OpenAI API)

**工具(1 个)**:Tavily

**自部署(1 个)**:BGE-M3

### V1.5 阶段(加新 Skill 时接入,7 个服务)

**长文相关(2 个)**:DeepSeek-V4-Pro + Kimi K2

**抖音/小红书(1 个)**:豆包 Pro

**视频生成(2 个)**:Veo 3 + Seedance 2

**专业图像(2 个)**:Nano Banana 2 + Kling Image / Kling 2

### Agent 职责对应(V2 修正)

- Agent 1 = 文字(研究员/文案师)
- **Agent 2 = 文档**(从原"图"修正)
- **Agent 3 = 图**(从原"视频"修正)
- **Agent 4 = 视频**(从原"文档"修正)

---

**文档版本历史**:

| 版本 | 日期 | 主要变更 |
|---|---|---|
| V1.0 | 2026-05-04 | 首版 |
| V2.0 | 2026-05-04 | V1/V1.5 阶段分离 |
| V3.0 | 2026-05-04 | Agent 2/3/4 职责修正;新增 HR/财务经理 2 个支持 Agent;新增互动消息生成路由;反诈视频/电商详情图场景 Agent 调用对应修正 |
