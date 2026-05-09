'use client';

// 单条消息渲染:气泡 / 卡片 / 互动 / HITL
// 严肃场景由 conversation.serious_mode 控制(铁律 §19:严肃场景关闭表情)
// 头像悬停 / 双击触发 AgentProfileCard(v4 §232-241)
import { useEffect, useRef, useState } from 'react';
import clsx from 'clsx';
import { CornerDownLeft, MoreHorizontal, Smile } from 'lucide-react';
import type {
  AgentCardMessage,
  HitlImageMessage,
  HitlScriptMessage,
  HitlVideoMessage,
  Message,
} from '@/stores/conversation';
import { ROLES } from '@/lib/agents';
import { TaskCard } from '@/components/chat/TaskCard';
import { ScriptApproval } from '@/components/hitl/ScriptApproval';
import { ImageSelection } from '@/components/hitl/ImageSelection';
import { VideoFinalReview } from '@/components/hitl/VideoFinalReview';
import { AgentProfileCard } from '@/components/chat/AgentProfileCard';
import { MessageContextMenu } from '@/components/chat/MessageContextMenu';
import { highlightMentions } from '@/lib/mention';
import { useOpenPrivateChat } from '@/lib/api';
import { useRouter } from 'next/navigation';
import { useConversationStore } from '@/stores/conversation';
import { ROLE_AVATAR } from '@/lib/agent-avatars';

const PROFILE_OPEN_EVENT = 'agent-profile-card-open';

export function MessageBubble({ message }: { message: Message }) {
  const meta = ROLES[message.role];
  const isUser = message.role === 'user';
  const isSystem = message.kind === 'system';
  const avatarStyle = ROLE_AVATAR[message.role];
  const avatarRef = useRef<HTMLSpanElement>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const [actionsOpen, setActionsOpen] = useState(false);
  const [anchor, setAnchor] = useState<DOMRect | null>(null);
  const hoverTimer = useRef<number | undefined>(undefined);
  const closeProfileTimer = useRef<number | undefined>(undefined);
  const openPrivate = useOpenPrivateChat();
  const router = useRouter();
  const setQuoted = useConversationStore((s) => s.setQuoted);
  const toggleStar = useConversationStore((s) => s.toggleStar);
  const withdraw = useConversationStore((s) => s.withdrawMessage);
  const starred = useConversationStore((s) => s.starred.includes(message.id));
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const canShowActions = ['user_text', 'agent_text', 'interaction'].includes(message.kind) && !!message.text;

  useEffect(() => {
    function closeWhenAnotherProfileOpens(event: Event) {
      const detail = (event as CustomEvent<{ messageId: string }>).detail;
      if (detail?.messageId !== message.id) setProfileOpen(false);
    }

    window.addEventListener(PROFILE_OPEN_EVENT, closeWhenAnotherProfileOpens);
    return () => {
      window.removeEventListener(PROFILE_OPEN_EVENT, closeWhenAnotherProfileOpens);
      if (hoverTimer.current) window.clearTimeout(hoverTimer.current);
      if (closeProfileTimer.current) window.clearTimeout(closeProfileTimer.current);
    };
  }, [message.id]);

  function cancelProfileClose() {
    if (closeProfileTimer.current) window.clearTimeout(closeProfileTimer.current);
  }

  function scheduleProfileClose() {
    cancelProfileClose();
    closeProfileTimer.current = window.setTimeout(() => setProfileOpen(false), 120);
  }

  function openProfile() {
    if (isUser || isSystem) return;
    cancelProfileClose();
    setAnchor(avatarRef.current?.getBoundingClientRect() ?? null);
    window.dispatchEvent(
      new CustomEvent(PROFILE_OPEN_EVENT, { detail: { messageId: message.id } }),
    );
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
    onForward: () => {
      const text = `转发自 ${meta.name}:\n${message.text || ''}`;
      void navigator.clipboard.writeText(text);
      alert('已复制为转发文本');
    },
    onStar: () => toggleStar(message.id),
    onWithdraw: isUser ? () => withdraw(message.conversation_id, message.id) : undefined,
    onLocate: () => {
      const el = document.getElementById(`msg-${message.id}`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el?.classList.add('ring-2', 'ring-wechat-green');
      setTimeout(() => el?.classList.remove('ring-2', 'ring-wechat-green'), 1500);
    },
  };

  if (isSystem) {
    return (
      <div className="my-5 text-center">
        <span className="text-[11px] leading-none text-[#8f96a3]">
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
      onMouseEnter={() => setActionsOpen(true)}
      onMouseLeave={() => setActionsOpen(false)}
      className={clsx(
        'mb-3.5 flex animate-fade-up items-start gap-2.5 transition-shadow',
        isUser ? 'flex-row-reverse' : 'flex-row',
        starred && 'ring-1 ring-amber-300',
      )}
    >
      <span
        ref={avatarRef}
        className={clsx(
          'flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-cover bg-center text-[12px] font-bold text-white shadow-sm',
          !isUser && 'cursor-pointer ring-wechat-green hover:ring-2',
        )}
        style={avatarStyle ?? { background: meta.color }}
        onMouseEnter={() => {
          if (isUser || isSystem) return;
          cancelProfileClose();
          hoverTimer.current = window.setTimeout(openProfile, 300);
        }}
        onMouseLeave={() => {
          if (hoverTimer.current) window.clearTimeout(hoverTimer.current);
          scheduleProfileClose();
        }}
        onDoubleClick={openProfile}
      >
        {!avatarStyle && meta.initial}
      </span>

      {profileOpen && (
        <AgentProfileCard
          data={{ role: message.role }}
          anchorRect={anchor}
          onClose={() => setProfileOpen(false)}
          onPrivateChat={startPrivateChat}
          onMouseEnter={cancelProfileClose}
          onMouseLeave={scheduleProfileClose}
        />
      )}
      {menu && (
        <MessageContextMenu
          x={menu.x}
          y={menu.y}
          isUser={isUser}
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
            <span className="text-[12px] font-normal leading-4 tracking-normal text-[#6B7280] [font-family:Sora,var(--font-wechat)]">
              {meta.name}
            </span>
            {message.time && (
              <span className="text-[11px] text-wechat-mute">{message.time}</span>
            )}
          </div>
        )}

        {/* 文字气泡 */}
        {(message.kind === 'user_text' ||
          message.kind === 'agent_text' ||
          message.kind === 'interaction') &&
          message.text && (
            <div className="relative">
              <BubbleText
                isUser={isUser}
                text={message.text}
                isInteraction={message.kind === 'interaction'}
              />
              {actionsOpen && canShowActions && (
                <MessageHoverActions
                  isUser={isUser}
                  onQuote={() => menuActions.onQuote()}
                  onMore={(event) => {
                    const rect = event.currentTarget.getBoundingClientRect();
                    setMenu({ x: rect.left, y: rect.bottom + 6 });
                  }}
                />
              )}
            </div>
          )}

        {/* TaskCard */}
        {message.kind === 'agent_card' && (
          <TaskCard
            card={(message as AgentCardMessage).card}
            agentColor={meta.color}
          />
        )}

        {/* HITL gates 内嵌入消息流 */}
        {message.kind === 'hitl_script' && (
          <ScriptApproval
            taskId={(message as HitlScriptMessage).task_id}
            gateId={(message as HitlScriptMessage).gate_id}
            versions={(message as HitlScriptMessage).versions}
          />
        )}
        {message.kind === 'hitl_image' && (
          <ImageSelection
            taskId={(message as HitlImageMessage).task_id}
            gateId={(message as HitlImageMessage).gate_id}
            images={(message as HitlImageMessage).images}
          />
        )}
        {message.kind === 'hitl_video' && (
          <VideoFinalReview
            taskId={(message as HitlVideoMessage).task_id}
            gateId={(message as HitlVideoMessage).gate_id}
            videoUrl={(message as HitlVideoMessage).video_url}
          />
        )}
      </div>
    </div>
  );
}

function BubbleText({
  isUser,
  text,
  isInteraction,
}: {
  isUser: boolean;
  text: string;
  isInteraction?: boolean;
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
          'rounded-[16px] px-3 py-2 font-normal leading-5 tracking-normal text-[14px] [font-family:Sora,var(--font-wechat)]',
          isUser
            ? 'bg-[#71BEFF1A] text-[#111827]'
            : 'bg-[#00000008] text-[#111827]',
          isInteraction && 'italic text-wechat-sub',
        )}
      >
        {highlightMentions(text)}
      </div>
    </div>
  );
}

function MessageHoverActions({
  isUser,
  onQuote,
  onMore,
}: {
  isUser: boolean;
  onQuote: () => void;
  onMore: (event: React.MouseEvent<HTMLButtonElement>) => void;
}) {
  return (
    <div
      className={clsx(
        'absolute top-1/2 z-20 flex h-10 items-center gap-1 rounded-[12px] bg-white px-2 shadow-[0_8px_24px_rgba(17,24,39,0.14)] ring-1 ring-black/5',
        'animate-message-actions-pop',
        isUser ? 'right-full mr-2' : 'left-full ml-2',
      )}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <button
        type="button"
        className="flex h-7 w-7 items-center justify-center rounded-full text-[#6B7280] transition-colors hover:bg-[#00000008] hover:text-[#111827]"
        aria-label="Emoji"
      >
        <Smile size={18} strokeWidth={1.7} />
      </button>
      <button
        type="button"
        onClick={onQuote}
        className="flex h-7 w-7 items-center justify-center rounded-full text-[#6B7280] transition-colors hover:bg-[#00000008] hover:text-[#111827]"
        aria-label="Quote"
      >
        <CornerDownLeft size={18} strokeWidth={1.7} />
      </button>
      <button
        type="button"
        onClick={onMore}
        className="flex h-7 w-7 items-center justify-center rounded-full text-[#6B7280] transition-colors hover:bg-[#00000008] hover:text-[#111827]"
        aria-label="More"
      >
        <MoreHorizontal size={18} strokeWidth={1.7} />
      </button>
    </div>
  );
}
