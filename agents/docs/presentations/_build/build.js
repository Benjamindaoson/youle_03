// 给老板的智能体技术架构 PPT — youle_mas
// 9 维度全栈能力 · 9 篇 ADR 治理 · production-grade

const pptxgen = require("pptxgenjs");
const path = require("path");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.3 × 7.5
pres.author = "Benjamin";
pres.title = "youle_mas 智能体技术架构";

// ─── 调色板:Midnight Executive + Coral 强调 ───
const C = {
  navy:    "1E2761", // 主色
  navyDk:  "0F1838", // 深背景
  ice:     "CADCFC", // 次色
  coral:   "F96167", // 强调色
  white:   "FFFFFF",
  bgSoft:  "F8FAFC",
  textDk:  "1E1E1E",
  textMut: "64748B",
  green:   "10B981",
  amber:   "F59E0B",
};

const F = { head: "Cambria", body: "Calibri" };

// 工具:小标题 + 装饰小条
function addBigTitle(slide, text, opts = {}) {
  slide.addText(text, {
    x: 0.7, y: 0.5, w: 12, h: 0.9,
    fontSize: opts.size || 32, fontFace: F.head, bold: true,
    color: opts.color || C.navy, margin: 0,
  });
}

function addPageNum(slide, n, total) {
  slide.addText(`${n} / ${total}`, {
    x: 12.0, y: 7.05, w: 0.9, h: 0.3,
    fontSize: 9, color: C.textMut, align: "right", fontFace: F.body,
  });
}

const TOTAL = 12;

// ════════════════════════════════════════════════════════════════
// Slide 1 — 封面
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.navyDk };

  // 装饰圆斑
  s.addShape(pres.shapes.OVAL, {
    x: -2, y: -2, w: 6, h: 6,
    fill: { color: C.navy, transparency: 50 }, line: { type: "none" },
  });
  s.addShape(pres.shapes.OVAL, {
    x: 9, y: 4, w: 5.5, h: 5.5,
    fill: { color: C.coral, transparency: 75 }, line: { type: "none" },
  });

  // 主标题
  s.addText("youle_mas", {
    x: 0.9, y: 2.3, w: 12, h: 0.8,
    fontSize: 22, color: C.ice, fontFace: F.body,
    charSpacing: 8, bold: false, margin: 0,
  });
  s.addText("智能体技术架构", {
    x: 0.9, y: 2.9, w: 12, h: 1.2,
    fontSize: 56, fontFace: F.head, bold: true, color: C.white, margin: 0,
  });
  s.addText("Multi-Agent Architecture · Strategic Briefing", {
    x: 0.9, y: 4.3, w: 12, h: 0.5,
    fontSize: 16, color: C.ice, fontFace: F.body, italic: true, margin: 0,
  });

  // 红色细线
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.9, y: 4.95, w: 1.2, h: 0.05,
    fill: { color: C.coral }, line: { type: "none" },
  });

  // 三标签
  const tags = ["9 维度全栈", "9 篇 ADR 治理", "Production-grade"];
  tags.forEach((t, i) => {
    s.addText(t, {
      x: 0.9 + i * 2.7, y: 5.3, w: 2.5, h: 0.5,
      fontSize: 13, fontFace: F.body, color: C.ice, align: "center", valign: "middle",
      fill: { color: C.navy }, margin: 0,
    });
  });

  // Footer
  s.addText("Benjamin · 2026-05-09", {
    x: 0.9, y: 6.85, w: 12, h: 0.3,
    fontSize: 10, color: C.ice, fontFace: F.body, margin: 0,
  });
}

// ════════════════════════════════════════════════════════════════
// Slide 2 — 一句话定位 (TL;DR)
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bgSoft };

  s.addText("01 / 一句话定位", {
    x: 0.7, y: 0.45, w: 6, h: 0.4,
    fontSize: 13, color: C.textMut, fontFace: F.body, charSpacing: 4, margin: 0,
  });

  s.addText("不是单一智能体,是工业级多智能体平台", {
    x: 0.7, y: 1.0, w: 12, h: 0.9,
    fontSize: 36, fontFace: F.head, bold: true, color: C.navy, margin: 0,
  });

  s.addText([
    { text: "主编排 ", options: { fontSize: 22, color: C.coral, bold: true } },
    { text: "+", options: { fontSize: 22, color: C.textMut } },
    { text: " 4 工种 worker ", options: { fontSize: 22, color: C.coral, bold: true } },
    { text: "+", options: { fontSize: 22, color: C.textMut } },
    { text: " 9 MCP 工具服务", options: { fontSize: 22, color: C.coral, bold: true } },
  ], {
    x: 0.7, y: 2.1, w: 12, h: 0.6, fontFace: F.body, margin: 0,
  });

  s.addText(
    "全 9 维度(意图、澄清、HITL、编排、工具、记忆、通信、状态、上下文)production-grade 落地,与 2026 硅谷一线(Manus / Devin / Anthropic Skills)同档骨架。",
    {
      x: 0.7, y: 2.85, w: 12, h: 0.9,
      fontSize: 14, fontFace: F.body, color: C.textDk, margin: 0, paraSpaceAfter: 6,
    }
  );

  // 三个 stat cards
  const stats = [
    { num: "9", label: "技术维度", sub: "意图 → 上下文,全栈覆盖" },
    { num: "9", label: "ADR 治理", sub: "架构决策有据可查" },
    { num: "35+", label: "新增模块", sub: "150+ 单测 case" },
  ];
  stats.forEach((st, i) => {
    const x = 0.7 + i * 4.15;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 4.3, w: 3.85, h: 2.4,
      fill: { color: C.white }, line: { color: C.ice, width: 1 },
      shadow: { type: "outer", color: "000000", blur: 12, offset: 3, angle: 90, opacity: 0.06 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 4.3, w: 3.85, h: 0.08,
      fill: { color: C.coral }, line: { type: "none" },
    });
    s.addText(st.num, {
      x, y: 4.55, w: 3.85, h: 1.2,
      fontSize: 72, fontFace: F.head, bold: true, color: C.navy,
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(st.label, {
      x, y: 5.85, w: 3.85, h: 0.35,
      fontSize: 16, fontFace: F.body, bold: true, color: C.textDk,
      align: "center", margin: 0,
    });
    s.addText(st.sub, {
      x: x + 0.2, y: 6.25, w: 3.45, h: 0.4,
      fontSize: 11, fontFace: F.body, color: C.textMut,
      align: "center", margin: 0,
    });
  });

  addPageNum(s, 2, TOTAL);
}

// ════════════════════════════════════════════════════════════════
// Slide 3 — 整体架构图
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bgSoft };

  s.addText("02 / 系统架构总览", {
    x: 0.7, y: 0.45, w: 6, h: 0.4,
    fontSize: 13, color: C.textMut, fontFace: F.body, charSpacing: 4, margin: 0,
  });
  s.addText("分层架构 + 异步消息总线", {
    x: 0.7, y: 0.95, w: 12, h: 0.7,
    fontSize: 28, fontFace: F.head, bold: true, color: C.navy, margin: 0,
  });

  // ─ 用户/前端 ─
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 5.45, y: 1.95, w: 2.4, h: 0.55,
    fill: { color: C.navy }, line: { type: "none" }, rectRadius: 0.08,
  });
  s.addText("用户 · 前端 (Next.js)", {
    x: 5.45, y: 1.95, w: 2.4, h: 0.55,
    fontSize: 12, fontFace: F.body, bold: true, color: C.white,
    align: "center", valign: "middle", margin: 0,
  });

  // 箭头线
  s.addShape(pres.shapes.LINE, {
    x: 6.65, y: 2.5, w: 0, h: 0.4, line: { color: C.textMut, width: 2 },
  });
  s.addText("WebSocket", {
    x: 5.4, y: 2.55, w: 2.5, h: 0.25, fontSize: 9, color: C.textMut, fontFace: F.body, align: "center", margin: 0,
  });

  // ─ 后端 + 主编排 ─
  s.addShape(pres.shapes.RECTANGLE, {
    x: 1.3, y: 2.95, w: 10.7, h: 1.2,
    fill: { color: C.white }, line: { color: C.ice, width: 1 },
    shadow: { type: "outer", color: "000000", blur: 8, offset: 2, angle: 90, opacity: 0.05 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 1.3, y: 2.95, w: 0.06, h: 1.2,
    fill: { color: C.coral }, line: { type: "none" },
  });
  s.addText("Backend · FastAPI", {
    x: 1.55, y: 3.05, w: 4.5, h: 0.4,
    fontSize: 14, fontFace: F.head, bold: true, color: C.navy, margin: 0,
  });
  s.addText("API · WS · Result Waiter · 用户态 · DB 镜像", {
    x: 1.55, y: 3.45, w: 4.5, h: 0.3,
    fontSize: 10, color: C.textMut, fontFace: F.body, margin: 0,
  });

  s.addShape(pres.shapes.LINE, {
    x: 6.3, y: 3.1, w: 0, h: 0.95, line: { color: C.ice, width: 1 },
  });

  s.addText("主编排 · LangGraph Runner", {
    x: 6.55, y: 3.05, w: 5.3, h: 0.4,
    fontSize: 14, fontFace: F.head, bold: true, color: C.navy, margin: 0,
  });
  s.addText("Planner · Critic · HITL · Persona · Time-travel", {
    x: 6.55, y: 3.45, w: 5.3, h: 0.3,
    fontSize: 10, color: C.textMut, fontFace: F.body, margin: 0,
  });

  // 中间:Redis Streams Bus
  s.addText("⇣ Redis Streams (agent_tasks:* / agent_results:* / flywheel:*) ⇣", {
    x: 1.3, y: 4.25, w: 10.7, h: 0.35,
    fontSize: 11, fontFace: F.body, italic: true, color: C.coral, align: "center", margin: 0,
  });

  // ─ 4 worker ─
  const workers = [
    { name: "agent_1", role: "文字 / 调研", color: C.navy },
    { name: "agent_2", role: "文档专员", color: C.navy },
    { name: "agent_3", role: "设计师", color: C.navy },
    { name: "agent_4", role: "影音师", color: C.navy },
  ];
  workers.forEach((w, i) => {
    const x = 1.3 + i * 2.75;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 4.7, w: 2.5, h: 1.05,
      fill: { color: C.white }, line: { color: C.ice, width: 1 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 4.7, w: 2.5, h: 0.08,
      fill: { color: C.navy }, line: { type: "none" },
    });
    s.addText(w.name, {
      x: x + 0.1, y: 4.85, w: 2.3, h: 0.35,
      fontSize: 13, fontFace: F.head, bold: true, color: C.navy, margin: 0,
    });
    s.addText(w.role, {
      x: x + 0.1, y: 5.25, w: 2.3, h: 0.3,
      fontSize: 11, color: C.textMut, fontFace: F.body, margin: 0,
    });
    s.addText("ReAct + MCP", {
      x: x + 0.1, y: 5.5, w: 2.3, h: 0.25,
      fontSize: 9, color: C.coral, fontFace: F.body, italic: true, margin: 0,
    });
  });

  // ─ MCP 工具层 ─
  s.addShape(pres.shapes.RECTANGLE, {
    x: 1.3, y: 6.0, w: 10.7, h: 0.85,
    fill: { color: C.navy }, line: { type: "none" },
  });
  s.addText("9 个 MCP 工具服务 (HTTP)", {
    x: 1.3, y: 6.05, w: 10.7, h: 0.3,
    fontSize: 12, fontFace: F.head, bold: true, color: C.white,
    align: "center", margin: 0,
  });
  s.addText("search · image_tools · video_tools · audio_tools · document_tools · oss · platform_publish · browser_use · code_executor", {
    x: 1.3, y: 6.4, w: 10.7, h: 0.4,
    fontSize: 10, color: C.ice, fontFace: F.body, align: "center", margin: 0,
  });

  addPageNum(s, 3, TOTAL);
}

// ════════════════════════════════════════════════════════════════
// Slide 4 — 9 维度能力一览
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bgSoft };

  s.addText("03 / 全栈覆盖", {
    x: 0.7, y: 0.45, w: 6, h: 0.4,
    fontSize: 13, color: C.textMut, fontFace: F.body, charSpacing: 4, margin: 0,
  });
  s.addText("9 维度能力一览", {
    x: 0.7, y: 0.95, w: 12, h: 0.7,
    fontSize: 28, fontFace: F.head, bold: true, color: C.navy, margin: 0,
  });

  const dims = [
    { num: "01", title: "意图理解", desc: "Pydantic Intent · 7 类 × 6 域", file: "intent.py" },
    { num: "02", title: "意图澄清", desc: "5 种交互形式 · ≤ 5 轮", file: "clarification.py" },
    { num: "03", title: "Human in the Loop", desc: "WS gate · Time-travel rollback", file: "hitl_gate.py" },
    { num: "04", title: "任务编排", desc: "LangGraph + Planner · 双轨", file: "langgraph_runner/" },
    { num: "05", title: "工具调用", desc: "MCP-first · Retry × Cache × ReAct", file: "react_runner.py" },
    { num: "06", title: "记忆模块", desc: "工作 / 情景 / 语义 / 程序 4 层", file: "skill_registry.py" },
    { num: "07", title: "通信协议", desc: "Redis Streams · DLQ · 心跳", file: "consumer.py" },
    { num: "08", title: "状态管理", desc: "PostgresSaver checkpoint · 镜像", file: "state.py" },
    { num: "09", title: "上下文窗口", desc: "OSS hydrate · ReAct 步数硬上限", file: "artifact_body.py" },
  ];

  dims.forEach((d, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = 0.7 + col * 4.15;
    const y = 1.85 + row * 1.65;

    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 3.85, h: 1.45,
      fill: { color: C.white }, line: { color: C.ice, width: 1 },
      shadow: { type: "outer", color: "000000", blur: 8, offset: 2, angle: 90, opacity: 0.06 },
    });
    // 左侧色条
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.08, h: 1.45,
      fill: { color: C.coral }, line: { type: "none" },
    });
    s.addText(d.num, {
      x: x + 0.25, y: y + 0.15, w: 0.7, h: 0.35,
      fontSize: 11, color: C.coral, fontFace: F.body, bold: true, charSpacing: 4, margin: 0,
    });
    s.addText("✓", {
      x: x + 3.4, y: y + 0.15, w: 0.35, h: 0.35,
      fontSize: 16, color: C.green, bold: true, fontFace: F.body, align: "center", margin: 0,
    });
    s.addText(d.title, {
      x: x + 0.25, y: y + 0.5, w: 3.5, h: 0.4,
      fontSize: 16, fontFace: F.head, bold: true, color: C.navy, margin: 0,
    });
    s.addText(d.desc, {
      x: x + 0.25, y: y + 0.92, w: 3.5, h: 0.3,
      fontSize: 10, color: C.textDk, fontFace: F.body, margin: 0,
    });
    s.addText(d.file, {
      x: x + 0.25, y: y + 1.18, w: 3.5, h: 0.25,
      fontSize: 9, color: C.textMut, fontFace: "Consolas", italic: true, margin: 0,
    });
  });

  addPageNum(s, 4, TOTAL);
}

// ════════════════════════════════════════════════════════════════
// Slide 5 — 智能化大脑(意图 / 澄清 / 编排)
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bgSoft };

  s.addText("04 / Deep Dive · I", {
    x: 0.7, y: 0.45, w: 6, h: 0.4,
    fontSize: 13, color: C.textMut, fontFace: F.body, charSpacing: 4, margin: 0,
  });
  s.addText("智能化大脑", {
    x: 0.7, y: 0.95, w: 12, h: 0.7,
    fontSize: 28, fontFace: F.head, bold: true, color: C.navy, margin: 0,
  });
  s.addText("意图理解 · 意图澄清 · 任务编排", {
    x: 0.7, y: 1.65, w: 12, h: 0.4,
    fontSize: 14, color: C.coral, fontFace: F.body, italic: true, margin: 0,
  });

  const sections = [
    {
      title: "意图理解",
      lines: [
        "Pydantic Intent(7×6 类)",
        "认知层模型(deepseek-v4-flash)",
        "memory_summary 注入 prompt",
        "JSON 解析失败优雅 fallback",
      ],
    },
    {
      title: "意图澄清",
      lines: [
        "5 种交互形式(选择题为主)",
        "≤ 5 轮硬上限(铁律 6)",
        "纯程序生成 — 不调 LLM",
        "字段填充 4 级优先级",
      ],
    },
    {
      title: "任务编排",
      lines: [
        "LangGraph + PostgresSaver",
        "Planner Agent(动态规划)",
        "Critic Loop(自动评审)",
        "Step Persona × 8(researcher/critic 等)",
        "Time-travel rollback",
      ],
    },
  ];

  sections.forEach((sec, i) => {
    const x = 0.7 + i * 4.15;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.35, w: 3.85, h: 4.4,
      fill: { color: C.white }, line: { color: C.ice, width: 1 },
      shadow: { type: "outer", color: "000000", blur: 10, offset: 3, angle: 90, opacity: 0.06 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.35, w: 3.85, h: 0.6,
      fill: { color: C.navy }, line: { type: "none" },
    });
    s.addText(sec.title, {
      x: x + 0.25, y: 2.4, w: 3.4, h: 0.5,
      fontSize: 16, fontFace: F.head, bold: true, color: C.white,
      valign: "middle", margin: 0,
    });

    sec.lines.forEach((line, j) => {
      // 圆点
      s.addShape(pres.shapes.OVAL, {
        x: x + 0.3, y: 3.25 + j * 0.55, w: 0.12, h: 0.12,
        fill: { color: C.coral }, line: { type: "none" },
      });
      s.addText(line, {
        x: x + 0.55, y: 3.15 + j * 0.55, w: 3.15, h: 0.4,
        fontSize: 11, color: C.textDk, fontFace: F.body, valign: "middle", margin: 0,
      });
    });
  });

  // 底部 callout
  s.addText("关键创新:Plan 是数据,不是代码 — Planner 动态产出 JSON,引擎照单执行(2026 硅谷一线 Manus / Devin 范式)", {
    x: 0.7, y: 6.95, w: 12.0, h: 0.35,
    fontSize: 11, fontFace: F.body, italic: true, color: C.navy, align: "center", margin: 0,
  });

  addPageNum(s, 5, TOTAL);
}

// ════════════════════════════════════════════════════════════════
// Slide 6 — 执行与协作(工具 / HITL / 通信)
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bgSoft };

  s.addText("05 / Deep Dive · II", {
    x: 0.7, y: 0.45, w: 6, h: 0.4,
    fontSize: 13, color: C.textMut, fontFace: F.body, charSpacing: 4, margin: 0,
  });
  s.addText("执行与协作", {
    x: 0.7, y: 0.95, w: 12, h: 0.7,
    fontSize: 28, fontFace: F.head, bold: true, color: C.navy, margin: 0,
  });
  s.addText("工具调用 · Human in the Loop · 通信协议", {
    x: 0.7, y: 1.65, w: 12, h: 0.4,
    fontSize: 14, color: C.coral, fontFace: F.body, italic: true, margin: 0,
  });

  const sections = [
    {
      title: "工具调用",
      lines: [
        "9 个独立 MCP HTTP 服务",
        "Retry × 3 指数退避",
        "Redis 缓存(server-specific TTL)",
        "ReAct loop · 步数上限 10",
        "永不抛 · 失败优雅降级",
      ],
    },
    {
      title: "Human in the Loop",
      lines: [
        "3 种 gate 类型",
        "WS event_opened / closed",
        "interrupt() + Command(resume)",
        "Time-travel:rollback_to_step",
        "Shape A 与 backend 严格对齐",
      ],
    },
    {
      title: "通信协议",
      lines: [
        "AgentTask / AgentResult Pydantic v2",
        "5 条 Redis Stream 通道",
        "MAXLEN 防御(50/500/2000)",
        "重试 / DLQ / 心跳 / 幂等去重",
        "全链路 trace_id 透传",
      ],
    },
  ];

  sections.forEach((sec, i) => {
    const x = 0.7 + i * 4.15;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.35, w: 3.85, h: 4.4,
      fill: { color: C.white }, line: { color: C.ice, width: 1 },
      shadow: { type: "outer", color: "000000", blur: 10, offset: 3, angle: 90, opacity: 0.06 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.35, w: 3.85, h: 0.6,
      fill: { color: C.navy }, line: { type: "none" },
    });
    s.addText(sec.title, {
      x: x + 0.25, y: 2.4, w: 3.4, h: 0.5,
      fontSize: 16, fontFace: F.head, bold: true, color: C.white,
      valign: "middle", margin: 0,
    });

    sec.lines.forEach((line, j) => {
      s.addShape(pres.shapes.OVAL, {
        x: x + 0.3, y: 3.25 + j * 0.55, w: 0.12, h: 0.12,
        fill: { color: C.coral }, line: { type: "none" },
      });
      s.addText(line, {
        x: x + 0.55, y: 3.15 + j * 0.55, w: 3.15, h: 0.4,
        fontSize: 11, color: C.textDk, fontFace: F.body, valign: "middle", margin: 0,
      });
    });
  });

  s.addText("关键创新:沙箱化代码执行(ADR-025 e2b/Firecracker)+ 浏览器自动化 — 通用执行能力对标 Manus", {
    x: 0.7, y: 6.95, w: 12.0, h: 0.35,
    fontSize: 11, fontFace: F.body, italic: true, color: C.navy, align: "center", margin: 0,
  });

  addPageNum(s, 6, TOTAL);
}

// ════════════════════════════════════════════════════════════════
// Slide 7 — 记忆与韧性(记忆 / 状态 / 上下文)
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bgSoft };

  s.addText("06 / Deep Dive · III", {
    x: 0.7, y: 0.45, w: 6, h: 0.4,
    fontSize: 13, color: C.textMut, fontFace: F.body, charSpacing: 4, margin: 0,
  });
  s.addText("记忆与韧性", {
    x: 0.7, y: 0.95, w: 12, h: 0.7,
    fontSize: 28, fontFace: F.head, bold: true, color: C.navy, margin: 0,
  });
  s.addText("记忆模块 · 状态管理 · 上下文窗口", {
    x: 0.7, y: 1.65, w: 12, h: 0.4,
    fontSize: 14, color: C.coral, fontFace: F.body, italic: true, margin: 0,
  });

  // 左:4 层记忆
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 2.35, w: 5.6, h: 4.4,
    fill: { color: C.white }, line: { color: C.ice, width: 1 },
    shadow: { type: "outer", color: "000000", blur: 10, offset: 3, angle: 90, opacity: 0.06 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 2.35, w: 5.6, h: 0.6,
    fill: { color: C.navy }, line: { type: "none" },
  });
  s.addText("4 层记忆架构", {
    x: 0.95, y: 2.4, w: 5.1, h: 0.5,
    fontSize: 16, fontFace: F.head, bold: true, color: C.white, valign: "middle", margin: 0,
  });

  const memLayers = [
    { title: "工作记忆", impl: "LangGraph TaskState",  status: "✓" },
    { title: "情景记忆", impl: "Qdrant workflow_traces", status: "✓" },
    { title: "语义记忆", impl: "Redis flywheel:prefs",   status: "✓" },
    { title: "程序记忆", impl: "Skill Registry · MD/YAML", status: "✓" },
  ];
  memLayers.forEach((m, j) => {
    const y = 3.2 + j * 0.85;
    s.addShape(pres.shapes.OVAL, {
      x: 0.95, y, w: 0.4, h: 0.4,
      fill: { color: C.coral }, line: { type: "none" },
    });
    s.addText(String(j + 1), {
      x: 0.95, y, w: 0.4, h: 0.4,
      fontSize: 14, color: C.white, bold: true, align: "center", valign: "middle", margin: 0, fontFace: F.body,
    });
    s.addText(m.title, {
      x: 1.5, y: y - 0.04, w: 2.8, h: 0.35,
      fontSize: 14, fontFace: F.head, bold: true, color: C.navy, margin: 0,
    });
    s.addText(m.impl, {
      x: 1.5, y: y + 0.32, w: 4.0, h: 0.3,
      fontSize: 10, color: C.textMut, fontFace: "Consolas", margin: 0,
    });
    s.addText(m.status, {
      x: 5.7, y: y, w: 0.4, h: 0.4,
      fontSize: 18, color: C.green, bold: true, align: "center", valign: "middle", margin: 0,
    });
  });

  // 右:状态 + 上下文
  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.55, y: 2.35, w: 6.05, h: 2.1,
    fill: { color: C.white }, line: { color: C.ice, width: 1 },
    shadow: { type: "outer", color: "000000", blur: 10, offset: 3, angle: 90, opacity: 0.06 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.55, y: 2.35, w: 6.05, h: 0.55,
    fill: { color: C.navy }, line: { type: "none" },
  });
  s.addText("状态管理(LangGraph)", {
    x: 6.8, y: 2.4, w: 5.6, h: 0.45,
    fontSize: 14, fontFace: F.head, bold: true, color: C.white, valign: "middle", margin: 0,
  });
  ["AsyncPostgresSaver checkpoint", "并发更新 reducer 合并", "镜像 → backend DB(task_steps)", "Time-travel · 历史查询"].forEach((line, j) => {
    s.addShape(pres.shapes.OVAL, {
      x: 6.85, y: 3.05 + j * 0.32, w: 0.1, h: 0.1,
      fill: { color: C.coral }, line: { type: "none" },
    });
    s.addText(line, {
      x: 7.05, y: 2.95 + j * 0.32, w: 5.4, h: 0.3,
      fontSize: 11, color: C.textDk, fontFace: F.body, valign: "middle", margin: 0,
    });
  });

  // 上下文窗口
  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.55, y: 4.65, w: 6.05, h: 2.1,
    fill: { color: C.white }, line: { color: C.ice, width: 1 },
    shadow: { type: "outer", color: "000000", blur: 10, offset: 3, angle: 90, opacity: 0.06 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.55, y: 4.65, w: 6.05, h: 0.55,
    fill: { color: C.navy }, line: { type: "none" },
  });
  s.addText("上下文窗口(多重硬上限)", {
    x: 6.8, y: 4.7, w: 5.6, h: 0.45,
    fontSize: 14, fontFace: F.head, bold: true, color: C.white, valign: "middle", margin: 0,
  });
  ["OSS hydrate ≤ 384 KB / 单产物 256 KB", "ReAct 步数 ≤ 10 · 工具响应 ≤ 48K 字符", "system clip 32K · skill body ≤ 256 KB", "流式 chunks 走 Redis(不进 state)"].forEach((line, j) => {
    s.addShape(pres.shapes.OVAL, {
      x: 6.85, y: 5.35 + j * 0.32, w: 0.1, h: 0.1,
      fill: { color: C.coral }, line: { type: "none" },
    });
    s.addText(line, {
      x: 7.05, y: 5.25 + j * 0.32, w: 5.4, h: 0.3,
      fontSize: 11, color: C.textDk, fontFace: F.body, valign: "middle", margin: 0,
    });
  });

  s.addText("关键设计:产物用 OSS 引用(铁律 4)— state 始终轻量,可序列化,checkpoint 可回放", {
    x: 0.7, y: 6.95, w: 12.0, h: 0.35,
    fontSize: 11, fontFace: F.body, italic: true, color: C.navy, align: "center", margin: 0,
  });

  addPageNum(s, 7, TOTAL);
}

// ════════════════════════════════════════════════════════════════
// Slide 8 — 与 2026 硅谷一线对标
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bgSoft };

  s.addText("07 / 战略对标", {
    x: 0.7, y: 0.45, w: 6, h: 0.4,
    fontSize: 13, color: C.textMut, fontFace: F.body, charSpacing: 4, margin: 0,
  });
  s.addText("与 2026 硅谷一线同档骨架", {
    x: 0.7, y: 0.95, w: 12, h: 0.7,
    fontSize: 28, fontFace: F.head, bold: true, color: C.navy, margin: 0,
  });

  // 表头
  const cols = [3.4, 2.2, 2.2, 2.2, 2.2];
  const xStart = 0.7;
  const headers = ["能力 / 维度", "youle_mas", "Anthropic", "Manus", "Devin"];
  const headerColors = [C.navy, C.coral, C.navy, C.navy, C.navy];

  let cx = xStart;
  headers.forEach((h, i) => {
    s.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: 2.05, w: cols[i], h: 0.55,
      fill: { color: headerColors[i] }, line: { type: "none" },
    });
    s.addText(h, {
      x: cx, y: 2.05, w: cols[i], h: 0.55,
      fontSize: 13, fontFace: F.head, bold: true, color: C.white,
      align: "center", valign: "middle", margin: 0,
    });
    cx += cols[i];
  });

  const rows = [
    ["多智能体编排",         "✓ LangGraph 双轨", "Task tool",          "✓ Planner",   "✓ 闭源"],
    ["动态 Plan(非 YAML)", "✓ ADR-019",        "Skills + Task",      "✓ 主路径",    "✓ 主路径"],
    ["MD Skills 知识包",     "✓ 一等公民",       "✓ 原生",             "?",            "?"],
    ["沙箱执行运行时",       "✓ ADR-025",        "Computer Use",       "✓ 杀手锏",    "✓ 闭源"],
    ["Critic 自动评审",      "✓ ADR-020",        "—",                  "—",           "—"],
    ["Step Persona 矩阵",    "✓ ADR-021 × 8",    "—",                  "—",           "—"],
    ["飞轮闭环(读+写)",     "✓ ADR-023",        "—",                  "?",            "?"],
    ["Production-grade",     "✓ 9 ADR 治理",     "✓",                  "✓",           "✓"],
  ];

  rows.forEach((row, i) => {
    const y = 2.6 + i * 0.45;
    const rowFill = i % 2 === 0 ? C.white : C.bgSoft;
    cx = xStart;
    row.forEach((cell, j) => {
      s.addShape(pres.shapes.RECTANGLE, {
        x: cx, y, w: cols[j], h: 0.45,
        fill: { color: rowFill }, line: { color: C.ice, width: 0.5 },
      });
      const isOurs = j === 1;
      s.addText(cell, {
        x: cx + 0.1, y, w: cols[j] - 0.2, h: 0.45,
        fontSize: 11, fontFace: F.body,
        bold: isOurs || j === 0,
        color: isOurs ? C.coral : (j === 0 ? C.navy : C.textDk),
        align: j === 0 ? "left" : "center", valign: "middle", margin: 0,
      });
      cx += cols[j];
    });
  });

  s.addText("结论:8 项核心能力中,我们 8 项 ✓ — 与 Anthropic / Manus / Devin 同档,部分维度更完整(Critic / Persona / 飞轮)", {
    x: 0.7, y: 6.95, w: 12.0, h: 0.35,
    fontSize: 11, fontFace: F.body, italic: true, color: C.navy, align: "center", margin: 0,
  });

  addPageNum(s, 8, TOTAL);
}

// ════════════════════════════════════════════════════════════════
// Slide 9 — 9 篇 ADR 治理
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bgSoft };

  s.addText("08 / 架构决策有据可查", {
    x: 0.7, y: 0.45, w: 6, h: 0.4,
    fontSize: 13, color: C.textMut, fontFace: F.body, charSpacing: 4, margin: 0,
  });
  s.addText("9 篇 ADR 治理记录", {
    x: 0.7, y: 0.95, w: 12, h: 0.7,
    fontSize: 28, fontFace: F.head, bold: true, color: C.navy, margin: 0,
  });
  s.addText("agents/docs/ADR-019..027 — 每一项重大设计决策都有书面 trace", {
    x: 0.7, y: 1.65, w: 12, h: 0.4,
    fontSize: 13, color: C.textMut, fontFace: F.body, italic: true, margin: 0,
  });

  const adrs = [
    { id: "019", title: "Planner Agent 与动态规划路径",  cat: "智能化" },
    { id: "020", title: "Critic Loop · 创作自动评审",     cat: "质量保障" },
    { id: "021", title: "Step Persona 正交于 Worker",     cat: "智能化" },
    { id: "022", title: "MD Skills + Episode 召回",       cat: "记忆 / 知识" },
    { id: "023", title: "Critique → Reflexion 飞轮桥",    cat: "飞轮" },
    { id: "024", title: "S2 集成路径(Planner / 飞轮闭环)", cat: "对接" },
    { id: "025", title: "Sandbox Task Runtime",           cat: "安全 / 隔离" },
    { id: "026", title: "browser_use + code_executor MCP",cat: "执行能力" },
    { id: "027", title: "Eval 评测体系",                  cat: "可观测" },
  ];

  adrs.forEach((a, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = 0.7 + col * 4.15;
    const y = 2.3 + row * 1.4;

    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 3.85, h: 1.2,
      fill: { color: C.white }, line: { color: C.ice, width: 1 },
      shadow: { type: "outer", color: "000000", blur: 8, offset: 2, angle: 90, opacity: 0.05 },
    });

    // ADR-XXX
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 1.0, h: 1.2,
      fill: { color: C.navy }, line: { type: "none" },
    });
    s.addText("ADR", {
      x: x, y: y + 0.18, w: 1.0, h: 0.3,
      fontSize: 10, color: C.ice, fontFace: F.body, align: "center", margin: 0, charSpacing: 4,
    });
    s.addText(a.id, {
      x: x, y: y + 0.42, w: 1.0, h: 0.6,
      fontSize: 32, fontFace: F.head, bold: true, color: C.white, align: "center", margin: 0,
    });

    s.addText(a.title, {
      x: x + 1.15, y: y + 0.2, w: 2.6, h: 0.55,
      fontSize: 12, fontFace: F.head, bold: true, color: C.navy, margin: 0,
    });
    s.addText(a.cat, {
      x: x + 1.15, y: y + 0.78, w: 2.6, h: 0.3,
      fontSize: 10, color: C.coral, fontFace: F.body, italic: true, margin: 0,
    });
  });

  addPageNum(s, 9, TOTAL);
}

// ════════════════════════════════════════════════════════════════
// Slide 10 — 当前态势
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bgSoft };

  s.addText("09 / 当前态势", {
    x: 0.7, y: 0.45, w: 6, h: 0.4,
    fontSize: 13, color: C.textMut, fontFace: F.body, charSpacing: 4, margin: 0,
  });
  s.addText("已落地 + 准备就绪", {
    x: 0.7, y: 0.95, w: 12, h: 0.7,
    fontSize: 28, fontFace: F.head, bold: true, color: C.navy, margin: 0,
  });

  // 三列
  const blocks = [
    {
      title: "✓ 代码 · 已合并 dev",
      color: C.green,
      items: [
        "9 维度全栈骨架",
        "30+ 新增模块",
        "150+ 单元测试 case",
        "完整 .gitignore 防泄漏",
      ],
    },
    {
      title: "✓ 文档 · production-ready",
      color: C.navy,
      items: [
        "9 篇 ADR 治理记录",
        "对后端对接套件(SQL / YAML / 代码)",
        "对前端对接套件(.d.ts / 时序示例)",
        "K8s + Docker Compose 完整 spec",
      ],
    },
    {
      title: "🔧 上线时按需开 flag",
      color: C.coral,
      items: [
        "ENABLE_DYNAMIC_PLAN(Planner)",
        "ENABLE_CRITIC_LOOP(评审)",
        "ENABLE_EPISODE_RETRIEVAL(Qdrant)",
        "SANDBOX_PROVIDER=e2b(production 必选)",
      ],
    },
  ];

  blocks.forEach((b, i) => {
    const x = 0.7 + i * 4.15;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.95, w: 3.85, h: 4.55,
      fill: { color: C.white }, line: { color: C.ice, width: 1 },
      shadow: { type: "outer", color: "000000", blur: 10, offset: 3, angle: 90, opacity: 0.06 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.95, w: 0.08, h: 4.55,
      fill: { color: b.color }, line: { type: "none" },
    });
    s.addText(b.title, {
      x: x + 0.3, y: 2.15, w: 3.5, h: 0.6,
      fontSize: 14, fontFace: F.head, bold: true, color: C.navy, margin: 0,
    });
    b.items.forEach((it, j) => {
      s.addShape(pres.shapes.OVAL, {
        x: x + 0.35, y: 3.0 + j * 0.7, w: 0.14, h: 0.14,
        fill: { color: b.color }, line: { type: "none" },
      });
      s.addText(it, {
        x: x + 0.6, y: 2.85 + j * 0.7, w: 3.15, h: 0.55,
        fontSize: 11, color: C.textDk, fontFace: F.body, valign: "middle", margin: 0,
      });
    });
  });

  // 底部:GitHub 状态
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 6.65, w: 12.0, h: 0.55,
    fill: { color: C.navy }, line: { type: "none" },
  });
  s.addText("已推到 GitHub:dev branch  ·  老 dev 备份保留:dev-backup-20260509  ·  main 不动", {
    x: 0.7, y: 6.65, w: 12.0, h: 0.55,
    fontSize: 12, fontFace: F.body, color: C.white,
    align: "center", valign: "middle", margin: 0, italic: true,
  });

  addPageNum(s, 10, TOTAL);
}

// ════════════════════════════════════════════════════════════════
// Slide 11 — 路线图(S1-S5)
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bgSoft };

  s.addText("10 / 路线图", {
    x: 0.7, y: 0.45, w: 6, h: 0.4,
    fontSize: 13, color: C.textMut, fontFace: F.body, charSpacing: 4, margin: 0,
  });
  s.addText("18 周升级方案 · 已完成 ~70%", {
    x: 0.7, y: 0.95, w: 12, h: 0.7,
    fontSize: 28, fontFace: F.head, bold: true, color: C.navy, margin: 0,
  });

  const sprints = [
    { id: "S1", title: "智能化骨架", weeks: "4w", status: "✓ 完成", desc: "Planner / dynamic_compiler / subagent / 双层模型路由", color: C.green },
    { id: "S2", title: "飞轮闭环",   weeks: "4w", status: "✓ 完成", desc: "episode 召回 / Critic Loop / Reflexion 桥 / Skill registry", color: C.green },
    { id: "S3", title: "通用执行",   weeks: "3w", status: "✓ 完成", desc: "browser_use / code_executor / Step Persona", color: C.green },
    { id: "S4", title: "沙箱与长任务", weeks: "4w", status: "🟡 50%", desc: "Sandbox 抽象已落,长任务暂停/恢复留 follow-up", color: C.amber },
    { id: "S5", title: "生态与评测", weeks: "3w", status: "🟡 60%", desc: "MD Skill ✓ / Eval ✓ · adaptive router 留 follow-up", color: C.amber },
  ];

  sprints.forEach((sp, i) => {
    const y = 2.0 + i * 0.95;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.7, y, w: 12.0, h: 0.78,
      fill: { color: C.white }, line: { color: C.ice, width: 1 },
      shadow: { type: "outer", color: "000000", blur: 6, offset: 1, angle: 90, opacity: 0.05 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.7, y, w: 0.1, h: 0.78,
      fill: { color: sp.color }, line: { type: "none" },
    });
    s.addText(sp.id, {
      x: 0.95, y: y + 0.1, w: 0.6, h: 0.55,
      fontSize: 22, fontFace: F.head, bold: true, color: C.navy,
      align: "left", valign: "middle", margin: 0,
    });
    s.addText(sp.title, {
      x: 1.65, y: y + 0.05, w: 2.5, h: 0.4,
      fontSize: 14, fontFace: F.head, bold: true, color: C.navy, margin: 0, valign: "middle",
    });
    s.addText(sp.weeks, {
      x: 1.65, y: y + 0.43, w: 2.5, h: 0.3,
      fontSize: 10, color: C.textMut, fontFace: F.body, margin: 0,
    });
    s.addText(sp.desc, {
      x: 4.3, y, w: 6.4, h: 0.78,
      fontSize: 11, color: C.textDk, fontFace: F.body, valign: "middle", margin: 0,
    });
    s.addText(sp.status, {
      x: 10.85, y, w: 1.7, h: 0.78,
      fontSize: 12, fontFace: F.body, bold: true, color: sp.color,
      align: "center", valign: "middle", margin: 0,
    });
  });

  // 底部进度条
  s.addText("整体完成度", {
    x: 0.7, y: 6.85, w: 1.8, h: 0.3,
    fontSize: 11, color: C.textMut, fontFace: F.body, margin: 0, valign: "middle",
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 2.5, y: 6.9, w: 8.5, h: 0.2,
    fill: { color: C.ice }, line: { type: "none" },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 2.5, y: 6.9, w: 8.5 * 0.7, h: 0.2,
    fill: { color: C.coral }, line: { type: "none" },
  });
  s.addText("70%", {
    x: 11.1, y: 6.85, w: 1.5, h: 0.3,
    fontSize: 12, fontFace: F.head, bold: true, color: C.coral, margin: 0, valign: "middle",
  });

  addPageNum(s, 11, TOTAL);
}

// ════════════════════════════════════════════════════════════════
// Slide 12 — 总结 + Q&A
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.navyDk };

  // 装饰
  s.addShape(pres.shapes.OVAL, {
    x: 10.5, y: -2, w: 6, h: 6,
    fill: { color: C.coral, transparency: 80 }, line: { type: "none" },
  });
  s.addShape(pres.shapes.OVAL, {
    x: -2, y: 4, w: 5, h: 5,
    fill: { color: C.navy, transparency: 50 }, line: { type: "none" },
  });

  s.addText("11 / 总结", {
    x: 0.9, y: 0.6, w: 6, h: 0.4,
    fontSize: 13, color: C.ice, fontFace: F.body, charSpacing: 4, margin: 0,
  });

  s.addText("一句话:可推、可看、可验证", {
    x: 0.9, y: 1.15, w: 12, h: 1.0,
    fontSize: 38, fontFace: F.head, bold: true, color: C.white, margin: 0,
  });

  const points = [
    { num: "01", title: "对标硅谷一线", desc: "8 项核心能力 ✓ · 部分维度(Critic / Persona / 飞轮)更完整" },
    { num: "02", title: "Production-ready", desc: "9 ADR 治理 · 完整对接套件 · 多重 production guard" },
    { num: "03", title: "已推到 GitHub", desc: "dev = 9c1b649 · 老 dev 完整备份在 dev-backup-20260509" },
  ];

  points.forEach((p, i) => {
    const y = 2.7 + i * 1.1;
    s.addShape(pres.shapes.OVAL, {
      x: 0.9, y, w: 0.7, h: 0.7,
      fill: { color: C.coral }, line: { type: "none" },
    });
    s.addText(p.num, {
      x: 0.9, y, w: 0.7, h: 0.7,
      fontSize: 16, fontFace: F.head, bold: true, color: C.white,
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(p.title, {
      x: 1.85, y: y - 0.05, w: 10, h: 0.45,
      fontSize: 20, fontFace: F.head, bold: true, color: C.white, margin: 0,
    });
    s.addText(p.desc, {
      x: 1.85, y: y + 0.4, w: 10.5, h: 0.4,
      fontSize: 12, color: C.ice, fontFace: F.body, margin: 0,
    });
  });

  // Q&A footer
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.9, y: 6.2, w: 1.5, h: 0.05,
    fill: { color: C.coral }, line: { type: "none" },
  });
  s.addText("Q & A", {
    x: 0.9, y: 6.3, w: 12, h: 0.6,
    fontSize: 24, fontFace: F.head, bold: true, color: C.white, margin: 0,
  });

  addPageNum(s, 12, TOTAL);
}

// ── 输出 ──
const out = path.resolve("../agent_architecture_for_boss.pptx");
pres.writeFile({ fileName: out }).then((f) => {
  console.log("✓ Written:", f);
});
