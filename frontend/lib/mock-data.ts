// 本地 mock 数据 — 后端未起或 dev fallback。
// 真接线后由 useConversations / WS 取代。
import type { ConversationSummary, AgentMember, Message } from '@/stores/conversation';

export const MOCK_CONVERSATIONS: ConversationSummary[] = [
  {
    id: 'main',
    name: '你的第 1 个专属 AI 团队',
    kind: 'main_session',
    work_mode: 'auto',
    preview: '@一下,你就有了',
    preview_time: '05:49',
    avatar_image: '/team-avatar.png',
  },
  {
    id: 'assistant',
    name: '特别助理',
    kind: 'private_chat',
    preview: '今天有什么需要我帮忙?',
    preview_time: '06:08',
    avatar_bg: '#F4C95D',
    avatar_text: '助',
  },
  {
    id: 'hr',
    name: 'HR 经理',
    kind: 'private_chat',
    preview: '上次任务已完成',
    preview_time: '昨天',
    avatar_bg: '#5B9DD9',
    avatar_text: 'HR',
  },
  {
    id: 'short-video',
    name: '短视频制作群',
    kind: 'group',
    work_mode: 'auto',
    preview: '小研: 这个模板不错',
    preview_time: '04:11',
    avatar_colors: ['#E05A5A', '#F4C95D', '#7EB872', '#5B9DD9'],
  },
  {
    id: 'ecom',
    name: '电商作图群',
    kind: 'group',
    work_mode: 'plan',
    preview: '小图: 新素材发群里了',
    preview_time: '昨天',
    avatar_colors: ['#E8A47E', '#F4C95D', '#A07BC8', '#BBBBBB'],
  },
];

export const MOCK_MEMBERS: Record<string, AgentMember[]> = {
  main: [
    { id: 'ceo_assistant',   status: 'idle' },
    { id: 'agent_1',         status: 'idle' },
    { id: 'agent_2',         status: 'idle' },
    { id: 'agent_3',         status: 'idle' },
    { id: 'agent_4',         status: 'idle' },
    { id: 'hr',              status: 'idle' },
    { id: 'finance_manager', status: 'idle' },
  ],
  'short-video': [
    { id: 'ceo_assistant', status: 'working' },
    { id: 'agent_1',       status: 'working' },
    { id: 'agent_2',       status: 'idle' },
    { id: 'agent_3',       status: 'fishing' },
    { id: 'agent_4',       status: 'idle' },
  ],
  ecom: [
    { id: 'ceo_assistant', status: 'idle' },
    { id: 'agent_1',       status: 'idle' },
    { id: 'agent_2',       status: 'idle' },
    { id: 'agent_3',       status: 'training' },
    { id: 'agent_4',       status: 'idle' },
  ],
};
export const MOCK_MESSAGES: Record<string, Message[]> = {
  'short-video': [
    {
      id: 'm1',
      conversation_id: 'short-video',
      kind: 'user_text',
      role: 'user',
      text: '@研究员 做一条城市漫游短视频',
    },
    {
      id: 'm2',
      conversation_id: 'short-video',
      kind: 'agent_text',
      role: 'agent_1',
      time: '14:36',
      text: '明白,先确认两点:受众?内容风格?',
    },
    {
      id: 'm3',
      conversation_id: 'short-video',
      kind: 'user_text',
      role: 'user',
      text: '都市白领 + 治愈风',
    },
    {
      id: 'm4',
      conversation_id: 'short-video',
      kind: 'agent_card',
      role: 'agent_1',
      time: '14:38',
      card: {
        icon: 'doc',
        title: '研究交付',
        tag: '研究报告 · md',
        tag_status: 'done',
        items: [
          '8 个高质量城市素材',
          '老街清晨光影——核心场景',
          '滨江步道与社区咖啡店——补充场景',
          '4 个共性特征:松弛 / 步行友好 / 生活感 / 易拍摄',
        ],
        footer: '在右栏查看执行细节',
        word_count: '2,140 字',
      },
    } as Message,
    {
      id: 'm5',
      conversation_id: 'short-video',
      kind: 'agent_text',
      role: 'agent_1',
      time: '14:38',
      text: '扫了简报,开始写脚本',
    },
    {
      id: 'm6',
      conversation_id: 'short-video',
      kind: 'agent_card',
      role: 'agent_1',
      time: '14:40',
      card: {
        icon: 'pen',
        title: '小文写作中',
        tag: '短视频脚本_v1 · 2/4 段 · 进行中',
        tag_status: 'running',
        items: [
          '第 1 段:引入 / "清晨七点,城市刚刚醒来……"',
          '第 2 段:路线,从老街走到滨江步道,沿途经过三处小店……',
        ],
        word_count: '156 / 380 字',
        progress: 41,
      },
    } as Message,
  ],
};
