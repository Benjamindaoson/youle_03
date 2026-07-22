'use client';

import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { API_BASE } from './client';
import type { UserEvent } from './ws-events';
import type { AgentStatus, RoleKey } from './agents';
import type { Message, WorkMode } from '@/stores/conversation';
import { useConversationStore } from '@/stores/conversation';
import { useHitlStore, type HITLGate } from '@/stores/hitl';
import { useTaskStore } from '@/stores/task';
import { useWsStore } from '@/stores/ws';
import { appendCachedMessage, appendCachedMessageDelta } from '@/lib/query-client';

export type SSEFrame = { id?: string; event?: string; data: string };

export class SSEFrameParser {
  private buffer = '';

  feed(chunk: string): SSEFrame[] {
    this.buffer += chunk.replaceAll('\r\n', '\n');
    const frames: SSEFrame[] = [];
    let boundary = this.buffer.indexOf('\n\n');
    while (boundary >= 0) {
      const block = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      const frame = this.parseBlock(block);
      if (frame) frames.push(frame);
      boundary = this.buffer.indexOf('\n\n');
    }
    return frames;
  }

  private parseBlock(block: string): SSEFrame | null {
    let id: string | undefined;
    let event: string | undefined;
    const data: string[] = [];
    for (const line of block.split('\n')) {
      if (!line || line.startsWith(':')) continue;
      const separator = line.indexOf(':');
      const field = separator < 0 ? line : line.slice(0, separator);
      const value = separator < 0 ? '' : line.slice(separator + 1).replace(/^ /, '');
      if (field === 'id') id = value;
      else if (field === 'event') event = value;
      else if (field === 'data') data.push(value);
    }
    return data.length ? { id, event, data: data.join('\n') } : null;
  }
}

export class EventDeduplicator {
  private readonly seen = new Set<string>();
  private readonly order: string[] = [];

  constructor(private readonly capacity = 500) {}

  accept(id: string): boolean {
    if (this.seen.has(id)) return false;
    this.seen.add(id);
    this.order.push(id);
    if (this.order.length > this.capacity) {
      const oldest = this.order.shift();
      if (oldest) this.seen.delete(oldest);
    }
    return true;
  }
}

export function buildSSEHeaders(
  token: string,
  lastEventId?: string | null,
): Record<string, string> {
  return {
    Accept: 'text/event-stream',
    Authorization: `Bearer ${token}`,
    ...(lastEventId ? { 'Last-Event-ID': lastEventId } : {}),
  };
}

export function reconnectDelay(attempt: number, jitter = Math.random()): number {
  const base = Math.min(500 * 2 ** attempt, 30_000);
  return Math.round(Math.min(30_000, base * (1 + jitter * 0.2)));
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

export function applyUserEvent(event: UserEvent, onArtifactAdded: () => void = () => {}): void {
  const payload = event.payload as Record<string, unknown>;
  const conversationId = event.conversation_id ?? stringValue(payload.conversation_id);
  const conversation = useConversationStore.getState();
  const task = useTaskStore.getState();
  const hitl = useHitlStore.getState();

  switch (event.type) {
    case 'message_added':
    case 'agent_message_started': {
      const raw = payload.message as Record<string, unknown> | undefined;
      if (!raw || !conversationId) break;
      const role = stringValue(raw.role) ?? event.agent_id ?? 'ceo_assistant';
      appendCachedMessage({
        id: stringValue(raw.id) ?? stringValue(payload.message_id) ?? event.id,
        conversation_id: conversationId,
        kind: role === 'user' ? 'user_text' : 'agent_text',
        role: role as RoleKey,
        text: stringValue(raw.content) ?? stringValue(raw.text) ?? '',
      } as Message);
      break;
    }
    case 'agent_message_delta':
    case 'step_streaming': {
      if (!conversationId) break;
      const messageId = stringValue(payload.message_id);
      const delta = stringValue(payload.delta) ?? stringValue(payload.chunk);
      if (messageId && delta) {
        appendCachedMessageDelta(conversationId, messageId, delta);
      }
      if (event.type === 'step_streaming') {
        const stepId = stringValue(payload.step_id);
        if (stepId && delta) task.appendChunk(stepId, delta);
      }
      break;
    }
    case 'step_started':
      task.upsertStep({
        step_id: stringValue(payload.step_id) ?? '',
        agent_id: event.agent_id ?? stringValue(payload.agent_id) ?? '',
        status: 'running',
      });
      break;
    case 'step_completed':
      task.upsertStep({
        step_id: stringValue(payload.step_id) ?? '',
        agent_id: event.agent_id ?? stringValue(payload.agent_id) ?? '',
        status: 'completed',
        artifact: payload.artifact as never,
      });
      break;
    case 'hitl_gate_opened':
      if (payload.gate && typeof payload.gate === 'object') {
        const gate = payload.gate as Record<string, unknown>;
        const taskId = event.task_id ?? stringValue(gate.task_id);
        if (!taskId) break;
        hitl.push({
          ...gate,
          task_id: taskId,
          conversation_id: conversationId,
          preview_artifact: payload.preview_artifact,
        } as HITLGate);
      }
      break;
    case 'hitl_gate_closed': {
      const gateId = stringValue(payload.gate_id) ?? stringValue(payload.id);
      if (gateId) hitl.resolve(gateId);
      break;
    }
    case 'clarification_required': {
      const clarification = payload.clarification;
      if (conversationId && clarification && typeof clarification === 'object') {
        hitl.setClarification(conversationId, clarification as never);
      }
      break;
    }
    case 'task_started': {
      if (conversationId) hitl.clearClarification(conversationId);
      const taskId = event.task_id ?? stringValue(payload.task_id);
      if (taskId) task.start(taskId);
      break;
    }
    case 'artifact_added':
      onArtifactAdded();
      break;
    case 'task_completed': {
      if (!conversationId) break;
      task.finish('completed');
      const artifact = (payload.artifact ?? payload.primary_artifact) as
        | Record<string, unknown>
        | undefined;
      appendCachedMessage({
        id: `task-completed-${event.id}`,
        conversation_id: conversationId,
        kind: 'agent_card',
        role: (event.agent_id ?? 'ceo_assistant') as RoleKey,
        text: stringValue(payload.message) ?? '任务已完成',
        card: {
          icon: artifact?.type === 'video'
            ? 'video'
            : artifact?.type === 'image'
              ? 'image'
              : 'doc',
          title: stringValue(payload.title) ?? '任务已完成',
          tag: '已完成',
          tag_status: 'done',
          items: [stringValue(payload.summary) ?? '结果已生成并保存到成果库'],
          footer: artifact?.reference ? String(artifact.reference) : undefined,
        },
      });
      onArtifactAdded();
      break;
    }
    case 'task_failed': {
      if (!conversationId) break;
      task.finish('failed');
      appendCachedMessage({
        id: `task-failed-${event.id}`,
        conversation_id: conversationId,
        kind: 'agent_card',
        role: (event.agent_id ?? 'ceo_assistant') as RoleKey,
        text: stringValue(payload.message) ?? '任务执行失败',
        card: {
          icon: 'doc',
          title: stringValue(payload.title) ?? '任务执行失败',
          tag: '失败',
          tag_status: 'error',
          items: [
            stringValue(payload.error)
              ?? stringValue(payload.detail)
              ?? '请检查配置后重试',
          ],
        },
      });
      break;
    }
    case 'agent_status_changed':
      if (conversationId && event.agent_id) {
        conversation.patchMemberStatus(
          conversationId,
          event.agent_id as RoleKey,
          payload.status as AgentStatus,
        );
      }
      break;
    case 'work_mode_changed':
      if (conversationId && stringValue(payload.to)) {
        conversation.patchMode(conversationId, payload.to as WorkMode);
      }
      break;
    default:
      break;
  }
}

export function reportSSEError(error: unknown): void {
  const message = error instanceof Error ? error.message : '实时连接失败';
  useWsStore.getState().setConnected(false);
  useWsStore.getState().setError(message);
}

async function consumeStream(
  conversationId: string,
  token: string,
  lastEventId: string | null,
  signal: AbortSignal,
  deduplicator: EventDeduplicator,
  onArtifactAdded: () => void,
): Promise<void> {
  const response = await fetch(
    `${API_BASE}/api/conversations/${conversationId}/events`,
    { headers: buildSSEHeaders(token, lastEventId), signal },
  );
  if (!response.ok) throw new Error(`实时连接失败 (${response.status})`);
  if (!response.body) throw new Error('浏览器不支持流式响应');
  useWsStore.getState().setConnected(true);

  const parser = new SSEFrameParser();
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { value, done } = await reader.read();
    if (done) throw new Error('实时连接已断开');
    for (const frame of parser.feed(decoder.decode(value, { stream: true }))) {
      if (!frame.id || !deduplicator.accept(frame.id)) continue;
      const event = JSON.parse(frame.data) as UserEvent;
      useWsStore.getState().setLastEventId(frame.id);
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.setItem(`haole.sse.${conversationId}.last_event_id`, frame.id);
      }
      applyUserEvent(event, onArtifactAdded);
    }
  }
}

export function useConversationEvents(
  conversationId: string,
  token: string | null,
): void {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!token) return;
    let stopped = false;
    let attempt = 0;
    let controller = new AbortController();
    const deduplicator = new EventDeduplicator();

    const run = async () => {
      while (!stopped) {
        const lastEventId = typeof sessionStorage === 'undefined'
          ? null
          : sessionStorage.getItem(`haole.sse.${conversationId}.last_event_id`);
        try {
          await consumeStream(
            conversationId,
            token,
            lastEventId,
            controller.signal,
            deduplicator,
            () => {
              void queryClient.invalidateQueries({ queryKey: ['artifacts'] });
            },
          );
        } catch (error) {
          if (stopped || controller.signal.aborted) return;
          reportSSEError(error);
          await new Promise((resolve) => setTimeout(resolve, reconnectDelay(attempt++)));
          controller = new AbortController();
        }
      }
    };
    void run();
    return () => {
      stopped = true;
      controller.abort();
      useWsStore.getState().setConnected(false);
    };
  }, [conversationId, queryClient, token]);
}
