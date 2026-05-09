'use client';

// Agent 产出的"任务卡片"消息(对齐 frontend_001 视觉)
// v4 §23 #211-218:卡片操作 [下载] [追问] [改一下]
import { useState } from 'react';
import {
  ArrowRight,
  Download,
  FileText,
  Image as ImageIcon,
  MessageCircle,
  PenLine,
  Wand2,
  Video,
} from 'lucide-react';
import clsx from 'clsx';
import type { AgentCardMessage } from '@/stores/conversation';
import { useConversationStore } from '@/stores/conversation';

const ICONS = {
  doc: FileText,
  pen: PenLine,
  image: ImageIcon,
  video: Video,
};

const REVISE_OPTIONS: { key: string; label: string }[] = [
  { key: 'style', label: '改风格' },
  { key: 'content', label: '改内容' },
  { key: 'length', label: '改长度' },
];

export function TaskCard({
  card,
  agentColor,
  conversationId,
  reference,
  onAskFollowUp,
  onRevise,
}: {
  card: AgentCardMessage['card'];
  agentColor: string;
  conversationId?: string;
  reference?: string;
  onAskFollowUp?: () => void;
  onRevise?: (key: string) => void;
}) {
  const Icon = ICONS[card.icon];
  const isDone = card.tag_status === 'done';
  const [reviseOpen, setReviseOpen] = useState(false);
  const setQuoted = useConversationStore((s) => s.setQuoted);

  function defaultAskFollowUp() {
    if (conversationId) {
      setQuoted(conversationId, {
        messageId: `card-${card.title}`,
        preview: card.title,
        role: 'ceo_assistant',
      });
      // 滚动到输入框
      requestAnimationFrame(() => {
        document.querySelector('textarea')?.focus();
      });
    }
  }

  return (
    <div className="w-[480px] max-w-full overflow-hidden rounded-md border border-wechat-line bg-white shadow-sm">
      <div className="flex items-center gap-2 border-b border-neutral-100 px-3.5 py-2.5">
        <span
          className="grid h-[18px] w-[18px] flex-shrink-0 place-items-center rounded-sm text-white"
          style={{ background: agentColor }}
        >
          <Icon size={10} strokeWidth={2.5} />
        </span>
        <span className="flex-1 truncate text-[12px] font-semibold text-wechat-fg">
          {card.title}
        </span>
        <span className="flex-shrink-0 text-[10px] font-medium text-wechat-green">
          {card.tag}
        </span>
      </div>

      {!isDone && card.progress !== undefined && (
        <div className="h-[3px] bg-neutral-100">
          <span
            className="block h-full bg-wechat-green transition-all"
            style={{ width: `${card.progress}%` }}
          />
        </div>
      )}

      <div className="px-3.5 py-2.5">
        {card.word_count && (
          <div className="mb-2">
            <span className="pill">{card.word_count}</span>
          </div>
        )}

        <ul className="flex flex-col gap-1">
          {card.items.map((it, i) => (
            <li
              key={i}
              className="flex items-start gap-1.5 text-[12px] leading-[1.6] text-neutral-700"
            >
              <span className="flex-shrink-0 font-bold leading-[1.6] text-wechat-green">·</span>
              <span>{it}</span>
            </li>
          ))}
        </ul>

        {card.footer && (
          <button
            type="button"
            className="mt-2 flex items-center gap-1 border-t border-neutral-100 pt-2 text-[11px] text-[#5B9DD9]"
          >
            <ArrowRight size={10} strokeWidth={2.5} />
            {card.footer}
          </button>
        )}
      </div>

      {isDone && (
        <div className="flex divide-x divide-neutral-100 border-t border-neutral-100 bg-neutral-50">
          {reference && (
            <a
              href={reference}
              target="_blank"
              rel="noreferrer"
              className="flex flex-1 items-center justify-center gap-1 py-1.5 text-[11px] text-wechat-fg hover:bg-white"
            >
              <Download size={11} /> 下载
            </a>
          )}
          <button
            type="button"
            onClick={onAskFollowUp ?? defaultAskFollowUp}
            className="flex flex-1 items-center justify-center gap-1 py-1.5 text-[11px] text-wechat-fg hover:bg-white"
          >
            <MessageCircle size={11} /> 追问
          </button>
          <button
            type="button"
            onClick={() => setReviseOpen((v) => !v)}
            className={clsx(
              'flex flex-1 items-center justify-center gap-1 py-1.5 text-[11px] hover:bg-white',
              reviseOpen ? 'bg-white text-wechat-green' : 'text-wechat-fg',
            )}
          >
            <Wand2 size={11} /> 改一下
          </button>
        </div>
      )}

      {reviseOpen && (
        <div className="flex flex-wrap gap-1.5 border-t border-neutral-100 bg-white px-3 py-2">
          {REVISE_OPTIONS.map((o) => (
            <button
              key={o.key}
              type="button"
              onClick={() => {
                onRevise?.(o.key);
                setReviseOpen(false);
              }}
              className="rounded-sm border border-wechat-line bg-white px-2 py-0.5 text-[11px] text-wechat-fg hover:border-wechat-green hover:bg-wechat-green-soft"
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
