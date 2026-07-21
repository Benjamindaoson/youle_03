'use client';

// @ 调用机制(v4 #173-178)
// 当 textarea 输入到 @ 时弹出三类候选:
//   - 人(AI 员工)
//   - 文件(素材库)
//   - 提示词(知识库)
// 实时过滤,Enter / 单击 即插入

import { useEffect, useMemo, useRef, useState } from 'react';
import clsx from 'clsx';
import { File, Sparkles, User } from 'lucide-react';
import { ROLES, MAIN_SESSION_ROLES, GROUP_ROLES, type RoleKey } from '@/lib/agents';
import type { ConversationKind } from '@/stores/conversation';

export type MentionItem =
  | { kind: 'agent'; key: string; label: string; subtitle?: string; role: RoleKey }
  | { kind: 'material'; key: string; label: string; subtitle?: string; mime?: string }
  | { kind: 'prompt'; key: string; label: string; content: string; subtitle?: string };

interface Props {
  conversationKind: ConversationKind;
  query: string;
  materials: { id: string; name: string; mime?: string }[];
  prompts: { id: string; name: string; content: string }[];
  onPick: (item: MentionItem) => void;
  onClose: () => void;
}

const TAB_LABEL: Record<MentionItem['kind'], string> = {
  agent: '员工',
  material: '文件',
  prompt: '提示词',
};

export function MentionPopover({
  conversationKind,
  query,
  materials,
  prompts,
  onPick,
  onClose,
}: Props) {
  const [tab, setTab] = useState<MentionItem['kind']>('agent');
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);

  const items = useMemo<MentionItem[]>(() => {
    const q = query.trim().toLowerCase();
    const roles =
      conversationKind === 'main_session' ? MAIN_SESSION_ROLES : GROUP_ROLES;
    if (tab === 'agent') {
      return roles
        .map((r): MentionItem => ({
          kind: 'agent',
          key: r,
          label: ROLES[r].name,
          subtitle: ROLES[r].description,
          role: r,
        }))
        .filter((i) =>
          q ? i.label.toLowerCase().includes(q) || i.key.includes(q) : true,
        );
    }
    if (tab === 'material') {
      return materials
        .filter((m) => (q ? m.name.toLowerCase().includes(q) : true))
        .map((m): MentionItem => ({
          kind: 'material',
          key: m.id,
          label: m.name,
          subtitle: m.mime,
          mime: m.mime,
        }));
    }
    return prompts
      .filter((p) => (q ? p.name.toLowerCase().includes(q) : true))
      .map((p): MentionItem => ({
        kind: 'prompt',
        key: p.id,
        label: p.name,
        content: p.content,
        subtitle: p.content.slice(0, 36),
      }));
  }, [tab, query, materials, prompts, conversationKind]);

  // 选择项随过滤变化重置
  useEffect(() => setActive(0), [tab, query]);

  // 键盘导航
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActive((i) => Math.min(items.length - 1, i + 1));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActive((i) => Math.max(0, i - 1));
        return;
      }
      if (e.key === 'Tab') {
        e.preventDefault();
        const order: MentionItem['kind'][] = ['agent', 'material', 'prompt'];
        setTab((t) => order[(order.indexOf(t) + 1) % order.length]);
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        const it = items[active];
        if (it) onPick(it);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [items, active, onClose, onPick]);

  return (
    <div className="absolute bottom-[112px] left-3.5 z-30 w-[280px] overflow-hidden rounded-md border border-wechat-line bg-white shadow-lg">
      <div className="flex border-b border-wechat-line text-[11px]">
        {(['agent', 'material', 'prompt'] as const).map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => setTab(k)}
            className={clsx(
              'flex flex-1 items-center justify-center gap-1 py-1.5 transition-colors',
              tab === k
                ? 'bg-wechat-green-soft text-wechat-green'
                : 'text-wechat-mute hover:bg-neutral-50',
            )}
          >
            {k === 'agent' && <User size={11} />}
            {k === 'material' && <File size={11} />}
            {k === 'prompt' && <Sparkles size={11} />}
            {TAB_LABEL[k]}
          </button>
        ))}
      </div>

      <ul ref={listRef} className="max-h-[220px] overflow-y-auto py-1">
        {items.length === 0 && (
          <li className="px-3 py-3 text-center text-[11px] text-wechat-mute">
            没有匹配项
          </li>
        )}
        {items.map((it, idx) => (
          <li key={`${it.kind}-${it.key}`}>
            <button
              type="button"
              onMouseEnter={() => setActive(idx)}
              onClick={() => onPick(it)}
              className={clsx(
                'flex w-full items-start gap-2 px-2.5 py-1.5 text-left transition-colors',
                idx === active ? 'bg-wechat-green-soft' : 'hover:bg-neutral-50',
              )}
            >
              {it.kind === 'agent' ? (
                <span
                  className="grid h-6 w-6 flex-shrink-0 place-items-center rounded text-[10px] font-bold text-white"
                  style={{ background: ROLES[it.role].color }}
                >
                  {ROLES[it.role].initial}
                </span>
              ) : it.kind === 'material' ? (
                <File size={16} className="mt-0.5 flex-shrink-0 text-wechat-sub" />
              ) : (
                <Sparkles size={16} className="mt-0.5 flex-shrink-0 text-wechat-sub" />
              )}
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12px] font-medium text-wechat-fg">
                  {it.label}
                </span>
                {it.subtitle && (
                  <span className="block truncate text-[10px] text-wechat-mute">
                    {it.subtitle}
                  </span>
                )}
              </span>
            </button>
          </li>
        ))}
      </ul>

      <div className="flex items-center gap-2 border-t border-wechat-line px-2 py-1 text-[10px] text-wechat-mute">
        <span>↑↓ 选择</span>
        <span>Tab 换类</span>
        <span>Enter 插入</span>
        <span>Esc 关闭</span>
      </div>
    </div>
  );
}
