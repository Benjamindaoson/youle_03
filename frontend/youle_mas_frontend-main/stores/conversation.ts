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
  /** 用户置顶 */
  pinned?: boolean;
  /** 用户静音 */
  muted?: boolean;
}

export interface AgentMember {
  id: RoleKey;
  status: AgentStatus;
}

export type MessageKind =
  | 'user_text'
  | 'agent_text'
  | 'agent_card'
  | 'system'
  | 'interaction'
  | 'hitl_script'
  | 'hitl_image'
  | 'hitl_video';

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
    tag_status: 'done' | 'running';
    items: string[];
    footer?: string;
    word_count?: string;
    progress?: number;
  };
}

export interface HitlScriptMessage extends MessageBase {
  kind: 'hitl_script';
  task_id: string;
  gate_id: string;
  versions: { label: string; content: string }[];
}

export interface HitlImageMessage extends MessageBase {
  kind: 'hitl_image';
  task_id: string;
  gate_id: string;
  images: { id: string; url: string }[];
}

export interface HitlVideoMessage extends MessageBase {
  kind: 'hitl_video';
  task_id: string;
  gate_id: string;
  video_url: string;
}

export type Message =
  | MessageBase
  | AgentCardMessage
  | HitlScriptMessage
  | HitlImageMessage
  | HitlVideoMessage;

export type QuotedRef = { messageId: string; preview: string; role: RoleKey };

interface State {
  list: ConversationSummary[];
  currentId: string | null;
  members: Record<string, AgentMember[]>; // conversation_id → members
  messages: Record<string, Message[]>;     // conversation_id → 历史
  quoted: Record<string, QuotedRef | null>; // conversation_id → 当前引用
  starred: string[];                        // 收藏的 message id
  setList: (list: ConversationSummary[]) => void;
  upsertConversation: (c: ConversationSummary) => void;
  setCurrent: (id: string) => void;
  setMembers: (id: string, members: AgentMember[]) => void;
  setMessages: (id: string, messages: Message[]) => void;
  appendMessage: (msg: Message) => void;
  withdrawMessage: (conversationId: string, messageId: string) => void;
  patchMode: (id: string, mode: WorkMode) => void;
  patchMemberStatus: (id: string, role: RoleKey, status: AgentStatus) => void;
  togglePin: (id: string) => void;
  toggleMute: (id: string) => void;
  remove: (id: string) => void;
  setQuoted: (conversationId: string, ref: QuotedRef | null) => void;
  toggleStar: (messageId: string) => void;
}

export const useConversationStore = create<State>((set) => ({
  list: [],
  currentId: null,
  members: {},
  messages: {},
  quoted: {},
  starred: [],
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
  setMessages: (id, messages) =>
    set((s) => ({ messages: { ...s.messages, [id]: messages } })),
  appendMessage: (msg) =>
    set((s) => {
      const prev = s.messages[msg.conversation_id] ?? [];
      return {
        messages: {
          ...s.messages,
          [msg.conversation_id]: [...prev, msg],
        },
      };
    }),
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
  togglePin: (id) =>
    set((s) => ({
      list: s.list.map((c) =>
        c.id === id && c.kind !== 'main_session' ? { ...c, pinned: !c.pinned } : c,
      ),
    })),
  toggleMute: (id) =>
    set((s) => ({
      list: s.list.map((c) =>
        c.id === id && c.kind !== 'main_session' ? { ...c, muted: !c.muted } : c,
      ),
    })),
  remove: (id) =>
    set((s) => ({
      list: s.list.filter((c) => c.id !== id || c.kind === 'main_session'),
    })),
  withdrawMessage: (conversationId, messageId) =>
    set((s) => ({
      messages: {
        ...s.messages,
        [conversationId]: (s.messages[conversationId] ?? []).filter((m) => m.id !== messageId),
      },
    })),
  setQuoted: (conversationId, ref) =>
    set((s) => ({ quoted: { ...s.quoted, [conversationId]: ref } })),
  toggleStar: (messageId) =>
    set((s) => ({
      starred: s.starred.includes(messageId)
        ? s.starred.filter((x) => x !== messageId)
        : [...s.starred, messageId],
    })),
}));
