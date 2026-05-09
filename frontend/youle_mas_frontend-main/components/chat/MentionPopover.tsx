'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import clsx from 'clsx';
import { ROLES, MAIN_SESSION_ROLES, GROUP_ROLES, type RoleKey } from '@/lib/agents';
import { ROLE_AVATAR } from '@/lib/agent-avatars';
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

export function MentionPopover({
  conversationKind,
  query,
  onPick,
  onClose,
}: Props) {
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);

  const items = useMemo<MentionItem[]>(() => {
    const q = query.trim().toLowerCase();
    const roles =
      conversationKind === 'main_session' ? MAIN_SESSION_ROLES : GROUP_ROLES;

    return roles
      .slice(0, 3)
      .map((role): MentionItem => ({
        kind: 'agent',
        key: role,
        label: ROLES[role].name,
        role,
      }))
      .filter((item) =>
        q ? item.label.toLowerCase().includes(q) || item.key.includes(q) : true,
      );
  }, [query, conversationKind]);

  useEffect(() => setActive(0), [query]);

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
      if (e.key === 'Enter') {
        e.preventDefault();
        const item = items[active];
        if (item) onPick(item);
      }
    }

    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [items, active, onClose, onPick]);

  return (
    <div className="absolute bottom-[152px] left-3.5 z-30 w-[240px] overflow-hidden rounded-[14px] border border-black/[0.04] bg-white p-1.5 shadow-[0_12px_32px_rgba(17,24,39,0.16)]">
      <ul ref={listRef} className="max-h-[220px] overflow-y-auto">
        {items.length === 0 && (
          <li className="px-3 py-3 text-center text-[12px] text-[#9CA3AF]">
            {'\u6ca1\u6709\u5339\u914d\u9879'}
          </li>
        )}
        {items.map((item, index) => {
          const avatarStyle = item.kind === 'agent' ? ROLE_AVATAR[item.role] : undefined;

          return (
            <li key={`${item.kind}-${item.key}`}>
              <button
                type="button"
                onMouseEnter={() => setActive(index)}
                onClick={() => onPick(item)}
                className={clsx(
                  'flex h-12 w-full items-center gap-3 rounded-[6px] px-3 text-left transition-colors',
                  index === active ? 'bg-[#EFF8FF]' : 'hover:bg-[#00000005]',
                )}
              >
                {item.kind === 'agent' && (
                  <span
                    className="grid h-7 w-7 flex-shrink-0 place-items-center rounded-full bg-cover bg-center text-[10px] font-bold text-white"
                    style={avatarStyle ?? { background: ROLES[item.role].color }}
                  >
                    {!avatarStyle && ROLES[item.role].initial}
                  </span>
                )}
                <span className="min-w-0 flex-1 truncate text-[13px] font-normal leading-5 text-[#111827]">
                  {item.label}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
