import { create } from 'zustand';

type Step = {
  step_id: string;
  agent_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'pending_external';
  streaming_chunks?: string;
  artifact?: { type: string; reference: string };
};

type State = {
  currentTaskId: string | null;
  currentStatus: 'idle' | 'running' | 'completed' | 'failed';
  currentSteps: Step[];
  start: (taskId: string) => void;
  finish: (status: 'completed' | 'failed') => void;
  upsertStep: (step: Step) => void;
  appendChunk: (stepId: string, chunk: string) => void;
  reset: () => void;
};

export const useTaskStore = create<State>((set) => ({
  currentTaskId: null,
  currentStatus: 'idle',
  currentSteps: [],
  start: (taskId) => set({ currentTaskId: taskId, currentStatus: 'running', currentSteps: [] }),
  finish: (status) => set({ currentStatus: status }),
  upsertStep: (step) =>
    set((s) => ({
      currentSteps: s.currentSteps.find((x) => x.step_id === step.step_id)
        ? s.currentSteps.map((x) => (x.step_id === step.step_id ? { ...x, ...step } : x))
        : [...s.currentSteps, step],
    })),
  appendChunk: (stepId, chunk) =>
    set((s) => ({
      currentSteps: s.currentSteps.map((x) =>
        x.step_id === stepId ? { ...x, streaming_chunks: (x.streaming_chunks ?? '') + chunk } : x,
      ),
    })),
  reset: () => set({ currentTaskId: null, currentStatus: 'idle', currentSteps: [] }),
}));
