'use client';

import clsx from 'clsx';
import { ROLE_AVATAR } from '@/lib/agent-avatars';
import { ROLES, type RoleKey } from '@/lib/agents';

const TITLE = '\u7fa4\u534f\u4f5c\u770b\u677f\uff08\u7cfb\u7edf\u5728\u7f16\u6392\uff09';
const FLOW_TITLE = '\u7ade\u54c1\u5206\u6790\u5e08 \u00b7 \u5b9e\u65f6\u6267\u884c\u6d41';

const HERO_ROLES: RoleKey[] = ['agent_1', 'agent_2', 'agent_3'];

const STEPS = [
  {
    title: '\u6536\u5230\u4efb\u52a1\uff1a\u626b\u63cf\u4e09\u80ce\u8d5b\u9053',
    detail: 'spec_id=T1 \u00b7 \u6765\u81ea \u7cfb\u7edf\u7f16\u6392',
  },
  {
    title: '\u8c03\u7528\u5de5\u5177\uff1asearch_brand_list',
    detail: '\u5173\u952e\u8bcd\uff1a\u6bcd\u5a74\u3001\u6559\u80b2\u3001\u5065\u5eb7 \u00b7 \u4e09\u80ce',
    active: true,
  },
  {
    title: '\u6293\u53d6\u8fd1 30 \u5929\u6570\u636e',
    detail: '\u5df2\u8986\u76d6 47 \u4e2a\u54c1\u724c\u7684\u7535\u5546 + \u793e\u5a92\u6307\u6807',
  },
];

export function AgentPanel() {
  return (
    <section className="relative flex h-screen flex-col overflow-hidden border-l border-wechat-line bg-white">
      <header className="flex h-10 flex-shrink-0 items-center border-b border-wechat-line px-4">
        <h2 className="text-[14px] font-semibold leading-5 tracking-normal text-[#111827]">
          {TITLE}
        </h2>
      </header>

      <div className="flex h-[78px] flex-shrink-0 items-center gap-4 border-b border-wechat-line px-4">
        {HERO_ROLES.map((role, index) => (
          <AgentAvatar key={role} role={role} featured={index === 0} />
        ))}
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-5">
        <div className="mb-5 text-[12px] font-normal leading-5 text-[#6B7280]">
          {FLOW_TITLE}
        </div>

        <ol className="relative">
          {STEPS.map((step, index) => (
            <TimelineStep
              key={step.title}
              title={step.title}
              detail={step.detail}
              active={step.active}
              isLast={index === STEPS.length - 1}
            />
          ))}
          <li className="relative flex min-h-[34px] items-start gap-4">
            <div className="relative flex w-[26px] flex-shrink-0 justify-center">
              <span className="mt-1 h-4 w-4 rounded-full border-[4px] border-[#d9ecff] bg-[#57aaf7]" />
            </div>
            <span className="rounded-full bg-[#00000008] px-2.5 py-1 text-[11px] leading-4 text-[#9CA3AF]">
              {'\u601d\u8003\u4e2d...'}
            </span>
          </li>
        </ol>
      </div>
    </section>
  );
}

function AgentAvatar({ role, featured }: { role: RoleKey; featured?: boolean }) {
  const meta = ROLES[role];
  const avatarStyle = ROLE_AVATAR[role];

  return (
    <span
      className={clsx(
        'flex flex-shrink-0 items-center justify-center rounded-[14px] bg-cover bg-center text-white shadow-sm',
        featured ? 'h-12 w-12 bg-[#00000008]' : 'h-8 w-8 rounded-full',
      )}
      style={avatarStyle ?? { background: meta.color }}
      aria-label={meta.name}
      title={meta.name}
    >
      {!avatarStyle && meta.initial}
    </span>
  );
}

function TimelineStep({
  title,
  detail,
  active,
  isLast,
}: {
  title: string;
  detail: string;
  active?: boolean;
  isLast: boolean;
}) {
  return (
    <li className="relative flex items-start gap-3 pb-5">
      <div className="relative flex w-[18px] flex-shrink-0 justify-center">
        <span className="relative z-10 mt-1 h-3.5 w-3.5 rounded-full border-[4px] border-[#e8e9eb] bg-[#cfd2d8]" />
        {!isLast && (
          <span className="absolute left-1/2 top-5 h-[calc(100%-4px)] w-px -translate-x-1/2 bg-[#E5E7EB]" />
        )}
      </div>

      <div
        className={clsx(
          '-mt-1 min-w-0 flex-1',
          active && 'rounded-[8px] bg-[#00000008] px-3 py-2',
        )}
      >
        <div className="text-[13px] font-semibold leading-5 tracking-normal text-[#111827]">
          {title}
        </div>
        <div className="mt-0.5 text-[12px] font-normal leading-5 text-[#8B8F99]">
          {detail}
        </div>
      </div>
    </li>
  );
}
