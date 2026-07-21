'use client';

// 240px 会话列表 — 搜索 + 主会话置顶 + 长按菜单(置顶/静音/删除)+ 模式标识
import { useRouter } from 'next/navigation';
import { Pin, PinOff, Search, Trash2, VolumeX, Volume2 } from 'lucide-react';
import clsx from 'clsx';
import { useMemo, useRef, useState } from 'react';
import { useConversationStore, type ConversationSummary } from '@/stores/conversation';

const MODE_LABEL: Record<string, string> = { plan: 'Plan', ask: 'Ask', auto: 'Auto' };

export function ChatList() {
  const list = useConversationStore((s) => s.list);
  const currentId = useConversationStore((s) => s.currentId);
  const setCurrent = useConversationStore((s) => s.setCurrent);
  const togglePin = useConversationStore((s) => s.togglePin);
  const toggleMute = useConversationStore((s) => s.toggleMute);
  const remove = useConversationStore((s) => s.remove);
  const router = useRouter();
  const [keyword, setKeyword] = useState('');
  const [menu, setMenu] = useState<{ id: string; x: number; y: number } | null>(null);

  // 排序:主会话永远第一 → pinned → last_message_at
  const sorted = useMemo(() => {
    return [...list].sort((a, b) => {
      if (a.kind === 'main_session') return -1;
      if (b.kind === 'main_session') return 1;
      const ap = a.pinned ? 1 : 0;
      const bp = b.pinned ? 1 : 0;
      if (ap !== bp) return bp - ap;
      return (b.preview_time || '').localeCompare(a.preview_time || '');
    });
  }, [list]);

  const filtered = keyword
    ? sorted.filter((c) => c.name.includes(keyword) || c.preview?.includes(keyword))
    : sorted;

  function pick(c: ConversationSummary) {
    setCurrent(c.id);
    if (c.kind === 'main_session') router.push('/');
    else router.push(`/chat/${c.id}`);
  }

  return (
    <aside className="flex h-screen w-[240px] flex-shrink-0 flex-col border-r border-wechat-line bg-white">
      <div className="px-3 py-2">
        <label className="flex h-7 items-center gap-2 rounded bg-neutral-100 px-2">
          <Search size={12} strokeWidth={2.2} className="text-neutral-400" />
          <input
            type="text"
            placeholder="搜索群聊 / 消息"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
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
        {filtered.map((c) => (
          <ChatRow
            key={c.id}
            chat={c}
            active={currentId === c.id}
            onClick={() => pick(c)}
            onContextMenu={(e) => {
              e.preventDefault();
              if (c.kind === 'main_session') return;
              setMenu({ id: c.id, x: e.clientX, y: e.clientY });
            }}
          />
        ))}
      </div>

      {menu && (
        <>
          <span className="fixed inset-0 z-40" onClick={() => setMenu(null)} />
          <ContextMenu
            x={menu.x}
            y={menu.y}
            target={list.find((c) => c.id === menu.id)}
            onPin={() => {
              togglePin(menu.id);
              setMenu(null);
            }}
            onMute={() => {
              toggleMute(menu.id);
              setMenu(null);
            }}
            onDelete={() => {
              if (confirm('删除这个会话?')) remove(menu.id);
              setMenu(null);
            }}
            onClose={() => setMenu(null)}
          />
        </>
      )}
    </aside>
  );
}

function ChatRow({
  chat,
  active,
  onClick,
  onContextMenu,
}: {
  chat: ConversationSummary;
  active: boolean;
  onClick: () => void;
  onContextMenu: (e: React.MouseEvent) => void;
}) {
  const longPressTimer = useRef<number | undefined>(undefined);
  function startLongPress(e: React.PointerEvent) {
    longPressTimer.current = window.setTimeout(() => {
      const fake = new MouseEvent('contextmenu', {
        clientX: e.clientX,
        clientY: e.clientY,
      }) as unknown as React.MouseEvent;
      onContextMenu(fake);
    }, 500);
  }
  function cancelLongPress() {
    if (longPressTimer.current) window.clearTimeout(longPressTimer.current);
  }

  return (
    <button
      type="button"
      onClick={onClick}
      onContextMenu={onContextMenu}
      onPointerDown={startLongPress}
      onPointerUp={cancelLongPress}
      onPointerLeave={cancelLongPress}
      className={clsx(
        'flex h-14 w-full items-center gap-2.5 rounded-md px-2 transition-colors',
        active ? 'bg-wechat-green-soft' : 'hover:bg-neutral-100',
      )}
      style={{ margin: '0 4px', width: 'calc(100% - 8px)' }}
    >
      <div className="relative">
        <ChatAvatar chat={chat} />
        {chat.unread !== undefined && chat.unread > 0 && (
          <span className="absolute -right-1 -top-1 grid h-4 min-w-[16px] place-items-center rounded-full bg-red-500 px-1 text-[9px] font-bold leading-none text-white">
            {chat.unread > 99 ? '99+' : chat.unread}
          </span>
        )}
        {chat.muted && (
          <VolumeX
            size={9}
            className="absolute -bottom-0.5 -right-0.5 rounded-full bg-white p-px text-wechat-mute"
          />
        )}
      </div>
      <div className="min-w-0 flex-1 text-left">
        <div className="mb-0.5 flex items-baseline justify-between gap-1">
          <span className="flex min-w-0 items-center gap-1">
            {chat.pinned && <Pin size={9} className="flex-shrink-0 text-wechat-green" />}
            <span className="truncate text-[13px] font-medium text-wechat-fg">{chat.name}</span>
            {chat.work_mode && (
              <span className="flex-shrink-0 rounded-sm bg-wechat-green-soft px-1 py-px text-[9px] text-wechat-green">
                {MODE_LABEL[chat.work_mode]}
              </span>
            )}
          </span>
          {chat.preview_time && (
            <span className="flex-shrink-0 text-[11px] text-wechat-mute">{chat.preview_time}</span>
          )}
        </div>
        <div className="truncate text-[11px] text-wechat-sub">{chat.preview ?? ''}</div>
      </div>
    </button>
  );
}

function ChatAvatar({ chat }: { chat: ConversationSummary }) {
  const SIZE = 'h-9 w-9 flex-shrink-0';
  if (chat.avatar_image) {
    /* eslint-disable-next-line @next/next/no-img-element */
    return <img src={chat.avatar_image} alt={chat.name} className={`${SIZE} rounded object-cover`} />;
  }
  if (chat.avatar_colors) {
    return (
      <div className={`${SIZE} grid grid-cols-2 gap-[1.5px] overflow-hidden rounded`}>
        {chat.avatar_colors.map((c, i) => (
          <span key={i} style={{ background: c }} />
        ))}
      </div>
    );
  }
  return (
    <div
      className={`${SIZE} flex items-center justify-center rounded text-[12px] font-semibold text-white`}
      style={{ background: chat.avatar_bg ?? '#999' }}
    >
      {chat.avatar_text ?? chat.name.slice(0, 1)}
    </div>
  );
}

function ContextMenu({
  x,
  y,
  target,
  onPin,
  onMute,
  onDelete,
}: {
  x: number;
  y: number;
  target?: ConversationSummary;
  onPin: () => void;
  onMute: () => void;
  onDelete: () => void;
  onClose: () => void;
}) {
  if (!target) return null;
  return (
    <div
      className="fixed z-50 min-w-[140px] overflow-hidden rounded-md border border-wechat-line bg-white shadow-lg"
      style={{ top: y, left: x }}
      onClick={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        onClick={onPin}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-wechat-fg hover:bg-neutral-50"
      >
        {target.pinned ? <PinOff size={12} /> : <Pin size={12} />}
        {target.pinned ? '取消置顶' : '置顶'}
      </button>
      <button
        type="button"
        onClick={onMute}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-wechat-fg hover:bg-neutral-50"
      >
        {target.muted ? <Volume2 size={12} /> : <VolumeX size={12} />}
        {target.muted ? '取消静音' : '静音'}
      </button>
      <button
        type="button"
        onClick={onDelete}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-red-600 hover:bg-red-50"
      >
        <Trash2 size={12} /> 删除会话
      </button>
    </div>
  );
}
