import { ThemeProvider } from '@mui/material';
import { useEffect, useMemo, type ReactNode } from 'react';

import { useThemeStore } from '@/stores/theme-store';
import { createAppTheme } from '@/theme/app-theme';

interface AppThemeProviderProps {
  children: ReactNode;
}

export default function AppThemeProvider({ children }: AppThemeProviderProps) {
  const mode = useThemeStore((state) => state.mode);
  const theme = useMemo(() => createAppTheme(mode), [mode]);

  useEffect(() => {
    document.documentElement.dataset.colorMode = mode;
  }, [mode]);

  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}
