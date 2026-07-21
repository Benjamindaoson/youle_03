'use client';

// 消息长按菜单(v4 §161 / §165):复制 / 引用 / 转发 / 收藏 / 撤回 / 跳转上下文
import { Copy, CornerDownRight, Forward, Star, Undo2, Crosshair } from 'lucide-react';
import { useEffect } from 'react';

export interface MessageMenuActions {
  onCopy: () => void;
  onQuote: () => void;
  onForward: () => void;
  onStar: () => void;
  onWithdraw?: () => void;
  onLocate?: () => void;
}

export function MessageContextMenu({
  x,
  y,
  isUser,
  actions,
  onClose,
}: {
  x: number;
  y: number;
  isUser: boolean;
  actions: MessageMenuActions;
  onClose: () => void;
}) {
  useEffect(() => {
    function onEsc(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onEsc);
    return () => window.removeEventListener('keydown', onEsc);
  }, [onClose]);

  return (
    <>
      <span className="fixed inset-0 z-40" onClick={onClose} />
      <div
        className="fixed z-50 min-w-[140px] overflow-hidden rounded-md border border-wechat-line bg-white shadow-lg"
        style={{ top: Math.max(8, Math.min(y, window.innerHeight - 220)), left: Math.max(8, Math.min(x, window.innerWidth - 160)) }}
        onClick={(e) => e.stopPropagation()}
      >
        <Item icon={<Copy size={12} />} label="复制" onClick={() => { actions.onCopy(); onClose(); }} />
        <Item icon={<CornerDownRight size={12} />} label="引用" onClick={() => { actions.onQuote(); onClose(); }} />
        <Item icon={<Forward size={12} />} label="转发" onClick={() => { actions.onForward(); onClose(); }} />
        <Item icon={<Star size={12} />} label="收藏" onClick={() => { actions.onStar(); onClose(); }} />
        {actions.onLocate && (
          <Item icon={<Crosshair size={12} />} label="定位上下文" onClick={() => { actions.onLocate?.(); onClose(); }} />
        )}
        {isUser && actions.onWithdraw && (
          <Item icon={<Undo2 size={12} />} label="撤回" danger onClick={() => { actions.onWithdraw?.(); onClose(); }} />
        )}
      </div>
    </>
  );
}

function Item({
  icon,
  label,
  danger,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  danger?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] hover:bg-neutral-50 ${danger ? 'text-red-600 hover:bg-red-50' : 'text-wechat-fg'}`}
    >
      {icon}
      {label}
    </button>
  );
}
