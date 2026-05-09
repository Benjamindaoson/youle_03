'use client';

// Center chat panel: header, message stream, composer.
import { useEffect } from 'react';
import { MessageList } from '@/components/chat/MessageList';
import { Composer } from '@/components/chat/Composer';
import { ChatHeader } from '@/components/chat/ChatHeader';
import { useConversationStore } from '@/stores/conversation';
import { useMessages, useMembers } from '@/lib/api';

export function ChatPanel({ conversationId }: { conversationId: string }) {
  const setCurrent = useConversationStore((s) => s.setCurrent);
  const setMessages = useConversationStore((s) => s.setMessages);
  const setMembers = useConversationStore((s) => s.setMembers);
  const { data: messages } = useMessages(conversationId);
  const { data: members } = useMembers(conversationId);

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
      <div className="flex-1 overflow-y-auto px-8 py-4">
        <MessageList conversationId={conversationId} />
      </div>
      <Composer conversationId={conversationId} />
    </div>
  );
}
