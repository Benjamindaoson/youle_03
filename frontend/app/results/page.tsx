'use client';

// 成果库二级页(v4 §34 §300-311)
import { useState } from 'react';
import { Download, ExternalLink, FileText, Image as ImageIcon, Music, Video } from 'lucide-react';
import clsx from 'clsx';
import { AppShell } from '@/components/layout/AppShell';
import { useArtifacts, type ArtifactRow } from '@/lib/api';

type TypeKey = 'all' | 'text' | 'image' | 'video' | 'document' | 'audio';

const TYPE_LABEL: Record<TypeKey, { label: string; icon: typeof FileText }> = {
  all: { label: '全部', icon: FileText },
  text: { label: '文字', icon: FileText },
  image: { label: '图', icon: ImageIcon },
  video: { label: '视频', icon: Video },
  document: { label: '文档', icon: FileText },
  audio: { label: '音频', icon: Music },
};

export default function ResultsPage() {
  const [typeFilter, setTypeFilter] = useState<TypeKey>('all');
  const [onlyFinal, setOnlyFinal] = useState(true);
  const { data: items = [] } = useArtifacts({
    type: typeFilter === 'all' ? undefined : typeFilter,
    only_final: onlyFinal,
  });

  return (
    <AppShell>
      <div className="flex h-full flex-col bg-white">
        <header className="flex h-14 flex-shrink-0 items-center justify-between border-b border-wechat-line px-5">
          <div>
            <h1 className="text-[15px] font-semibold text-wechat-fg">成果库</h1>
            <p className="text-[11px] text-wechat-mute">所有群产出统一归档,跨群访问</p>
          </div>
          <label className="flex items-center gap-1 text-[12px] text-wechat-sub">
            <input
              type="checkbox"
              checked={onlyFinal}
              onChange={(e) => setOnlyFinal(e.target.checked)}
              className="h-3 w-3"
            />
            只看最终交付
          </label>
        </header>

        <div className="flex flex-1 overflow-hidden">
          <aside className="w-44 flex-shrink-0 border-r border-wechat-line bg-neutral-50 p-2">
            <div className="px-2 pb-1 pt-1 text-[10px] font-medium text-wechat-mute">类型</div>
            {(Object.keys(TYPE_LABEL) as TypeKey[]).map((k) => {
              const Icon = TYPE_LABEL[k].icon;
              return (
                <button
                  key={k}
                  type="button"
                  onClick={() => setTypeFilter(k)}
                  className={clsx(
                    'flex w-full items-center gap-2 rounded-sm px-2 py-1 text-left text-[12px] transition-colors',
                    typeFilter === k
                      ? 'bg-wechat-green-soft text-wechat-fg'
                      : 'text-wechat-sub hover:bg-neutral-100',
                  )}
                >
                  <Icon size={13} />
                  {TYPE_LABEL[k].label}
                </button>
              );
            })}
          </aside>

          <main className="flex-1 overflow-y-auto p-5">
            {items.length === 0 ? (
              <div className="grid h-full place-items-center text-[13px] text-wechat-mute">
                暂无成果
              </div>
            ) : (
              <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {items.map((a) => (
                  <ArtifactCard key={a.id} item={a} />
                ))}
              </ul>
            )}
          </main>
        </div>
      </div>
    </AppShell>
  );
}

function ArtifactCard({ item }: { item: ArtifactRow }) {
  const Icon =
    item.type === 'image'
      ? ImageIcon
      : item.type === 'video'
        ? Video
        : item.type === 'audio'
          ? Music
          : FileText;
  const date = new Date(item.created_at).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
  return (
    <li className="rounded-md border border-wechat-line bg-white p-3 transition-colors hover:border-wechat-green">
      <div className="mb-2 flex items-center gap-2">
        <Icon size={16} className="text-wechat-sub" />
        <span className="flex-1 truncate text-[13px] font-medium text-wechat-fg">
          {item.title || `${item.type}-${item.id.slice(0, 6)}`}
        </span>
        {item.is_final && (
          <span className="rounded-sm bg-wechat-green-soft px-1.5 py-0.5 text-[10px] text-wechat-green">
            最终
          </span>
        )}
      </div>
      <div className="mb-2 truncate text-[10px] text-wechat-mute">{item.reference}</div>
      <div className="flex items-center justify-between text-[11px] text-wechat-mute">
        <span>{date}</span>
        <div className="flex gap-1">
          <a
            href={item.reference}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 rounded-sm border border-wechat-line bg-white px-2 py-0.5 text-wechat-fg hover:bg-neutral-50"
          >
            <Download size={11} /> 下载
          </a>
          {item.source_conversation_id && (
            <a
              href={`/chat/${item.source_conversation_id}`}
              className="flex items-center gap-1 rounded-sm border border-wechat-line bg-white px-2 py-0.5 text-wechat-fg hover:bg-neutral-50"
            >
              <ExternalLink size={11} /> 来源群
            </a>
          )}
        </div>
      </div>
    </li>
  );
}
