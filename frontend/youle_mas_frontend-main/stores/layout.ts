import { create } from 'zustand';

interface LayoutState {
  desktopRightCollapsed: boolean;
  setDesktopRightCollapsed: (collapsed: boolean) => void;
}

export const useLayoutStore = create<LayoutState>((set) => ({
  desktopRightCollapsed: false,
  setDesktopRightCollapsed: (desktopRightCollapsed) => set({ desktopRightCollapsed }),
}));
