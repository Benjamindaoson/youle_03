'use client';

// HITL gate 1:脚本审核(version_select)— 内嵌入消息流
import { useState } from 'react';
import clsx from 'clsx';
import { Check } from 'lucide-react';
import { useHitlDecision } from '@/lib/api';

export function ScriptApproval({
  taskId,
  gateId,
  versions,
}: {
  taskId: string;
  gateId: string;
  versions: { label: string; content: string }[];
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const decide = useHitlDecision(taskId, gateId);

  return (
    <div className="w-[480px] max-w-full overflow-hidden rounded-md border border-wechat-line bg-white shadow-sm">
      <div className="flex items-center gap-2 border-b border-neutral-100 px-3.5 py-2.5">
        <span className="grid h-[18px] w-[18px] place-items-center rounded-sm bg-wechat-green text-white">
          <Check size={10} strokeWidth={2.5} />
        </span>
        <span className="flex-1 text-[12px] font-semibold text-wechat-fg">脚本审核 · 选一版</span>
        <span className="text-[10px] text-wechat-sub">HITL · gate 1</span>
      </div>
      <div className="space-y-2 p-3.5">
        {versions.map((v) => (
          <button
            type="button"
            key={v.label}
            onClick={() => {
              setPicked(v.label);
              decide.mutate({ action: 'approve', payload: { user_choice: { version: v.label } } });
            }}
            className={clsx(
              'w-full rounded border p-2.5 text-left transition-colors',
              picked === v.label
                ? 'border-wechat-green bg-wechat-green-soft'
                : 'border-neutral-100 hover:border-wechat-green/50',
            )}
          >
            <div className="text-[11px] font-medium text-wechat-sub">{v.label}</div>
            <div className="mt-1 whitespace-pre-wrap text-[12px] leading-[1.65] text-wechat-fg">
              {v.content}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
