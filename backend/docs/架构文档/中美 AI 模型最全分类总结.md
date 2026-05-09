## 中美 AI 模型最全分类总结

 **抓取日期**:2026年5月5日

------

## 1.通用对话 / 文案写作 (Text Arena)

| 排名   | 模型                        | 国家 | Elo           | 价格 in/out per M | 协议    |
| ------ | --------------------------- | ---- | ------------- | ----------------- | ------- |
| 1      | claude-opus-4-7-thinking    | 🇺🇸   | 1503          | $5/$25            | 闭源    |
| 2      | claude-opus-4-6-thinking    | 🇺🇸   | 1502          | $5/$25            | 闭源    |
| 3      | gemini-3.1-pro              | 🇺🇸   | 1493          | $2/$12            | 闭源    |
| 4      | meta-muse-spark             | 🇺🇸   | 1490 *Prelim* | N/A               | 闭源    |
| 5      | gpt-5.5-high                | 1488 | 🇺🇸            | $5/$30            | 闭源    |
| **15** | **ernie-5.1-preview(百度)** | 🇨🇳   | 1475 *Prelim* | N/A               | 闭源    |
| **18** | **glm-5.1(智谱)**           | 🇨🇳   | 1471          | $1.40/$4.40       | MIT     |
| **22** | **mimo-v2.5-pro(小米)**     | 🇨🇳   | 1463          | $1/$3             | MIT     |
| **24** | **deepseek-v4-pro**         | 🇨🇳   | 1463          | $0.43/$0.87 ⭐     | MIT     |
| **25** | **qwen3.5-max-preview**     | 🇨🇳   | 1463          | N/A               | 闭源    |
| **28** | **kimi-k2.6**               | 🇨🇳   | 1460          | $0.95/$4          | Mod-MIT |
| **30** | **dola-seed-2.0-pro(字节)** | 🇨🇳   | 1459          | N/A               | 闭源    |

**🏆 全球第一**:Claude Opus 4.7-thinking
 **🇨🇳 中国第一**:ERNIE 5.1(百度,Preliminary)→ 实际稳定第一是 GLM-5.1
 **💰 性价比之王**:**DeepSeek V4-Pro**($0.43/$0.87,Elo 1463)— 比 Claude 便宜 12 倍

------

## 2. 文生视频 (Text-to-Video Arena)

| 排名   | 模型                                     | 国家 | Elo               |
| ------ | ---------------------------------------- | ---- | ----------------- |
| **1**  | **dreamina-seedance-2.0-720p(字节即梦)** | 🇨🇳   | **1460**          |
| **2**  | **happyhorse-1.0(阿里-ATH)**             | 🇨🇳   | **1444** *Prelim* |
| 3      | veo-3.1-audio-1080p                      | 🇺🇸   | 1375              |
| 4      | veo-3.1-fast-audio-1080p                 | 🇺🇸   | 1368              |
| 5      | sora-2-pro                               | 🇺🇸   | 1366              |
| 8      | grok-imagine-video-720p                  | 🇺🇸   | 1359              |
| **10** | **wan2.6-t2v(阿里通义万相)**             | 🇨🇳   | 1345              |
| **20** | **kling-2.6-pro(快手)**                  | 🇨🇳   | 1219              |

**🏆 全球第一 = 中国第一**:Seedance 2.0(把 Veo/Sora 甩开 85+ 分)
 **这是中国唯一全面碾压美国的领域**

------

## 4️⃣ 图生视频 (Image-to-Video Arena)

| 排名   | 模型                                 | 国家 | Elo               |
| ------ | ------------------------------------ | ---- | ----------------- |
| **1**  | **dreamina-seedance-2.0-720p(字节)** | 🇨🇳   | **1454**          |
| **2**  | **happyhorse-1.0(阿里-ATH)**         | 🇨🇳   | **1444** *Prelim* |
| 3      | grok-imagine-video-720p              | 🇺🇸   | 1421              |
| 4      | veo-3.1-audio-1080p                  | 🇺🇸   | 1402              |
| 5      | veo-3.1-audio                        | 🇺🇸   | 1396              |
| **9**  | **vidu-q3-pro(生数科技)**            | 🇨🇳   | 1359              |
| **10** | **kling-v3-pro(快手)**               | 🇨🇳   | 1357              |
| **11** | **wan2.5-i2v-preview(阿里)**         | 🇨🇳   | 1334              |
| **14** | **wan2.6-i2v**                       | 🇨🇳   | 1308              |
| **22** | **hailuo-2.3**                       | 🇨🇳   | 1255              |
| **31** | **hunyuan-video-1.5(腾讯)**          | 🇨🇳   | 1195              |

**🏆 全球第一 = 中国第一**:Seedance 2.0
 **📌 注**:Vidu Q3 Pro 是图生视频专项,多参考图一致性最强

------

## 5️⃣ 文生图 (Text-to-Image Arena)

| 排名   | 模型                                   | 国家 | Elo           |
| ------ | -------------------------------------- | ---- | ------------- |
| 1      | **gpt-image-2 (medium)**               | 🇺🇸   | 1507 *Prelim* |
| 2      | gemini-3.1-flash-image (Nano-Banana 2) | 🇺🇸   | 1271          |
| 3      | gemini-3-pro-image-2k                  | 🇺🇸   | 1244          |
| 4      | gpt-image-1.5-high-fidelity            | 🇺🇸   | 1242          |
| 5      | gemini-3-pro-image                     | 🇺🇸   | 1232          |
| 6      | mai-image-2(微软)                      | 🇺🇸   | 1183          |
| **9**  | **qwen-image-2.0-pro(阿里)**           | 🇨🇳   | 1168          |
| **15** | **hunyuan-image-3.0(腾讯)**            | 🇨🇳   | 1151          |
| **18** | **seedream-4.5(字节)**                 | 🇨🇳   | 1142          |
| **20** | **qwen-image-2512**                    | 🇨🇳   | 1133          |

**🏆 全球第一**:GPT-Image-2,中国第一(Qwen)落后 339 分
 **这是中国差距最大的领域**

------

## 6️⃣ 图像编辑 (Image Edit Arena - Single Image)

| 排名   | 模型                                    | 国家 | Elo           |
| ------ | --------------------------------------- | ---- | ------------- |
| 1      | gpt-image-2 (medium)                    | 🇺🇸   | 1510 *Prelim* |
| 2      | chatgpt-image-latest-high-fidelity      | 🇺🇸   | 1393          |
| 3      | gemini-3-pro-image-2k (Nano-Banana Pro) | 🇺🇸   | 1389          |
| 4      | gemini-3-pro-image                      | 🇺🇸   | 1387          |
| 5      | gemini-3.1-flash-image                  | 🇺🇸   | 1387          |
| 6      | gpt-image-1.5-high-fidelity             | 🇺🇸   | 1376          |
| **10** | **seedream-4.5(字节)**                  | 🇨🇳   | **1304**      |
| **11** | **wan2.7-image-pro(阿里)**              | 🇨🇳   | 1304          |
| **12** | **wan2.7-image**                        | 🇨🇳   | 1303          |
| **14** | **hunyuan-image-3.0(腾讯)**             | 🇨🇳   | 1299          |
| **17** | **qwen-image-2.0-pro**                  | 🇨🇳   | 1272          |
| **23** | **qwen-image-edit(开源 Apache 2.0)**    | 🇨🇳   | 1239          |

**🏆 全球第一**:GPT-Image-2(美国包揽前 9)
 **🇨🇳 中国第一**:Seedream 4.5(字节)/ Wan2.7-image
 **💡 这个分类对你电商图二次修改、产品图换背景特别关键**

------

## 7️⃣ 多模态视觉理解 (Vision Arena)

**811,827 票 | 120 模型 | 2026-05-01**

| 排名   | 模型                             | 国家 | Elo           |
| ------ | -------------------------------- | ---- | ------------- |
| 1      | claude-opus-4-6-thinking         | 🇺🇸   | 1303          |
| 2      | claude-opus-4-7-thinking         | 🇺🇸   | 1302          |
| 3      | claude-opus-4-7                  | 🇺🇸   | 1299          |
| 4      | meta-muse-spark                  | 🇺🇸   | 1294 *Prelim* |
| 5      | gpt-5.5                          | 🇺🇸   | 1293          |
| 6      | gemini-3-pro                     | 🇺🇸   | 1288          |
| **13** | **kimi-k2.6**                    | 🇨🇳   | **1261**      |
| **15** | **dola-seed-2.0-pro(字节)**      | 🇨🇳   | 1259          |
| **20** | **kimi-k2.5-thinking**           | 🇨🇳   | 1247          |
| **24** | **qwen3.5-397b-a17b**            | 🇨🇳   | 1242          |
| **30** | **glm-5v-turbo(智谱)**           | 🇨🇳   | 1227          |
| **37** | **ernie-5.0-preview-1220(百度)** | 🇨🇳   | 1218          |

**🏆 全球第一**:Claude Opus 4.6
 **🇨🇳 中国第一**:Kimi K2.6($0.95/$4,Elo 1261)
 **💰 性价比**:Qwen3.5-397B-A17B($0.39/$2.34,Apache 2.0,可自部署)

------

## 8️⃣ 联网搜索 / Grounding (Search Arena)

**490,941 票 | 28 模型 | 2026-05-01**

| 排名 | 模型                     | 国家 | Elo  |
| ---- | ------------------------ | ---- | ---- |
| 1    | claude-opus-4-6-search   | 🇺🇸   | 1255 |
| 2    | gpt-5.5-search           | 🇺🇸   | 1235 |
| 3    | claude-opus-4-7          | 🇺🇸   | 1233 |
| 4    | claude-sonnet-4-6-search | 🇺🇸   | 1221 |
| 5    | gemini-3.1-pro-grounding | 🇺🇸   | 1218 |
| 6    | gpt-5.2-search           | 🇺🇸   | 1213 |

⚠️ **Search Arena 没有任何中国模型上榜**——LMArena Search Arena 默认接入英文搜索引擎,中国模型(豆包搜索、Kimi 探索版、文心一言搜索、通义搜索)虽然在国内可用,但没有提交到 LMArena。
 **给中国客户做产品时**:豆包搜索 / Kimi 探索版 / 文心搜索是国内合规可用的,但缺权威盲测数据。

------

## 9️⃣ Agent / 工具调用 (BFCL v3 / tau-bench)

**来源:awesomeagents.ai 4月17日聚合榜**

### A. 结构化函数调用 (BFCL v3)

| 排名 | 模型                       | 国家 | BFCL v3          |
| ---- | -------------------------- | ---- | ---------------- |
| 1    | **GLM 4.5 Thinking(智谱)** | 🇨🇳   | **76.7%**        |
| 2    | Qwen3 32B / Thinking       | 🇨🇳   | 75.7%            |
| 4    | Qwen3 Max                  | 🇨🇳   | 74.9%            |
| 5    | GLM-4.7-Flash              | 🇨🇳   | 74.6%            |
| 13   | Gemini 3 Flash             | 🇺🇸   | 53.5%            |
| 18   | Claude Opus 4              | 🇺🇸   | 25.3% (格式问题) |

**🇨🇳 中国在结构化 JSON 输出领先**

### B. 多轮对话工具编排 (tau-bench Retail)

| 排名 | 模型              | 国家 | Score     |
| ---- | ----------------- | ---- | --------- |
| 1    | Claude Sonnet 4.5 | 🇺🇸   | 0.862     |
| 2    | Claude Opus 4.1   | 🇺🇸   | 0.824     |
| 3    | Claude Opus 4     | 🇺🇸   | 0.814     |
| 6    | **GLM-4.5(智谱)** | 🇨🇳   | **0.797** |
| 7    | GLM-4.5-Air       | 🇨🇳   | 0.779     |
| 8    | Qwen3-Coder 480B  | 🇨🇳   | 0.775     |

**🇺🇸 美国在多轮容错编排领先**

------

# 全分类汇总表

| #    | 场景            | 全球第一             | 国   | 中国第一              | 国内性价比之王                   |
| ---- | --------------- | -------------------- | ---- | --------------------- | -------------------------------- |
| 1    | 通用对话/写作   | Claude Opus 4.7      | 🇺🇸   | GLM-5.1 / DeepSeek V4 | **DeepSeek V4-Pro**($0.43/$0.87) |
| 2    | Web 开发        | Claude Opus 4.7      | 🇺🇸   | GLM-5.1               | Qwen3.6-Plus($0.33/$1.95)        |
| 3    | 文生视频        | **Seedance 2.0**     | 🇨🇳   | (本身)                | Wan2.6-t2v                       |
| 4    | 图生视频        | **Seedance 2.0**     | 🇨🇳   | (本身)                | Vidu Q3 Pro                      |
| 5    | 文生图          | GPT-Image-2          | 🇺🇸   | Qwen-Image-2.0-Pro    | Qwen-Image-2512(Apache 2.0)      |
| 6    | 图像编辑        | GPT-Image-2          | 🇺🇸   | Seedream 4.5 / Wan2.7 | Qwen-Image-Edit(Apache 2.0)      |
| 7    | 视觉理解        | Claude Opus 4.6      | 🇺🇸   | Kimi K2.6             | Qwen3.5-397B(Apache 2.0,$0.39)   |
| 8    | 联网搜索        | Claude Opus 4.6      | 🇺🇸   | (无榜数据)            | 豆包搜索 / Kimi 探索版           |
| 9a   | 函数调用        | **GLM 4.5 Thinking** | 🇨🇳   | (本身)                | Qwen3 32B($0.08/$0.24)           |
| 9b   | 多轮 Agent 编排 | Claude Sonnet 4.5    | 🇺🇸   | GLM-4.5               | GLM-4.5-Air                      |

