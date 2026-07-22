'use client';

import { Copy, CornerDownRight, Crosshair } from 'lucide-react';
import { useEffect } from 'react';

export interface MessageMenuActions {
  onCopy: () => void;
  onQuote: () => void;
  onLocate: () => void;
}

export function MessageContextMenu({ x, y, actions, onClose }: {
  x: number;
  y: number;
  actions: MessageMenuActions;
  onClose: () => void;
}) {
  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);

  const items = [
    { icon: <Copy size={12} />, label: '复制', action: actions.onCopy },
    { icon: <CornerDownRight size={12} />, label: '引用', action: actions.onQuote },
    { icon: <Crosshair size={12} />, label: '定位', action: actions.onLocate },
  ];

  return (
    <>
      <button type="button" aria-label="关闭消息菜单" className="fixed inset-0 z-40 cursor-default" onClick={onClose} />
      <div
        className="fixed z-50 min-w-[120px] overflow-hidden rounded-md border border-wechat-line bg-white shadow-lg"
        style={{
          top: Math.max(8, Math.min(y, window.innerHeight - 140)),
          left: Math.max(8, Math.min(x, window.innerWidth - 140)),
        }}
      >
        {items.map((item) => (
          <button
            key={item.label}
            type="button"
            onClick={() => { item.action(); onClose(); }}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-wechat-fg hover:bg-neutral-50"
          >
            {item.icon}{item.label}
          </button>
        ))}
      </div>
    </>
  );
}
