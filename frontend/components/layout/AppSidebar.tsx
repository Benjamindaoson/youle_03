'use client';

// 60px 应用栏 — 顶部用户头像 + 6 个 nav
// ADR-016 简化:取消通讯录等多余入口;v4 §3 加 AI 学院 / 技能市场
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  BookOpen,
  GraduationCap,
  MessageSquare,
  Package,
  Settings,
  Store,
} from 'lucide-react';
import clsx from 'clsx';
import { useProfile } from '@/lib/api';

type NavId =
  | 'chat'
  | 'prompts'
  | 'results'
  | 'academy'
  | 'market'
  | 'settings';

const NAV: {
  id: NavId;
  label: string;
  icon: typeof MessageSquare;
  href: string;
  position: 'top' | 'bottom';
}[] = [
  { id: 'chat',     label: '聊天',     icon: MessageSquare, href: '/',         position: 'top' },
  { id: 'prompts',  label: '知识库',   icon: BookOpen,      href: '/prompts',  position: 'top' },
  { id: 'results',  label: '成果库',   icon: Package,       href: '/results',  position: 'top' },
  { id: 'academy',  label: 'AI 学院',  icon: GraduationCap, href: '/academy',  position: 'top' },
  { id: 'market',   label: '技能市场', icon: Store,         href: '/market',   position: 'top' },
  { id: 'settings', label: '设置',     icon: Settings,      href: '/settings', position: 'bottom' },
];

export function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { data: profile } = useProfile();

  function activeFor(href: string): boolean {
    if (href === '/') return pathname === '/' || pathname.startsWith('/chat');
    return pathname.startsWith(href);
  }

  return (
    <nav className="flex h-screen w-[60px] flex-shrink-0 flex-col items-center border-r border-wechat-line bg-neutral-50 py-3">
      <button
        type="button"
        onClick={() => router.push('/profile')}
        className="mb-4 h-[34px] w-[34px] overflow-hidden rounded-full"
        title="个人主页"
      >
        <span className="grid h-full w-full place-items-center bg-wechat-green-soft text-[12px] font-semibold text-wechat-green">
          {profile?.nickname?.slice(0, 2) ?? '老板'}
        </span>
      </button>

      {NAV.filter((i) => i.position === 'top').map((it) => (
        <NavLink
          key={it.id}
          href={it.href}
          label={it.label}
          active={activeFor(it.href)}
        >
          <it.icon size={20} strokeWidth={1.8} />
        </NavLink>
      ))}

      <div className="flex-1" />

      {NAV.filter((i) => i.position === 'bottom').map((it) => (
        <NavLink
          key={it.id}
          href={it.href}
          label={it.label}
          active={activeFor(it.href)}
        >
          <it.icon size={20} strokeWidth={1.8} />
        </NavLink>
      ))}
    </nav>
  );
}

function NavLink({
  href,
  active,
  label,
  children,
}: {
  href: string;
  active: boolean;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      title={label}
      className={clsx(
        'mb-1 flex h-9 w-9 items-center justify-center rounded transition-colors',
        active
          ? 'bg-wechat-green-soft text-wechat-green'
          : 'text-wechat-mute hover:bg-neutral-200 hover:text-wechat-fg',
      )}
    >
      {children}
    </Link>
  );
}
