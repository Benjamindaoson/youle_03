'use client';

// 中栏对话面板:
// - 顶部 56px:会话名 + 模式切换 chip + 群成员快查 + 工具栏
// - 中部:消息流(WeChat 气泡 / TaskCard / 互动消息 / HITL 内嵌组件)
// - 底部:输入区(Composer)
import { useEffect } from 'react';
import { MessageList } from '@/components/chat/MessageList';
import { Composer } from '@/components/chat/Composer';
import { ChatHeader } from '@/components/chat/ChatHeader';
import { QuotaWidget } from '@/components/layout/QuotaWidget';
import { useConversationStore } from '@/stores/conversation';
import { useMessages, useMembers } from '@/lib/api';
import { useConversationEvents } from '@/lib/sse';
import { useUserStore } from '@/stores/user';

export function ChatPanel({ conversationId }: { conversationId: string }) {
  const setCurrent = useConversationStore((s) => s.setCurrent);
  const setMessages = useConversationStore((s) => s.setMessages);
  const setMembers = useConversationStore((s) => s.setMembers);
  const { data: messages } = useMessages(conversationId);
  const { data: members } = useMembers(conversationId);
  const conv = useConversationStore((s) => s.list.find((c) => c.id === conversationId));
  const isMainSession = conv?.kind === 'main_session';
  const token = useUserStore((s) => s.token);

  useConversationEvents(conversationId, token);

  useEffect(() => {
    setCurrent(conversationId);
  }, [conversationId, setCurrent]);

  useEffect(() => {
    if (messages) setMessages(conversationId, messages);
  }, [messages, conversationId, setMessages]);

  useEffect(() => {
    if (members) setMembers(conversationId, members);
  }, [members, conversationId, setMembers]);

  return (
    <div className="flex h-screen w-full min-w-0 flex-col bg-wechat-bg">
      <ChatHeader conversationId={conversationId} />
      {isMainSession && (
        <div className="flex-shrink-0 border-b border-wechat-line bg-white px-4 py-2">
          <QuotaWidget compact />
        </div>
      )}
      <div className="flex-1 overflow-y-auto px-8 py-4">
        <MessageList conversationId={conversationId} />
      </div>
      <Composer conversationId={conversationId} />
    </div>
  );
}
