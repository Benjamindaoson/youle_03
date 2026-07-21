'use client';

import { QueryClient } from '@tanstack/react-query';

import type { Message } from '@/stores/conversation';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, refetchOnWindowFocus: false },
  },
});

export const messageQueryKey = (conversationId: string) => [
  'messages',
  conversationId,
] as const;

export function appendCachedMessage(message: Message): void {
  queryClient.setQueryData<Message[]>(
    messageQueryKey(message.conversation_id),
    (current = []) => current.some((item) => item.id === message.id)
      ? current
      : [...current, message],
  );
}

export function appendCachedMessageDelta(
  conversationId: string,
  messageId: string,
  delta: string,
): void {
  queryClient.setQueryData<Message[]>(
    messageQueryKey(conversationId),
    (current = []) => current.map((message) => message.id === messageId
      ? { ...message, text: `${message.text ?? ''}${delta}` }
      : message),
  );
}

export function removeCachedMessage(conversationId: string, messageId: string): void {
  queryClient.setQueryData<Message[]>(
    messageQueryKey(conversationId),
    (current = []) => current.filter((message) => message.id !== messageId),
  );
}
