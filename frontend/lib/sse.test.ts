import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { UserEvent } from './ws-events';
import {
  EventDeduplicator,
  SSEFrameParser,
  applyUserEvent,
  buildSSEHeaders,
  reconnectDelay,
  reportSSEError,
} from './sse';
import { useConversationStore } from '@/stores/conversation';
import { useHitlStore } from '@/stores/hitl';
import { useTaskStore } from '@/stores/task';
import { useWsStore } from '@/stores/ws';
import {
  appendCachedMessage,
  messageQueryKey,
  queryClient,
} from './query-client';


function event(overrides: Partial<UserEvent> = {}): UserEvent {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    type: 'agent_message_delta',
    user_id: '22222222-2222-4222-8222-222222222222',
    conversation_id: '33333333-3333-4333-8333-333333333333',
    task_id: null,
    agent_id: 'agent_1',
    payload: { message_id: 'message-1', delta: '好' },
    created_at: '2026-07-21T00:00:00Z',
    ...overrides,
  };
}


describe('conversation SSE', () => {
  beforeEach(() => {
    useConversationStore.setState({ list: [], currentId: null });
    queryClient.clear();
    useHitlStore.setState({ queue: [], clarifications: {} });
    useTaskStore.getState().reset();
    useWsStore.setState({ connected: false, lastEventId: null, error: null });
  });

  it('parses frames split across network chunks', () => {
    const parser = new SSEFrameParser();
    expect(parser.feed('id: evt-1\nevent: message_added\nda')).toEqual([]);
    expect(parser.feed('ta: {"ok":true}\n\n')).toEqual([
      { id: 'evt-1', event: 'message_added', data: '{"ok":true}' },
    ]);
  });

  it('deduplicates replayed stable event IDs', () => {
    const dedupe = new EventDeduplicator(2);
    expect(dedupe.accept('one')).toBe(true);
    expect(dedupe.accept('one')).toBe(false);
    expect(dedupe.accept('two')).toBe(true);
    expect(dedupe.accept('three')).toBe(true);
    expect(dedupe.accept('one')).toBe(true);
  });

  it('aggregates message deltas into shared chat state', () => {
    appendCachedMessage({
      id: 'message-1',
      conversation_id: '33333333-3333-4333-8333-333333333333',
      kind: 'agent_text',
      role: 'agent_1',
      text: '你',
    });

    applyUserEvent(event());

    expect(queryClient.getQueryData<{ text?: string }[]>(
      messageQueryKey(event().conversation_id!),
    )?.[0].text).toBe('你好');
  });

  it('sends Bearer auth and Last-Event-ID on reconnect', () => {
    expect(buildSSEHeaders('jwt-token', 'event-9')).toEqual({
      Accept: 'text/event-stream',
      Authorization: 'Bearer jwt-token',
      'Last-Event-ID': 'event-9',
    });
    expect(reconnectDelay(0, 0)).toBe(500);
    expect(reconnectDelay(10, 0)).toBe(30_000);
  });

  it('makes connection failures visible in the transport store', () => {
    reportSSEError(new Error('network down'));

    expect(useWsStore.getState()).toMatchObject({
      connected: false,
      error: 'network down',
    });
  });

  it('applies HITL lifecycle events and invalidates artifact queries', () => {
    const gate = {
      id: 'gate-1',
      step_id: 'step-1',
      gate_type: 'quality_review' as const,
    };
    const preview = { type: 'image', reference: 'mock://task-1/step-1' };
    applyUserEvent(event({
      type: 'hitl_gate_opened',
      task_id: 'task-1',
      payload: { gate, preview_artifact: preview },
    }));
    expect(useHitlStore.getState().queue).toEqual([{
      ...gate,
      task_id: 'task-1',
      conversation_id: event().conversation_id,
      preview_artifact: preview,
    }]);

    applyUserEvent(event({ type: 'hitl_gate_closed', payload: { gate_id: 'gate-1' } }));
    expect(useHitlStore.getState().queue).toEqual([]);

    const invalidateArtifacts = vi.fn();
    applyUserEvent(event({ type: 'artifact_added', payload: {} }), invalidateArtifacts);
    expect(invalidateArtifacts).toHaveBeenCalledOnce();
  });

  it('stores clarification prompts for the active conversation', () => {
    applyUserEvent(event({
      type: 'clarification_required',
      payload: {
        clarification: {
          field: '风格',
          form: 'single_select',
          question: '请选择风格',
          options: ['治愈向', '故事向'],
        },
      },
    }));

    expect(useHitlStore.getState().clarifications[event().conversation_id!]).toMatchObject({
      field: '风格',
      question: '请选择风格',
      options: ['治愈向', '故事向'],
    });
  });

  it('starts a real task and clears stale execution steps', () => {
    useTaskStore.getState().upsertStep({
      step_id: 'stale',
      agent_id: 'agent_1',
      status: 'completed',
    });

    applyUserEvent(event({
      type: 'task_started',
      task_id: 'task-new',
      payload: {},
    }));

    expect(useTaskStore.getState()).toMatchObject({
      currentTaskId: 'task-new',
      currentStatus: 'running',
      currentSteps: [],
    });
  });

  it('renders a completed task artifact through the canonical event reducer', () => {
    const invalidateArtifacts = vi.fn();
    applyUserEvent(event({
      type: 'task_completed',
      payload: {
        title: '无密钥任务已完成',
        summary: 'mock AgentResult 已返回',
        primary_artifact: { type: 'document', reference: 'mock://result.md' },
      },
    }), invalidateArtifacts);

    expect(queryClient.getQueryData<{ card?: { title: string; footer?: string } }[]>(
      messageQueryKey(event().conversation_id!),
    )?.[0].card?.title).toBe('无密钥任务已完成');
    expect(queryClient.getQueryData<{ card?: { footer?: string } }[]>(
      messageQueryKey(event().conversation_id!),
    )?.[0].card?.footer).toBe('mock://result.md');
    expect(invalidateArtifacts).toHaveBeenCalledOnce();
    expect(useTaskStore.getState().currentStatus).toBe('completed');
  });

  it('makes task failures visible in the owning conversation', () => {
    applyUserEvent(event({
      type: 'task_failed',
      payload: { error: '上游服务不可用' },
    }));

    expect(queryClient.getQueryData<{ card?: { tag_status: string; items: string[] } }[]>(
      messageQueryKey(event().conversation_id!),
    )?.[0].card).toMatchObject({
      tag_status: 'error',
      items: ['上游服务不可用'],
    });
    expect(useTaskStore.getState().currentStatus).toBe('failed');
  });
});
