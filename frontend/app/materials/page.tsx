'use client';

// 素材库二级页(v4 §31 §274-280)
// 支持类型筛选 / 文件夹分组 / 拖拽上传(占位)/ URL 抓取 / 删除
import { useState } from 'react';
import { File, FolderOpen, Image, Music, Trash2, Upload, Video } from 'lucide-react';
import clsx from 'clsx';
import { AppShell } from '@/components/layout/AppShell';
import {
  useMaterials,
  useCreateMaterial,
  useDeleteMaterial,
  type MaterialItem,
} from '@/lib/api';

type Filter = 'all' | 'image' | 'video' | 'audio' | 'document';

const FILTER_LABEL: Record<Filter, { label: string; icon: typeof File; mime?: string }> = {
  all: { label: '全部', icon: File },
  image: { label: '图片', icon: Image, mime: 'image/' },
  video: { label: '视频', icon: Video, mime: 'video/' },
  audio: { label: '音频', icon: Music, mime: 'audio/' },
  document: { label: '文档', icon: File, mime: 'application/' },
};

export default function MaterialsPage() {
  const { data: items = [] } = useMaterials();
  const create = useCreateMaterial();
  const remove = useDeleteMaterial();
  const [filter, setFilter] = useState<Filter>('all');
  const [folder, setFolder] = useState<string | null>(null);
  const [showAddUrl, setShowAddUrl] = useState(false);
  const [urlInput, setUrlInput] = useState('');

  const folders = Array.from(
    new Set(items.map((i) => i.folder).filter(Boolean) as string[]),
  );

  const filtered = items.filter((it) => {
    if (folder && it.folder !== folder) return false;
    if (filter === 'all') return true;
    const prefix = FILTER_LABEL[filter].mime;
    return prefix ? it.mime?.startsWith(prefix) : true;
  });

  function handleUploadClick() {
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.onchange = (e) => {
      const files = (e.target as HTMLInputElement).files;
      if (!files) return;
      Array.from(files).forEach((f) => {
        create.mutate({
          name: f.name,
          mime: f.type,
          folder: folder ?? undefined,
        });
      });
    };
    input.click();
  }

  function handleAddUrl() {
    if (!urlInput.trim()) return;
    const name = urlInput.split('/').pop() || urlInput;
    create.mutate({ name, url: urlInput, folder: folder ?? undefined });
    setUrlInput('');
    setShowAddUrl(false);
  }

  return (
    <AppShell>
      <div className="flex h-full flex-col bg-white">
        <header className="flex h-14 flex-shrink-0 items-center justify-between border-b border-wechat-line px-5">
          <div>
            <h1 className="text-[15px] font-semibold text-wechat-fg">素材库</h1>
            <p className="text-[11px] text-wechat-mute">在群里通过 @文件名 调用</p>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={handleUploadClick}
              className="flex items-center gap-1 rounded-sm border border-wechat-line bg-white px-3 py-1 text-[12px] text-wechat-fg hover:bg-neutral-50"
            >
              <Upload size={12} /> 上传
            </button>
            <button
              type="button"
              onClick={() => setShowAddUrl((v) => !v)}
              className="rounded-sm border border-wechat-line bg-white px-3 py-1 text-[12px] text-wechat-fg hover:bg-neutral-50"
            >
              链接抓取
            </button>
          </div>
        </header>

        {showAddUrl && (
          <div className="flex items-center gap-2 border-b border-wechat-line bg-neutral-50 px-5 py-2">
            <input
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              placeholder="https://..."
              className="flex-1 rounded-sm border border-wechat-line bg-white px-2 py-1 text-[12px] outline-none focus:border-wechat-green"
            />
            <button
              type="button"
              onClick={handleAddUrl}
              className="rounded-sm bg-wechat-green px-3 py-1 text-[12px] text-white"
            >
              抓取
            </button>
          </div>
        )}

        <div className="flex flex-1 overflow-hidden">
          <aside className="flex w-44 flex-shrink-0 flex-col gap-1 border-r border-wechat-line bg-neutral-50 p-2">
            <div className="px-2 pb-1 pt-1 text-[10px] font-medium text-wechat-mute">类型</div>
            {(Object.keys(FILTER_LABEL) as Filter[]).map((k) => {
              const Icon = FILTER_LABEL[k].icon;
              return (
                <button
                  key={k}
                  type="button"
                  onClick={() => setFilter(k)}
                  className={clsx(
                    'flex items-center gap-2 rounded-sm px-2 py-1 text-left text-[12px] transition-colors',
                    filter === k
                      ? 'bg-wechat-green-soft text-wechat-fg'
                      : 'text-wechat-sub hover:bg-neutral-100',
                  )}
                >
                  <Icon size={13} />
                  {FILTER_LABEL[k].label}
                </button>
              );
            })}
            {folders.length > 0 && (
              <>
                <div className="mt-3 px-2 pb-1 text-[10px] font-medium text-wechat-mute">
                  文件夹
                </div>
                <button
                  type="button"
                  onClick={() => setFolder(null)}
                  className={clsx(
                    'flex items-center gap-2 rounded-sm px-2 py-1 text-left text-[12px]',
                    !folder
                      ? 'bg-wechat-green-soft text-wechat-fg'
                      : 'text-wechat-sub hover:bg-neutral-100',
                  )}
                >
                  全部文件夹
                </button>
                {folders.map((f) => (
                  <button
                    key={f}
                    type="button"
                    onClick={() => setFolder(f)}
                    className={clsx(
                      'flex items-center gap-2 rounded-sm px-2 py-1 text-left text-[12px]',
                      folder === f
                        ? 'bg-wechat-green-soft text-wechat-fg'
                        : 'text-wechat-sub hover:bg-neutral-100',
                    )}
                  >
                    <FolderOpen size={13} />
                    {f}
                  </button>
                ))}
              </>
            )}
          </aside>

          <main
            className="flex-1 overflow-y-auto p-5"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              Array.from(e.dataTransfer.files).forEach((f) =>
                create.mutate({
                  name: f.name,
                  mime: f.type,
                  folder: folder ?? undefined,
                }),
              );
            }}
          >
            {filtered.length === 0 ? (
              <div className="grid h-full place-items-center text-[13px] text-wechat-mute">
                <div className="text-center">
                  <Upload size={32} className="mx-auto text-wechat-mute" />
                  <p className="mt-2">拖拽文件到此处,或点击右上角上传</p>
                </div>
              </div>
            ) : (
              <ul className="grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-3">
                {filtered.map((it) => (
                  <MaterialCard
                    key={it.id}
                    item={it}
                    onDelete={() => remove.mutate(it.id)}
                  />
                ))}
              </ul>
            )}
          </main>
        </div>
      </div>
    </AppShell>
  );
}

function MaterialCard({
  item,
  onDelete,
}: {
  item: MaterialItem;
  onDelete: () => void;
}) {
  const Icon = item.mime?.startsWith('image/')
    ? Image
    : item.mime?.startsWith('video/')
      ? Video
      : item.mime?.startsWith('audio/')
        ? Music
        : File;
  return (
    <li className="group flex items-center gap-3 rounded-md border border-wechat-line bg-white p-3 hover:border-wechat-green">
      <Icon size={28} className="flex-shrink-0 text-wechat-sub" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium text-wechat-fg">{item.name}</div>
        <div className="truncate text-[10px] text-wechat-mute">
          {item.mime || '未知类型'}{item.folder ? ` · ${item.folder}` : ''}
        </div>
      </div>
      <button
        type="button"
        onClick={onDelete}
        className="text-wechat-mute opacity-0 transition-opacity hover:text-red-500 group-hover:opacity-100"
        title="删除"
      >
        <Trash2 size={14} />
      </button>
    </li>
  );
}
