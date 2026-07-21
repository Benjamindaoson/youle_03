import { beforeEach, describe, expect, it } from 'vitest';

import { useConversationStore } from './conversation';


describe('shared conversation message state', () => {
  beforeEach(() => {
    useConversationStore.setState({ messages: {}, list: [], currentId: null });
  });

  it('deduplicates an event replay and aggregates streamed deltas', () => {
    const store = useConversationStore.getState();
    const message = {
      id: 'message-1',
      conversation_id: 'conv-1',
      kind: 'agent_text' as const,
      role: 'agent_1' as const,
      text: '你',
    };

    store.appendMessage(message);
    store.appendMessage(message);
    useConversationStore.getState().appendMessageDelta('conv-1', 'message-1', '好');

    expect(useConversationStore.getState().messages['conv-1']).toEqual([
      { ...message, text: '你好' },
    ]);
  });
});
