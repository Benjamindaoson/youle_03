'use client';

import { MoreHorizontal, Phone, Search, Video } from 'lucide-react';
import { ModeSwitcher } from '@/components/chat/ModeSwitcher';
import { GroupMembers } from '@/components/chat/GroupMembers';
import { useConversationStore } from '@/stores/conversation';

export function ChatHeader({ conversationId }: { conversationId: string }) {
  const conv = useConversationStore((s) =>
    s.list.find((c) => c.id === conversationId),
  );
  if (!conv) return <div className="h-14 flex-shrink-0 border-b border-wechat-line bg-white" />;

  const isGroup = conv.kind !== 'private_chat';

  return (
    <header className="flex h-14 flex-shrink-0 items-center justify-between border-b border-wechat-line bg-white px-4">
      <div className="flex items-center gap-2">
        <span className="text-[14px] font-semibold text-wechat-fg">{conv.name}</span>
        <Search size={14} strokeWidth={2.2} className="cursor-pointer text-wechat-mute" />
        {isGroup && <ModeSwitcher conversationId={conversationId} />}
      </div>

      <div className="flex items-center gap-1">
        {isGroup && <GroupMembers conversationId={conversationId} />}
        <button type="button" className="toolbar-btn" title="语音">
          <Phone size={18} strokeWidth={1.8} />
        </button>
        <button type="button" className="toolbar-btn" title="视频">
          <Video size={18} strokeWidth={1.8} />
        </button>
        <button type="button" className="toolbar-btn" title="更多">
          <MoreHorizontal size={18} strokeWidth={1.8} />
        </button>
      </div>
    </header>
  );
}
