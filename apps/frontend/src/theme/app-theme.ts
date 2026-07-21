import { alpha, createTheme, type PaletteMode } from '@mui/material/styles';

const primary = '#0B6472';
const ink = '#14282C';
const muted = '#5F7074';

export function createAppTheme(mode: PaletteMode) {
  const isDark = mode === 'dark';
  const palette = isDark
    ? {
      mode,
      primary: { main: '#56B6C2', dark: '#2D8895', light: '#153B42', contrastText: '#0D1C1F' },
      info: { main: '#69BDD0', dark: '#3B8DA0', light: '#143840' },
      success: { main: '#64B992', dark: '#3F916F', light: '#16382C' },
      warning: { main: '#E4AD62', dark: '#B87A29', light: '#443016' },
      error: { main: '#E68686', dark: '#BC5555', light: '#442326' },
      background: { default: '#152022', paper: '#1C2A2D' },
      text: { primary: '#E2ECE9', secondary: '#AABCB9' },
      divider: '#344548',
    }
    : {
      mode,
      primary: { main: primary, dark: '#084B56', light: '#DDEFF0', contrastText: '#FFFFFF' },
      info: { main: '#16758B', dark: '#0C596B', light: '#E2F0F4' },
      success: { main: '#258463', dark: '#176246', light: '#E3F3EC' },
      warning: { main: '#A86514', dark: '#7A470C', light: '#FFF1DC' },
      error: { main: '#B63B3B', dark: '#8A2929', light: '#FDEAEA' },
      background: { default: '#F3F6F5', paper: '#FFFFFF' },
      text: { primary: ink, secondary: muted },
      divider: '#DCE5E3',
    };

  return createTheme({
  palette,
  shape: { borderRadius: 8 },
  typography: {
    fontFamily: 'var(--font-body)',
    h4: { fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '1.85rem', lineHeight: 1.22 },
    h5: { fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '1.5rem', lineHeight: 1.28 },
    h6: { fontWeight: 650, fontSize: '1.125rem', lineHeight: 1.35 },
    subtitle1: { fontWeight: 600 },
    subtitle2: { fontWeight: 600, fontSize: '0.875rem' },
    button: { fontWeight: 600, fontSize: '0.8125rem', lineHeight: 1.25 },
    overline: { fontSize: '0.6875rem', fontWeight: 700, lineHeight: 1.6, letterSpacing: 0 },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        html: { backgroundColor: palette.background.default },
        body: { backgroundColor: palette.background.default, color: palette.text.primary },
        '::selection': { backgroundColor: alpha(primary, 0.18) },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { borderRadius: 7, textTransform: 'none', minHeight: 36, paddingInline: 12, fontWeight: 600 },
        sizeSmall: { minHeight: 36, paddingInline: 10 },
        sizeLarge: { minHeight: 46, paddingInline: 18 },
        containedPrimary: { boxShadow: `0 1px 2px ${alpha('#063D45', 0.18)}` },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: { borderRadius: 8, borderColor: palette.divider, boxShadow: isDark ? '0 1px 2px rgba(0, 0, 0, 0.22)' : '0 1px 2px rgba(20, 40, 44, 0.035)' },
      },
    },
    MuiPaper: {
      styleOverrides: { root: { backgroundImage: 'none' } },
    },
    MuiChip: {
      styleOverrides: {
        root: { borderRadius: 6, fontWeight: 600 },
        sizeSmall: { height: 24, fontSize: '0.6875rem' },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: { transition: 'background-color 140ms ease, color 140ms ease' },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: { borderRadius: 7 },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: { borderRadius: 6, fontSize: '0.75rem' },
      },
    },
    MuiTabs: {
      styleOverrides: { indicator: { height: 3, borderRadius: '3px 3px 0 0' } },
    },
    MuiTab: {
      styleOverrides: { root: { minHeight: 44, textTransform: 'none', fontWeight: 600, color: muted, '&.Mui-selected': { color: ink } } },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: { borderRadius: 7, backgroundColor: palette.background.paper, '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: palette.primary.main, borderWidth: 1 } },
        sizeSmall: { minHeight: 36 },
        notchedOutline: { borderColor: isDark ? '#4A5D5E' : '#CCD9D6' },
      },
    },
    MuiAlert: {
      styleOverrides: { root: { borderRadius: 8, alignItems: 'center' } },
    },
  },
  });
}

export const appTheme = createAppTheme('light');
