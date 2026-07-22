'use client';

import { Check, X } from 'lucide-react';

import { ClarificationCard } from '@/components/chat/ClarificationCard';
import { useHitlDecision, useSendMessage } from '@/lib/api';
import { useHitlStore, type HITLGate } from '@/stores/hitl';

export function formatClarificationAnswer(answer: Record<string, string | number>): string {
  return Object.entries(answer)
    .map(([field, value]) => `${field}：${value}`)
    .join('；');
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

function PendingGate({ gate }: { gate: HITLGate }) {
  const decide = useHitlDecision(gate.task_id, gate.id);
  const resolve = useHitlStore((state) => state.resolve);
  const label = gate.gate_type === 'version_select'
    ? '脚本审核'
    : gate.gate_type === 'quality_review'
      ? '素材审核'
      : '成品终审';

  const submit = (action: 'approve' | 'cancel') => {
    decide.mutate(
      action === 'approve'
        ? { action, payload: { user_choice: {} } }
        : { action, payload: { reason: '用户取消' } },
      { onSuccess: () => resolve(gate.id) },
    );
  };

  return (
    <div className="max-w-[480px] rounded-md border border-wechat-line bg-white p-3 shadow-sm">
      <div className="text-[12px] font-semibold text-wechat-fg">{label}</div>
      {gate.preview_artifact?.reference && (
        <ArtifactPreview artifact={gate.preview_artifact} />
      )}
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={decide.isPending}
          onClick={() => submit('approve')}
          className="flex items-center gap-1 rounded bg-wechat-green px-3 py-1 text-[12px] text-white disabled:opacity-50"
        >
          <Check size={12} /> 通过并继续
        </button>
        <button
          type="button"
          disabled={decide.isPending}
          onClick={() => submit('cancel')}
          className="flex items-center gap-1 rounded border border-wechat-line px-3 py-1 text-[12px] text-red-600 disabled:opacity-50"
        >
          <X size={12} /> 取消任务
        </button>
      </div>
      {decide.error instanceof Error && (
        <p className="mt-2 text-[11px] text-red-600">{decide.error.message}</p>
      )}
    </div>
  );
}

function ArtifactPreview({ artifact }: {
  artifact: NonNullable<HITLGate['preview_artifact']>;
}) {
  const canOpen = /^https?:\/\//.test(artifact.reference);
  if (canOpen && artifact.type === 'video') {
    return <video src={artifact.reference} controls className="mt-2 max-h-64 w-full rounded bg-black" />;
  }
  if (canOpen && artifact.type === 'audio') {
    return <audio src={artifact.reference} controls className="mt-2 w-full" />;
  }
  if (canOpen && artifact.type === 'image') {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={artifact.reference} alt="待审核成果" className="mt-2 max-h-64 rounded object-contain" />;
  }
  return (
    <div className="mt-1 break-all rounded bg-neutral-50 p-2 text-[10px] text-wechat-sub">
      {artifact.reference}
    </div>
  );
}
