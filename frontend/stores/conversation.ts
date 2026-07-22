import { create } from 'zustand';
import type { RoleKey, AgentStatus } from '@/lib/agents';

export type WorkMode = 'plan' | 'ask' | 'auto';

export type ConversationKind = 'main_session' | 'group' | 'private_chat';

export interface ConversationSummary {
  id: string;
  name: string;
  kind: ConversationKind;
  work_mode?: WorkMode;
  preview?: string;
  preview_time?: string;
  unread?: number;
  /** 聚合头像配色(普通群)*/
  avatar_colors?: string[];
  /** 单图头像 */
  avatar_image?: string;
  /** 单字头像背景 */
  avatar_bg?: string;
  /** 单字头像文字 */
  avatar_text?: string;
  /** 是否严肃场景(金融/医疗/政务)— 关闭表情 */
  serious_mode?: boolean;
}

export interface AgentMember {
  id: RoleKey;
  status: AgentStatus;
}

export type MessageKind =
  | 'user_text'
  | 'agent_text'
  | 'agent_card'
  | 'system';

export interface MessageBase {
  id: string;
  conversation_id: string;
  kind: MessageKind;
  role: RoleKey;
  time?: string;
  text?: string;
}

export interface AgentCardMessage extends MessageBase {
  kind: 'agent_card';
  card: {
    icon: 'doc' | 'pen' | 'image' | 'video';
    title: string;
    tag: string;
    tag_status: 'done' | 'running' | 'error';
    items: string[];
    footer?: string;
    word_count?: string;
    progress?: number;
  };
}

export type Message = MessageBase | AgentCardMessage;

export type QuotedRef = { messageId: string; preview: string; role: RoleKey };

interface State {
  list: ConversationSummary[];
  currentId: string | null;
  members: Record<string, AgentMember[]>; // conversation_id → members
  quoted: Record<string, QuotedRef | null>; // conversation_id → 当前引用
  setList: (list: ConversationSummary[]) => void;
  upsertConversation: (c: ConversationSummary) => void;
  setCurrent: (id: string) => void;
  setMembers: (id: string, members: AgentMember[]) => void;
  patchMode: (id: string, mode: WorkMode) => void;
  patchMemberStatus: (id: string, role: RoleKey, status: AgentStatus) => void;
  setQuoted: (conversationId: string, ref: QuotedRef | null) => void;
}

export const useConversationStore = create<State>((set) => ({
  list: [],
  currentId: null,
  members: {},
  quoted: {},
  setList: (list) => set({ list }),
  upsertConversation: (c) =>
    set((s) => {
      const idx = s.list.findIndex((x) => x.id === c.id);
      if (idx === -1) return { list: [c, ...s.list] };
      const next = [...s.list];
      next[idx] = { ...next[idx], ...c };
      return { list: next };
    }),
  setCurrent: (id) => set({ currentId: id }),
  setMembers: (id, members) =>
    set((s) => ({ members: { ...s.members, [id]: members } })),
  patchMode: (id, mode) =>
    set((s) => ({
      list: s.list.map((c) => (c.id === id ? { ...c, work_mode: mode } : c)),
    })),
  patchMemberStatus: (id, role, status) =>
    set((s) => {
      const members = s.members[id];
      if (!members) return s;
      return {
        members: {
          ...s.members,
          [id]: members.map((m) => (m.id === role ? { ...m, status } : m)),
        },
      };
    }),
  setQuoted: (conversationId, ref) =>
    set((s) => ({ quoted: { ...s.quoted, [conversationId]: ref } })),
}));
