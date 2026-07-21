import { beforeEach, describe, expect, it } from 'vitest';

import type { Message } from './conversation';
import {
  appendCachedMessage,
  appendCachedMessageDelta,
  messageQueryKey,
  queryClient,
} from '@/lib/query-client';


describe('shared conversation message query', () => {
  beforeEach(() => {
    queryClient.clear();
  });

  it('deduplicates an event replay and aggregates streamed deltas', () => {
    const message: Message = {
      id: 'message-1',
      conversation_id: 'conv-1',
      kind: 'agent_text' as const,
      role: 'agent_1' as const,
      text: '你',
    };

    appendCachedMessage(message);
    appendCachedMessage(message);
    appendCachedMessageDelta('conv-1', 'message-1', '好');

    expect(queryClient.getQueryData(messageQueryKey('conv-1'))).toEqual([
      { ...message, text: '你好' },
    ]);
  });
});
