import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { themeStorageKey, useThemeStore } from './theme-store';

describe('theme store', () => {
  beforeEach(() => {
    const values = new Map<string, string>();
    vi.stubGlobal('window', {
      localStorage: {
        getItem: (key: string) => values.get(key) ?? null,
        setItem: (key: string, value: string) => values.set(key, value),
        clear: () => values.clear(),
      },
      matchMedia: () => ({ matches: false }),
    });
    useThemeStore.setState({ mode: 'light' });
  });

  afterEach(() => vi.unstubAllGlobals());

  it('toggles the color mode and persists the selection', () => {
    useThemeStore.getState().toggleMode();
    expect(useThemeStore.getState().mode).toBe('dark');
    expect(window.localStorage.getItem(themeStorageKey)).toBe('dark');
  });

  it('sets an explicit mode and persists it', () => {
    useThemeStore.getState().setMode('light');
    expect(useThemeStore.getState().mode).toBe('light');
    expect(window.localStorage.getItem(themeStorageKey)).toBe('light');
  });
});
