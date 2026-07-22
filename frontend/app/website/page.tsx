import Link from 'next/link';
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  MessagesSquare,
  Radio,
  ShieldCheck,
  Sparkles,
  Store,
  Users,
} from 'lucide-react';

const FEATURES = [
  {
    icon: Users,
    title: '一个群，就是一支 AI 团队',
    description: '总裁助理统一拆解任务，研究、写作、图像和音视频 Agent 按同一份任务契约协作。',
  },
  {
    icon: MessagesSquare,
    title: '群聊与私聊共用上下文',
    description: '在群里推进工作，也可以打开单个 Agent 私聊；消息历史和执行状态保持一致。',
  },
  {
    icon: Radio,
    title: '过程实时可见',
    description: 'SSE 持续传递消息增量、步骤、人工确认和成果事件，断线后可从游标继续。',
  },
  {
    icon: Store,
    title: 'Skill 可安装、可停用',
    description: '从技能市场搜索工作流，先查看 Agent、工具和权限，再决定安装或启用。',
  },
  {
    icon: ShieldCheck,
    title: '关键节点由人确认',
    description: '脚本、图片与最终成果可进入 HITL 审核，自动化不等于放弃控制。',
  },
  {
    icon: Bot,
    title: '统一 Agent 与 MCP 协议',
    description: 'AgentTask、AgentResult 与 MCP URI 有明确契约，便于替换能力而不改写整条流程。',
  },
];

const STEPS = [
  ['01', '说出目标', '在主群输入需求，或用 @ 指定合适的 Agent。'],
  ['02', '确认方案', '选择 Ask、Plan 或 Auto 模式，在关键决策点人工确认。'],
  ['03', '实时协作', '查看 Agent 状态、步骤进度、流式内容和中间成果。'],
  ['04', '沉淀复用', '最终成果进入成果库，成熟流程可作为 Skill 再次调用。'],
];

export default function WebsitePage() {
  return (
    <main className="min-h-screen overflow-x-hidden bg-[#0e1713] text-white">
      <nav className="fixed inset-x-0 top-0 z-50 border-b border-white/10 bg-[#0e1713]/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link href="/website" className="flex items-center gap-2 font-semibold">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-wechat-green text-sm">有</span>
            haole
          </Link>
          <div className="hidden items-center gap-7 text-sm text-white/60 md:flex">
            <a href="#features" className="hover:text-white">产品能力</a>
            <a href="#workflow" className="hover:text-white">工作方式</a>
            <a href="#architecture" className="hover:text-white">技术边界</a>
          </div>
          <Link href="/login" className="rounded-full bg-wechat-green px-4 py-2 text-sm font-medium">
            登录工作台
          </Link>
        </div>
      </nav>

      <section className="relative flex min-h-[760px] items-center px-6 pt-16">
        <div className="absolute left-1/2 top-1/3 h-[480px] w-[680px] -translate-x-1/2 rounded-full bg-wechat-green/15 blur-[120px]" />
        <div className="relative mx-auto max-w-4xl text-center">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-wechat-green/30 bg-wechat-green/10 px-3 py-1 text-xs text-[#77e9ad]">
            <Sparkles size={12} /> 多 Agent 工作平台
          </span>
          <h1 className="mt-7 text-5xl font-semibold leading-[1.08] tracking-tight md:text-7xl">
            不是再加一个聊天框，
            <span className="block text-[#77e9ad]">而是把 AI 组织成团队。</span>
          </h1>
          <p className="mx-auto mt-7 max-w-2xl text-base leading-8 text-white/55 md:text-lg">
            haole把群聊、任务编排、专业 Agent、Skill、MCP 工具与人工审核放进同一个工作台。
            你负责目标和判断，系统负责协调执行。
          </p>
          <div className="mt-10 flex flex-col justify-center gap-3 sm:flex-row">
            <Link href="/login" className="inline-flex items-center justify-center gap-2 rounded-full bg-wechat-green px-7 py-3.5 text-sm font-semibold">
              进入工作台 <ArrowRight size={15} />
            </Link>
            <a href="#workflow" className="rounded-full border border-white/15 px-7 py-3.5 text-sm text-white/70 hover:bg-white/5">
              看它如何工作
            </a>
          </div>
          <div className="mx-auto mt-16 grid max-w-2xl gap-3 text-left text-xs text-white/55 sm:grid-cols-3">
            {['统一任务与事件契约', 'Skill 安全元数据校验', '可恢复的实时事件流'].map((item) => (
              <span key={item} className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <CheckCircle2 size={14} className="text-[#77e9ad]" /> {item}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section id="features" className="bg-[#f4f3ee] px-6 py-24 text-[#17201b]">
        <div className="mx-auto max-w-6xl">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-wechat-green">Product capabilities</p>
          <h2 className="mt-3 max-w-2xl text-4xl font-semibold tracking-tight md:text-5xl">从一句需求，到一条可检查的执行链。</h2>
          <div className="mt-12 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, description }) => (
              <article key={title} className="rounded-2xl border border-black/5 bg-white p-6 shadow-sm">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-wechat-green-soft text-wechat-green"><Icon size={19} /></span>
                <h3 className="mt-5 font-semibold">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-black/55">{description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="workflow" className="px-6 py-24">
        <div className="mx-auto max-w-6xl">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#77e9ad]">How it works</p>
          <h2 className="mt-3 text-4xl font-semibold tracking-tight md:text-5xl">把工作交给团队，而不是交给黑盒。</h2>
          <div className="mt-12 grid gap-4 md:grid-cols-4">
            {STEPS.map(([number, title, description]) => (
              <article key={number} className="rounded-2xl border border-white/10 bg-white/[0.035] p-5">
                <div className="text-2xl font-semibold text-[#77e9ad]">{number}</div>
                <h3 className="mt-7 font-semibold">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-white/45">{description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="architecture" className="border-y border-white/10 bg-black/15 px-6 py-20">
        <div className="mx-auto flex max-w-5xl flex-col items-start justify-between gap-8 md:flex-row md:items-center">
          <div>
            <h2 className="text-3xl font-semibold">现在开始组织你的 AI 团队。</h2>
            <p className="mt-3 max-w-xl text-sm leading-6 text-white/50">当前版本提供短信登录、群聊与私聊、三种工作模式、实时执行状态、人工审核和 Skill 生命周期管理。</p>
          </div>
          <Link href="/login" className="flex shrink-0 items-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-semibold text-[#17201b]">
            登录体验 <ArrowRight size={15} />
          </Link>
        </div>
      </section>

      <footer className="px-6 py-8 text-center text-xs text-white/30">
        haole · Unified multi-agent workspace
      </footer>
    </main>
  );
}
