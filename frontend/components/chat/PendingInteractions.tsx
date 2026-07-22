'use client';

import { Check, X } from 'lucide-react';

import { ClarificationCard } from '@/components/chat/ClarificationCard';
import { useHitlDecision, useSendMessage } from '@/lib/api';
import { useHitlStore, type HITLGate } from '@/stores/hitl';

export function formatClarificationAnswer(answer: Record<string, string | number>): string {
  return Object.entries(answer)
    .map(([field, value]) => field + '：' + value)
    .join('；');
}

export function imageConfirmationDetails(gate: HITLGate) {
  if (gate.gate_type !== 'image_generation_confirmation') return null;
  const metadata = gate.preview_artifact?.metadata ?? {};
  const count = Number(metadata.image_count ?? 0);
  const unitCost = Number(metadata.estimated_cost_cny_per_image ?? 0);
  return {
    count,
    provider: String(metadata.provider ?? '火山方舟'),
    model: String(metadata.model ?? 'doubao-seedream-4-0-250828'),
    unitCost,
    totalCost: count * unitCost,
  };
}

export function approvalPayload(gate: HITLGate): Record<string, unknown> {
  const imageConfirmation = imageConfirmationDetails(gate);
  return imageConfirmation
    ? { user_choice: { confirmed_image_count: imageConfirmation.count } }
    : { user_choice: {} };
}

export function PendingInteractions({ conversationId }: { conversationId: string }) {
  const clarification = useHitlStore((state) => state.clarifications[conversationId]);
  const clearClarification = useHitlStore((state) => state.clearClarification);
  const gates = useHitlStore((state) =>
    state.queue.filter((gate) => gate.conversation_id === conversationId),
  );
  const send = useSendMessage(conversationId);

  if (!clarification && gates.length === 0) return null;

  return (
    <div className="space-y-2 border-t border-wechat-line bg-white px-4 py-3">
      {clarification && (
        <ClarificationCard
          data={clarification}
          disabled={send.isPending}
          onAnswer={(answer) => {
            send.mutate(formatClarificationAnswer(answer), {
              onSuccess: (result) => {
                const decision = (result as { decision?: string }).decision;
                if (decision !== 'clarification_required') clearClarification(conversationId);
              },
            });
          }}
        />
      )}
      {gates.map((gate) => <PendingGate key={gate.id} gate={gate} />)}
    </div>
  );
}

export function PendingGate({ gate }: { gate: HITLGate }) {
  const decide = useHitlDecision(gate.task_id, gate.id);
  const resolve = useHitlStore((state) => state.resolve);
  const confirmation = imageConfirmationDetails(gate);
  const label = confirmation
    ? '图片生成确认'
    : gate.gate_type === 'version_select'
      ? '脚本审核'
      : gate.gate_type === 'quality_review'
        ? '素材审核'
        : '成品终审';

  const submit = (action: 'approve' | 'cancel') => {
    decide.mutate(
      action === 'approve'
        ? { action, payload: approvalPayload(gate) }
        : { action, payload: { reason: confirmation ? '用户取消本次图片生成' : '用户取消' } },
      { onSuccess: () => resolve(gate.id) },
    );
  };

  return (
    <div className="max-w-[480px] rounded-md border border-wechat-line bg-white p-3 shadow-sm">
      <div className="text-[12px] font-semibold text-wechat-fg">{label}</div>
      {confirmation ? (
        <div className="mt-2 rounded bg-amber-50 p-2 text-[12px] text-wechat-fg">
          <p className="font-medium">确认生成 {confirmation.count} 张图片</p>
          <p className="mt-1 text-wechat-sub">
            {confirmation.provider} · {confirmation.model}
          </p>
          <p className="text-wechat-sub">
            预计 ¥{confirmation.unitCost.toFixed(2)}/张，合计 ¥{confirmation.totalCost.toFixed(2)}
          </p>
        </div>
      ) : gate.preview_artifact?.reference ? (
        <ArtifactPreview artifact={gate.preview_artifact} />
      ) : null}
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={decide.isPending}
          onClick={() => submit('approve')}
          className="flex items-center gap-1 rounded bg-wechat-green px-3 py-1 text-[12px] text-white disabled:opacity-50"
        >
          <Check size={12} /> {confirmation ? '确认并生成 ' + confirmation.count + ' 张' : '通过并继续'}
        </button>
        <button
          type="button"
          disabled={decide.isPending}
          onClick={() => submit('cancel')}
          className="flex items-center gap-1 rounded border border-wechat-line px-3 py-1 text-[12px] text-red-600 disabled:opacity-50"
        >
          <X size={12} /> {confirmation ? '取消本次生成' : '取消任务'}
        </button>
      </div>
      {decide.error instanceof Error && (
        <p className="mt-2 text-[11px] text-red-600">{decide.error.message}</p>
      )}
    </div>
  );
}

function ArtifactPreview({ artifact }: { artifact: NonNullable<HITLGate['preview_artifact']> }) {
  const canOpen = /^https?:\/\//.test(artifact.reference ?? '');
  if (canOpen && artifact.type === 'video') {
    return <video src={artifact.reference} controls className="mt-2 max-h-64 w-full rounded bg-black" />;
  }
  if (canOpen && artifact.type === 'audio') {
    return <audio src={artifact.reference} controls className="mt-2 w-full" />;
  }
  if (canOpen && artifact.type === 'image') {
    // Remote signed artifact URLs are not statically known to Next's image optimizer.
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={artifact.reference} alt="待审核成果" className="mt-2 max-h-64 rounded object-contain" />;
  }
  return (
    <div className="mt-1 break-all rounded bg-neutral-50 p-2 text-[10px] text-wechat-sub">
      {artifact.reference}
    </div>
  );
}
