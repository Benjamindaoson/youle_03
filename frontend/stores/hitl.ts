import { create } from 'zustand';
import type { components } from '@/lib/api-types';

type APIHITLGate = components['schemas']['HITLGateOut'];

export type HITLGate = Omit<APIHITLGate, 'gate_type'> & {
  gate_type: 'version_select' | 'quality_review' | 'final_approval' | 'image_generation_confirmation';
  conversation_id?: string;
  preview_artifact?: {
    type?: string;
    reference?: string;
    metadata?: Record<string, unknown>;
  };
};

export type ClarificationPrompt = {
  field: string;
  form: 'single_select' | 'multi_select' | 'image_compare' | 'version_compare' | 'image_upload';
  question: string;
  options: unknown[];
  default?: unknown;
  round_number?: number;
  total_missing?: number;
};

type State = {
  queue: HITLGate[];
  clarifications: Record<string, ClarificationPrompt>;
  push: (g: HITLGate) => void;
  resolve: (id: string) => void;
  setClarification: (conversationId: string, prompt: ClarificationPrompt) => void;
  clearClarification: (conversationId: string) => void;
};

export const useHitlStore = create<State>((set) => ({
  queue: [],
  clarifications: {},
  push: (g) => set((s) => ({
    queue: [...s.queue.filter((item) => item.id !== g.id), g],
  })),
  resolve: (id) => set((s) => ({ queue: s.queue.filter((x) => x.id !== id) })),
  setClarification: (conversationId, prompt) => set((s) => ({
    clarifications: { ...s.clarifications, [conversationId]: prompt },
  })),
  clearClarification: (conversationId) => set((s) => {
    const clarifications = { ...s.clarifications };
    delete clarifications[conversationId];
    return { clarifications };
  }),
}));
