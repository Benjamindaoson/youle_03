'use client';

import { useEffect, useRef, useState, type CSSProperties } from 'react';
import {
  Download,
  File as FileIcon,
  Grid2X2,
  Image as ImageIcon,
  Link as LinkIcon,
  MinusCircle,
  PlusCircle,
  Search,
  Star,
  Upload,
  X,
} from 'lucide-react';
import clsx from 'clsx';

const TITLE = '\u77e5\u8bc6\u5e93';
const ALL_KNOWLEDGE = '\u5168\u90e8\u77e5\u8bc6\u5e93';
const SEARCH_PLACEHOLDER = '\u641c\u7d22';
const UPLOAD_LABEL = '\u4e0a\u4f20\u77e5\u8bc6\u5e93';

type CategoryKey = 'all' | 'favorite' | 'media' | 'file' | 'link';
type FileKind = 'ppt' | 'word' | 'excel' | 'image' | 'pdf' | 'dark';
type KnowledgeFile = {
  id: string;
  name: string;
  project: string;
  time: string;
  kind: FileKind;
  size?: string;
  url?: string;
  mime?: string;
  file?: globalThis.File;
  local?: boolean;
};

const CATEGORIES: Array<{
  key: CategoryKey;
  label: string;
  icon: typeof Grid2X2;
}> = [
  { key: 'all', label: '\u5168\u90e8\u77e5\u8bc6\u5e93', icon: Grid2X2 },
  { key: 'favorite', label: '\u6211\u7684\u6536\u85cf', icon: Star },
  { key: 'media', label: '\u56fe\u7247\u4e0e\u89c6\u9891', icon: ImageIcon },
  { key: 'file', label: '\u6587\u4ef6', icon: FileIcon },
  { key: 'link', label: '\u94fe\u63a5', icon: LinkIcon },
];

const FILES: KnowledgeFile[] = [
  {
    id: '1',
    name: '\u5c0f\u7ea2\u4e66\u8fd0\u8425.pptx',
    project: '\u5c0f\u7ea2\u4e66\u8fd0\u8425\u77ed\u89c6\u9891\u53d1\u5e03',
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

export default function MaterialsPage() {
  const [category, setCategory] = useState<CategoryKey>('all');
  const [localFiles, setLocalFiles] = useState<KnowledgeFile[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(FILES[0]?.id ?? null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const allFiles = [...localFiles, ...FILES];
  const selectedFile = allFiles.find((file) => file.id === selectedId) ?? null;

  function handleUpload(files: FileList | null) {
    if (!files) return;
    const uploaded = Array.from(files).map((file) => ({
      id: `local-${crypto.randomUUID()}`,
      name: file.name,
      project: '本地上传预览',
      time: '刚刚',
      kind: getFileKind(file),
      size: formatFileSize(file.size),
      url: URL.createObjectURL(file),
      mime: file.type,
      file,
      local: true,
    }));

    setLocalFiles((current) => [...uploaded, ...current]);
    if (uploaded[0]) {
      setSelectedId(uploaded[0].id);
    }
  }

  return (
    <div className="flex h-full w-full min-w-0 flex-1 bg-white">
      <aside className="w-[270px] flex-shrink-0 border-r border-wechat-line bg-white">
        <div className="flex h-[44px] items-center justify-between px-5">
          <div className="flex items-center gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/avatar.jpg" alt="" className="h-8 w-8 rounded-full object-cover" />
            <div className="text-[15px] font-medium leading-5 text-[#111827]">{TITLE}</div>
          </div>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex h-5 w-5 items-center justify-center rounded-full text-[#111827] hover:bg-[#00000008]"
            aria-label={UPLOAD_LABEL}
            title={UPLOAD_LABEL}
          >
            <PlusCircle size={15} strokeWidth={1.8} />
          </button>
        </div>

        <div className="px-2">
          <label className="mb-2 flex h-8 items-center gap-2 rounded-full bg-[#00000008] px-4 text-[#9CA3AF]">
            <Search size={15} />
            <input
              placeholder={SEARCH_PLACEHOLDER}
              className="min-w-0 flex-1 bg-transparent text-[12px] outline-none placeholder:text-[#9CA3AF]"
            />
          </label>

          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(event) => {
              handleUpload(event.target.files);
              event.target.value = '';
            }}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="mb-2 flex h-9 w-full items-center gap-3 rounded-[6px] bg-[#00000005] px-4 text-left text-[13px] text-[#111827] transition-colors hover:bg-[#00000008]"
          >
            <Upload size={15} strokeWidth={1.8} />
            <span>{UPLOAD_LABEL}</span>
          </button>

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
            <h1 className="text-[13px] font-medium leading-5 text-[#111827]">{ALL_KNOWLEDGE}</h1>
          </header>

          <div className="h-[calc(100%-50px)] overflow-y-auto px-8 py-5">
            <ul>
              {allFiles.map((file) => (
                <li key={file.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(file.id)}
                    className={clsx(
                      'grid w-full grid-cols-[1fr_92px] items-center rounded-[6px] px-4 py-3 text-left text-[12px] leading-5 transition-colors',
                      selectedId === file.id
                        ? 'bg-[#EAF6FF]'
                        : 'border-b border-[#F3F4F6] hover:bg-[#00000004]',
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
                    <div className="text-right text-[12px] text-[#6B7280]">{file.time}</div>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {selectedFile && <PreviewPanel file={selectedFile} onClose={() => setSelectedId(null)} />}
      </main>
    </div>
  );
}

function PreviewPanel({
  file,
  onClose,
}: {
  file: KnowledgeFile;
  onClose: () => void;
}) {
  const [zoom, setZoom] = useState(100);

  useEffect(() => {
    setZoom(100);
  }, [file.id]);

  function downloadFile() {
    if (!file.url) return;
    const link = document.createElement('a');
    link.href = file.url;
    link.download = file.name;
    link.click();
  }

  return (
    <aside className="min-w-0 basis-[60%] border-l border-wechat-line bg-white">
      <header className="flex h-[50px] items-center justify-between border-b border-wechat-line px-4">
        <div className="truncate text-[12px] font-medium leading-5 text-[#111827]">
          {file.name.replace(/\.[^.]+$/, '')}
        </div>
        <div className="flex items-center gap-3 text-[#111827]">
          <button
            type="button"
            onClick={() => setZoom((value) => Math.min(value + 10, 160))}
            className="hover:text-[#2563EB]"
            aria-label="放大"
          >
            <PlusCircle size={16} strokeWidth={1.7} />
          </button>
          <button
            type="button"
            onClick={() => setZoom((value) => Math.max(value - 10, 70))}
            className="hover:text-[#2563EB]"
            aria-label="缩小"
          >
            <MinusCircle size={16} strokeWidth={1.7} />
          </button>
          <span className="w-9 text-center text-[11px] leading-5 text-[#6B7280]">{zoom}%</span>
          <button
            type="button"
            onClick={downloadFile}
            className="hover:text-[#2563EB]"
            aria-label="下载"
          >
            <Download size={16} strokeWidth={1.7} />
          </button>
          <button type="button" onClick={onClose} className="hover:text-[#EF4444]" aria-label="关闭">
            <X size={17} strokeWidth={1.8} />
          </button>
        </div>
      </header>

      <div className="h-[calc(100%-50px)] overflow-auto bg-white px-10 py-4">
        {file.url && file.mime?.startsWith('image/') ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={file.url}
            alt={file.name}
            className="mx-auto max-h-full max-w-full origin-top object-contain"
            style={{ transform: `scale(${zoom / 100})` }}
          />
        ) : file.url && file.mime === 'application/pdf' ? (
          <iframe src={file.url} title={file.name} className="h-full min-h-[720px] w-full border-0" />
        ) : file.local && file.file && isOfficeKind(file.kind) ? (
          <OfficePreview file={file.file} kind={file.kind} zoom={zoom} />
        ) : file.local ? (
          <div className="mx-auto flex h-[420px] max-w-[520px] flex-col items-center justify-center rounded-[8px] border border-[#0000000F] bg-[#00000003] text-center">
            <FileThumb kind={file.kind} />
            <div className="mt-4 max-w-[360px] truncate text-[15px] font-medium leading-6 text-[#111827]">
              {file.name}
            </div>
            <div className="mt-1 text-[12px] leading-5 text-[#6B7280]">
              {file.size ?? '未知大小'} · 当前文件类型暂不支持直接预览
            </div>
          </div>
        ) : (
          <DemoPreview />
        )}
      </div>
    </aside>
  );
}

function OfficePreview({ file, kind, zoom }: { file: globalThis.File; kind: FileKind; zoom: number }) {
  const [state, setState] = useState<
    | { status: 'loading' }
    | { status: 'error'; message: string }
    | { status: 'ready'; preview: OfficePreviewData }
  >({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;

    parseOfficeFile(file, kind)
      .then((preview) => {
        if (!cancelled) setState({ status: 'ready', preview });
      })
      .catch((error) => {
        if (!cancelled) {
          setState({
            status: 'error',
            message: error instanceof Error ? error.message : '预览失败',
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [file, kind]);

  if (state.status === 'loading') {
    return (
      <div className="mx-auto flex h-[520px] max-w-[680px] flex-col items-center justify-center rounded-[8px] border border-[#0000000F] bg-[#00000003] text-[13px] text-[#6B7280]">
        <div className="mb-3 h-7 w-7 animate-spin rounded-full border-2 border-[#D1D5DB] border-t-[#2563EB]" />
        正在生成预览...
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <div className="mx-auto flex h-[420px] max-w-[520px] flex-col items-center justify-center rounded-[8px] border border-[#0000000F] bg-[#00000003] text-center">
        <FileThumb kind={kind} />
        <div className="mt-4 text-[15px] font-medium leading-6 text-[#111827]">暂时无法预览</div>
        <div className="mt-1 max-w-[360px] text-[12px] leading-5 text-[#6B7280]">{state.message}</div>
      </div>
    );
  }

  const { preview } = state;
  const scaleStyle = {
    transform: `scale(${zoom / 100})`,
    transformOrigin: 'top center',
    width: `${10000 / zoom}%`,
  };

  if (preview.type === 'sheet') {
    return <SpreadsheetPreview preview={preview} scaleStyle={scaleStyle} />;
  }

  if (preview.type === 'slides') {
    return (
      <div className="mx-auto max-w-[780px] space-y-6" style={scaleStyle}>
        {preview.slides.map((slide, index) => (
          <section key={index} className="rounded-[8px] border border-[#0000000F] bg-white p-6 shadow-sm">
            <div className="mb-4 text-[12px] font-medium leading-5 text-[#6B7280]">第 {index + 1} 页</div>
            <div className="space-y-3 text-[16px] leading-7 text-[#111827]">
              {slide.map((block, blockIndex) =>
                block.type === 'image' ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    key={`${block.src}-${blockIndex}`}
                    src={block.src}
                    alt={block.alt}
                    className="max-h-[460px] max-w-full rounded-[4px] object-contain"
                  />
                ) : (
                  <p key={blockIndex}>{block.text}</p>
                ),
              )}
            </div>
          </section>
        ))}
      </div>
    );
  }

  return (
    <article className="mx-auto max-w-[760px] rounded-[8px] border border-[#0000000F] bg-white px-10 py-8 shadow-sm" style={scaleStyle}>
      <div className="space-y-4 text-[14px] leading-7 text-[#111827]">
        {preview.blocks.map((block, index) => {
          if (block.type === 'image') {
            return (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={`${block.src}-${index}`}
                src={block.src}
                alt={block.alt}
                className="max-h-[520px] max-w-full rounded-[4px] object-contain"
              />
            );
          }

          return (
            <p key={index} className="flex gap-2">
              {block.listLabel ? <span className="shrink-0">{block.listLabel}</span> : null}
              <span>{block.text}</span>
            </p>
          );
        })}
      </div>
    </article>
  );
}

function SpreadsheetPreview({
  preview,
  scaleStyle,
}: {
  preview: Extract<OfficePreviewData, { type: 'sheet' }>;
  scaleStyle: CSSProperties;
}) {
  const [activeSheet, setActiveSheet] = useState(preview.activeSheet);
  const sheet = preview.sheets[activeSheet] ?? preview.sheets[0];
  const rows = sheet?.rows ?? [];
  const columnCount = Math.max(10, ...rows.map((row) => row.length));
  const visibleRows = rows.length ? rows : [['']];

  useEffect(() => {
    setActiveSheet(preview.activeSheet);
  }, [preview]);

  return (
    <div className="mx-auto flex h-[calc(100vh-150px)] max-w-full flex-col overflow-hidden rounded-[8px] border border-[#D1D5DB] bg-white shadow-sm" style={scaleStyle}>
      <div className="min-h-0 flex-1 overflow-auto bg-white">
        <table className="border-collapse text-left text-[12px] leading-5 text-[#111827]">
          <thead>
            <tr>
              <th className="sticky left-0 top-0 z-30 h-6 w-10 min-w-10 border border-[#D7DDE5] bg-[#F3F4F6]" />
              {Array.from({ length: columnCount }, (_, index) => (
                <th
                  key={index}
                  className="sticky top-0 z-20 h-6 min-w-[116px] border border-[#D7DDE5] bg-[#F3F4F6] text-center text-[11px] font-normal text-[#374151]"
                >
                  {indexToExcelColumn(index)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                <th className="sticky left-0 z-10 h-7 w-10 min-w-10 border border-[#D7DDE5] bg-[#F8FAFC] text-center text-[11px] font-normal text-[#6B7280]">
                  {rowIndex + 1}
                </th>
                {Array.from({ length: columnCount }, (_, cellIndex) => {
                  const cell = row[cellIndex] ?? '';
                  return (
                    <td
                      key={cellIndex}
                      className={clsx(
                        'h-7 min-w-[116px] max-w-[260px] border border-[#D7DDE5] px-2 align-middle text-[12px] leading-5',
                        rowIndex === 0 && cell ? 'bg-[#EAF6FF] font-semibold' : 'bg-white',
                      )}
                      title={cell}
                    >
                      <div className="truncate">{cell}</div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex h-9 items-center gap-1 border-t border-[#D1D5DB] bg-[#F8FAFC] px-3">
        {preview.sheets.map((item, index) => (
          <button
            key={`${item.name}-${index}`}
            type="button"
            onClick={() => setActiveSheet(index)}
            className={clsx(
              'h-7 rounded-t-[6px] border px-3 text-[12px] leading-5 transition-colors',
              activeSheet === index
                ? 'border-[#D1D5DB] border-b-white bg-white font-medium text-[#059669]'
                : 'border-transparent text-[#374151] hover:bg-white',
            )}
          >
            {item.name}
          </button>
        ))}
      </div>
    </div>
  );
}

function DemoPreview() {
  return (
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
  );
}

function getFileKind(file: globalThis.File): FileKind {
  const name = file.name.toLowerCase();
  if (file.type.startsWith('image/')) return 'image';
  if (file.type === 'application/pdf' || name.endsWith('.pdf')) return 'pdf';
  if (name.endsWith('.ppt') || name.endsWith('.pptx')) return 'ppt';
  if (name.endsWith('.doc') || name.endsWith('.docx')) return 'word';
  if (name.endsWith('.xls') || name.endsWith('.xlsx')) return 'excel';
  return 'dark';
}

type WordBlock =
  | { type: 'paragraph'; text: string; listLabel?: string }
  | { type: 'image'; src: string; alt: string };
type SlideBlock =
  | { type: 'text'; text: string }
  | { type: 'image'; src: string; alt: string };

type OfficePreviewData =
  | { type: 'document'; blocks: WordBlock[] }
  | { type: 'sheet'; sheets: SheetPreview[]; activeSheet: number }
  | { type: 'slides'; slides: SlideBlock[][] };
type SheetPreview = {
  name: string;
  rows: string[][];
};

function isOfficeKind(kind: FileKind) {
  return kind === 'word' || kind === 'excel' || kind === 'ppt';
}

function isZipBuffer(buffer: ArrayBuffer) {
  const view = new DataView(buffer);
  return buffer.byteLength >= 4 && view.getUint32(0, true) === 0x04034b50;
}

async function parseOfficeFile(file: globalThis.File, kind: FileKind): Promise<OfficePreviewData> {
  const buffer = await file.arrayBuffer();
  if (!isZipBuffer(buffer)) {
    throw new Error('老版本 .doc/.xls/.ppt 需要先转成 PDF 才能完整预览');
  }
  const zip = await readZipEntries(buffer);

  if (kind === 'word') {
    const documentXml = zip.get('word/document.xml');
    if (!documentXml) throw new Error('没有找到 Word 文档内容');
    const xml = await entryToText(documentXml);
    const relationships = await readWordRelationships(zip);
    const listCounters = new Map<string, number>();
    const blocks: WordBlock[] = [];

    for (const paragraphXml of extractXmlBlocks(xml, 'w:p')) {
      const text = extractXmlBlocks(paragraphXml, 'w:t').map(xmlTextContent).join('').trim();
      const imageRelIds = extractImageRelationshipIds(paragraphXml);
      const listLabel = paragraphXml.includes('<w:numPr') ? nextListLabel(paragraphXml, listCounters) : undefined;

      if (text || (listLabel && imageRelIds.length)) {
        blocks.push({ type: 'paragraph', text, listLabel });
      }

      for (const relId of imageRelIds) {
        const target = relationships.get(relId);
        if (!target) continue;
        const entry = zip.get(target);
        if (!entry) continue;
        const bytes = await entryToBytes(entry);
        blocks.push({
          type: 'image',
          src: URL.createObjectURL(new Blob([uint8ToArrayBuffer(bytes)], { type: imageMimeFromPath(target) })),
          alt: target.split('/').pop() ?? 'image',
        });
      }
    }

    return {
      type: 'document',
      blocks: blocks.length ? blocks : [{ type: 'paragraph', text: '未解析到文字内容' }],
    };
  }

  if (kind === 'excel') {
    const sharedStringsXml = zip.get('xl/sharedStrings.xml');
    const workbookXmlEntry = zip.get('xl/workbook.xml');
    if (!workbookXmlEntry) throw new Error('没有找到 Excel 工作簿内容');

    const sharedStrings = sharedStringsXml
      ? extractXmlBlocks(await entryToText(sharedStringsXml), 'si').map((item) =>
          extractXmlBlocks(item, 't').map(xmlTextContent).join(''),
        )
      : [];
    const workbookXml = await entryToText(workbookXmlEntry);
    const workbookRelationships = await readWorkbookRelationships(zip);
    const workbookSheets = readWorkbookSheets(workbookXml);
    const sheets = await Promise.all(
      workbookSheets.map(async (sheet) => {
        const target = workbookRelationships.get(sheet.relId) ?? `xl/worksheets/sheet${sheet.sheetId}.xml`;
        const sheetEntry = zip.get(target);
        if (!sheetEntry) return { name: sheet.name, rows: [['未找到工作表内容']] };
        return {
          name: sheet.name,
          rows: buildSheetRows(await entryToText(sheetEntry), sharedStrings),
        };
      }),
    );
    return {
      type: 'sheet',
      sheets: sheets.length ? sheets : [{ name: 'Sheet1', rows: [['未解析到表格内容']] }],
      activeSheet: readActiveSheetIndex(workbookXml, sheets.length),
    };
  }

  if (kind === 'ppt') {
    const slideNames = [...zip.keys()]
      .filter((name) => /^ppt\/slides\/slide\d+\.xml$/.test(name))
      .sort((a, b) => Number(a.match(/\d+/)?.[0] ?? 0) - Number(b.match(/\d+/)?.[0] ?? 0));
    if (!slideNames.length) throw new Error('没有找到 PPT 页面内容');

    const slides = await Promise.all(
      slideNames.slice(0, 20).map(async (name) => {
        const xml = await entryToText(zip.get(name)!);
        const relationships = await readSlideRelationships(zip, name);
        const blocks: SlideBlock[] = extractXmlBlocks(xml, 'a:t')
          .map(xmlTextContent)
          .map((text) => text.trim())
          .filter(Boolean)
          .map((text) => ({ type: 'text', text }));
        for (const relId of extractImageRelationshipIds(xml)) {
          const target = relationships.get(relId);
          if (!target) continue;
          const entry = zip.get(target);
          if (!entry) continue;
          const bytes = await entryToBytes(entry);
          blocks.push({
            type: 'image',
            src: URL.createObjectURL(new Blob([uint8ToArrayBuffer(bytes)], { type: imageMimeFromPath(target) })),
            alt: target.split('/').pop() ?? 'image',
          });
        }
        return blocks;
      }),
    );
    return {
      type: 'slides',
      slides: slides.map((slide) => (slide.length ? slide : [{ type: 'text', text: '本页未解析到内容' }])),
    };
  }

  throw new Error('当前文件类型暂不支持预览');
}

type ZipEntry = {
  method: number;
  compressed: Uint8Array;
};

async function readZipEntries(buffer: ArrayBuffer) {
  const view = new DataView(buffer);
  const bytes = new Uint8Array(buffer);
  const entries = new Map<string, ZipEntry>();
  let eocdOffset = -1;

  for (let offset = bytes.length - 22; offset >= 0; offset -= 1) {
    if (view.getUint32(offset, true) === 0x06054b50) {
      eocdOffset = offset;
      break;
    }
  }

  if (eocdOffset < 0) throw new Error('文件格式不正确，无法读取压缩包');

  const totalEntries = view.getUint16(eocdOffset + 10, true);
  let centralOffset = view.getUint32(eocdOffset + 16, true);
  const decoder = new TextDecoder();

  for (let index = 0; index < totalEntries; index += 1) {
    if (view.getUint32(centralOffset, true) !== 0x02014b50) break;

    const method = view.getUint16(centralOffset + 10, true);
    const compressedSize = view.getUint32(centralOffset + 20, true);
    const fileNameLength = view.getUint16(centralOffset + 28, true);
    const extraLength = view.getUint16(centralOffset + 30, true);
    const commentLength = view.getUint16(centralOffset + 32, true);
    const localHeaderOffset = view.getUint32(centralOffset + 42, true);
    const nameStart = centralOffset + 46;
    const name = decoder.decode(bytes.slice(nameStart, nameStart + fileNameLength));

    const localNameLength = view.getUint16(localHeaderOffset + 26, true);
    const localExtraLength = view.getUint16(localHeaderOffset + 28, true);
    const dataStart = localHeaderOffset + 30 + localNameLength + localExtraLength;
    entries.set(name, {
      method,
      compressed: bytes.slice(dataStart, dataStart + compressedSize),
    });

    centralOffset += 46 + fileNameLength + extraLength + commentLength;
  }

  return entries;
}

async function entryToText(entry: ZipEntry) {
  const data = await entryToBytes(entry);
  return new TextDecoder().decode(data);
}

async function entryToBytes(entry: ZipEntry) {
  let data = entry.compressed;
  if (entry.method === 8) {
    if (!('DecompressionStream' in window)) {
      throw new Error('当前浏览器不支持本地解压预览');
    }
    const stream = new Blob([uint8ToArrayBuffer(entry.compressed)])
      .stream()
      .pipeThrough(new DecompressionStream('deflate-raw'));
    data = new Uint8Array(await new Response(stream).arrayBuffer());
  } else if (entry.method !== 0) {
    throw new Error('暂不支持这个压缩方式');
  }

  return data;
}

async function readWordRelationships(zip: Map<string, ZipEntry>) {
  const relationships = new Map<string, string>();
  const relsEntry = zip.get('word/_rels/document.xml.rels');
  if (!relsEntry) return relationships;

  const relsXml = await entryToText(relsEntry);
  const relationshipPattern = /<Relationship\b[^>]*\bId="([^"]+)"[^>]*\bTarget="([^"]+)"[^>]*>/g;

  for (const match of relsXml.matchAll(relationshipPattern)) {
    const [, id, target] = match;
    if (!target) continue;
    if (!/\.(png|jpe?g|gif|bmp|webp|svg)$/i.test(target)) continue;
    relationships.set(id, target.startsWith('/') ? target.slice(1) : `word/${target.replace(/^\.\.\//, '')}`);
  }

  return relationships;
}

async function readSlideRelationships(zip: Map<string, ZipEntry>, slidePath: string) {
  const relationships = new Map<string, string>();
  const slideFile = slidePath.split('/').pop();
  if (!slideFile) return relationships;
  const relsEntry = zip.get(`ppt/slides/_rels/${slideFile}.rels`);
  if (!relsEntry) return relationships;

  const relsXml = await entryToText(relsEntry);
  const relationshipPattern = /<Relationship\b[^>]*\bId="([^"]+)"[^>]*\bTarget="([^"]+)"[^>]*>/g;

  for (const match of relsXml.matchAll(relationshipPattern)) {
    const [, id, target] = match;
    if (!target) continue;
    if (!/\.(png|jpe?g|gif|bmp|webp|svg)$/i.test(target)) continue;
    relationships.set(id, target.startsWith('/') ? target.slice(1) : `ppt/${target.replace(/^\.\.\//, '')}`);
  }

  return relationships;
}

async function readWorkbookRelationships(zip: Map<string, ZipEntry>) {
  const relationships = new Map<string, string>();
  const relsEntry = zip.get('xl/_rels/workbook.xml.rels');
  if (!relsEntry) return relationships;

  const relsXml = await entryToText(relsEntry);
  const relationshipPattern = /<Relationship\b[^>]*\bId="([^"]+)"[^>]*\bTarget="([^"]+)"[^>]*>/g;

  for (const match of relsXml.matchAll(relationshipPattern)) {
    const [, id, target] = match;
    if (!target) continue;
    if (!target.includes('worksheets/')) continue;
    relationships.set(id, target.startsWith('/') ? target.slice(1) : `xl/${target.replace(/^\.\//, '')}`);
  }

  return relationships;
}

function readWorkbookSheets(workbookXml: string) {
  const sheetPattern = /<sheet\b([^>]*)\/?>/g;
  return [...workbookXml.matchAll(sheetPattern)].map((match, index) => {
    const attrs = match[1];
    return {
      name: decodeXmlEntities(attrs.match(/\bname="([^"]+)"/)?.[1] ?? `Sheet${index + 1}`),
      sheetId: attrs.match(/\bsheetId="([^"]+)"/)?.[1] ?? `${index + 1}`,
      relId: attrs.match(/\br:id="([^"]+)"/)?.[1] ?? '',
    };
  });
}

function readActiveSheetIndex(workbookXml: string, sheetCount: number) {
  const active = Number(workbookXml.match(/\bactiveTab="(\d+)"/)?.[1] ?? 0);
  if (!Number.isFinite(active)) return 0;
  return Math.min(Math.max(active, 0), Math.max(sheetCount - 1, 0));
}

function buildSheetRows(sheetXml: string, sharedStrings: string[]) {
  const rowMap = new Map<number, Map<number, string>>();
  let maxColumn = 0;
  const cellPattern = /<c\b([^>]*)>([\s\S]*?)<\/c>/g;

  for (const match of sheetXml.matchAll(cellPattern)) {
    const [, attrs, cellXml] = match;
    const reference = attrs.match(/\br="([A-Z]+)(\d+)"/)?.slice(1);
    if (!reference) continue;

    const [columnName, rowNumberText] = reference;
    const rowIndex = Number(rowNumberText) - 1;
    const columnIndex = excelColumnToIndex(columnName);
    const type = attrs.match(/\bt="([^"]+)"/)?.[1];
    const value = readCellValue(cellXml, type, sharedStrings);
    if (!value) continue;

    if (!rowMap.has(rowIndex)) rowMap.set(rowIndex, new Map());
    rowMap.get(rowIndex)!.set(columnIndex, value);
    maxColumn = Math.max(maxColumn, columnIndex);
  }

  const rows = [...rowMap.entries()]
    .sort(([a], [b]) => a - b)
    .slice(0, 80)
    .map(([, cells]) =>
      Array.from({ length: Math.min(maxColumn + 1, 24) }, (_, columnIndex) => cells.get(columnIndex) ?? ''),
    )
    .filter((row) => row.some(Boolean));
  return rows;
}

function readCellValue(cellXml: string, type: string | undefined, sharedStrings: string[]) {
  if (type === 's') {
    const index = Number(xmlTextContent(extractXmlBlocks(cellXml, 'v')[0] ?? ''));
    return sharedStrings[index] ?? '';
  }

  if (type === 'inlineStr') {
    return extractXmlBlocks(cellXml, 't').map(xmlTextContent).join('');
  }

  if (type === 'str') {
    return xmlTextContent(extractXmlBlocks(cellXml, 'v')[0] ?? '');
  }

  return xmlTextContent(extractXmlBlocks(cellXml, 'v')[0] ?? '');
}

function excelColumnToIndex(column: string) {
  return column.split('').reduce((total, char) => total * 26 + char.charCodeAt(0) - 64, 0) - 1;
}

function indexToExcelColumn(index: number) {
  let value = index + 1;
  let label = '';
  while (value > 0) {
    const remainder = (value - 1) % 26;
    label = String.fromCharCode(65 + remainder) + label;
    value = Math.floor((value - 1) / 26);
  }
  return label;
}

function extractImageRelationshipIds(paragraphXml: string) {
  return [
    ...new Set(
      [...paragraphXml.matchAll(/r:embed="([^"]+)"/g), ...paragraphXml.matchAll(/r:link="([^"]+)"/g)].map(
        (match) => match[1],
      ),
    ),
  ];
}

function nextListLabel(paragraphXml: string, counters: Map<string, number>) {
  const numId = paragraphXml.match(/<w:numId\b[^>]*w:val="([^"]+)"/)?.[1] ?? 'default';
  const level = paragraphXml.match(/<w:ilvl\b[^>]*w:val="([^"]+)"/)?.[1] ?? '0';
  const key = `${numId}:${level}`;
  const next = (counters.get(key) ?? 0) + 1;
  counters.set(key, next);
  return `${next}、`;
}

function imageMimeFromPath(path: string) {
  const lower = path.toLowerCase();
  if (lower.endsWith('.png')) return 'image/png';
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg';
  if (lower.endsWith('.gif')) return 'image/gif';
  if (lower.endsWith('.bmp')) return 'image/bmp';
  if (lower.endsWith('.webp')) return 'image/webp';
  if (lower.endsWith('.svg')) return 'image/svg+xml';
  return 'application/octet-stream';
}

function uint8ToArrayBuffer(bytes: Uint8Array) {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

function extractXmlBlocks(xml: string, tagName: string) {
  const escaped = tagName.replace(':', '\\:');
  const pattern = new RegExp(`<${escaped}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${escaped}>`, 'g');
  return [...xml.matchAll(pattern)].map((match) => match[1]);
}

function xmlTextContent(xml: string) {
  return decodeXmlEntities(xml.replace(/<[^>]+>/g, ''));
}

function decodeXmlEntities(text: string) {
  return text
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'");
}

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
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
    pdf: { text: 'PDF', bg: '#DC2626' },
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
