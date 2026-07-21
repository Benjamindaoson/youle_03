'use client';

// 澄清气泡(v4 §187-194):4 种形式
// - single_select  3-4 个按钮
// - multi_select   多字段合并一次问完(checkbox 风)
// - image_compare  3 张参考图缩略图供选
// - version_compare 实时调 Agent 生成 3 个版本
import { useState } from 'react';
import clsx from 'clsx';

export type ClarificationForm =
  | 'single_select'
  | 'multi_select'
  | 'image_compare'
  | 'version_compare';

export interface SingleSelect {
  form: 'single_select';
  field: string;
  question: string;
  options: { label: string; value: string | number }[];
  default?: string | number;
}

export interface MultiSelect {
  form: 'multi_select';
  question: string;
  fields: {
    name: string;
    label: string;
    options: { label: string; value: string | number }[];
    default?: string | number;
  }[];
}

export interface ImageCompare {
  form: 'image_compare';
  field: string;
  question: string;
  options: { id: string; label: string; thumbnail: string }[];
}

export interface VersionCompare {
  form: 'version_compare';
  field: string;
  question: string;
  versions: { id: string; label: string; content: string }[];
}

export type Clarification =
  | SingleSelect
  | MultiSelect
  | ImageCompare
  | VersionCompare;

interface Props {
  data: Clarification;
  onAnswer: (answer: Record<string, string | number>) => void;
}

export function ClarificationCard({ data, onAnswer }: Props) {
  return (
    <div className="my-2 max-w-[480px] rounded-md border border-wechat-green-soft bg-wechat-green-soft/50 p-3">
      <div className="mb-2 text-[12px] font-medium text-wechat-fg">{data.question}</div>
      {data.form === 'single_select' && <SingleSelectView d={data} onAnswer={onAnswer} />}
      {data.form === 'multi_select' && <MultiSelectView d={data} onAnswer={onAnswer} />}
      {data.form === 'image_compare' && <ImageCompareView d={data} onAnswer={onAnswer} />}
      {data.form === 'version_compare' && <VersionCompareView d={data} onAnswer={onAnswer} />}
    </div>
  );
}

function SingleSelectView({
  d,
  onAnswer,
}: {
  d: SingleSelect;
  onAnswer: Props['onAnswer'];
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {d.options.map((opt) => (
        <button
          key={String(opt.value)}
          type="button"
          onClick={() => onAnswer({ [d.field]: opt.value })}
          className="rounded-sm border border-wechat-line bg-white px-3 py-1 text-[12px] text-wechat-fg hover:border-wechat-green hover:bg-wechat-green-soft"
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

function MultiSelectView({
  d,
  onAnswer,
}: {
  d: MultiSelect;
  onAnswer: Props['onAnswer'];
}) {
  const [draft, setDraft] = useState<Record<string, string | number>>(() => {
    const init: Record<string, string | number> = {};
    for (const f of d.fields) if (f.default !== undefined) init[f.name] = f.default;
    return init;
  });
  const allFilled = d.fields.every((f) => draft[f.name] !== undefined);
  return (
    <div className="space-y-2">
      {d.fields.map((f) => (
        <div key={f.name}>
          <div className="mb-1 text-[11px] text-wechat-sub">{f.label}</div>
          <div className="flex flex-wrap gap-1.5">
            {f.options.map((opt) => {
              const active = draft[f.name] === opt.value;
              return (
                <button
                  key={String(opt.value)}
                  type="button"
                  onClick={() =>
                    setDraft((s) => ({ ...s, [f.name]: opt.value }))
                  }
                  className={clsx(
                    'rounded-sm border px-2.5 py-1 text-[12px] transition-colors',
                    active
                      ? 'border-wechat-green bg-wechat-green text-white'
                      : 'border-wechat-line bg-white text-wechat-fg hover:border-wechat-green',
                  )}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>
      ))}
      <button
        type="button"
        disabled={!allFilled}
        onClick={() => onAnswer(draft)}
        className="mt-1 w-full rounded-sm bg-wechat-green py-1.5 text-[12px] text-white disabled:opacity-50"
      >
        确定
      </button>
    </div>
  );
}

function ImageCompareView({
  d,
  onAnswer,
}: {
  d: ImageCompare;
  onAnswer: Props['onAnswer'];
}) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {d.options.map((opt) => (
        <button
          key={opt.id}
          type="button"
          onClick={() => onAnswer({ [d.field]: opt.id })}
          className="overflow-hidden rounded-sm border border-wechat-line bg-white text-left transition-colors hover:border-wechat-green"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={opt.thumbnail}
            alt={opt.label}
            className="h-24 w-full object-cover"
          />
          <div className="px-2 py-1 text-center text-[11px] text-wechat-fg">
            {opt.label}
          </div>
        </button>
      ))}
    </div>
  );
}

function VersionCompareView({
  d,
  onAnswer,
}: {
  d: VersionCompare;
  onAnswer: Props['onAnswer'];
}) {
  return (
    <div className="space-y-2">
      {d.versions.map((v) => (
        <button
          key={v.id}
          type="button"
          onClick={() => onAnswer({ [d.field]: v.id })}
          className="block w-full rounded-sm border border-wechat-line bg-white p-2 text-left transition-colors hover:border-wechat-green"
        >
          <div className="mb-1 text-[11px] font-medium text-wechat-green">
            版本 {v.label}
          </div>
          <p className="text-[12px] leading-[1.6] text-wechat-fg">{v.content}</p>
        </button>
      ))}
    </div>
  );
}
