import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  apiRequest,
  createConversation,
  fetchConversations,
  fetchConversationMessages,
  loginWithSms,
  mockModeEnabled,
  openPrivateConversation,
  fetchSkillDetail,
  fetchSkills,
  setSkillLifecycle,
  sendConversationMessage,
  submitHitlDecision,
} from './client';
import { useUserStore } from '@/stores/user';


function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}


describe('typed API client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useUserStore.setState({ user: null, token: null });
  });

  it('enables mock behavior only for the explicit true flag', () => {
    expect(mockModeEnabled(undefined)).toBe(false);
    expect(mockModeEnabled('false')).toBe(false);
    expect(mockModeEnabled('true')).toBe(true);
  });

  it('logs in through the canonical SMS endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ access_token: 'jwt-token', token_type: 'bearer', user_id: 'user-1' }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await loginWithSms('13800138000', '123456');

    expect(result.access_token).toBe('jwt-token');
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/auth\/login$/),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ phone: '13800138000', code: '123456' }),
      }),
    );
  });

  it('attaches the JWT and normalizes backend conversations', async () => {
    useUserStore.setState({ token: 'jwt-token' });
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse([
        { id: 'conv-1', name: '工作群', mode: 'group', work_mode: 'auto', status: 'active' },
      ]),
    );
    vi.stubGlobal('fetch', fetchMock);

    const conversations = await fetchConversations();

    expect(conversations[0]).toMatchObject({ id: 'conv-1', kind: 'group', work_mode: 'auto' });
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get('authorization')).toBe(
      'Bearer jwt-token',
    );
  });

  it('loads and normalizes shared group/private message history', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse([
          {
            id: 'message-1',
            conversation_id: 'conv-1',
            role: 'agent_1',
            content: '已完成',
            content_type: 'text',
            extra_metadata: {},
            created_at: '2026-07-21T00:00:00Z',
          },
        ]),
      ),
    );

    const messages = await fetchConversationMessages('conv-1');

    expect(messages[0]).toMatchObject({
      id: 'message-1',
      conversation_id: 'conv-1',
      kind: 'agent_text',
      text: '已完成',
    });
  });

  it('uses canonical group message and private chat routes', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ message_id: 'm1', decision: 'chitchat', payload: {} }))
      .mockResolvedValueOnce(
        jsonResponse({
          id: 'private-1',
          name: '与 agent_1 的私聊',
          mode: 'private_chat',
          work_mode: null,
          status: 'active',
        }),
      );
    vi.stubGlobal('fetch', fetchMock);

    await sendConversationMessage('group-1', '你好');
    const privateChat = await openPrivateConversation('agent_1');

    expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/conversations\/group-1\/messages$/);
    expect(fetchMock.mock.calls[0][1].body).toBe(JSON.stringify({ content: '你好' }));
    expect(fetchMock.mock.calls[1][0]).toMatch(/\/api\/conversations\/private-chat\/agent_1$/);
    expect(privateChat.kind).toBe('private_chat');
  });

  it('creates the first main conversation through the canonical API', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        id: 'main-1',
        name: '我的 AI 团队',
        mode: 'main_session',
        work_mode: 'auto',
        status: 'active',
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const conversation = await createConversation({
      mode: 'main_session',
      work_mode: 'auto',
      name: '我的 AI 团队',
    });

    expect(conversation).toMatchObject({ id: 'main-1', kind: 'main_session', work_mode: 'auto' });
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/conversations$/);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify({ mode: 'main_session', work_mode: 'auto', name: '我的 AI 团队' }),
    });
  });

  it('surfaces structured API errors instead of returning mock data', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ detail: { code: 'quota', detail: '额度不足' } }, 402)),
    );

    await expect(apiRequest('/api/tasks')).rejects.toMatchObject({
      status: 402,
      code: 'quota',
      message: '额度不足',
    });
  });

  it('connects Skill search, detail, install, enable, and disable routes', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse({ id: 'skill-1', name: 'Skill' }))
      .mockImplementation(() =>
        Promise.resolve(jsonResponse({ skill_id: 'skill-1', status: 'installed_enabled' })),
      );
    vi.stubGlobal('fetch', fetchMock);

    await fetchSkills({ q: '短视频', domain: 'video' });
    await fetchSkillDetail('skill-1');
    await setSkillLifecycle('skill-1', 'install');
    await setSkillLifecycle('skill-1', 'enable');
    await setSkillLifecycle('skill-1', 'disable');

    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      expect.stringMatching(/\/api\/skills\?q=.*&domain=video$/),
      expect.stringMatching(/\/api\/skills\/skill-1$/),
      expect.stringMatching(/\/api\/skills\/skill-1\/install$/),
      expect.stringMatching(/\/api\/skills\/skill-1\/enable$/),
      expect.stringMatching(/\/api\/skills\/skill-1\/disable$/),
    ]);
  });

  it('sends video cancellation to the cancel endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: 'cancelled' }));
    vi.stubGlobal('fetch', fetchMock);

    await submitHitlDecision('task-1', 'gate-1', 'cancel', { reason: '用户取消' });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/tasks\/task-1\/hitl_gates\/gate-1\/cancel$/),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ reason: '用户取消' }),
      }),
    );
  });
});
