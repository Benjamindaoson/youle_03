'use client';

import { Check, LoaderCircle } from 'lucide-react';
import { useMemo } from 'react';

import { ROLES, type RoleKey } from '@/lib/agents';
import { useTaskStore } from '@/stores/task';

export function AgentPanel() {
  const steps = useTaskStore((state) => state.currentSteps);
  const currentTaskId = useTaskStore((state) => state.currentTaskId);
  const currentStatus = useTaskStore((state) => state.currentStatus);
  const groups = useMemo(() => {
    const grouped = new Map<string, typeof steps>();
    for (const step of steps) {
      const agentId = step.agent_id || 'ceo_assistant';
      grouped.set(agentId, [...(grouped.get(agentId) ?? []), step]);
    }
    return Array.from(grouped.entries());
  }, [steps]);

  return (
    <section className="flex h-screen flex-col overflow-hidden border-l border-wechat-line bg-white">
      <header className="flex h-14 flex-shrink-0 items-center border-b border-wechat-line px-3.5">
        <div>
          <div className="text-[13px] font-semibold text-wechat-fg">执行流</div>
          <div className="mt-px text-[11px] text-wechat-sub">
            {currentTaskId
              ? `任务 ${currentTaskId.slice(0, 8)} ${currentStatus === 'running' ? '执行中' : currentStatus === 'completed' ? '已完成' : '失败'}`
              : `${steps.length} 个已记录步骤`}
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto p-3">
        {groups.length === 0 ? (
          <div className="grid h-full place-items-center text-center text-[12px] text-wechat-mute">
            发送 Auto 任务后，实时步骤会显示在这里。
          </div>
        ) : groups.map(([agentId, agentSteps]) => {
          const role = agentId as RoleKey;
          const meta = ROLES[role] ?? ROLES.ceo_assistant;
          return (
            <section key={agentId} className="mb-3 overflow-hidden rounded-md border border-wechat-line bg-neutral-50">
              <div className="flex items-center gap-2 border-b border-wechat-line px-3 py-2">
                <span
                  className="grid h-6 w-6 place-items-center rounded-full text-[10px] font-bold text-white"
                  style={{ background: meta.color }}
                >
                  {meta.initial}
                </span>
                <span className="text-[12px] font-semibold text-wechat-fg">{meta.name}</span>
              </div>
              <ol className="space-y-2 px-3 py-2">
                {agentSteps.map((step) => (
                  <li key={step.step_id} className="flex items-start gap-2 text-[11px]">
                    {step.status === 'completed' ? (
                      <Check size={13} className="mt-0.5 flex-shrink-0 text-wechat-green" />
                    ) : (
                      <LoaderCircle size={13} className="mt-0.5 flex-shrink-0 animate-spin text-wechat-green" />
                    )}
                    <div className="min-w-0">
                      <div className="break-all text-wechat-fg">{step.step_id}</div>
                      {step.streaming_chunks && (
                        <div className="mt-0.5 line-clamp-3 text-wechat-sub">{step.streaming_chunks}</div>
                      )}
                      {step.artifact?.reference && (
                        <div className="mt-0.5 break-all text-[10px] text-wechat-mute">
                          {step.artifact.reference}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          );
        })}
      </div>
    </section>
  );
}
