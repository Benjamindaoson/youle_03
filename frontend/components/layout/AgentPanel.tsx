'use client';

// 400px 执行流右栏(对齐 frontend_001 agent-panel 的视觉)
// V1 行为:Auto 模式自动展开,Plan/Ask 默认折叠(实际折叠由 AppShell 控制是否渲染)
// v4 §22 #195-210:6 种动作类型 + 三层抽屉(阶段 / 子任务 / 实时细节)
import { useEffect, useMemo, useState } from 'react';
import {
  BrainCircuit,
  Check,
  ChevronDown,
  Eye,
  FileText,
  Search,
  Sparkles,
  Terminal,
  Wand2,
  X,
} from 'lucide-react';
import clsx from 'clsx';
import { useTaskStore } from '@/stores/task';
import { ROLES, type RoleKey } from '@/lib/agents';
import { MOCK_EXEC_GROUPS, type ExecActionType, type ExecGroup, type ExecStep } from '@/lib/mock-data';

const ACTION_META: Record<ExecActionType, { icon: typeof Terminal; label: string }> = {
  terminal: { icon: Terminal, label: '运行终端' },
  read:     { icon: FileText, label: '阅读' },
  create:   { icon: Sparkles, label: '创建' },
  thinking: { icon: BrainCircuit, label: '思考中' },
  search:   { icon: Search, label: '搜索' },
  generate: { icon: Wand2, label: '生成' },
};

export function AgentPanel() {
  const liveSteps = useTaskStore((s) => s.currentSteps);

  const liveGroups = useMemo<ExecGroup[]>(() => {
    if (!liveSteps.length) return [];
    const byAgent = new Map<string, ExecGroup>();
    for (const ls of liveSteps) {
      const role = (ls.agent_id as RoleKey) || 'agent_1';
      const key = role;
      let g = byAgent.get(key);
      if (!g) {
        g = {
          id: `live-${role}`,
          agent: role as ExecGroup['agent'],
          title: `${ROLES[role]?.name ?? role} 进行中`,
          time_label: '实时',
          steps: [],
        };
        byAgent.set(key, g);
      }
      const status: ExecStep['status'] =
        ls.status === 'completed' ? 'done' : ls.status === 'pending' ? 'pending' : 'running';
      g.steps.push({
        id: ls.step_id,
        label: ls.step_id,
        status,
        detail: ls.streaming_chunks?.slice(-60),
      });
    }
    return Array.from(byAgent.values());
  }, [liveSteps]);

  const groups = liveGroups.length ? liveGroups : MOCK_EXEC_GROUPS;
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  return (
    <section className="flex h-screen flex-col overflow-hidden border-l border-wechat-line bg-white">
      <header className="flex h-14 flex-shrink-0 items-center justify-between border-b border-wechat-line px-3.5">
        <div>
          <div className="text-[13px] font-semibold text-wechat-fg">执行流</div>
          <div className="mt-px text-[11px] text-wechat-sub">
            已工作 4&apos;38&quot; · {groups.length} 个分组
          </div>
        </div>
        <button type="button" className="toolbar-btn" title="折叠右栏">
          <X size={14} />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-3 py-3">
        {groups.map((g, i) => {
          const meta = ROLES[g.agent];
          const isCollapsed = collapsed[g.id];
          const running = g.steps.some((s) => s.status === 'running');
          return (
            <div key={g.id}>
              {i > 0 && (
                <div className="my-3 flex items-center gap-2 text-[10px] text-wechat-mute">
                  <span className="h-px flex-1 bg-wechat-line" />
                  <span className="whitespace-nowrap">— {g.time_label} —</span>
                  <span className="h-px flex-1 bg-wechat-line" />
                </div>
              )}
              <div className="mb-1.5 overflow-hidden rounded-lg border border-wechat-line bg-neutral-50">
                <button
                  type="button"
                  onClick={() =>
                    setCollapsed((prev) => ({ ...prev, [g.id]: !prev[g.id] }))
                  }
                  className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-neutral-100"
                >
                  <span
                    className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white"
                    style={{ background: meta.color }}
                  >
                    {meta.initial}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[12px] font-semibold text-wechat-fg">
                      {g.title}
                    </div>
                    <div className="mt-px text-[10px] text-wechat-sub">{g.time_label}</div>
                  </div>
                  {running && <span className="pill flex-shrink-0">进行中</span>}
                  <ChevronDown
                    size={12}
                    className={clsx(
                      'flex-shrink-0 text-wechat-mute transition-transform',
                      isCollapsed && '-rotate-90',
                    )}
                  />
                </button>
                {!isCollapsed && (
                  <ol className="border-t border-neutral-100 px-3 py-1.5">
                    {g.steps.map((s, idx) => (
                      <StepRow
                        key={s.id}
                        step={s}
                        agentColor={meta.color}
                        isLast={idx === g.steps.length - 1}
                      />
                    ))}
                  </ol>
                )}
              </div>
            </div>
          );
        })}
        {groups.length === 0 && (
          <div className="grid h-full place-items-center text-[12px] text-wechat-mute">
            等待任务派发……
          </div>
        )}
      </div>
    </section>
  );
}

function StepRow({
  step,
  agentColor,
  isLast,
}: {
  step: ExecStep;
  agentColor: string;
  isLast: boolean;
}) {
  const cursorVisible = useBlinkingCursor();
  const [open, setOpen] = useState(false);
  const ActionIcon = step.action ? ACTION_META[step.action].icon : null;
  const actionLabel = step.action ? ACTION_META[step.action].label : null;

  return (
    <li className="flex items-start gap-0">
      <div className="flex w-[22px] flex-shrink-0 flex-col items-center pt-2">
        {step.status === 'done' && (
          <span className="z-10 grid h-3.5 w-3.5 place-items-center rounded-full bg-wechat-green text-white">
            <Check size={8} strokeWidth={3.5} />
          </span>
        )}
        {step.status === 'running' && (
          <span
            className="z-10 h-3.5 w-3.5 animate-spin rounded-full border-[2.5px] border-t-transparent"
            style={{ borderColor: agentColor, borderTopColor: 'transparent' }}
          />
        )}
        {step.status === 'pending' && (
          <span className="z-10 h-3.5 w-3.5 rounded-full border border-neutral-200 bg-neutral-50" />
        )}
        {!isLast && (
          <span
            className="mt-0.5 min-h-[18px] flex-1"
            style={{
              width: 1.5,
              background: step.status === 'done' ? '#07c160' : '#e5e5e5',
            }}
          />
        )}
      </div>
      <div className={clsx('min-w-0 flex-1 pl-2 pt-1.5', isLast ? 'pb-1' : 'pb-2.5')}>
        <button
          type="button"
          onClick={() => step.expanded_detail && setOpen((v) => !v)}
          disabled={!step.expanded_detail}
          className="flex w-full items-center gap-1.5 text-left disabled:cursor-default"
        >
          {ActionIcon && actionLabel && (
            <span className="flex flex-shrink-0 items-center gap-0.5 rounded-sm bg-neutral-100 px-1 py-0.5 text-[9px] text-wechat-sub">
              <ActionIcon size={9} /> {actionLabel}
            </span>
          )}
          <span
            className={clsx(
              'flex-1 truncate text-[12px]',
              step.status === 'pending'
                ? 'text-wechat-mute'
                : step.status === 'running'
                  ? 'font-semibold text-wechat-fg'
                  : 'text-wechat-fg',
            )}
          >
            {step.label}
            {step.target && <span className="text-wechat-mute"> · {step.target}</span>}
          </span>
          {step.status !== 'pending' && step.word_count && (
            <span className="pill flex-shrink-0">{step.word_count}</span>
          )}
          {step.expanded_detail && (
            <ChevronDown
              size={11}
              className={clsx(
                'flex-shrink-0 text-wechat-mute transition-transform',
                open && 'rotate-180',
              )}
            />
          )}
        </button>
        {step.status === 'running' && (
          <>
            {step.progress !== undefined && (
              <div className="mt-1 h-[3px] overflow-hidden rounded bg-wechat-green-soft">
                <span
                  className="block h-full bg-wechat-green transition-all"
                  style={{ width: `${step.progress}%` }}
                />
              </div>
            )}
            {step.detail && (
              <div className="mt-1 flex items-center gap-px text-[11px] text-neutral-600">
                <span className="truncate">{step.detail}</span>
                <span
                  className={clsx(
                    'inline-block h-[11px] w-[1.5px] flex-shrink-0 rounded-sm bg-wechat-fg transition-opacity',
                    cursorVisible ? 'opacity-100' : 'opacity-0',
                  )}
                />
              </div>
            )}
          </>
        )}
        {step.status === 'done' && step.detail && !step.word_count && (
          <div className="mt-px text-[11px] text-wechat-sub">{step.detail}</div>
        )}
        {open && step.expanded_detail && (
          <div className="mt-1.5 overflow-hidden rounded-sm border border-neutral-200 bg-neutral-50">
            <div className="flex items-center gap-1 border-b border-neutral-200 bg-white px-2 py-1 text-[10px] text-wechat-mute">
              {step.expanded_detail.kind === 'terminal' && <Terminal size={10} />}
              {step.expanded_detail.kind === 'text' && <FileText size={10} />}
              {step.expanded_detail.kind === 'thinking' && <BrainCircuit size={10} />}
              {step.expanded_detail.kind === 'preview' && <Eye size={10} />}
              {step.expanded_detail.kind === 'terminal'
                ? '终端输出'
                : step.expanded_detail.kind === 'text'
                  ? '文件内容'
                  : step.expanded_detail.kind === 'thinking'
                    ? '思考过程'
                    : '产物预览'}
            </div>
            <pre
              className={clsx(
                'max-h-40 overflow-y-auto whitespace-pre-wrap break-words p-2 text-[11px] leading-[1.55]',
                step.expanded_detail.kind === 'terminal'
                  ? 'bg-neutral-900 font-mono text-green-300'
                  : 'text-wechat-fg',
              )}
            >
              {step.expanded_detail.content}
            </pre>
          </div>
        )}
      </div>
    </li>
  );
}

function useBlinkingCursor() {
  const [v, setV] = useState(true);
  useEffect(() => {
    const t = setInterval(() => setV((x) => !x), 530);
    return () => clearInterval(t);
  }, []);
  return v;
}
