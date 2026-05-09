'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import clsx from 'clsx';
import { useProfile } from '@/lib/api';

type SvgNavItem = {
  id: string;
  label: string;
  tip?: string;
  href: string;
  svgActive: string;
  svgInactive: string;
};

const SVG_NAV: SvgNavItem[] = [
  {
    id: 'chat',
    label: '\u6d88\u606f',
    href: '/',
    svgActive: '/home/message-active.svg',
    svgInactive: '/home/message.svg',
  },
  {
    id: 'prompts',
    label: '\u6210\u679c\u5e93',
    tip: '\u6210\u679c\u5e93\uff0c\u6570\u5b57\u5458\u5de5\u7684\u6240\u6709\u5de5\u4f5c\u6210\u679c',
    href: '/results',
    svgActive: '/home/library-active.svg',
    svgInactive: '/home/library.svg',
  },
  {
    id: 'results',
    label: '\u77e5\u8bc6\u5e93',
    tip: '\u77e5\u8bc6\u5e93\uff0c\u4f60\u4e0a\u4f20\u8fc7\u7684\u6240\u6709\u6587\u4ef6\u8d44\u6599',
    href: '/materials',
    svgActive: '/home/resources-active.svg',
    svgInactive: '/home/resources.svg',
  },
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
    <nav className="flex h-screen w-[60px] flex-shrink-0 flex-col items-center border-r border-wechat-line bg-[#f5f5f5] py-3">
      <button
        type="button"
        onClick={() => router.push('/profile')}
        className="mb-4 h-[34px] w-[34px] overflow-hidden rounded-full"
        title="Profile"
      >
        <span className="grid h-full w-full place-items-center bg-wechat-green-soft text-[12px] font-semibold text-wechat-green">
          {profile?.nickname?.slice(0, 2) ?? '\u8001\u677f'}
        </span>
      </button>

      {SVG_NAV.map((it) => {
        const active = activeFor(it.href);
        return (
          <Link
            key={it.id}
            href={it.href}
            className="tip-parent relative mb-1 flex h-9 w-9 items-center justify-center rounded transition-opacity"
            aria-label={it.label}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={active ? it.svgActive : it.svgInactive}
              alt={it.label}
              width={36}
              height={36}
              className={clsx('rounded-full', !active && 'opacity-60')}
            />
            {it.tip && <span className="tip-base tip-right">{it.tip}</span>}
          </Link>
        );
      })}

      <div className="flex-1" />

      <Link
        href="/settings"
        aria-label="Settings"
        className="mb-1 flex h-9 w-9 items-center justify-center rounded transition-opacity"
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/home/icon-skills.svg"
          alt="Settings"
          width={20}
          height={20}
          className={clsx(pathname.startsWith('/settings') ? 'opacity-100' : 'opacity-40 hover:opacity-70')}
        />
      </Link>
    </nav>
  );
}
