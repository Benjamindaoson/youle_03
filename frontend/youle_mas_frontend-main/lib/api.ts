'use client';

// REST 客户端骨架。前端铁律:fetch().then(res => res.json) → 必须 TanStack Query。
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from '@tanstack/react-query';
import { useUserStore } from '@/stores/user';
import {
  MOCK_CONVERSATIONS,
  MOCK_MEMBERS,
  MOCK_MESSAGES,
} from '@/lib/mock-data';
import type {
  AgentMember,
  ConversationSummary,
  Message,
  WorkMode,
} from '@/stores/conversation';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== 'false';

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = useUserStore.getState().token;
  const resp = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'content-type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (!resp.ok) throw new Error(`${resp.status} ${await resp.text()}`);
  return resp.json() as Promise<T>;
}

async function safeRequest<T>(path: string, fallback: T, init?: RequestInit): Promise<T> {
  if (USE_MOCK) return fallback;
  try {
    return await request<T>(path, init);
  } catch {
    return fallback;
  }
}

export function useConversations(opts?: Partial<UseQueryOptions<ConversationSummary[]>>) {
  return useQuery<ConversationSummary[]>({
    queryKey: ['conversations'],
    queryFn: () => safeRequest('/api/conversations', MOCK_CONVERSATIONS),
    ...opts,
  });
}

export function useMembers(
  conversationId: string | null,
  opts?: Partial<UseQueryOptions<AgentMember[]>>,
) {
  return useQuery<AgentMember[]>({
    queryKey: ['members', conversationId],
    enabled: !!conversationId,
    queryFn: () =>
      safeRequest(
        `/api/conversations/${conversationId}/members`,
        MOCK_MEMBERS[conversationId ?? ''] ?? [],
      ),
    ...opts,
  });
}

export function useMessages(
  conversationId: string | null,
  opts?: Partial<UseQueryOptions<Message[]>>,
) {
  return useQuery<Message[]>({
    queryKey: ['messages', conversationId],
    enabled: !!conversationId,
    queryFn: () =>
      safeRequest(
        `/api/conversations/${conversationId}/messages`,
        MOCK_MESSAGES[conversationId ?? ''] ?? [],
      ),
    ...opts,
  });
}

export function useSendMessage(conversationId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (text: string) => {
      if (USE_MOCK || !conversationId) {
        return { id: `local-${Date.now()}`, text };
      }
      return request(`/api/conversations/${conversationId}/messages`, {
        method: 'POST',
        body: JSON.stringify({ content: text }),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['messages', conversationId] });
    },
  });
}

export function useSwitchWorkMode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { conversationId: string; target: WorkMode }) => {
      if (USE_MOCK) return { ok: true, ...vars };
      return request(`/api/conversations/${vars.conversationId}/switch-work-mode`, {
        method: 'POST',
        body: JSON.stringify({ target: vars.target, triggered_by: 'user' }),
      });
    },
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['conversations'] });
      void vars;
    },
  });
}

// ── 素材库 / 知识库(@ 调用支持)──
export type MaterialItem = {
  id: string;
  name: string;
  mime?: string;
  url?: string;
  size?: number;
  folder?: string;
  source?: 'upload' | 'url' | 'task_output';
  created_at?: string;
};
export type PromptItem = {
  id: string;
  name: string;
  content: string;
  used_count?: number;
  created_at?: string;
};

const MOCK_MATERIALS: MaterialItem[] = [
  { id: 'm1', name: '商品主图.jpg', mime: 'image/jpeg', folder: '电商素材', source: 'upload' },
  { id: 'm2', name: '反诈案例.xlsx', mime: 'application/vnd.ms-excel', folder: '反诈', source: 'upload' },
  { id: 'm3', name: '品牌字体.zip', mime: 'application/zip', source: 'upload' },
];
const MOCK_PROMPTS: PromptItem[] = [
  { id: 'p1', name: '反诈标准开场', content: '请用 5 秒短句钩子,提醒老人警惕电信诈骗', used_count: 12 },
  { id: 'p2', name: '电商详情图风格', content: '风格:简洁、留白、品牌色统一;文字三行内', used_count: 5 },
];

export function useMaterials(opts?: Partial<UseQueryOptions<MaterialItem[]>>) {
  return useQuery<MaterialItem[]>({
    queryKey: ['materials'],
    queryFn: () => safeRequest('/api/materials', MOCK_MATERIALS),
    ...opts,
  });
}

export function useCreateMaterial() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { name: string; mime?: string; url?: string; folder?: string }) => {
      if (USE_MOCK) {
        return { id: `m-${Date.now()}`, ...vars, source: 'upload' as const };
      }
      return request('/api/materials', { method: 'POST', body: JSON.stringify(vars) });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['materials'] }),
  });
}

export function useDeleteMaterial() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      if (USE_MOCK) return { ok: true };
      return request(`/api/materials/${id}`, { method: 'DELETE' });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['materials'] }),
  });
}

export function usePrompts(opts?: Partial<UseQueryOptions<PromptItem[]>>) {
  return useQuery<PromptItem[]>({
    queryKey: ['prompts'],
    queryFn: () => safeRequest('/api/prompts', MOCK_PROMPTS),
    ...opts,
  });
}

export function useCreatePrompt() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { name: string; content: string }) => {
      if (USE_MOCK) return { id: `p-${Date.now()}`, ...vars, used_count: 0 };
      return request('/api/prompts', { method: 'POST', body: JSON.stringify(vars) });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['prompts'] }),
  });
}

export function useDeletePrompt() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      if (USE_MOCK) return { ok: true };
      return request(`/api/prompts/${id}`, { method: 'DELETE' });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['prompts'] }),
  });
}

// ── 私聊 ──
export function useOpenPrivateChat() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (agentId: string) => {
      if (USE_MOCK) {
        return {
          id: `private-${agentId}`,
          name: `与 ${agentId} 的私聊`,
          mode: 'private_chat',
          work_mode: null,
          status: 'active',
        };
      }
      return request(`/api/conversations/private-chat/${agentId}`, { method: 'POST' });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conversations'] }),
  });
}

// ── Skill 浏览 / 订阅 ──
export type SkillCard = {
  id: string;
  skill_id: string;
  name: string;
  description?: string;
  domain?: string;
  scenario?: string;
  version: string;
  creator_type: string;
  visibility: string;
  keywords?: string[];
  subscribed: boolean;
};
const MOCK_SKILLS: SkillCard[] = [
  {
    id: 's1',
    skill_id: 'anti_fraud_video',
    name: '反诈视频制作',
    description: '5 步生成 30-90 秒反诈短视频,适合社区宣传、抖音投放',
    domain: 'video',
    scenario: 'anti_fraud',
    version: '1.0',
    creator_type: 'platform',
    visibility: 'public',
    keywords: ['反诈', '防诈骗', '老人'],
    subscribed: true,
  },
  {
    id: 's2',
    skill_id: 'ecommerce_detail_image',
    name: '电商详情图制作',
    description: '风格分析 → 文案 → 5 张分段图 → 长图拼接',
    domain: 'image',
    scenario: 'ecommerce_detail',
    version: '1.0',
    creator_type: 'platform',
    visibility: 'public',
    keywords: ['电商', '详情图', '商品'],
    subscribed: true,
  },
];

export function useSkills() {
  return useQuery<SkillCard[]>({
    queryKey: ['skills'],
    queryFn: () => safeRequest('/api/skills', MOCK_SKILLS),
  });
}

export function useMySkills() {
  return useQuery<SkillCard[]>({
    queryKey: ['skills', 'mine'],
    queryFn: () => safeRequest('/api/skills/mine', MOCK_SKILLS),
  });
}

export function useSubscribeSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (skillId: string) => {
      if (USE_MOCK) return { skill_id: skillId, status: 'subscribed' };
      return request(`/api/skills/${skillId}/subscribe`, { method: 'POST' });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skills'] });
      qc.invalidateQueries({ queryKey: ['skills', 'mine'] });
    },
  });
}

export function useUnsubscribeSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (skillId: string) => {
      if (USE_MOCK) return { ok: true };
      return request(`/api/skills/${skillId}/subscribe`, { method: 'DELETE' });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skills'] });
      qc.invalidateQueries({ queryKey: ['skills', 'mine'] });
    },
  });
}

// ── 成果库 ──
export type ArtifactRow = {
  id: string;
  source_task_id?: string;
  source_conversation_id: string;
  source_step_id?: string;
  type: string;
  is_final: boolean;
  reference: string;
  title?: string;
  created_at: string;
};

const MOCK_ARTIFACTS: ArtifactRow[] = [
  {
    id: 'a1',
    source_conversation_id: 'main',
    type: 'video',
    is_final: true,
    reference: 'oss://youle-dev/anti-fraud/2026-05-01.mp4',
    title: '反诈视频:警惕养老投资骗局',
    created_at: '2026-05-01T10:23:00Z',
  },
  {
    id: 'a2',
    source_conversation_id: 'main',
    type: 'image',
    is_final: true,
    reference: 'oss://youle-dev/ecommerce/detail-001.jpg',
    title: '电商详情图:夏季新品系列',
    created_at: '2026-05-03T09:10:00Z',
  },
];

export function useArtifacts(filters?: {
  type?: string;
  conversation_id?: string;
  only_final?: boolean;
}) {
  const qs = new URLSearchParams();
  if (filters?.type) qs.set('artifact_type', filters.type);
  if (filters?.conversation_id) qs.set('conversation_id', filters.conversation_id);
  if (filters?.only_final) qs.set('only_final', 'true');
  const path = qs.toString() ? `/api/artifacts?${qs}` : '/api/artifacts';
  return useQuery<ArtifactRow[]>({
    queryKey: ['artifacts', filters],
    queryFn: () => safeRequest(path, MOCK_ARTIFACTS),
  });
}

// ── 个人主页 ──
export type ProfileSummary = {
  id: string;
  phone: string;
  nickname?: string;
  avatar_url?: string;
  avatar_style?: string;
  plan: string;
  created_at: string;
  last_login_at?: string;
};
const MOCK_PROFILE: ProfileSummary = {
  id: 'mock-user',
  phone: '13800138000',
  nickname: '老板',
  plan: 'free',
  created_at: '2026-04-01T00:00:00Z',
};

export function useProfile() {
  return useQuery<ProfileSummary>({
    queryKey: ['profile'],
    queryFn: () => safeRequest('/api/profile/me', MOCK_PROFILE),
  });
}

export function usePatchProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: Partial<ProfileSummary>) => {
      if (USE_MOCK) return { ...MOCK_PROFILE, ...vars };
      return request('/api/profile/me', { method: 'PATCH', body: JSON.stringify(vars) });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profile'] }),
  });
}

export function useProfileStats() {
  return useQuery<{ artifacts: number; skills_used: number }>({
    queryKey: ['profile', 'stats'],
    queryFn: () => safeRequest('/api/profile/me/stats', { artifacts: 12, skills_used: 2 }),
  });
}

export type QuotaRow = { used: number; total: number; remaining: number; percent: number };
export type QuotaSummary = {
  plan: string;
  auto_tasks_daily: QuotaRow;
  video_tasks_daily: QuotaRow;
  groups_monthly: QuotaRow;
  warnings?: string[];
};

const MOCK_QUOTA: QuotaSummary = {
  plan: 'free',
  auto_tasks_daily: { used: 7, total: 30, remaining: 23, percent: 23.3 },
  video_tasks_daily: { used: 1, total: 3, remaining: 2, percent: 33.3 },
  groups_monthly: { used: 2, total: 5, remaining: 3, percent: 40.0 },
  warnings: [],
};

export function useMyQuota(opts?: Partial<UseQueryOptions<QuotaSummary>>) {
  return useQuery<QuotaSummary>({
    queryKey: ['quota', 'me'],
    queryFn: () => safeRequest('/api/quota/me', MOCK_QUOTA),
    refetchInterval: 60_000,
    ...opts,
  });
}

export function useMonthlyBilling(month?: string) {
  return useQuery<{ month: string; by_quota_type: Record<string, number>; total_items: number }>({
    queryKey: ['billing', month ?? 'current'],
    queryFn: () =>
      safeRequest(`/api/quota/me/billing${month ? `?month=${month}` : ''}`, {
        month: month ?? '2026-05',
        by_quota_type: { auto_tasks_daily: 7, video_tasks_daily: 1 },
        total_items: 8,
      }),
  });
}

export function useSupportRespond(role: 'hr' | 'finance') {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { conversationId: string; content: string }) => {
      if (USE_MOCK) {
        return {
          message_id: `local-${role}-${Date.now()}`,
          role,
          content: role === 'hr'
            ? '我帮你看看团队里谁最合适。你这个需求偏偏向哪类(写作/作图/视频)?'
            : '当前套餐 free,今日 Auto 任务 7/30,视频任务 1/3,群 2/5。要升级吗?',
          quota_warning: [],
        };
      }
      return request(`/api/support/${role}/respond`, {
        method: 'POST',
        body: JSON.stringify({ conversation_id: vars.conversationId, content: vars.content }),
      });
    },
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['messages', vars.conversationId] });
      qc.invalidateQueries({ queryKey: ['quota', 'me'] });
    },
  });
}

export function useHitlDecision(taskId: string, gateId: string) {
  return useMutation({
    mutationFn: async (vars: {
      action: 'approve' | 'modify';
      payload?: Record<string, unknown>;
    }) => {
      if (USE_MOCK) return { ok: true, ...vars };
      return request(`/api/tasks/${taskId}/hitl_gates/${gateId}/${vars.action}`, {
        method: 'POST',
        body: JSON.stringify(vars.payload ?? {}),
      });
    },
  });
}
