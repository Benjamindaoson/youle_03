'use client';

// 微信式输入区:textarea + 工具栏(发送文件 / 截图 / 表情 / 发送按钮)
// 严肃场景(conversation.serious_mode)关闭表情入口
// @ 触发弹出员工/文件/提示词候选 popover
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ChevronDown,
  Folder,
  Scissors,
  Smile,
} from 'lucide-react';
import clsx from 'clsx';
import { useConversationStore } from '@/stores/conversation';
import { useMaterials, usePrompts, useSendMessage } from '@/lib/api';
import { ROLES } from '@/lib/agents';
import { X } from 'lucide-react';
import { EmojiPicker } from '@/components/chat/EmojiPicker';
import { MentionPopover, type MentionItem } from '@/components/chat/MentionPopover';

interface MentionState {
  start: number;
  query: string;
}

export function Composer({ conversationId }: { conversationId: string }) {
  const [text, setText] = useState('');
  const [showEmoji, setShowEmoji] = useState(false);
  const [mention, setMention] = useState<MentionState | null>(null);
  const conv = useConversationStore((s) => s.list.find((c) => c.id === conversationId));
  const appendMessage = useConversationStore((s) => s.appendMessage);
  const quoted = useConversationStore((s) => s.quoted[conversationId] ?? null);
  const setQuoted = useConversationStore((s) => s.setQuoted);
  const send = useSendMessage(conversationId);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const { data: materials = [] } = useMaterials();
  const { data: prompts = [] } = usePrompts();

  // 检测光标前的 @ 位置 → 开 popover / 更新 query
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    const pos = ta.selectionStart ?? text.length;
    const upto = text.slice(0, pos);
    const match = /(?:^|\s)@(\S*)$/.exec(upto);
    if (match) {
      const start = pos - match[1].length - 1;
      setMention({ start, query: match[1] });
    } else {
      setMention(null);
    }
  }, [text]);

  function dispatch() {
    const trimmed = text.trim();
    if (!trimmed) return;
    const finalText = quoted
      ? `> ${ROLES[quoted.role].name}:${quoted.preview}\n${trimmed}`
      : trimmed;
    appendMessage({
      id: `local-${Date.now()}`,
      conversation_id: conversationId,
      kind: 'user_text',
      role: 'user',
      text: finalText,
    });
    send.mutate(finalText);
    setText('');
    setMention(null);
    setQuoted(conversationId, null);
  }

  function applyMention(item: MentionItem) {
    if (!mention) return;
    const before = text.slice(0, mention.start);
    const afterStart = mention.start + 1 + mention.query.length;
    const after = text.slice(afterStart);

    if (item.kind === 'agent') {
      const label = `@${ROLES[item.role].name} `;
      const next = before + label + after;
      setText(next);
      setMention(null);
      requestAnimationFrame(() => {
        const ta = taRef.current;
        if (ta) {
          const caret = (before + label).length;
          ta.setSelectionRange(caret, caret);
          ta.focus();
        }
      });
      return;
    }
    if (item.kind === 'material') {
      const label = `@${item.label} `;
      setText(before + label + after);
      setMention(null);
      return;
    }
    if (item.kind === 'prompt') {
      // 提示词:展开内容到当前光标
      const expanded = item.content + ' ';
      setText(before + expanded + after);
      setMention(null);
      requestAnimationFrame(() => {
        const ta = taRef.current;
        if (ta) {
          const caret = (before + expanded).length;
          ta.setSelectionRange(caret, caret);
          ta.focus();
        }
      });
    }
  }

  const seriousMode = conv?.serious_mode;
  const canSend = text.trim().length > 0;

  const popover = useMemo(() => {
    if (!mention || !conv) return null;
    return (
      <MentionPopover
        conversationKind={conv.kind}
        query={mention.query}
        materials={materials}
        prompts={prompts}
        onPick={applyMention}
        onClose={() => setMention(null)}
      />
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mention, conv, materials, prompts]);

  return (
    <div className="relative flex-shrink-0 border-t border-wechat-line bg-white">
      {popover}

      {quoted && (
        <div className="mx-4 mt-2 flex items-start gap-2 rounded-sm border-l-2 border-wechat-green bg-neutral-50 px-2 py-1.5 text-[11px]">
          <CornerDownIcon />
          <div className="flex-1 truncate">
            <span className="text-wechat-green">{ROLES[quoted.role].name}:</span>
            <span className="ml-1 text-wechat-sub">{quoted.preview}</span>
          </div>
          <button
            type="button"
            onClick={() => setQuoted(conversationId, null)}
            className="text-wechat-mute hover:text-wechat-fg"
            aria-label="移除引用"
          >
            <X size={11} />
          </button>
        </div>
      )}

      <div className="px-4 pb-1.5 pt-2.5">
        <textarea
          ref={taRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            // 让 popover 接管方向键 / Enter / Tab / Esc
            if (mention && ['ArrowDown', 'ArrowUp', 'Enter', 'Tab', 'Escape'].includes(e.key)) {
              return;
            }
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              dispatch();
            }
          }}
          placeholder="@一下 AI 员工,分配任务..."
          className="w-full min-h-[68px] resize-none border-none bg-transparent text-[13px] leading-[1.65] text-wechat-fg outline-none caret-wechat-green placeholder:text-wechat-mute"
        />
        <div className="flex justify-end pb-1.5">
          <button
            type="button"
            onClick={dispatch}
            disabled={!canSend}
            className={clsx(
              'rounded-sm border border-wechat-line px-4 py-1 text-[12px] transition-colors',
              canSend
                ? 'bg-wechat-green text-white hover:bg-[#06AE56]'
                : 'cursor-not-allowed bg-neutral-100 text-wechat-mute',
            )}
          >
            发送
          </button>
        </div>
      </div>

      <div className="flex items-center gap-0.5 border-t border-wechat-line px-3.5 py-1.5">
        <button type="button" className="toolbar-btn" title="发送文件">
          <Folder size={18} strokeWidth={1.8} />
        </button>
        <button type="button" className="toolbar-btn" title="截图">
          <Scissors size={18} strokeWidth={1.8} />
        </button>
        <button
          type="button"
          className="toolbar-btn"
          title="截图选项"
          onClick={() => undefined}
        >
          <ChevronDown size={9} className="text-wechat-mute" />
        </button>
        {!seriousMode && (
          <button
            type="button"
            className="toolbar-btn"
            title="表情"
            onClick={() => setShowEmoji((v) => !v)}
          >
            <Smile size={18} strokeWidth={1.8} />
          </button>
        )}
      </div>

      {/* placeholder element for the quoted icon - kept inline above */}
      {showEmoji && !seriousMode && (
        <EmojiPicker
          onClose={() => setShowEmoji(false)}
          onPick={(emoji) => {
            setText((t) => t + emoji);
            setShowEmoji(false);
          }}
        />
      )}
    </div>
  );
}

function CornerDownIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className="mt-0.5 flex-shrink-0 text-wechat-green"
    >
      <polyline points="9 10 4 15 9 20" />
      <path d="M20 4v7a4 4 0 0 1-4 4H4" />
    </svg>
  );
}
