import { create } from 'zustand';

type HITLGate = {
  id: string;
  task_id: string;
  step_id: string;
  gate_type: 'version_select' | 'quality_review' | 'final_approval';
  preview_artifact?: { type: string; reference: string };
};

type State = {
  queue: HITLGate[];
  push: (g: HITLGate) => void;
  resolve: (id: string) => void;
};

export const useHitlStore = create<State>((set) => ({
  queue: [],
  push: (g) => set((s) => ({ queue: [...s.queue, g] })),
  resolve: (id) => set((s) => ({ queue: s.queue.filter((x) => x.id !== id) })),
}));
