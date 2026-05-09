'use client';

// Chat composer: textarea + quick tools + send action.
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ClipboardEvent,
  type MouseEvent as ReactMouseEvent,
} from 'react';
import Image from 'next/image';
import { FileText, X } from 'lucide-react';
import clsx from 'clsx';
import { useConversationStore } from '@/stores/conversation';
import { useMaterials, usePrompts, useSendMessage } from '@/lib/api';
import { ROLES } from '@/lib/agents';
import { MentionPopover, type MentionItem } from '@/components/chat/MentionPopover';

interface MentionState {
  start: number;
  query: string;
}

interface PastedImage {
  id: string;
  url: string;
  name: string;
  size: number;
  isImage: boolean;
  loaded: boolean;
}

const SEND_PLACEHOLDER = '\u53d1\u9001\u6d88\u606f\uff0c\u7ed9\u6570\u5b57\u5458\u5de5\u6d3e\u6d3b...';

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

export function Composer({ conversationId }: { conversationId: string }) {
  const [text, setText] = useState('');
  const [pastedImages, setPastedImages] = useState<PastedImage[]>([]);
  const [mention, setMention] = useState<MentionState | null>(null);
  const [screenshotMode, setScreenshotMode] = useState(false);
  const conv = useConversationStore((s) => s.list.find((c) => c.id === conversationId));
  const appendMessage = useConversationStore((s) => s.appendMessage);
  const quoted = useConversationStore((s) => s.quoted[conversationId] ?? null);
  const setQuoted = useConversationStore((s) => s.setQuoted);
  const send = useSendMessage(conversationId);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pastedImagesRef = useRef<PastedImage[]>([]);

  const { data: materials = [] } = useMaterials();
  const { data: prompts = [] } = usePrompts();

  useEffect(() => {
    pastedImagesRef.current = pastedImages;
  }, [pastedImages]);

  useEffect(() => {
    return () => {
      pastedImagesRef.current.forEach((image) => {
        if (image.url) URL.revokeObjectURL(image.url);
      });
    };
  }, []);

  // Detect the @ before the cursor and open/update the mention popover.
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    const pos = ta.selectionStart ?? text.length;
    const upto = text.slice(0, pos);
    const match = /(?:^|\s)@(\S*)$/.exec(upto);
    if (match) {
      const start = pos - match[1].length - 1;
      setMention({ start, query: match[1] });
    } else {
      setMention(null);
    }
  }, [text]);

  function dispatch() {
    const trimmed = text.trim();
    if (!trimmed && pastedImages.length === 0) return;
    const finalText = quoted
      ? `> ${ROLES[quoted.role].name}:${quoted.preview}\n${trimmed}`
      : trimmed;
    appendMessage({
      id: `local-${Date.now()}`,
      conversation_id: conversationId,
      kind: 'user_text',
      role: 'user',
      text: finalText,
    });
    send.mutate(finalText);
    setText('');
    setPastedImages((prev) => {
      prev.forEach((image) => {
        if (image.url) URL.revokeObjectURL(image.url);
      });
      return [];
    });
    setMention(null);
    setQuoted(conversationId, null);
  }

  function handlePaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const files = Array.from(event.clipboardData.files).filter((file) =>
      file.type.startsWith('image/'),
    );
    if (!files.length) return;

    event.preventDefault();
    setPastedImages((prev) => [
      ...prev,
      ...files.map((file) => ({
        id: `${file.name}-${file.lastModified}-${crypto.randomUUID()}`,
        url: URL.createObjectURL(file),
        name: file.name || '\u7c98\u8d34\u56fe\u7247',
        size: file.size,
        isImage: true,
        loaded: false,
      })),
    ]);
  }

  function addLocalFiles(files: File[]) {
    if (!files.length) return;
    setPastedImages((prev) => [
      ...prev,
      ...files.map((file) => {
        const isImage = file.type.startsWith('image/');
        return {
          id: `${file.name}-${file.lastModified}-${crypto.randomUUID()}`,
          url: isImage ? URL.createObjectURL(file) : '',
          name: file.name || '\u672c\u5730\u6587\u4ef6',
          size: file.size,
          isImage,
          loaded: !isImage,
        };
      }),
    ]);
  }

  function handleLocalFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    addLocalFiles(Array.from(event.target.files ?? []));
    event.target.value = '';
  }

  function markPastedImageLoaded(id: string) {
    setPastedImages((prev) =>
      prev.map((image) => (image.id === id ? { ...image, loaded: true } : image)),
    );
  }

  function removePastedImage(id: string) {
    setPastedImages((prev) => {
      const target = prev.find((image) => image.id === id);
      if (target?.url) URL.revokeObjectURL(target.url);
      return prev.filter((image) => image.id !== id);
    });
  }

  async function captureSelection(rect: DOMRectInit) {
    try {
      const blob = await renderSelectionToBlob(rect);
      const url = URL.createObjectURL(blob);
      setPastedImages((prev) => [
        ...prev,
        {
          id: `screenshot-${Date.now()}-${crypto.randomUUID()}`,
          url,
          name: '\u622a\u56fe.png',
          size: blob.size,
          isImage: true,
          loaded: false,
        },
      ]);
    } catch {
      alert('\u5f53\u524d\u9875\u9762\u542b\u6709\u6d4f\u89c8\u5668\u4e0d\u5141\u8bb8\u76f4\u63a5\u7ed8\u5236\u7684\u8d44\u6e90\uff0c\u5df2\u963b\u6b62\u7f51\u9875\u5185\u622a\u56fe\u3002\u8bf7\u4f7f\u7528\u7cfb\u7edf\u622a\u56fe\u540e\u7c98\u8d34\u5230\u8f93\u5165\u6846\u3002');
    } finally {
      setScreenshotMode(false);
    }
  }

  async function renderSelectionToBlob(rect: DOMRectInit) {
    const width = Math.max(1, Math.round(rect.width ?? 0));
    const height = Math.max(1, Math.round(rect.height ?? 0));
    const left = Math.round(rect.x ?? 0);
    const top = Math.round(rect.y ?? 0);
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const clone = document.body.cloneNode(true) as HTMLElement;
    clone.querySelectorAll('[data-screenshot-ui="true"]').forEach((node) => node.remove());
    clone.querySelectorAll('script, next-route-announcer').forEach((node) => node.remove());
    await inlineCloneImages(clone);
    clone.style.margin = '0';
    clone.style.width = `${document.documentElement.scrollWidth}px`;
    clone.style.minHeight = `${document.documentElement.scrollHeight}px`;

    const styleText = Array.from(document.styleSheets)
      .map((sheet) => {
        try {
          return Array.from(sheet.cssRules)
            .map((rule) => rule.cssText)
            .join('\n');
        } catch {
          return '';
        }
      })
      .join('\n');

    const html = clone.innerHTML;
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">
        <foreignObject width="${viewportWidth}" height="${viewportHeight}" x="${-left}" y="${-top}">
          <div xmlns="http://www.w3.org/1999/xhtml" style="margin:0;width:${document.documentElement.scrollWidth}px;min-height:${document.documentElement.scrollHeight}px;">
            <style><![CDATA[${styleText}]]></style>
            ${html}
          </div>
        </foreignObject>
      </svg>
    `;
    const svgBlob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(svgBlob);

    try {
      const image = await new Promise<HTMLImageElement>((resolve, reject) => {
        const img = new window.Image();
        img.onload = () => resolve(img);
        img.onerror = reject;
        img.src = url;
      });

      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('No canvas context');
      ctx.drawImage(image, 0, 0);

      const blob = await new Promise<Blob | null>((resolve) =>
        canvas.toBlob(resolve, 'image/png'),
      );
      if (!blob) throw new Error('No screenshot blob');
      return blob;
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  async function inlineCloneImages(root: HTMLElement) {
    const images = Array.from(root.querySelectorAll('img'));
    await Promise.all(
      images.map(async (image) => {
        const src = image.getAttribute('src');
        if (!src || src.startsWith('data:') || src.startsWith('blob:')) return;
        try {
          const absoluteUrl = new URL(src, window.location.href);
          if (absoluteUrl.origin !== window.location.origin) return;
          const response = await fetch(absoluteUrl.href);
          const blob = await response.blob();
          const dataUrl = await blobToDataUrl(blob);
          image.setAttribute('src', dataUrl);
        } catch {
          image.removeAttribute('src');
        }
      }),
    );
  }

  function blobToDataUrl(blob: Blob) {
    return new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  function applyMention(item: MentionItem) {
    if (!mention) return;
    const before = text.slice(0, mention.start);
    const afterStart = mention.start + 1 + mention.query.length;
    const after = text.slice(afterStart);

    if (item.kind === 'agent') {
      const label = `@${ROLES[item.role].name} `;
      const next = before + label + after;
      setText(next);
      setMention(null);
      requestAnimationFrame(() => {
        const ta = taRef.current;
        if (ta) {
          const caret = (before + label).length;
          ta.setSelectionRange(caret, caret);
          ta.focus();
        }
      });
      return;
    }

    if (item.kind === 'material') {
      const label = `@${item.label} `;
      setText(before + label + after);
      setMention(null);
      return;
    }

    if (item.kind === 'prompt') {
      const expanded = item.content + ' ';
      setText(before + expanded + after);
      setMention(null);
      requestAnimationFrame(() => {
        const ta = taRef.current;
        if (ta) {
          const caret = (before + expanded).length;
          ta.setSelectionRange(caret, caret);
          ta.focus();
        }
      });
    }
  }

  const canSend = text.trim().length > 0 || pastedImages.length > 0;

  const popover = useMemo(() => {
    if (!mention || !conv) return null;
    return (
      <MentionPopover
        conversationKind={conv.kind}
        query={mention.query}
        materials={materials}
        prompts={prompts}
        onPick={applyMention}
        onClose={() => setMention(null)}
      />
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mention, conv, materials, prompts]);

  return (
    <div className="relative flex-shrink-0 border-t border-wechat-line bg-white">
      {popover}

      {quoted && (
        <div className="mx-2 mt-2 flex h-9 items-center rounded-[6px] bg-[#00000008] pl-4 pr-2">
          <div className="min-w-0 flex-1 truncate text-[12px] font-normal leading-4 text-[#8B8F99]">
            <span>{'\u56de\u590d '}</span>
            <span>{ROLES[quoted.role].name}</span>
            <span>{': '}</span>
            <span>{quoted.preview}</span>
          </div>
          <button
            type="button"
            onClick={() => setQuoted(conversationId, null)}
            className="ml-3 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-[#00000020] text-white transition-colors hover:bg-[#00000033]"
            aria-label="Remove quote"
          >
            <X size={13} strokeWidth={2.2} />
          </button>
        </div>
      )}

      <div className="relative h-[168px] px-10 pb-4 pt-5">
        {pastedImages.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-2">
            {pastedImages.map((image) => (
              <div
                key={image.id}
                className={clsx(
                  'group relative overflow-visible rounded-[8px]',
                  image.isImage ? 'h-[52px] w-[52px]' : 'h-[52px] w-[150px]',
                )}
              >
                {image.isImage ? (
                  <>
                    <img
                      src={image.url}
                      alt={image.name}
                      onLoad={() => markPastedImageLoaded(image.id)}
                      className="h-full w-full rounded-[8px] object-cover"
                    />
                    {!image.loaded && (
                      <div className="absolute inset-0 grid place-items-center rounded-[8px] bg-black/45">
                        <span className="h-5 w-5 animate-spin rounded-full border-2 border-white/70 border-t-transparent" />
                      </div>
                    )}
                  </>
                ) : (
                  <div className="flex h-full w-full items-center gap-2 rounded-[8px] border border-black/[0.06] bg-white px-3">
                    <FileText size={20} className="flex-shrink-0 text-[#9CA3AF]" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[12px] leading-4 text-[#111827]">{image.name}</div>
                      <div className="mt-0.5 text-[11px] leading-4 text-[#9CA3AF]">
                        {formatFileSize(image.size)}
                      </div>
                    </div>
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => removePastedImage(image.id)}
                  className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-[#00000099] text-white transition-colors hover:bg-[#000000cc]"
                  aria-label="Remove pasted image"
                  title="Remove pasted image"
                >
                  <X size={13} strokeWidth={2.2} />
                </button>
              </div>
            ))}
          </div>
        )}
        <textarea
          ref={taRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onPaste={handlePaste}
          onKeyDown={(e) => {
            if (mention && ['ArrowDown', 'ArrowUp', 'Enter', 'Tab', 'Escape'].includes(e.key)) {
              return;
            }
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              dispatch();
            }
          }}
          placeholder={SEND_PLACEHOLDER}
          className="h-[100px] w-full resize-none border-none bg-transparent text-[13px] leading-[1.65] text-wechat-fg outline-none caret-wechat-green placeholder:text-[#c6cad1]"
        />

        <div className="absolute bottom-4 left-10 flex items-center gap-3">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={handleLocalFileChange}
          />
          <button
            type="button"
            className="composer-icon-btn tip-parent relative"
            title="Attach"
            aria-label="Attach"
            onClick={() => fileInputRef.current?.click()}
          >
            <Image src="/home/microphone.svg" alt="" width={20} height={20} />
            <span className="tip-base tip-top">{'\u4e0a\u4f20\u4f60\u7684\u6587\u4ef6\u8d44\u6599'}</span>
          </button>
          <button
            type="button"
            className="composer-icon-btn tip-parent relative"
            title="Cut"
            aria-label="Cut"
            onClick={() => setScreenshotMode(true)}
          >
            <Image src="/home/icon-cut.svg" alt="" width={20} height={20} />
            <span className="tip-base tip-top">{'\u622a\u56fe\u5e76\u63d0\u51fa\u4f60\u7684\u4fee\u6539\u610f\u89c1'}</span>
          </button>
        </div>

        <button
          type="button"
          onClick={dispatch}
          disabled={!canSend}
          className={clsx(
            'absolute bottom-[11px] right-5 flex h-9 w-9 items-center justify-center rounded-full transition-colors',
            canSend ? 'bg-[#f3f4f6] hover:bg-[#e9edf2]' : 'cursor-not-allowed bg-[#f4f5f7] opacity-60',
          )}
          aria-label="Send"
          title="Send"
        >
          <Image src="/home/icon-upload.svg" alt="" width={20} height={20} />
        </button>
      </div>

      {screenshotMode && (
        <ScreenshotOverlay
          onCancel={() => setScreenshotMode(false)}
          onCapture={captureSelection}
        />
      )}
    </div>
  );
}

function ScreenshotOverlay({
  onCancel,
  onCapture,
}: {
  onCancel: () => void;
  onCapture: (rect: DOMRectInit) => void;
}) {
  const [start, setStart] = useState<{ x: number; y: number } | null>(null);
  const [current, setCurrent] = useState<{ x: number; y: number } | null>(null);
  const selecting = !!start && !!current;
  const rect = selecting
    ? {
        x: Math.min(start.x, current.x),
        y: Math.min(start.y, current.y),
        width: Math.abs(current.x - start.x),
        height: Math.abs(current.y - start.y),
      }
    : null;

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onCancel();
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onCancel]);

  function handleMouseDown(event: ReactMouseEvent<HTMLDivElement>) {
    if ((event.target as HTMLElement).closest('[data-screenshot-toolbar="true"]')) return;
    const point = { x: event.clientX, y: event.clientY };
    setStart(point);
    setCurrent(point);
  }

  function handleMouseMove(event: ReactMouseEvent<HTMLDivElement>) {
    if (!start) return;
    setCurrent({ x: event.clientX, y: event.clientY });
  }

  function handleMouseUp() {
    if (!rect) return;
    if (rect.width < 8 || rect.height < 8) {
      setStart(null);
      setCurrent(null);
      return;
    }
    onCapture(rect);
  }

  return (
    <div
      data-screenshot-ui="true"
      className="fixed inset-0 z-[10000] cursor-crosshair select-none bg-black/45"
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
    >
      <div
        data-screenshot-toolbar="true"
        className="absolute left-1/2 top-0 flex -translate-x-1/2 items-center overflow-hidden rounded-b-[8px] bg-[#1f2937] text-[14px] leading-5 text-white shadow-lg"
      >
        <button type="button" className="bg-white px-4 py-2 font-medium text-[#111827]">
          {'\u622a\u56fe'}
        </button>
        <button type="button" className="px-4 py-2 text-white/90">
          {'\u6eda\u52a8\u622a\u56fe'}
        </button>
        <button type="button" className="px-4 py-2 text-white/90">
          {'\u5f55\u5c4f'}
        </button>
        <button type="button" className="px-4 py-2 text-white/90">
          {'\u63d0\u53d6\u6587\u5b57'}
        </button>
        <button type="button" onClick={onCancel} className="px-3 py-2 text-white/70 hover:text-white">
          <X size={16} />
        </button>
      </div>

      {rect && (
        <div
          className="absolute border-2 border-[#409eff] bg-white/10"
          style={{
            left: rect.x,
            top: rect.y,
            width: rect.width,
            height: rect.height,
            boxShadow: '0 0 0 9999px rgba(0,0,0,0.18)',
          }}
        >
          <div className="absolute bottom-2 right-2 rounded bg-[#111827] px-2 py-1 text-[11px] leading-4 text-white">
            {`${Math.round(rect.width)} x ${Math.round(rect.height)}`}
          </div>
        </div>
      )}
    </div>
  );
}
