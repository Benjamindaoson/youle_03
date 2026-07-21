'use client';

// 技能市场二级页(v4 §33)
// V1 浏览 / 订阅;V2 创作者计划 / 分润 / 后台
import Link from 'next/link';
import { useState } from 'react';
import { Search, Star, Store } from 'lucide-react';
import clsx from 'clsx';
import {
  useDisableSkill,
  useEnableSkill,
  useInstallSkill,
  useSkills,
  type SkillCard,
} from '@/lib/api';

const DOMAINS: { key: string | null; label: string }[] = [
  { key: null, label: '全部' },
  { key: 'video', label: '视频' },
  { key: 'image', label: '图像' },
  { key: 'text', label: '文字' },
  { key: 'document', label: '文档' },
];

export default function MarketPage() {
  const [domain, setDomain] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const { data: skills = [] } = useSkills({ q: q || undefined, domain: domain || undefined });
  const install = useInstallSkill();
  const enable = useEnableSkill();
  const disable = useDisableSkill();

  function changeLifecycle(skill: SkillCard) {
    if (!skill.installed) install.mutate(skill.id);
    else if (skill.enabled) disable.mutate(skill.id);
    else enable.mutate(skill.id);
  }

  return (
    <div className="flex h-full flex-col bg-white">
        <header className="flex h-14 flex-shrink-0 items-center justify-between border-b border-wechat-line px-5">
          <div>
            <h1 className="flex items-center gap-2 text-[15px] font-semibold text-wechat-fg">
              <Store size={16} /> 技能市场
            </h1>
            <p className="text-[11px] text-wechat-mute">
              搜索、安装并启用平台 Skill
            </p>
          </div>
          <div className="flex items-center gap-1.5 rounded-sm border border-wechat-line bg-white px-2 py-1">
            <Search size={12} className="text-wechat-mute" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="搜索"
              className="w-44 bg-transparent text-[12px] outline-none"
            />
          </div>
        </header>

        <div className="flex flex-shrink-0 items-center gap-1 border-b border-wechat-line bg-neutral-50 px-5 py-2">
          {DOMAINS.map((d) => (
            <button
              key={d.label}
              type="button"
              onClick={() => setDomain(d.key)}
              className={clsx(
                'rounded-sm px-2.5 py-1 text-[11px] transition-colors',
                domain === d.key
                  ? 'bg-wechat-green text-white'
                  : 'text-wechat-sub hover:bg-neutral-200',
              )}
            >
              {d.label}
            </button>
          ))}
        </div>

        <main className="flex-1 overflow-y-auto p-5">
          {skills.length === 0 ? (
            <div className="grid h-full place-items-center text-[13px] text-wechat-mute">
              没有匹配的 Skill
            </div>
          ) : (
            <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {skills.map((s) => (
                <MarketCard
                  key={s.id}
                  skill={s}
                  onToggle={() => changeLifecycle(s)}
                />
              ))}
            </ul>
          )}
        </main>
    </div>
  );
}

function MarketCard({
  skill,
  onToggle,
}: {
  skill: SkillCard;
  onToggle: () => void;
}) {
  return (
    <li className="rounded-md border border-wechat-line bg-white p-3 hover:border-wechat-green">
      <div className="mb-1 flex items-center justify-between">
        <Link
          href={`/market/${skill.id}`}
          className="text-[13px] font-semibold text-wechat-fg hover:text-wechat-green"
        >
          {skill.name}
        </Link>
        {skill.built_in && (
          <span className="flex items-center gap-1 rounded-sm bg-wechat-green-soft px-1.5 py-0.5 text-[10px] text-wechat-green">
            <Star size={9} /> 内置
          </span>
        )}
      </div>
      <p className="mb-3 line-clamp-2 text-[11px] text-wechat-sub">
        {skill.description || '无描述'}
      </p>
      <div className="mb-2 flex flex-wrap items-center gap-1 text-[10px] text-wechat-mute">
        {(skill.keywords ?? []).slice(0, 3).map((k) => (
          <span key={k} className="rounded-sm bg-neutral-100 px-1.5 py-0.5">
            {k}
          </span>
        ))}
      </div>
      <Link
        href={`/market/${skill.id}`}
        className="mb-2 block text-[11px] text-wechat-green hover:underline"
      >
        查看工作流与权限
      </Link>
      <button
        type="button"
        onClick={onToggle}
        className={clsx(
          'w-full rounded-sm border py-1 text-[12px] transition-colors',
          skill.installed
            ? 'border-wechat-line bg-white text-wechat-fg hover:bg-neutral-50'
            : 'border-wechat-green bg-wechat-green text-white hover:bg-[#06AE56]',
        )}
      >
        {!skill.installed ? '安装并启用' : skill.enabled ? '已启用 · 停用' : '重新启用'}
      </button>
    </li>
  );
}
