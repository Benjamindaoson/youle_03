'use client';

// AI 学院二级页(v4 §32)
// 学习中心:浏览所有 Skill;管理已订阅 / 平台预置 / 自己创建
// V1 不含 Skill 创作 / Agent 进修 (V2)
import { useState } from 'react';
import { CheckCircle, GraduationCap, Layers, Lock } from 'lucide-react';
import clsx from 'clsx';
import { AppShell } from '@/components/layout/AppShell';
import { useMySkills, useSkills, type SkillCard } from '@/lib/api';

type Tab = 'browse' | 'mine';

export default function AcademyPage() {
  const [tab, setTab] = useState<Tab>('browse');
  const { data: all = [] } = useSkills();
  const { data: mine = [] } = useMySkills();
  const items = tab === 'browse' ? all : mine;

  return (
    <AppShell>
      <div className="flex h-full flex-col bg-white">
        <header className="flex h-14 flex-shrink-0 items-center justify-between border-b border-wechat-line px-5">
          <div>
            <h1 className="flex items-center gap-2 text-[15px] font-semibold text-wechat-fg">
              <GraduationCap size={16} /> AI 学院
            </h1>
            <p className="text-[11px] text-wechat-mute">
              浏览 Skill,挑选订阅(Skill 创作 / Agent 进修 V2 上线)
            </p>
          </div>
          <div className="flex rounded-md border border-wechat-line bg-white p-0.5 text-[12px]">
            {(['browse', 'mine'] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTab(t)}
                className={clsx(
                  'rounded-sm px-3 py-1 transition-colors',
                  tab === t
                    ? 'bg-wechat-green-soft text-wechat-green'
                    : 'text-wechat-mute hover:bg-neutral-50',
                )}
              >
                {t === 'browse' ? '学习中心' : '我的 Skill'}
              </button>
            ))}
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-5">
          {items.length === 0 ? (
            <div className="grid h-full place-items-center text-[13px] text-wechat-mute">
              {tab === 'browse' ? '暂无可用 Skill' : '尚未订阅任何 Skill'}
            </div>
          ) : (
            <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {items.map((s) => (
                <SkillCardView key={s.id} skill={s} />
              ))}
            </ul>
          )}

          <section className="mt-8 rounded-md border border-dashed border-wechat-line bg-neutral-50 p-4">
            <h2 className="mb-1 flex items-center gap-1.5 text-[13px] font-medium text-wechat-fg">
              <Lock size={12} /> Skill 创作 · Agent 进修(V2)
            </h2>
            <p className="text-[11px] text-wechat-mute">
              V2 开放给创作者:用户可让总裁助理从最近工作流中自动总结 Skill 草稿;通过 HR 给 Agent 喂语料让其专精领域。
            </p>
          </section>
        </main>
      </div>
    </AppShell>
  );
}

function SkillCardView({ skill }: { skill: SkillCard }) {
  return (
    <li className="rounded-md border border-wechat-line bg-white p-3 hover:border-wechat-green">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[13px] font-semibold text-wechat-fg">{skill.name}</span>
        {skill.subscribed && (
          <span className="flex items-center gap-1 text-[10px] text-wechat-green">
            <CheckCircle size={10} /> 已订阅
          </span>
        )}
      </div>
      <p className="mb-2 line-clamp-2 text-[11px] text-wechat-sub">
        {skill.description || '无描述'}
      </p>
      <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-wechat-mute">
        <span className="flex items-center gap-0.5">
          <Layers size={10} /> v{skill.version}
        </span>
        {skill.domain && (
          <span className="rounded-sm bg-neutral-100 px-1.5 py-0.5">{skill.domain}</span>
        )}
        {(skill.keywords ?? []).slice(0, 3).map((k) => (
          <span key={k} className="rounded-sm bg-wechat-green-soft px-1.5 py-0.5 text-wechat-green">
            {k}
          </span>
        ))}
      </div>
    </li>
  );
}
