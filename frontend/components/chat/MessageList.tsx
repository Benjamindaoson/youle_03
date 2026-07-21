'use client';

// 消息流(微信式气泡 + TaskCard + 互动消息 + HITL 内嵌组件)
import { useEffect, useRef } from 'react';
import { useConversationStore } from '@/stores/conversation';
import { MessageBubble } from '@/components/chat/MessageBubble';

export function MessageList({ conversationId }: { conversationId: string }) {
  const messages = useConversationStore(
    (s) => s.messages[conversationId] ?? [],
  );
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: 'smooth' });
  }, [messages.length]);

  return (
    <div ref={ref} className="flex flex-col gap-0">
      <div className="mb-3 text-center">
        <span className="rounded-sm bg-black/5 px-2.5 py-0.5 text-[11px] text-wechat-mute">
          14:35
        </span>
      </div>
      {messages.length === 0 && (
        <div className="grid h-40 place-items-center text-[12px] text-wechat-mute">
          @一下 AI 员工,分配任务……
        </div>
      )}
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
    </div>
  );
}
