'use client';

import { useState } from 'react';

import type { ClarificationPrompt } from '@/stores/hitl';

type Answer = Record<string, string | number>;

function optionValue(option: unknown): string | number | null {
  if (typeof option === 'string' || typeof option === 'number') return option;
  if (!option || typeof option !== 'object') return null;
  const value = (option as Record<string, unknown>).value;
  return typeof value === 'string' || typeof value === 'number' ? value : null;
}

function optionLabel(option: unknown): string {
  if (typeof option === 'string' || typeof option === 'number') return String(option);
  if (!option || typeof option !== 'object') return '';
  const record = option as Record<string, unknown>;
  return String(record.label ?? record.value ?? '');
}

export function ClarificationCard({
  data,
  disabled = false,
  onAnswer,
}: {
  data: ClarificationPrompt;
  disabled?: boolean;
  onAnswer: (answer: Answer) => void;
}) {
  const [draft, setDraft] = useState(
    typeof data.default === 'string' || typeof data.default === 'number'
      ? String(data.default)
      : '',
  );
  const options = data.options
    .map((option) => ({ label: optionLabel(option), value: optionValue(option) }))
    .filter((option): option is { label: string; value: string | number } => option.value !== null);

  return (
    <div className="max-w-[480px] rounded-md border border-wechat-green-soft bg-wechat-green-soft/50 p-3">
      <div className="mb-1 text-[12px] font-medium text-wechat-fg">{data.question}</div>
      <div className="mb-2 text-[10px] text-wechat-mute">
        第 {(data.round_number ?? 0) + 1} 轮 · 还需 {data.total_missing ?? 1} 项
      </div>
      {options.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {options.map((option) => (
            <button
              key={String(option.value)}
              type="button"
              disabled={disabled}
              onClick={() => onAnswer({ [data.field]: option.value })}
              className="rounded-sm border border-wechat-line bg-white px-3 py-1 text-[12px] text-wechat-fg hover:border-wechat-green disabled:opacity-50"
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : (
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (draft.trim()) onAnswer({ [data.field]: draft.trim() });
          }}
        >
          <input
            value={draft}
            disabled={disabled}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={data.form === 'image_upload' ? '输入图片 URL 或素材引用' : '请输入内容'}
            className="min-w-0 flex-1 rounded-sm border border-wechat-line bg-white px-2 py-1 text-[12px] outline-none focus:border-wechat-green"
          />
          <button
            type="submit"
            disabled={disabled || !draft.trim()}
            className="rounded-sm bg-wechat-green px-3 py-1 text-[12px] text-white disabled:opacity-50"
          >
            确定
          </button>
        </form>
      )}
    </div>
  );
}
