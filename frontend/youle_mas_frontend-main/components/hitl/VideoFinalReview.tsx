'use client';

// HITL gate 3:视频终审(final_approval)— 内嵌入消息流
// 铁律 §14:V1 终审仅 [接受][微调][取消],无回滚按钮(中断 C 是 V2)
import { Check, Sliders, X } from 'lucide-react';
import { useHitlDecision } from '@/lib/api';

export function VideoFinalReview({
  taskId,
  gateId,
  videoUrl,
}: {
  taskId: string;
  gateId: string;
  videoUrl: string;
}) {
  const decide = useHitlDecision(taskId, gateId);

  return (
    <div className="w-[480px] max-w-full overflow-hidden rounded-md border border-wechat-line bg-white shadow-sm">
      <div className="flex items-center gap-2 border-b border-neutral-100 px-3.5 py-2.5">
        <span className="grid h-[18px] w-[18px] place-items-center rounded-sm bg-wechat-green text-white">
          <Check size={10} strokeWidth={2.5} />
        </span>
        <span className="flex-1 text-[12px] font-semibold text-wechat-fg">视频终审</span>
        <span className="text-[10px] text-wechat-sub">HITL · gate 3</span>
      </div>

      <video src={videoUrl} controls className="block w-full" />

      <div className="flex flex-wrap items-center gap-2 border-t border-neutral-100 px-3.5 py-3">
        <button
          type="button"
          onClick={() => decide.mutate({ action: 'approve' })}
          className="flex items-center gap-1 rounded bg-wechat-green px-3.5 py-1 text-[12px] text-white hover:bg-[#06AE56]"
        >
          <Check size={12} strokeWidth={2.5} /> 接受,发布
        </button>
        <button
          type="button"
          onClick={() =>
            decide.mutate({
              action: 'modify',
              payload: { target_step: 'video_compose', parameters: { tweak: 'subtitle' } },
            })
          }
          className="flex items-center gap-1 rounded border border-wechat-line bg-white px-3.5 py-1 text-[12px] text-wechat-fg hover:bg-neutral-50"
        >
          <Sliders size={12} strokeWidth={2} /> 微调
        </button>
        <button
          type="button"
          onClick={() => decide.mutate({ action: 'approve', payload: { user_choice: { cancel: true } } })}
          className="flex items-center gap-1 rounded border border-wechat-line bg-white px-3.5 py-1 text-[12px] text-red-600 hover:bg-red-50"
        >
          <X size={12} strokeWidth={2} /> 取消
        </button>
        <span className="ml-auto text-[10px] text-wechat-mute">
          回滚到第 N 步重做(中断 C)= V2
        </span>
      </div>
    </div>
  );
}
