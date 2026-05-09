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
    id: 'anti-fraud',
    name: '反诈视频制作群',
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
  'anti-fraud': [
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
  'anti-fraud': [
    {
      id: 'm1',
      conversation_id: 'anti-fraud',
      kind: 'user_text',
      role: 'user',
      text: '@研究员 做反诈视频,2026 案例',
    },
    {
      id: 'm2',
      conversation_id: 'anti-fraud',
      kind: 'agent_text',
      role: 'agent_1',
      time: '14:36',
      text: '明白,先确认两点:受众?案例侧重?',
    },
    {
      id: 'm3',
      conversation_id: 'anti-fraud',
      kind: 'user_text',
      role: 'user',
      text: '城市老人 + 投资理财',
    },
    {
      id: 'm4',
      conversation_id: 'anti-fraud',
      kind: 'agent_card',
      role: 'agent_1',
      time: '14:38',
      card: {
        icon: 'doc',
        title: '研究交付',
        tag: '研究报告 · md',
        tag_status: 'done',
        items: [
          '8 个高质量案例',
          '上海老人虚拟币案例,损失 80 万——核心案例',
          '杭州高息理财 App,涉案 2.3 亿——第二案例',
          '4 个共性特征:AI 投顾包装 / 小额引诱 / 老带新 / 锁仓',
        ],
        footer: '在右栏查看执行细节',
        word_count: '2,140 字',
      },
    } as Message,
    {
      id: 'm5',
      conversation_id: 'anti-fraud',
      kind: 'agent_text',
      role: 'agent_1',
      time: '14:38',
      text: '扫了简报,开始写脚本',
    },
    {
      id: 'm6',
      conversation_id: 'anti-fraud',
      kind: 'agent_card',
      role: 'agent_1',
      time: '14:40',
      card: {
        icon: 'pen',
        title: '小文写作中',
        tag: '反诈脚本_v1 · 2/4 段 · 进行中',
        tag_status: 'running',
        items: [
          '第 1 段:引入 / "老张今年 68 岁,退休工程师,独居……"',
          '第 2 段:事件,收益数字漂漂亮亮地涨着,半年里被投入 80 万……',
        ],
        word_count: '156 / 380 字',
        progress: 41,
      },
    } as Message,
    {
      id: 'm7',
      conversation_id: 'anti-fraud',
      kind: 'interaction',
      role: 'ceo_assistant',
      time: '14:42',
      text: '小研先把脚本整完,小图去备 8 张老人特写,小影准备 BGM 池。',
    },
    {
      id: 'm8',
      conversation_id: 'anti-fraud',
      kind: 'hitl_script',
      role: 'agent_1',
      time: '14:44',
      task_id: 'task-anti-fraud-001',
      gate_id: 'gate-script-1',
      versions: [
        {
          label: 'v1 · 故事感',
          content:
            '老张今年 68 岁,退休工程师……\n半年内损失 80 万——一个看似正经的"AI 投顾"。',
        },
        {
          label: 'v2 · 数据感',
          content:
            '2026 上半年,涉老金融诈骗举报 +127%。\n本期 8 个案例,平均损失 64 万。',
        },
      ],
    } as Message,
  ],
};

export type ExecActionType =
  | 'terminal'
  | 'read'
  | 'create'
  | 'thinking'
  | 'search'
  | 'generate';

export interface ExecStep {
  id: string;
  label: string;
  status: 'done' | 'running' | 'pending';
  /** v4 §22 #197-202:6 种动作类型 */
  action?: ExecActionType;
  /** 操作对象(文件名 / 关键词 / 产物类型)*/
  target?: string;
  detail?: string;
  word_count?: string;
  progress?: number;
  /** 三层抽屉:展开看终端输出 / 文件内容 / 思考过程 / 产物预览 */
  expanded_detail?: {
    kind: 'terminal' | 'text' | 'thinking' | 'preview';
    content: string;
  };
}

export interface ExecGroup {
  id: string;
  agent: 'ceo_assistant' | 'agent_1' | 'agent_2' | 'agent_3' | 'agent_4';
  title: string;
  time_label: string;
  steps: ExecStep[];
}

export const MOCK_EXEC_GROUPS: ExecGroup[] = [
  {
    id: 'g1',
    agent: 'agent_1',
    title: '调研反诈视频 2026 案例',
    time_label: "调研 4'12\"",
    steps: [
      { id: 's1', label: '阅读素材', status: 'done', detail: '读取 3 个参考文档' },
      { id: 's2', label: '搜索案例', status: 'done', detail: '找到 8 个真实案例' },
      { id: 's3', label: '整理特征', status: 'done', detail: '4 个共性特征 · 2 个新型手法' },
      { id: 's4', label: '输出报告', status: 'done', detail: '2,140 字', word_count: '2,140 字' },
    ],
  },
  {
    id: 'g2',
    agent: 'agent_1',
    title: '小文写作中 · 写第 2 段',
    time_label: "写作 4'38\"",
    steps: [
      { id: 's1', label: '引入', status: 'done', detail: '32 字', word_count: '32 字' },
      {
        id: 's2',
        label: '第 2 段',
        status: 'running',
        detail: '收益数字漂漂亮亮地涨着,半年里被',
        word_count: '156 / 380 字',
        progress: 41,
      },
      { id: 's3', label: '第 3 段', status: 'pending' },
      { id: 's4', label: '收尾', status: 'pending' },
    ],
  },
];
