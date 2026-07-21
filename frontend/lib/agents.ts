// Agent 元数据(角色 → 色板 / 短名 / 头像首字 / Agent 编号)
// 严格对齐 ADR-001-rev:1=文字 / 2=文档 / 3=图 / 4=影音

export type RoleKey =
  | 'user'
  | 'ceo_assistant'
  | 'agent_1'
  | 'agent_2'
  | 'agent_3'
  | 'agent_4'
  | 'hr'
  | 'finance_manager';

export type AgentStatus = 'working' | 'idle' | 'fishing' | 'training';

export interface RoleMeta {
  id: RoleKey;
  name: string;        // 完整名(给徽章 / 群成员栏)
  short: string;       // 拟人化短名(给头像)
  initial: string;     // 头像首字(1-2 字)
  color: string;       // 头像背景色(配 frontend_001 色板)
  description?: string;
}

export const ROLES: Record<RoleKey, RoleMeta> = {
  user:            { id: 'user',            name: '老板',     short: '老板',   initial: '老', color: '#E8755A' },
  ceo_assistant:   { id: 'ceo_assistant',   name: '总裁助理', short: '助理',   initial: '助', color: '#F4C95D', description: '协调任务、调度团队' },
  agent_1:         { id: 'agent_1',         name: '研究员',   short: '小研',   initial: '研', color: '#7EB872', description: '文字 / 调研 / 写作(Agent 1)' },
  agent_2:         { id: 'agent_2',         name: '文档专员', short: '小文档', initial: '档', color: '#5B9DD9', description: '文档(Agent 2)' },
  agent_3:         { id: 'agent_3',         name: '设计师',   short: '小图',   initial: '图', color: '#A07BC8', description: '图像(Agent 3)' },
  agent_4:         { id: 'agent_4',         name: '影音师',   short: '小影',   initial: '影', color: '#7EB872', description: '影音(Agent 4)' },
  hr:              { id: 'hr',              name: 'HR',       short: 'HR',     initial: 'HR', color: '#5B9DD9', description: '管理 AI 团队成员' },
  finance_manager: { id: 'finance_manager', name: '财务经理', short: '财务',   initial: '财', color: '#E8755A', description: '订阅、配额、账单' },
};

export const MAIN_SESSION_ROLES: RoleKey[] = [
  'ceo_assistant',
  'agent_1',
  'agent_2',
  'agent_3',
  'agent_4',
  'hr',
  'finance_manager',
];

// 普通群(无 HR / 财务经理):总裁助理 + 4 Agent
export const GROUP_ROLES: RoleKey[] = [
  'ceo_assistant',
  'agent_1',
  'agent_2',
  'agent_3',
  'agent_4',
];

export const STATUS_LABEL: Record<AgentStatus, string> = {
  working: '工作中',
  idle: '发呆中',
  fishing: '摸鱼中',
  training: '进修中',
};

export const STATUS_DOT: Record<AgentStatus, string> = {
  working: 'bg-wechat-green',
  idle: 'bg-neutral-300',
  fishing: 'bg-amber-400',
  training: 'bg-blue-400',
};
