'use client';

import { useState } from 'react';
import {
  Download,
  File,
  Folder,
  Grid2X2,
  Image as ImageIcon,
  Link as LinkIcon,
  MinusCircle,
  PlusCircle,
  Search,
  Star,
  X,
} from 'lucide-react';
import clsx from 'clsx';

const TITLE = '\u6210\u679c\u5e93';
const ALL_RESULTS = '\u5168\u90e8\u6210\u679c';
const SEARCH_PLACEHOLDER = '\u641c\u7d22';

type CategoryKey = 'all' | 'favorite' | 'media' | 'file' | 'link';
type FileKind = 'ppt' | 'word' | 'excel' | 'image' | 'dark';

const CATEGORIES: Array<{
  key: CategoryKey;
  label: string;
  icon: typeof Grid2X2;
}> = [
  { key: 'all', label: '\u5168\u90e8\u6210\u679c', icon: Grid2X2 },
  { key: 'favorite', label: '\u6211\u7684\u6536\u85cf', icon: Star },
  { key: 'media', label: '\u56fe\u7247\u4e0e\u89c6\u9891', icon: ImageIcon },
  { key: 'file', label: '\u6587\u4ef6', icon: File },
  { key: 'link', label: '\u94fe\u63a5', icon: LinkIcon },
];

const FILES: Array<{
  id: string;
  name: string;
  project: string;
  size?: string;
  time: string;
  kind: FileKind;
}> = [
  {
    id: '1',
    name: '\u5c0f\u7ea2\u4e66\u8fd0\u8425.pptx',
    project: '\u5c0f\u7ea2\u4e66\u8fd0\u8425\u77ed\u89c6\u9891\u53d1\u5e03',
    size: '3.10 MB',
    time: '4\u670830\u65e5 17:13',
    kind: 'ppt',
  },
  ...Array.from({ length: 11 }, (_, index) => ({
    id: `${index + 2}`,
    name:
      index === 0
        ? 'f72c5-16a9-4d08bb3f-4bf964e48b70.pptx'
        : 'edaf72c5-16a9-4d08bb3f-4bf964e48b70.pptx',
    project: '\u5c0f\u7ea2\u4e66\u8fd0\u8425\u77ed\u89c6\u9891\u53d1\u5e03',
    time: '14:04',
    kind: (['image', 'dark', 'word', 'excel', 'image', 'ppt'] as FileKind[])[index % 6],
  })),
];

export default function ResultsPage() {
  const [category, setCategory] = useState<CategoryKey>('all');
  const [selectedId, setSelectedId] = useState<string | null>(FILES[0]?.id ?? null);
  const selectedFile = FILES.find((file) => file.id === selectedId) ?? null;

  return (
    <div className="flex h-full w-full min-w-0 flex-1 bg-white">
      <aside className="w-[270px] flex-shrink-0 border-r border-wechat-line bg-white">
        <div className="flex h-[56px] items-center gap-3 px-5">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/avatar.jpg" alt="" className="h-8 w-8 rounded-full object-cover" />
          <div className="text-[15px] font-medium leading-5 text-[#111827]">{TITLE}</div>
        </div>

        <div className="px-2">
          <label className="mb-3 flex h-8 items-center gap-2 rounded-full bg-[#00000008] px-4 text-[#9CA3AF]">
            <Search size={15} />
            <input
              placeholder={SEARCH_PLACEHOLDER}
              className="min-w-0 flex-1 bg-transparent text-[12px] outline-none placeholder:text-[#9CA3AF]"
            />
          </label>

          <nav className="space-y-1">
            {CATEGORIES.map((item) => {
              const Icon = item.icon;
              const active = category === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setCategory(item.key)}
                  className={clsx(
                    'flex h-9 w-full items-center gap-3 rounded-[6px] px-4 text-left text-[13px] transition-colors',
                    active ? 'bg-[#E8F1FF] text-[#111827]' : 'text-[#111827] hover:bg-[#00000005]',
                  )}
                >
                  <Icon size={15} strokeWidth={1.8} />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 overflow-hidden bg-white">
        <section className="min-w-0 basis-[40%] overflow-hidden bg-white">
        <header className="flex h-[50px] items-center border-b border-wechat-line px-4">
          <h1 className="text-[13px] font-medium leading-5 text-[#111827]">{ALL_RESULTS}</h1>
        </header>

        <div className="h-full overflow-y-auto px-8 py-5">
          <div className="grid grid-cols-[1fr_80px_104px] px-4 pb-2 text-[12px] leading-5 text-[#6B7280]">
            <span>{'\u540d\u79f0'}</span>
            <span>{'\u5927\u5c0f'}</span>
            <span>{'\u65f6\u95f4'}</span>
          </div>

          <ul>
            {FILES.map((file) => (
              <li
                key={file.id}
              >
                <button
                  type="button"
                  onClick={() => setSelectedId(file.id)}
                  className={clsx(
                    'grid w-full grid-cols-[1fr_80px_104px] items-center rounded-[6px] px-4 py-3 text-left text-[12px] leading-5 transition-colors',
                    selectedId === file.id ? 'bg-[#EAF6FF]' : 'border-b border-[#F3F4F6] hover:bg-[#00000004]',
                  )}
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <FileThumb kind={file.kind} />
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-medium leading-5 text-[#111827]">
                        {file.name}
                      </div>
                      <div className="truncate text-[11px] leading-4 text-[#6B7280]">
                        {file.project}
                      </div>
                    </div>
                  </div>
                  <div className="text-[12px] text-[#6B7280]">{file.size ?? ''}</div>
                  <div className="text-[12px] text-[#6B7280]">{file.time}</div>
                </button>
              </li>
            ))}
          </ul>
        </div>
        </section>

        {selectedFile && (
          <PreviewPanel
            file={selectedFile}
            onClose={() => setSelectedId(null)}
          />
        )}
      </main>
    </div>
  );
}

function PreviewPanel({
  file,
  onClose,
}: {
  file: (typeof FILES)[number];
  onClose: () => void;
}) {
  return (
    <aside className="min-w-0 basis-[60%] border-l border-wechat-line bg-white">
      <header className="flex h-[50px] items-center justify-between border-b border-wechat-line px-4">
        <div className="truncate text-[12px] font-medium leading-5 text-[#111827]">
          {file.name.replace(/\.[^.]+$/, '')}
        </div>
        <div className="flex items-center gap-3 text-[#111827]">
          <button type="button" className="hover:text-[#2563EB]" aria-label="Zoom in">
            <PlusCircle size={16} strokeWidth={1.7} />
          </button>
          <button type="button" className="hover:text-[#2563EB]" aria-label="Zoom out">
            <MinusCircle size={16} strokeWidth={1.7} />
          </button>
          <button type="button" className="hover:text-[#2563EB]" aria-label="Download">
            <Download size={16} strokeWidth={1.7} />
          </button>
          <button type="button" onClick={onClose} className="hover:text-[#EF4444]" aria-label="Close">
            <X size={17} strokeWidth={1.8} />
          </button>
        </div>
      </header>

      <div className="h-[calc(100%-50px)] overflow-auto bg-white px-10 py-4">
        <div className="mx-auto flex aspect-[0.72] h-auto min-h-[720px] w-full max-w-[min(720px,calc(100vw-80px))] flex-col items-center justify-between bg-[#111108] px-12 py-12 text-center shadow-sm">
          <div className="mt-44 rounded-full border border-[#806f16] bg-[#2b270e] px-6 py-2 text-[11px] font-semibold tracking-[0.16em] text-[#D6B51F]">
            WEB4.0 白皮书
          </div>

          <div className="flex flex-1 flex-col items-center justify-center">
            <div className="text-[44px] font-bold leading-none text-[#FFD60A]">Folus.com</div>
            <div className="mt-8 text-[14px] text-white/35">AI驱动的去中心化交易生态</div>
            <div className="mt-12 text-[26px] font-semibold leading-9 text-white">
              让AI接管交易，让人类掌控未来
            </div>
            <div className="mt-8 text-[12px] leading-6 text-white/35">
              <div>第四次工业革命的双引擎</div>
              <div>AI重塑生产力 · Web3重构生产关系</div>
            </div>
          </div>

          <div className="mb-2 text-[10px] tracking-[0.42em] text-white/35">
            AGENT GOVERNANCE · STRATEGY MARKET · DAO
          </div>
        </div>
      </div>
    </aside>
  );
}

function FileThumb({ kind }: { kind: FileKind }) {
  if (kind === 'image') {
    return (
      <span className="h-7 w-7 flex-shrink-0 overflow-hidden rounded-[4px] bg-[#F3F4F6]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/team-avatar.png" alt="" className="h-full w-full object-cover" />
      </span>
    );
  }
  if (kind === 'dark') {
    return <span className="h-7 w-7 flex-shrink-0 rounded-[4px] bg-[#111827]" />;
  }

  const meta = {
    ppt: { text: 'P', bg: '#E9572B' },
    word: { text: 'W', bg: '#2563EB' },
    excel: { text: 'X', bg: '#16A34A' },
  }[kind];

  return (
    <span
      className="grid h-7 w-7 flex-shrink-0 place-items-center rounded-[4px] text-[13px] font-semibold text-white"
      style={{ background: meta.bg }}
    >
      {meta.text}
    </span>
  );
}
