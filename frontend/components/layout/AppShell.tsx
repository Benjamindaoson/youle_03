'use client';

// 四栏布局壳:60px AppSidebar / 240px ChatList / 1fr 中栏 / 400px AgentPanel
// 桌面优先;移动端(< 768px)三栏可折叠为抽屉:
//   左栏抽屉 / 主对话(默认)/ 右栏抽屉
import { useEffect, useState } from 'react';
import { Menu, PanelRight, X } from 'lucide-react';
import clsx from 'clsx';
import { AppSidebar } from '@/components/layout/AppSidebar';
import { ChatList } from '@/components/layout/ChatList';
import { AgentPanel } from '@/components/layout/AgentPanel';
import { useConversationStore } from '@/stores/conversation';
import { useConversations } from '@/lib/api';
import { useUserStore } from '@/stores/user';
import { useWsLifecycle } from '@/lib/ws';

export function AppShell({ children }: { children: React.ReactNode }) {
  const { data: conversations } = useConversations();
  const setList = useConversationStore((s) => s.setList);
  const list = useConversationStore((s) => s.list);
  const currentId = useConversationStore((s) => s.currentId);
  const setCurrent = useConversationStore((s) => s.setCurrent);
  const token = useUserStore((s) => s.token);

  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);

  useWsLifecycle(token);

  useEffect(() => {
    if (conversations && conversations.length) setList(conversations);
  }, [conversations, setList]);

  useEffect(() => {
    if (!currentId && list.length) {
      const main = list.find((c) => c.kind === 'main_session') ?? list[0];
      if (main) setCurrent(main.id);
    }
  }, [list, currentId, setCurrent]);

  const current = list.find((c) => c.id === currentId) ?? null;
  const showAgentPanel =
    !!current && current.kind !== 'private_chat' && current.work_mode === 'auto';

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-wechat-bg">
      {/* 移动端顶部工具栏 */}
      <header className="absolute left-0 right-0 top-0 z-30 flex h-10 items-center justify-between border-b border-wechat-line bg-white px-2 md:hidden">
        <button
          type="button"
          onClick={() => setLeftOpen(true)}
          className="rounded p-1.5 text-wechat-fg hover:bg-neutral-100"
          aria-label="打开导航"
        >
          <Menu size={16} />
        </button>
        <span className="text-[13px] font-semibold text-wechat-fg">
          {current?.name ?? '有了'}
        </span>
        {showAgentPanel ? (
          <button
            type="button"
            onClick={() => setRightOpen(true)}
            className="rounded p-1.5 text-wechat-fg hover:bg-neutral-100"
            aria-label="打开执行流"
          >
            <PanelRight size={16} />
          </button>
        ) : (
          <span className="w-7" />
        )}
      </header>

      {/* 桌面侧栏 */}
      <div className="hidden md:contents">
        <AppSidebar />
        <ChatList />
      </div>

      {/* 移动端左侧抽屉 */}
      {leftOpen && (
        <Drawer side="left" onClose={() => setLeftOpen(false)}>
          <div className="flex h-full">
            <AppSidebar />
            <ChatList />
          </div>
        </Drawer>
      )}

      <main className="flex min-w-0 flex-1 overflow-hidden pt-10 md:pt-0">{children}</main>

      {/* 桌面右侧 AgentPanel */}
      {showAgentPanel && (
        <aside className="hidden w-[400px] flex-shrink-0 md:block">
          <AgentPanel />
        </aside>
      )}

      {/* 移动端右侧抽屉 */}
      {rightOpen && (
        <Drawer side="right" onClose={() => setRightOpen(false)}>
          <div className="h-full w-[320px] max-w-[80vw]">
            <AgentPanel />
          </div>
        </Drawer>
      )}
    </div>
  );
}

function Drawer({
  side,
  children,
  onClose,
}: {
  side: 'left' | 'right';
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <>
      <span
        className="fixed inset-0 z-40 bg-black/40 md:hidden"
        onClick={onClose}
      />
      <div
        className={clsx(
          'fixed inset-y-0 z-50 flex bg-white shadow-xl md:hidden',
          side === 'left' ? 'left-0 animate-slide-in-left' : 'right-0 animate-slide-in-right',
        )}
      >
        {children}
        <button
          type="button"
          onClick={onClose}
          className="absolute right-2 top-2 rounded p-1 text-wechat-mute hover:bg-neutral-100"
          aria-label="关闭"
        >
          <X size={14} />
        </button>
      </div>
    </>
  );
}
