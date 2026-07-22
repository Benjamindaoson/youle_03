'use client';

/* eslint-disable @next/next/no-img-element -- avatar URLs may be signed and short-lived */

import { Search } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';
import clsx from 'clsx';

import { useConversationStore, type ConversationSummary } from '@/stores/conversation';

const MODE_LABEL: Record<string, string> = { plan: 'Plan', ask: 'Ask', auto: 'Auto' };

export function ChatList() {
  const list = useConversationStore((state) => state.list);
  const currentId = useConversationStore((state) => state.currentId);
  const setCurrent = useConversationStore((state) => state.setCurrent);
  const router = useRouter();
  const [keyword, setKeyword] = useState('');

  const filtered = useMemo(() => {
    const ordered = [...list].sort((left, right) => {
      if (left.kind === 'main_session') return -1;
      if (right.kind === 'main_session') return 1;
      return (right.preview_time ?? '').localeCompare(left.preview_time ?? '');
    });
    if (!keyword) return ordered;
    return ordered.filter(
      (conversation) => conversation.name.includes(keyword)
        || conversation.preview?.includes(keyword),
    );
  }, [keyword, list]);

  function selectConversation(conversation: ConversationSummary) {
    setCurrent(conversation.id);
    router.push(
      conversation.kind === 'main_session' ? '/' : `/chat/${conversation.id}`,
    );
  }

  return (
    <aside className="flex h-screen w-[240px] flex-shrink-0 flex-col border-r border-wechat-line bg-white">
      <div className="px-3 py-2">
        <label className="flex h-7 items-center gap-2 rounded bg-neutral-100 px-2">
          <Search size={12} strokeWidth={2.2} className="text-neutral-400" />
          <input
            type="search"
            placeholder="搜索会话"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            className="flex-1 bg-transparent text-[12px] text-wechat-fg outline-none placeholder:text-wechat-mute"
          />
        </label>
      </div>

      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 && (
          <div className="px-4 py-8 text-center text-[12px] text-wechat-mute">
            没有匹配的会话
          </div>
        )}
        {filtered.map((conversation) => (
          <button
            key={conversation.id}
            type="button"
            onClick={() => selectConversation(conversation)}
            className={clsx(
              'mx-1 flex h-14 w-[calc(100%_-_8px)] items-center gap-2.5 rounded-md px-2 transition-colors',
              currentId === conversation.id
                ? 'bg-wechat-green-soft'
                : 'hover:bg-neutral-100',
            )}
          >
            <ChatAvatar conversation={conversation} />
            <div className="min-w-0 flex-1 text-left">
              <div className="mb-0.5 flex items-baseline justify-between gap-1">
                <span className="flex min-w-0 items-center gap-1">
                  <span className="truncate text-[13px] font-medium text-wechat-fg">
                    {conversation.name}
                  </span>
                  {conversation.work_mode && (
                    <span className="flex-shrink-0 rounded-sm bg-wechat-green-soft px-1 py-px text-[9px] text-wechat-green">
                      {MODE_LABEL[conversation.work_mode]}
                    </span>
                  )}
                </span>
                {conversation.preview_time && (
                  <span className="flex-shrink-0 text-[11px] text-wechat-mute">
                    {conversation.preview_time}
                  </span>
                )}
              </div>
              <div className="truncate text-[11px] text-wechat-sub">
                {conversation.preview ?? ''}
              </div>
            </div>
          </button>
        ))}
      </div>
    </aside>
  );
}

function ChatAvatar({ conversation }: { conversation: ConversationSummary }) {
  const size = 'h-9 w-9 flex-shrink-0';
  if (conversation.avatar_image) {
    return (
      <img
        src={conversation.avatar_image}
        alt={conversation.name}
        className={`${size} rounded object-cover`}
      />
    );
  }
  if (conversation.avatar_colors) {
    return (
      <div className={`${size} grid grid-cols-2 gap-[1.5px] overflow-hidden rounded`}>
        {conversation.avatar_colors.map((color, index) => (
          <span key={`${color}-${index}`} style={{ background: color }} />
        ))}
      </div>
    );
  }
  return (
    <div
      className={`${size} flex items-center justify-center rounded text-[12px] font-semibold text-white`}
      style={{ background: conversation.avatar_bg ?? '#999' }}
    >
      {conversation.avatar_text ?? conversation.name.slice(0, 1)}
    </div>
  );
}
