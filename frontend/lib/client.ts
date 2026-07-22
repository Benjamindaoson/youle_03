import type { components } from './api-types';
import type { RoleKey } from './agents';
import type { ConversationSummary, Message } from '@/stores/conversation';
import { useUserStore } from '@/stores/user';

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export function mockModeEnabled(value = process.env.NEXT_PUBLIC_MOCK_MODE): boolean {
  return value === 'true';
}

export const MOCK_MODE = mockModeEnabled();

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code?: string,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

function errorFromBody(status: number, body: unknown): ApiError {
  const root = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const detail = root.detail;
  if (detail && typeof detail === 'object') {
    const structured = detail as Record<string, unknown>;
    return new ApiError(
      status,
      String(structured.detail ?? structured.message ?? `请求失败 (${status})`),
      structured.code ? String(structured.code) : undefined,
      detail,
    );
  }
  return new ApiError(
    status,
    typeof detail === 'string' ? detail : `请求失败 (${status})`,
    undefined,
    detail,
  );
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = useUserStore.getState().token;
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has('content-type')) {
    headers.set('content-type', 'application/json');
  }
  if (token) headers.set('authorization', `Bearer ${token}`);

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  const text = response.status === 204 ? '' : await response.text();
  let body: unknown = undefined;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!response.ok) throw errorFromBody(response.status, body);
  return body as T;
}

export type TokenResponse = components['schemas']['TokenResponse'];
type BackendConversation = components['schemas']['ConversationOut'];
type ConversationCreate = components['schemas']['ConversationCreate'];

export async function sendSmsCode(phone: string): Promise<void> {
  await apiRequest<void>('/api/auth/sms/send', {
    method: 'POST',
    body: JSON.stringify({ phone }),
  });
}

export function loginWithSms(phone: string, code: string): Promise<TokenResponse> {
  return apiRequest<TokenResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ phone, code }),
  });
}

export function normalizeConversation(value: BackendConversation): ConversationSummary {
  return {
    id: value.id,
    name: value.name,
    kind: value.mode,
    work_mode: value.work_mode ?? undefined,
  };
}

export async function fetchConversations(): Promise<ConversationSummary[]> {
  const rows = await apiRequest<BackendConversation[]>('/api/conversations');
  return rows.map(normalizeConversation);
}

export async function createConversation(
  input: ConversationCreate,
): Promise<ConversationSummary> {
  const value = await apiRequest<BackendConversation>('/api/conversations', {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return normalizeConversation(value);
}

type BackendMessage = components['schemas']['Message'];

export function normalizeMessage(value: BackendMessage): Message {
  const kind = value.role === 'user'
    ? 'user_text'
    : value.role === 'system'
      ? 'system'
      : 'agent_text';
  return {
    id: value.id,
    conversation_id: value.conversation_id,
    role: value.role as RoleKey,
    kind,
    text: value.content ?? '',
    time: value.created_at,
  };
}

export async function fetchConversationMessages(conversationId: string): Promise<Message[]> {
  const rows = await apiRequest<BackendMessage[]>(
    `/api/conversations/${conversationId}/messages`,
  );
  return rows.map(normalizeMessage);
}

export function sendConversationMessage(conversationId: string, content: string): Promise<unknown> {
  return apiRequest(`/api/conversations/${conversationId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  });
}

export async function openPrivateConversation(agentId: string): Promise<ConversationSummary> {
  const value = await apiRequest<BackendConversation>(
    `/api/conversations/private-chat/${agentId}`,
    { method: 'POST' },
  );
  return normalizeConversation(value);
}

export type SkillCard = components['schemas']['SkillCard'];
export type SkillDetail = components['schemas']['SkillDetail'];
export type SkillLifecycleAction = 'install' | 'enable' | 'disable';
export type SkillLifecycleResult = { skill_id: string; status: string };

export function fetchSkills(filters?: { q?: string; domain?: string }): Promise<SkillCard[]> {
  const query = new URLSearchParams();
  if (filters?.q) query.set('q', filters.q);
  if (filters?.domain) query.set('domain', filters.domain);
  const suffix = query.size ? `?${query.toString()}` : '';
  return apiRequest<SkillCard[]>(`/api/skills${suffix}`);
}

export function fetchSkillDetail(skillId: string): Promise<SkillDetail> {
  return apiRequest<SkillDetail>(`/api/skills/${skillId}`);
}

export function setSkillLifecycle(
  skillId: string,
  action: SkillLifecycleAction,
): Promise<SkillLifecycleResult> {
  return apiRequest<SkillLifecycleResult>(`/api/skills/${skillId}/${action}`, {
    method: 'POST',
  });
}

export type HitlDecisionAction = 'approve' | 'modify' | 'cancel';

export function submitHitlDecision(
  taskId: string,
  gateId: string,
  action: HitlDecisionAction,
  payload: Record<string, unknown> = {},
): Promise<unknown> {
  return apiRequest(`/api/tasks/${taskId}/hitl_gates/${gateId}/${action}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
