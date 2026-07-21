'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { AlertTriangle, ArrowLeft, CheckCircle, ShieldCheck } from 'lucide-react';

import {
  useDisableSkill,
  useEnableSkill,
  useInstallSkill,
  useSkillDetail,
} from '@/lib/api';

export default function SkillDetailPage() {
  const params = useParams<{ skillId: string }>();
  const skillId = params.skillId;
  const { data: skill, error, isLoading } = useSkillDetail(skillId);
  const install = useInstallSkill();
  const enable = useEnableSkill();
  const disable = useDisableSkill();

  if (isLoading) {
    return <div className="grid h-full place-items-center text-sm text-wechat-mute">正在加载 Skill…</div>;
  }
  if (error || !skill) {
    return (
      <div className="grid h-full place-items-center text-sm text-red-600">
        无法加载 Skill 详情，请稍后重试。
      </div>
    );
  }

  const pending = install.isPending || enable.isPending || disable.isPending;
  const action = !skill.installed ? '安装并启用' : skill.enabled ? '停用 Skill' : '重新启用';
  const changeLifecycle = () => {
    if (!skill.installed) install.mutate(skill.id);
    else if (skill.enabled) disable.mutate(skill.id);
    else enable.mutate(skill.id);
  };

  return (
    <main className="h-full overflow-y-auto bg-white p-6">
      <div className="mx-auto max-w-3xl">
        <Link href="/market" className="mb-5 inline-flex items-center gap-1 text-xs text-wechat-green">
          <ArrowLeft size={13} /> 返回技能市场
        </Link>

        <header className="mb-6 border-b border-wechat-line pb-5">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold text-wechat-fg">{skill.name}</h1>
            {skill.built_in && (
              <span className="rounded bg-wechat-green-soft px-2 py-0.5 text-[11px] text-wechat-green">
                平台内置
              </span>
            )}
            <span className="text-xs text-wechat-mute">v{skill.version}</span>
          </div>
          <p className="text-sm leading-6 text-wechat-sub">{skill.description || '暂无描述'}</p>
          <div className="mt-4 flex items-center gap-3">
            <button
              type="button"
              disabled={pending}
              onClick={changeLifecycle}
              className="rounded bg-wechat-green px-4 py-2 text-xs text-white disabled:opacity-50"
            >
              {pending ? '处理中…' : action}
            </button>
            <span className="flex items-center gap-1 text-xs text-wechat-sub">
              {skill.enabled ? <CheckCircle size={13} className="text-wechat-green" /> : <AlertTriangle size={13} />}
              {skill.lifecycle}
            </span>
          </div>
        </header>

        <section className="grid gap-4 md:grid-cols-2">
          <DetailList title="所需 Agent" items={skill.required_agents ?? []} empty="无需专用 Agent" />
          <DetailList title="所需 MCP 工具" items={skill.required_mcp_tools ?? []} empty="无需 MCP 工具" />
          <DetailList title="权限声明" items={skill.permissions ?? []} empty="未申请额外权限" />
          <div className="rounded-md border border-wechat-line p-4">
            <h2 className="mb-2 flex items-center gap-1.5 text-sm font-medium">
              <ShieldCheck size={14} /> 安全校验
            </h2>
            <p className="text-xs text-wechat-sub">
              {skill.validated ? '该版本已通过平台结构与引用校验。' : '该版本尚未通过平台校验，请勿启用。'}
            </p>
          </div>
        </section>

        <section className="mt-4 rounded-md border border-wechat-line p-4">
          <h2 className="mb-3 text-sm font-medium">工作流摘要</h2>
          {(skill.workflow_summary ?? []).length ? (
            <ol className="space-y-2 text-xs text-wechat-sub">
              {(skill.workflow_summary ?? []).map((step, index) => (
                <li key={index} className="rounded bg-neutral-50 p-2">
                  {index + 1}. {JSON.stringify(step)}
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-xs text-wechat-mute">暂无公开工作流摘要。</p>
          )}
        </section>
      </div>
    </main>
  );
}

function DetailList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="rounded-md border border-wechat-line p-4">
      <h2 className="mb-2 text-sm font-medium">{title}</h2>
      {items.length ? (
        <ul className="space-y-1 text-xs text-wechat-sub">
          {items.map((item) => <li key={item}>• {item}</li>)}
        </ul>
      ) : (
        <p className="text-xs text-wechat-mute">{empty}</p>
      )}
    </div>
  );
}
