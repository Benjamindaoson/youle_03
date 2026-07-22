'use client';

// 单条消息渲染:气泡 / 卡片 / 互动 / HITL
// 严肃场景由 conversation.serious_mode 控制(铁律 §19:严肃场景关闭表情)
// 头像悬停 / 双击触发 AgentProfileCard(v4 §232-241)
import { useRef, useState } from 'react';
import clsx from 'clsx';
import type {
  AgentCardMessage,
  Message,
} from '@/stores/conversation';
import { ROLES } from '@/lib/agents';
import { TaskCard } from '@/components/chat/TaskCard';
import { AgentProfileCard } from '@/components/chat/AgentProfileCard';
import { MessageContextMenu } from '@/components/chat/MessageContextMenu';
import { highlightMentions } from '@/lib/mention';
import { useOpenPrivateChat } from '@/lib/api';
import { useRouter } from 'next/navigation';
import { useConversationStore } from '@/stores/conversation';

export function MessageBubble({ message }: { message: Message }) {
  const meta = ROLES[message.role];
  const isUser = message.role === 'user';
  const isSystem = message.kind === 'system';
  const avatarRef = useRef<HTMLSpanElement>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const [anchor, setAnchor] = useState<DOMRect | null>(null);
  const hoverTimer = useRef<number | undefined>(undefined);
  const openPrivate = useOpenPrivateChat();
  const router = useRouter();
  const setQuoted = useConversationStore((s) => s.setQuoted);
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);

  function openProfile() {
    if (isUser || isSystem) return;
    setAnchor(avatarRef.current?.getBoundingClientRect() ?? null);
    setProfileOpen(true);
  }

  function startPrivateChat() {
    if (isUser || isSystem) return;
    openPrivate.mutate(message.role, {
      onSuccess: (conv) => {
        router.push(`/chat/${(conv as { id: string }).id}`);
      },
    });
  }

  function openMenu(e: React.MouseEvent) {
    if (isSystem) return;
    e.preventDefault();
    setMenu({ x: e.clientX, y: e.clientY });
  }

  const longPressTimer = useRef<number | undefined>(undefined);
  function startLongPress(e: React.PointerEvent) {
    if (isSystem) return;
    const cx = e.clientX;
    const cy = e.clientY;
    longPressTimer.current = window.setTimeout(() => setMenu({ x: cx, y: cy }), 500);
  }
  function cancelLongPress() {
    if (longPressTimer.current) window.clearTimeout(longPressTimer.current);
  }

  const menuActions = {
    onCopy: () => {
      void navigator.clipboard.writeText(message.text || '');
    },
    onQuote: () => {
      setQuoted(message.conversation_id, {
        messageId: message.id,
        preview: (message.text || '').slice(0, 80),
        role: message.role,
      });
    },
    onLocate: () => {
      const el = document.getElementById(`msg-${message.id}`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el?.classList.add('ring-2', 'ring-wechat-green');
      setTimeout(() => el?.classList.remove('ring-2', 'ring-wechat-green'), 1500);
    },
  };

  if (isSystem) {
    return (
      <div className="my-3 text-center">
        <span className="rounded-sm bg-black/5 px-2.5 py-0.5 text-[11px] text-wechat-mute">
          {message.text}
        </span>
      </div>
    );
  }

  return (
    <div
      id={`msg-${message.id}`}
      onContextMenu={openMenu}
      onPointerDown={startLongPress}
      onPointerUp={cancelLongPress}
      onPointerLeave={cancelLongPress}
      className={clsx(
        'mb-3.5 flex animate-fade-up items-start gap-2.5 transition-shadow',
        isUser ? 'flex-row-reverse' : 'flex-row',
      )}
    >
      <span
        ref={avatarRef}
        className={clsx(
          'flex h-9 w-9 flex-shrink-0 items-center justify-center rounded text-[12px] font-bold text-white',
          !isUser && 'cursor-pointer ring-wechat-green hover:ring-2',
        )}
        style={{ background: meta.color }}
        onMouseEnter={() => {
          if (isUser || isSystem) return;
          hoverTimer.current = window.setTimeout(openProfile, 300);
        }}
        onMouseLeave={() => {
          if (hoverTimer.current) window.clearTimeout(hoverTimer.current);
        }}
        onDoubleClick={openProfile}
      >
        {meta.initial}
      </span>

      {profileOpen && (
        <AgentProfileCard
          data={{ role: message.role }}
          anchorRect={anchor}
          onClose={() => setProfileOpen(false)}
          onPrivateChat={startPrivateChat}
        />
      )}
      {menu && (
        <MessageContextMenu
          x={menu.x}
          y={menu.y}
          actions={menuActions}
          onClose={() => setMenu(null)}
        />
      )}

      <div
        className={clsx(
          'flex max-w-[72%] flex-col',
          isUser ? 'items-end' : 'items-start',
        )}
      >
        {!isUser && (
          <div className="mb-1 flex items-center gap-1.5">
            <span className="role-badge">{meta.name}</span>
            {message.time && (
              <span className="text-[11px] text-wechat-mute">{message.time}</span>
            )}
          </div>
        )}

        {/* 文字气泡 */}
        {(message.kind === 'user_text' || message.kind === 'agent_text') &&
          message.text && (
            <BubbleText isUser={isUser} text={message.text} />
          )}

        {/* TaskCard */}
        {message.kind === 'agent_card' && (
          <TaskCard
            card={(message as AgentCardMessage).card}
            agentColor={meta.color}
          />
        )}

      </div>
    </div>
  );
}

function BubbleText({
  isUser,
  text,
}: {
  isUser: boolean;
  text: string;
}) {
  return (
    <div className="relative">
      {isUser ? (
        <span className="absolute right-[-6px] top-2.5 h-0 w-0 border-y-[6px] border-l-[6px] border-y-transparent border-l-wechat-bubble-user" />
      ) : (
        <span className="absolute left-[-6px] top-2.5 h-0 w-0 border-y-[6px] border-r-[6px] border-y-transparent border-r-white" />
      )}
      <div
        className={clsx(
          'rounded-md px-3 py-2 text-[13px] leading-[1.65] shadow-sm',
          isUser
            ? 'bg-wechat-bubble-user text-wechat-fg'
            : 'bg-white text-wechat-fg',
        )}
      >
        {highlightMentions(text)}
      </div>
    </div>
  );
}
