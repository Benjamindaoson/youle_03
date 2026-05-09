'use client';

// HITL gate 2:配图审核(quality_review)— 内嵌入消息流
// 用户挑选 / 重生成 / 全部通过
import { Check, ImageIcon, RotateCcw } from 'lucide-react';
import { useHitlDecision } from '@/lib/api';

export function ImageSelection({
  taskId,
  gateId,
  images,
}: {
  taskId: string;
  gateId: string;
  images: { id: string; url: string }[];
}) {
  const decide = useHitlDecision(taskId, gateId);

  return (
    <div className="w-[480px] max-w-full overflow-hidden rounded-md border border-wechat-line bg-white shadow-sm">
      <div className="flex items-center gap-2 border-b border-neutral-100 px-3.5 py-2.5">
        <span className="grid h-[18px] w-[18px] place-items-center rounded-sm bg-wechat-green text-white">
          <ImageIcon size={10} strokeWidth={2.5} />
        </span>
        <span className="flex-1 text-[12px] font-semibold text-wechat-fg">配图审核 · 挑选/重生成</span>
        <span className="text-[10px] text-wechat-sub">HITL · gate 2</span>
      </div>

      <div className="grid grid-cols-3 gap-2 p-3.5">
        {images.map((img) => (
          <div key={img.id} className="relative">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={img.url}
              alt=""
              className="aspect-square w-full rounded object-cover"
            />
            <button
              type="button"
              onClick={() =>
                decide.mutate({
                  action: 'modify',
                  payload: {
                    target_step: 'image_process',
                    parameters: { regenerate: img.id },
                  },
                })
              }
              className="absolute bottom-1 right-1 flex items-center gap-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white hover:bg-black/80"
            >
              <RotateCcw size={10} strokeWidth={2} /> 重生成
            </button>
          </div>
        ))}
      </div>

      <div className="flex justify-end border-t border-neutral-100 px-3.5 py-2">
        <button
          type="button"
          onClick={() => decide.mutate({ action: 'approve' })}
          className="flex items-center gap-1 rounded bg-wechat-green px-3.5 py-1 text-[12px] text-white hover:bg-[#06AE56]"
        >
          <Check size={12} strokeWidth={2.5} /> 全部通过
        </button>
      </div>
    </div>
  );
}
