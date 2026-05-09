import type { Metadata } from 'next';
import { Providers } from '@/components/providers';
import { AppShell } from '@/components/layout/AppShell';
import './globals.css';

export const metadata: Metadata = {
  title: '有了 — 你的 AI 工作团队',
  description: '微信式群聊形态,1 个总裁助理 + 4 个分任务 Agent + 2 个支持 Agent',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="bg-wechat-bg font-wechat text-wechat-fg">
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
