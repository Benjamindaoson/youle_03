'use client';

import { BookOpen, LogOut } from 'lucide-react';
import { useRouter } from 'next/navigation';

import { useUserStore } from '@/stores/user';

export default function SettingsPage() {
  const router = useRouter();
  const logout = useUserStore((state) => state.logout);

  function handleLogout() {
    if (!window.confirm('确认退出登录？')) return;
    logout();
    router.push('/login');
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-white">
      <header className="flex h-14 flex-shrink-0 items-center border-b border-wechat-line px-5">
        <h1 className="text-[15px] font-semibold text-wechat-fg">设置</h1>
      </header>

      <div className="mx-auto w-full max-w-2xl space-y-5 p-6">
        <section className="rounded-md border border-wechat-line bg-white p-4">
          <h2 className="flex items-center gap-2 text-[13px] font-medium text-wechat-fg">
            <BookOpen size={14} /> 项目文档
          </h2>
          <p className="mt-1 text-[11px] text-wechat-mute">
            查看本地启动、低成本模式、API 配置和部署说明。
          </p>
          <a
            href="https://github.com/Benjamindaoson/youle-mas#readme"
            target="_blank"
            rel="noreferrer"
            className="mt-3 inline-block text-[12px] text-wechat-green hover:underline"
          >
            打开 README
          </a>
        </section>

        <button
          type="button"
          onClick={handleLogout}
          className="flex w-full items-center justify-center gap-2 rounded-sm border border-wechat-line py-2 text-[13px] text-red-600 hover:bg-red-50"
        >
          <LogOut size={13} /> 退出登录
        </button>
      </div>
    </div>
  );
}
