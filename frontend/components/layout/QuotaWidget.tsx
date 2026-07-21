'use client';

// 配额画像 + 80% 主动提醒(财务经理实时画像)
// 进入主会话时由顶部展示;非主会话隐藏
import { AlertTriangle } from 'lucide-react';
import clsx from 'clsx';
import { useMyQuota } from '@/lib/api';

const QUOTA_LABEL: Record<string, string> = {
  auto_tasks_daily: '今日任务',
  video_tasks_daily: '今日视频',
  groups_monthly: '本月新群',
};

export function QuotaWidget({ compact = false }: { compact?: boolean }) {
  const { data, isLoading } = useMyQuota();
  if (isLoading || !data) return null;

  const rows = [
    { key: 'auto_tasks_daily', row: data.auto_tasks_daily },
    { key: 'video_tasks_daily', row: data.video_tasks_daily },
    { key: 'groups_monthly', row: data.groups_monthly },
  ];
  const warnings = data.warnings ?? [];
  const hasWarning = warnings.length > 0;

  return (
    <div
      className={clsx(
        'flex flex-col gap-1 rounded-md border border-wechat-line bg-white',
        compact ? 'p-2' : 'p-3',
        hasWarning && 'border-amber-300 bg-amber-50',
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium text-wechat-sub">
          配额 · {data.plan === 'free' ? '免费版' : data.plan === 'personal' ? '个人版' : '团队版'}
        </span>
        {hasWarning && (
          <span className="flex items-center gap-1 text-[10px] text-amber-700">
            <AlertTriangle size={10} /> 财务经理提醒
          </span>
        )}
      </div>
      {rows.map(({ key, row }) => (
        <div key={key} className="flex items-center gap-2 text-[11px]">
          <span className="w-16 flex-shrink-0 text-wechat-mute">
            {QUOTA_LABEL[key]}
          </span>
          <div className="h-1 flex-1 overflow-hidden rounded bg-neutral-200">
            <span
              className={clsx(
                'block h-full transition-all',
                row.percent >= 80 ? 'bg-amber-500' : 'bg-wechat-green',
              )}
              style={{ width: `${Math.min(100, row.percent)}%` }}
            />
          </div>
          <span className="w-12 flex-shrink-0 text-right tabular-nums text-wechat-fg">
            {row.used}/{row.total}
          </span>
        </div>
      ))}
      {hasWarning && (
        <div className="mt-1 text-[11px] text-amber-800">
          @财务经理 提醒:你今日{warnings.includes('auto_tasks_daily') ? '任务' : '视频'}配额已超 80%,需要升级吗?
        </div>
      )}
    </div>
  );
}
