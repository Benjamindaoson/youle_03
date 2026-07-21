'use client';

// 个人主页(v4 §37 #327-331)
import { useState } from 'react';
import { Camera, Crown, ListTodo, Package } from 'lucide-react';
import { AppShell } from '@/components/layout/AppShell';
import { QuotaWidget } from '@/components/layout/QuotaWidget';
import {
  useMyQuota,
  usePatchProfile,
  useProfile,
  useProfileStats,
} from '@/lib/api';

const PLAN_LABEL: Record<string, string> = {
  free: '免费版',
  personal: '个人版',
  team: '团队版',
};

export default function ProfilePage() {
  const { data: profile } = useProfile();
  const { data: stats } = useProfileStats();
  const { data: quota } = useMyQuota();
  const patch = usePatchProfile();

  const [editingName, setEditingName] = useState(false);
  const [name, setName] = useState('');

  function saveName() {
    if (name.trim() && name !== profile?.nickname) {
      patch.mutate({ nickname: name.trim() });
    }
    setEditingName(false);
  }

  return (
    <AppShell>
      <div className="flex h-full flex-col overflow-y-auto bg-white">
        <header className="flex h-14 flex-shrink-0 items-center border-b border-wechat-line px-5">
          <h1 className="text-[15px] font-semibold text-wechat-fg">个人主页</h1>
        </header>

        <div className="mx-auto w-full max-w-2xl space-y-5 p-6">
          {/* 用户信息 */}
          <section className="flex items-center gap-4 rounded-md border border-wechat-line bg-white p-4">
            <button
              type="button"
              className="relative h-16 w-16 overflow-hidden rounded-full bg-wechat-green-soft"
              title="点击更换头像"
            >
              <span className="grid h-full w-full place-items-center text-[18px] font-semibold text-wechat-green">
                {profile?.nickname?.slice(0, 2) ?? '老板'}
              </span>
              <span className="absolute bottom-0 right-0 grid h-5 w-5 place-items-center rounded-full bg-white">
                <Camera size={11} className="text-wechat-fg" />
              </span>
            </button>
            <div className="flex-1">
              {editingName ? (
                <input
                  autoFocus
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onBlur={saveName}
                  onKeyDown={(e) => e.key === 'Enter' && saveName()}
                  className="w-full rounded-sm border border-wechat-line bg-white px-2 py-1 text-[14px] outline-none focus:border-wechat-green"
                />
              ) : (
                <div
                  className="cursor-text text-[15px] font-semibold text-wechat-fg"
                  onClick={() => {
                    setName(profile?.nickname ?? '');
                    setEditingName(true);
                  }}
                >
                  {profile?.nickname ?? '未命名'}
                </div>
              )}
              <div className="text-[12px] text-wechat-mute">
                {profile?.phone ?? '—'}
              </div>
              <div className="mt-1 flex items-center gap-1 text-[11px] text-wechat-sub">
                <Crown size={11} />
                {PLAN_LABEL[profile?.plan ?? 'free']}
              </div>
            </div>
          </section>

          {/* 配额 */}
          <section>
            <h2 className="mb-2 text-[12px] font-medium text-wechat-sub">配额(@财务经理)</h2>
            <QuotaWidget />
          </section>

          {/* 统计 */}
          <section className="grid grid-cols-2 gap-3">
            <StatCard
              icon={Package}
              label="产出成果"
              value={stats?.artifacts ?? 0}
              suffix="件"
            />
            <StatCard
              icon={ListTodo}
              label="用过 Skill"
              value={stats?.skills_used ?? 0}
              suffix="种"
            />
          </section>

          {/* 偏好画像(占位 — 真画像由飞轮 preference_embedder 沉淀)*/}
          <section className="rounded-md border border-wechat-line bg-white p-4">
            <h2 className="mb-2 text-[12px] font-medium text-wechat-sub">偏好画像</h2>
            <p className="text-[11px] text-wechat-mute">
              你连续 3 次同样选择系统会自动记为偏好,后续任务自动套用,不再重复问。
              对总裁助理说“以后做反诈视频默认用城市老人受众”也能直接录入。
            </p>
            <div className="mt-3 text-[11px] text-wechat-sub">
              {quota ? `当前已使用 ${quota.auto_tasks_daily.used} 次任务,沉淀中…` : ''}
            </div>
          </section>
        </div>
      </div>
    </AppShell>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  suffix,
}: {
  icon: typeof Package;
  label: string;
  value: number;
  suffix: string;
}) {
  return (
    <div className="rounded-md border border-wechat-line bg-white p-3">
      <div className="mb-1 flex items-center gap-1 text-[11px] text-wechat-mute">
        <Icon size={11} /> {label}
      </div>
      <div className="text-[20px] font-semibold tabular-nums text-wechat-fg">
        {value}
        <span className="ml-1 text-[11px] font-normal text-wechat-mute">{suffix}</span>
      </div>
    </div>
  );
}
