import { create } from 'zustand';

export type AppColorMode = 'light' | 'dark';

const storageKey = 'zhenhu_color_mode';

function readInitialMode(): AppColorMode {
  if (typeof window === 'undefined') return 'light';
  const stored = window.localStorage.getItem(storageKey);
  if (stored === 'light' || stored === 'dark') return stored;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function persistMode(mode: AppColorMode) {
  if (typeof window !== 'undefined') window.localStorage.setItem(storageKey, mode);
}

interface ThemeState {
  mode: AppColorMode;
  setMode: (mode: AppColorMode) => void;
  toggleMode: () => void;
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  mode: readInitialMode(),
  setMode: (mode) => {
    persistMode(mode);
    set({ mode });
  },
  toggleMode: () => {
    const mode = get().mode === 'light' ? 'dark' : 'light';
    persistMode(mode);
    set({ mode });
  },
}));

export { storageKey as themeStorageKey };
