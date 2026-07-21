import { create } from 'zustand';

type State = {
  connected: boolean;
  lastEventId: string | null;
  error: string | null;
  setConnected: (v: boolean) => void;
  setLastEventId: (id: string) => void;
  setError: (error: string | null) => void;
};

export const useWsStore = create<State>((set) => ({
  connected: false,
  lastEventId: null,
  error: null,
  setConnected: (v) => set({ connected: v, ...(v ? { error: null } : {}) }),
  setLastEventId: (id) => set({ lastEventId: id }),
  setError: (error) => set({ error }),
}));
