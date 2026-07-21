// Agent 拟人化表情(v4 §11 #105-108)
// 每 Agent 20 组表情,分 3 大类:joy(喜悦) / think(思考) / dejected(沮丧)
// 触发节点:
// - on_artifact_done    成果产出 → joy
// - on_failed           办不到   → dejected
// - on_user_praise      用户表扬 → joy
// - on_user_criticism   用户批评 → dejected
// - on_thinking         思考中   → think
//
// 严肃场景(serious_mode=true)— 关闭表情(铁律 §19,v4 #108)

import type { RoleKey } from '@/lib/agents';

export type EmotionTrigger =
  | 'on_artifact_done'
  | 'on_failed'
  | 'on_user_praise'
  | 'on_user_criticism'
  | 'on_thinking';

export type EmotionCategory = 'joy' | 'think' | 'dejected';

const TRIGGER_TO_CATEGORY: Record<EmotionTrigger, EmotionCategory> = {
  on_artifact_done: 'joy',
  on_user_praise: 'joy',
  on_thinking: 'think',
  on_failed: 'dejected',
  on_user_criticism: 'dejected',
};

interface AgentEmojiSet {
  joy: string[];      // 8 个
  think: string[];    // 5 个
  dejected: string[]; // 7 个
  // 总计 20 个
}

// 每个 Agent 一套独立表情(基底 emoji,实际产品可换 PNG/SVG 表情包)
export const AGENT_EMOJIS: Record<RoleKey, AgentEmojiSet> = {
  user: { joy: [], think: [], dejected: [] },
  ceo_assistant: {
    joy: ['🙂', '👍', '✅', '🎉', '😎', '🤝', '💼', '✨'],
    think: ['🤔', '👀', '📋', '🧐', '⏳'],
    dejected: ['😅', '🙏', '😐', '😬', '🤷', '😣', '😞'],
  },
  agent_1: {
    joy: ['🖋️', '📝', '✨', '🎯', '👍', '💡', '🌟', '📚'],
    think: ['🧠', '🤔', '🔍', '📖', '📊'],
    dejected: ['😓', '🥲', '🙁', '😕', '🤧', '😶', '😐'],
  },
  agent_2: {
    joy: ['📂', '✅', '👌', '📊', '📋', '🗂', '📑', '💼'],
    think: ['🧮', '🤓', '👓', '🔢', '📐'],
    dejected: ['😪', '😩', '😫', '🥱', '🙁', '😶', '😐'],
  },
  agent_3: {
    joy: ['🎨', '🖼️', '✨', '🌈', '🎭', '👍', '🌟', '🪄'],
    think: ['👀', '🤔', '🖌️', '🎯', '🔬'],
    dejected: ['😩', '😢', '😞', '🙁', '😕', '😬', '😣'],
  },
  agent_4: {
    joy: ['🎬', '🎵', '🎤', '🎧', '📽️', '🎉', '✨', '🌟'],
    think: ['🎚️', '🤔', '🎼', '👂', '⏱️'],
    dejected: ['😩', '😓', '🙁', '😕', '😬', '😪', '😐'],
  },
  hr: {
    joy: ['💼', '🤝', '👏', '👍', '🙌', '✅', '🎉', '🌟'],
    think: ['📋', '🤔', '🧐', '👀', '📝'],
    dejected: ['😅', '🙏', '😬', '😐', '🤷', '😶', '😕'],
  },
  finance_manager: {
    joy: ['💰', '💎', '✅', '📈', '👍', '🎯', '✨', '💼'],
    think: ['📊', '🤔', '🧮', '🔢', '📉'],
    dejected: ['📉', '😟', '😬', '🙁', '😐', '⚠️', '😕'],
  },
};

export function emojiFor(
  role: RoleKey,
  trigger: EmotionTrigger,
  seed = Date.now(),
): string | null {
  const set = AGENT_EMOJIS[role];
  if (!set) return null;
  const cat = TRIGGER_TO_CATEGORY[trigger];
  const pool = set[cat];
  if (!pool || pool.length === 0) return null;
  return pool[seed % pool.length];
}

export function totalEmojisFor(role: RoleKey): number {
  const set = AGENT_EMOJIS[role];
  if (!set) return 0;
  return set.joy.length + set.think.length + set.dejected.length;
}
