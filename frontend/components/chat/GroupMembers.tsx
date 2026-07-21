'use client';

// 群成员快查(顶部按钮 + hover 弹卡)— ADR-013
// 主会话 7 角色 / 普通群 5 角色(无 HR / 财务经理)
// 点头像/名字 → 弹出 AgentProfileCard(v4 §232-241)
import { useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import clsx from 'clsx';
import { Users } from 'lucide-react';
import {
  ROLES,
  STATUS_DOT,
  STATUS_LABEL,
  MAIN_SESSION_ROLES,
  GROUP_ROLES,
  type RoleKey,
} from '@/lib/agents';
import { useConversationStore, type AgentMember } from '@/stores/conversation';
import { AgentProfileCard } from '@/components/chat/AgentProfileCard';
import { useOpenPrivateChat } from '@/lib/api';

export function GroupMembers({ conversationId }: { conversationId: string }) {
  const [open, setOpen] = useState(false);
  const [activeRole, setActiveRole] = useState<RoleKey | null>(null);
  const [anchor, setAnchor] = useState<DOMRect | null>(null);
  const router = useRouter();
  const openPrivate = useOpenPrivateChat();

  const conv = useConversationStore((s) =>
    s.list.find((c) => c.id === conversationId),
  );
  const stored = useConversationStore((s) => s.members[conversationId]);

  const expectedRoles =
    conv?.kind === 'main_session' ? MAIN_SESSION_ROLES : GROUP_ROLES;

  const members: AgentMember[] = stored?.length
    ? stored
    : expectedRoles.map((r) => ({ id: r, status: 'idle' as const }));

  const memberMap = new Map(members.map((m) => [m.id, m] as const));
  const roles = expectedRoles.map((r) => memberMap.get(r) ?? { id: r, status: 'idle' as const });

  function showCard(role: RoleKey, rect: DOMRect | null) {
    setActiveRole(role);
    setAnchor(rect);
    setOpen(false);
  }

  function startPrivate(role: RoleKey) {
    openPrivate.mutate(role, {
      onSuccess: (conv) => {
        setActiveRole(null);
        router.push(`/chat/${(conv as { id: string }).id}`);
      },
    });
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 rounded px-2 py-1 text-[12px] text-wechat-sub hover:bg-neutral-100 hover:text-wechat-fg"
      >
        <Users size={14} strokeWidth={1.8} />
        <span>{roles.length}</span>
      </button>

      {open && (
        <>
          <span className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full z-40 mt-1 w-[260px] rounded-md border border-wechat-line bg-white p-2 shadow-lg">
            <div className="mb-1.5 px-1 text-[11px] font-medium text-wechat-sub">
              成员({roles.length})
            </div>
            <ul className="flex flex-col gap-0.5">
              {roles.map((m) => (
                <MemberRow
                  key={m.id}
                  role={m.id}
                  status={m.status}
                  onPick={(rect) => showCard(m.id, rect)}
                />
              ))}
            </ul>
          </div>
        </>
      )}

      {activeRole && (
        <AgentProfileCard
          data={{ role: activeRole }}
          anchorRect={anchor}
          onClose={() => setActiveRole(null)}
          onPrivateChat={() => startPrivate(activeRole)}
        />
      )}
    </div>
  );
}

function MemberRow({
  role,
  status,
  onPick,
}: {
  role: RoleKey;
  status: AgentMember['status'];
  onPick: (rect: DOMRect | null) => void;
}) {
  const meta = ROLES[role];
  const ref = useRef<HTMLLIElement>(null);
  return (
    <li
      ref={ref}
      onClick={() => onPick(ref.current?.getBoundingClientRect() ?? null)}
      className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1.5 hover:bg-neutral-50"
    >
      <span
        className="grid h-7 w-7 flex-shrink-0 place-items-center rounded text-[10px] font-bold text-white"
        style={{ background: meta.color }}
      >
        {meta.initial}
      </span>
      <div className="flex-1 min-w-0">
        <div className="truncate text-[12px] font-medium text-wechat-fg">{meta.name}</div>
        {meta.description && (
          <div className="truncate text-[10px] text-wechat-mute">{meta.description}</div>
        )}
      </div>
      <span className="flex items-center gap-1 text-[10px] text-wechat-sub">
        <span className={clsx('h-1.5 w-1.5 rounded-full', STATUS_DOT[status])} />
        {STATUS_LABEL[status]}
      </span>
    </li>
  );
}
