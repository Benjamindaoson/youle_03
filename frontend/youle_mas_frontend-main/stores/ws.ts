import { create } from 'zustand';

type State = {
  connected: boolean;
  lastEventId: string | null;
  setConnected: (v: boolean) => void;
  setLastEventId: (id: string) => void;
};

export const useWsStore = create<State>((set) => ({
  connected: false,
  lastEventId: null,
  setConnected: (v) => set({ connected: v }),
  setLastEventId: (id) => set({ lastEventId: id }),
}));
