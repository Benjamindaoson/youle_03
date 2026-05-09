'use client';

// 首次进入流程(对齐 CLAUDE.md §1.1):
// - 总裁助理 / HR / 财务经理 依次入群(系统提示 + 头像入场动画)
// - 3 段自介
// - 模式选择卡片(Plan / Ask / Auto + 简单了解)
// 不做传统 onboarding tour——用户直接对话上手
import { useEffect, useMemo, useState } from 'react';
import clsx from 'clsx';
import { ROLES } from '@/lib/agents';
import { useRouter } from 'next/navigation';
import { useConversationStore, type WorkMode } from '@/stores/conversation';
import { useSwitchWorkMode } from '@/lib/api';

type Step =
  | { kind: 'join'; role: 'ceo_assistant' | 'hr' | 'finance_manager'; time: string }
  | { kind: 'intro'; role: 'ceo_assistant' | 'hr' | 'finance_manager'; time: string; text: string };

const SCRIPT: Step[] = [
  { kind: 'join',  time: '14:00', role: 'ceo_assistant' },
  { kind: 'join',  time: '14:00', role: 'hr' },
  { kind: 'join',  time: '14:00', role: 'finance_manager' },
  { kind: 'intro', time: '14:01', role: 'ceo_assistant',   text: '你好,我是你的总裁助理,平时帮你协调任务、调度团队。' },
  { kind: 'intro', time: '14:01', role: 'hr',              text: '我管理你的 AI 团队成员,以后想加新员工或给员工进修,找我。' },
  { kind: 'intro', time: '14:01', role: 'finance_manager', text: '订阅、配额、账单都归我。预算紧张时我会提醒你。' },
];

export function OnboardingFlow() {
  const [shown, setShown] = useState(0);
  const [showHint, setShowHint] = useState(false);
  const router = useRouter();
  const patchMode = useConversationStore((s) => s.patchMode);
  const upsert = useConversationStore((s) => s.upsertConversation);
  const switchMode = useSwitchWorkMode();

  useEffect(() => {
    if (shown >= SCRIPT.length) return;
    const t = setTimeout(() => setShown((s) => s + 1), 700);
    return () => clearTimeout(t);
  }, [shown]);

  const finished = shown >= SCRIPT.length;

  function pickMode(target: WorkMode) {
    upsert({
      id: 'main',
      name: '你的第 1 个专属 AI 团队',
      kind: 'main_session',
      work_mode: target,
    });
    patchMode('main', target);
    switchMode.mutate({ conversationId: 'main', target });
    router.push('/chat/main');
  }

  const visible = useMemo(() => SCRIPT.slice(0, shown), [shown]);

  return (
    <div className="flex h-full w-full flex-col bg-wechat-bg">
      <header className="flex h-14 flex-shrink-0 items-center border-b border-wechat-line bg-white px-4">
        <span className="text-[14px] font-semibold text-wechat-fg">
          你的第 1 个专属 AI 团队
        </span>
        <span className="ml-2 rounded bg-wechat-green-soft px-1.5 py-0.5 text-[10px] text-wechat-green">
          主会话
        </span>
      </header>

      <div className="flex-1 overflow-y-auto px-8 py-6">
        <div className="mx-auto max-w-2xl space-y-3">
          {visible.map((line, i) => (
            <Line key={i} step={line} />
          ))}

          {finished && (
            <div className="mt-6 animate-fade-up rounded-md border border-wechat-line bg-white p-4 shadow-sm">
              <div className="mb-3 flex items-center gap-2">
                <span
                  className="grid h-7 w-7 place-items-center rounded text-[11px] font-bold text-white"
                  style={{ background: ROLES.ceo_assistant.color }}
                >
                  助
                </span>
                <span className="text-[13px] text-wechat-fg">
                  <span className="font-semibold">总裁助理:</span>{' '}
                  你想以哪种模式开始工作?
                </span>
              </div>

              <div className="flex flex-wrap gap-2">
                <ModeButton
                  emoji="💭"
                  title="讨论模式 Plan"
                  hint="一起捋思路,不直接动手(不扣任务配额)"
                  onClick={() => pickMode('plan')}
                />
                <ModeButton
                  emoji="❓"
                  title="询问模式 Ask"
                  hint="只回答问题,不开任务(不扣任务配额)"
                  onClick={() => pickMode('ask')}
                />
                <ModeButton
                  emoji="🚀"
                  title="自动模式 Auto"
                  hint="放手让 AI 干活(扣任务配额)"
                  onClick={() => pickMode('auto')}
                  primary
                />
              </div>

              <button
                type="button"
                onClick={() => setShowHint((v) => !v)}
                className="mt-3 text-[11px] text-wechat-sub underline-offset-2 hover:text-wechat-green hover:underline"
              >
                简单了解每种模式
              </button>

              {showHint && (
                <div className="mt-2 space-y-1 rounded bg-neutral-50 p-2.5 text-[11px] leading-[1.65] text-neutral-600">
                  <div><b>Plan(讨论)</b>:同群里跟 AI 聊方案、对结构,不直接动手;切到 Auto 才开干。</div>
                  <div><b>Ask(询问)</b>:只回答你的问题,不创建任务;适合查资料、找思路。</div>
                  <div><b>Auto(自动)</b>:放手让 AI 干活;Hero 任务有 HITL gate 让你审。</div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Line({ step }: { step: Step }) {
  if (step.kind === 'join') {
    const meta = ROLES[step.role];
    return (
      <div className="animate-fade-up py-1 text-center">
        <span className="rounded-sm bg-black/5 px-2.5 py-0.5 text-[11px] text-wechat-mute">
          [{step.time}] {meta.name} 加入群聊
        </span>
      </div>
    );
  }
  const meta = ROLES[step.role];
  return (
    <div className="flex animate-fade-up items-start gap-2.5">
      <span
        className="grid h-9 w-9 flex-shrink-0 place-items-center rounded text-[12px] font-bold text-white"
        style={{ background: meta.color }}
      >
        {meta.initial}
      </span>
      <div className="flex flex-col">
        <div className="mb-1 flex items-center gap-1.5">
          <span className="role-badge">{meta.name}</span>
          <span className="text-[11px] text-wechat-mute">{step.time}</span>
        </div>
        <div className="relative">
          <span className="absolute left-[-6px] top-2.5 h-0 w-0 border-y-[6px] border-r-[6px] border-y-transparent border-r-white" />
          <div className="rounded-md bg-white px-3 py-2 text-[13px] text-wechat-fg shadow-sm">
            {step.text}
          </div>
        </div>
      </div>
    </div>
  );
}

function ModeButton({
  emoji,
  title,
  hint,
  onClick,
  primary,
}: {
  emoji: string;
  title: string;
  hint: string;
  onClick: () => void;
  primary?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'flex flex-col items-start rounded border px-3.5 py-2 text-left transition-colors',
        primary
          ? 'border-wechat-green bg-wechat-green text-white hover:bg-[#06AE56]'
          : 'border-wechat-line bg-white text-wechat-fg hover:bg-neutral-50',
      )}
    >
      <span className="text-[13px] font-semibold">
        {emoji} {title}
      </span>
      <span className={clsx('mt-0.5 text-[11px]', primary ? 'text-white/85' : 'text-wechat-sub')}>
        {hint}
      </span>
    </button>
  );
}
