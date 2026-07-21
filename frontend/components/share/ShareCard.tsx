'use client';

// 卡片式分享(v4 §35 #312-318):群名片 / 成果 / Agent 名片
// V1 不做 [做同款] [加入此团队](v4 §319-320 V2 推迟)
import { Copy, Download, Share2, Users } from 'lucide-react';
import { ROLES, type RoleKey } from '@/lib/agents';

type Common = {
  open: boolean;
  onClose: () => void;
};

type GroupCardProps = Common & {
  kind: 'group';
  name: string;
  description?: string;
  agents: RoleKey[];
  skill?: string;
  artifactCount?: number;
};

type ArtifactCardProps = Common & {
  kind: 'artifact';
  title: string;
  type: string;
  reference: string;
  thumbnail?: string;
  origin?: { conversation_name?: string; agents?: RoleKey[]; skill?: string };
};

type AgentCardProps = Common & {
  kind: 'agent';
  role: RoleKey;
  personalCount?: number;
  platformCount?: number;
};

type Props = GroupCardProps | ArtifactCardProps | AgentCardProps;

export function ShareCard(props: Props) {
  if (!props.open) return null;
  return (
    <>
      <span className="fixed inset-0 z-50 bg-black/40" onClick={props.onClose} />
      <div className="fixed left-1/2 top-1/2 z-50 w-[360px] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-md border border-wechat-line bg-white shadow-xl">
        {props.kind === 'group' && <GroupBody {...props} />}
        {props.kind === 'artifact' && <ArtifactBody {...props} />}
        {props.kind === 'agent' && <AgentBody {...props} />}
      </div>
    </>
  );
}

// ── 群名片 ──
function GroupBody(p: GroupCardProps) {
  const text =
    `「${p.name}」\n` +
    (p.description ? `${p.description}\n` : '') +
    `团队:${p.agents.map((r) => ROLES[r].name).join(' / ')}\n` +
    (p.skill ? `Skill:${p.skill}\n` : '') +
    `战绩:${p.artifactCount ?? 0} 件成果\n— 来自「有了」AI 工作团队`;
  return (
    <>
      <div className="bg-gradient-to-br from-wechat-green-soft to-white p-4">
        <div className="mb-2 flex items-center gap-2">
          <Users size={14} className="text-wechat-green" />
          <span className="text-[10px] uppercase tracking-wider text-wechat-green">
            Team Card
          </span>
        </div>
        <div className="mb-1 text-[15px] font-semibold text-wechat-fg">{p.name}</div>
        {p.description && (
          <div className="mb-3 line-clamp-2 text-[12px] text-wechat-sub">
            {p.description}
          </div>
        )}
        <div className="mb-2 flex flex-wrap gap-1">
          {p.agents.map((r) => (
            <span
              key={r}
              className="grid h-7 w-7 place-items-center rounded text-[10px] font-bold text-white"
              style={{ background: ROLES[r].color }}
              title={ROLES[r].name}
            >
              {ROLES[r].initial}
            </span>
          ))}
        </div>
        <div className="text-[11px] text-wechat-mute">
          {p.skill ? `Skill:${p.skill} · ` : ''}已产出 {p.artifactCount ?? 0} 件
        </div>
      </div>
      <Footer text={text} onClose={p.onClose} secondaryLabel="查看成果" />
    </>
  );
}

// ── 成果分享 ──
function ArtifactBody(p: ArtifactCardProps) {
  const text =
    `「${p.title}」\n` +
    `${p.type} · 来源:${p.origin?.conversation_name ?? '工作群'}\n` +
    (p.origin?.skill ? `Skill:${p.origin.skill}\n` : '') +
    `— 来自「有了」AI 工作团队`;
  return (
    <>
      <div className="border-b border-wechat-line p-4">
        <div className="mb-1 text-[10px] uppercase tracking-wider text-wechat-green">
          Artifact
        </div>
        <div className="mb-2 text-[15px] font-semibold text-wechat-fg">{p.title}</div>
        {p.thumbnail && (
          <img
            src={p.thumbnail}
            alt={p.title}
            className="mb-2 h-32 w-full rounded-sm object-cover"
          />
        )}
        <div className="mb-1 text-[11px] text-wechat-sub">
          {p.type} · {p.reference}
        </div>
        {p.origin && (
          <div className="text-[11px] text-wechat-mute">
            来源:{p.origin.conversation_name ?? '工作群'}
            {p.origin.skill ? ` · ${p.origin.skill}` : ''}
            {p.origin.agents?.length
              ? ` · ${p.origin.agents.map((r) => ROLES[r].name).join('/')}`
              : ''}
          </div>
        )}
      </div>
      <div className="flex divide-x divide-wechat-line">
        <a
          href={p.reference}
          target="_blank"
          rel="noreferrer"
          className="flex flex-1 items-center justify-center gap-1 py-2 text-[12px] text-wechat-fg hover:bg-neutral-50"
        >
          <Download size={12} /> 下载
        </a>
        <button
          type="button"
          onClick={() => navigator.clipboard.writeText(text)}
          className="flex flex-1 items-center justify-center gap-1 py-2 text-[12px] text-wechat-fg hover:bg-neutral-50"
        >
          <Copy size={12} /> 复制文本
        </button>
        <button
          type="button"
          onClick={p.onClose}
          className="flex-1 py-2 text-[12px] text-wechat-mute hover:bg-neutral-50"
        >
          关闭
        </button>
      </div>
    </>
  );
}

// ── Agent 名片 ──
function AgentBody(p: AgentCardProps) {
  const meta = ROLES[p.role];
  const text =
    `${meta.name}\n` +
    (meta.description ? `${meta.description}\n` : '') +
    `已为 TA 完成 ${p.personalCount ?? 0} 次 · 平台累计 ${(p.platformCount ?? 0).toLocaleString('zh-CN')} 次\n` +
    `— 来自「有了」AI 工作团队`;
  return (
    <>
      <div className="border-b border-wechat-line p-4">
        <div className="mb-2 flex items-center gap-3">
          <span
            className="grid h-12 w-12 flex-shrink-0 place-items-center rounded text-[16px] font-bold text-white"
            style={{ background: meta.color }}
          >
            {meta.initial}
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[14px] font-semibold text-wechat-fg">{meta.name}</div>
            <div className="text-[11px] text-wechat-sub">{meta.description}</div>
          </div>
        </div>
        <div className="text-[11px] text-wechat-mute">
          已完成 {p.personalCount ?? 0} 次 · 平台累计 {(p.platformCount ?? 0).toLocaleString('zh-CN')} 次
        </div>
      </div>
      <Footer text={text} onClose={p.onClose} secondaryLabel="查看创作者" />
    </>
  );
}

// ── 通用底部按钮组 ──
function Footer({
  text,
  onClose,
  secondaryLabel,
}: {
  text: string;
  onClose: () => void;
  secondaryLabel?: string;
}) {
  function share() {
    if (navigator.share) void navigator.share({ text });
    else {
      void navigator.clipboard.writeText(text);
      alert('已复制名片文本');
    }
  }
  return (
    <div className="flex divide-x divide-wechat-line">
      <button
        type="button"
        onClick={share}
        className="flex flex-1 items-center justify-center gap-1 py-2 text-[12px] text-wechat-fg hover:bg-neutral-50"
      >
        <Share2 size={12} /> 分享
      </button>
      {secondaryLabel && (
        <button
          type="button"
          onClick={onClose}
          className="flex-1 py-2 text-[12px] text-wechat-fg hover:bg-neutral-50"
        >
          {secondaryLabel}
        </button>
      )}
      <button
        type="button"
        onClick={onClose}
        className="flex-1 py-2 text-[12px] text-wechat-mute hover:bg-neutral-50"
      >
        关闭
      </button>
    </div>
  );
}
