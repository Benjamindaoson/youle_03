import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

type User = { id: string; phone: string; nickname: string };

type State = {
  user: User | null;
  token: string | null;
  setAuth: (user: User, token: string) => void;
  logout: () => void;
};

export const useUserStore = create<State>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      setAuth: (user, token) => set({ user, token }),
      logout: () => set({ user: null, token: null }),
    }),
    {
      name: 'haole.auth',
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
