'use client';

import { ChevronRight } from 'lucide-react';
import { useConversationStore } from '@/stores/conversation';
import { useLayoutStore } from '@/stores/layout';

const WORK_LABEL = '\u5de5\u4f5c';

export function ChatHeader({ conversationId }: { conversationId: string }) {
  const conv = useConversationStore((s) =>
    s.list.find((c) => c.id === conversationId),
  );
  const members = useConversationStore((s) => s.members[conversationId] ?? []);
  const desktopRightCollapsed = useLayoutStore((s) => s.desktopRightCollapsed);
  const setDesktopRightCollapsed = useLayoutStore((s) => s.setDesktopRightCollapsed);

  if (!conv) return <div className="h-11 flex-shrink-0 border-b border-wechat-line bg-white" />;

  const isGroup = conv.kind !== 'private_chat';
  const memberCount = members.length || (isGroup ? 3 : 0);

  return (
    <header className="flex h-11 flex-shrink-0 items-center justify-between border-b border-wechat-line bg-white px-3">
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="truncate text-[13px] font-medium text-wechat-fg">{conv.name}</span>
        {isGroup && (
          <span className="flex-shrink-0 text-[11px] leading-none text-wechat-sub">
            ({memberCount})
          </span>
        )}
        {isGroup && (
          <span className="ml-1 flex-shrink-0 rounded-full bg-[#8ec5ff] px-2 py-[2px] text-[10px] font-medium leading-none text-white">
            {WORK_LABEL}
          </span>
        )}
      </div>

      <button
        type="button"
        onClick={() => setDesktopRightCollapsed(!desktopRightCollapsed)}
        className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-neutral-100 text-wechat-mute transition-colors hover:bg-neutral-200 hover:text-wechat-sub"
        aria-label={desktopRightCollapsed ? 'Expand right panel' : 'Collapse right panel'}
        title={desktopRightCollapsed ? 'Expand right panel' : 'Collapse right panel'}
      >
        <ChevronRight
          size={13}
          strokeWidth={1.8}
          className={desktopRightCollapsed ? 'rotate-180 transition-transform' : 'transition-transform'}
        />
      </button>
    </header>
  );
}
