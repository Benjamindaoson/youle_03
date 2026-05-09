'use client';

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useRouter } from 'next/navigation';
import { ROLE_AVATAR } from '@/lib/agent-avatars';
import { ROLES, type RoleKey } from '@/lib/agents';

export interface AgentCardData {
  role: RoleKey;
  personalCount?: number;
}

interface Props {
  data: AgentCardData;
  anchorRect: DOMRect | null;
  onClose: () => void;
  onPrivateChat?: () => void;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}

export function AgentProfileCard({
  data,
  anchorRect,
  onClose,
  onPrivateChat,
  onMouseEnter,
  onMouseLeave,
}: Props) {
  const router = useRouter();
  const meta = ROLES[data.role];
  const avatarStyle = ROLE_AVATAR[data.role];
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const [mounted, setMounted] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    function closeOnOutsidePointerDown(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && cardRef.current?.contains(target)) return;
      onClose();
    }

    document.addEventListener('pointerdown', closeOnOutsidePointerDown, true);
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsidePointerDown, true);
    };
  }, [onClose]);

  useEffect(() => {
    if (!anchorRect) return;
    const cardWidth = 260;
    const cardHeight = 128;
    let top = anchorRect.top - 8;
    let left = anchorRect.right + 12;

    if (top + cardHeight > window.innerHeight) top = window.innerHeight - cardHeight - 8;
    if (left + cardWidth > window.innerWidth) left = window.innerWidth - cardWidth - 8;
    setPosition({ top: Math.max(8, top), left: Math.max(8, left) });
  }, [anchorRect]);

  if (!mounted) return null;

  return createPortal(
    <>
      <span className="pointer-events-none fixed inset-0 z-[9998]" />
      <div
        ref={cardRef}
        className="fixed z-[9999] flex w-[260px] origin-top-left animate-profile-pop flex-col gap-2.5 rounded-[12px] border border-black/[0.06] bg-white p-2.5 shadow-[0_10px_28px_rgba(17,24,39,0.14)]"
        style={{ top: position.top, left: position.left }}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
      >
        <div className="flex items-center gap-3">
          <span
            className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-cover bg-center text-[14px] font-semibold text-white"
            style={avatarStyle ?? { background: meta.color }}
          >
            {!avatarStyle && meta.initial}
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[14px] font-medium leading-5 text-[#111827]">
              {meta.name}
            </div>
            <div className="mt-0.5 truncate text-[13px] font-normal leading-5 text-[#6B7280]">
              {'\u5de5\u4f5c\u4e2d...'}
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            onClose();
            if (onPrivateChat) onPrivateChat();
            else router.push(`/chat/private/${data.role}`);
          }}
          className="flex h-11 w-full items-center justify-center rounded-[8px] bg-[#00000008] text-[14px] font-medium leading-5 text-[#111827] transition-colors hover:bg-[#00000012]"
        >
          {'\u53d1\u6d88\u606f'}
        </button>
      </div>
    </>,
    document.body,
  );
}
