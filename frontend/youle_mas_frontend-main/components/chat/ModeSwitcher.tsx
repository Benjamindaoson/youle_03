'use client';

// 群顶部模式切换 chip(Plan/Ask/Auto)— ADR-014 三模式同群切换
// 切换 = POST /api/conversations/:id/switch-work-mode
// Plan/Ask 不扣任务配额(铁律 #20)
import clsx from 'clsx';
import { useConversationStore, type WorkMode } from '@/stores/conversation';
import { useSwitchWorkMode } from '@/lib/api';

const LABELS: Record<WorkMode, string> = {
  plan: '讨论',
  ask: '询问',
  auto: '自动',
};

const HINTS: Record<WorkMode, string> = {
  plan: 'Plan · 讨论(不扣任务配额)',
  ask: 'Ask · 询问(不扣任务配额)',
  auto: 'Auto · 自动(扣任务配额)',
};

export function ModeSwitcher({ conversationId }: { conversationId: string }) {
  const mode = useConversationStore(
    (s) => s.list.find((c) => c.id === conversationId)?.work_mode ?? 'auto',
  );
  const patchMode = useConversationStore((s) => s.patchMode);
  const { mutate, isPending } = useSwitchWorkMode();

  function switchTo(target: WorkMode) {
    if (target === mode || isPending) return;
    patchMode(conversationId, target);
    mutate({ conversationId, target });
  }

  return (
    <div className="ml-2 flex items-center gap-1 rounded-full border border-wechat-line bg-neutral-50 p-0.5">
      {(['plan', 'ask', 'auto'] as const).map((m) => (
        <button
          key={m}
          type="button"
          title={HINTS[m]}
          onClick={() => switchTo(m)}
          className={clsx(
            'rounded-full px-2.5 py-0.5 text-[11px] transition-colors',
            mode === m
              ? 'bg-wechat-green text-white shadow-sm'
              : 'text-neutral-500 hover:bg-white hover:text-wechat-fg',
          )}
        >
          {LABELS[m]}
        </button>
      ))}
    </div>
  );
}
