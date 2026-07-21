/**
 * 设计 Token → CSS 变量 / Tailwind 常量
 * 来源: 设计文档 §4.2 (OKLCH 色彩、4pt 间距、字体系统)
 */

export const tokens = {
  color: {
    surface: {
      page:    'oklch(97% 0.005 250)',
      card:    'oklch(100% 0 0)',
      subtle:  'oklch(95% 0.008 250)',
      elevated:'oklch(100% 0 0)',
    },
    text: {
      primary:   'oklch(15% 0.01 250)',
      secondary: 'oklch(40% 0.01 250)',
      disabled:  'oklch(65% 0.005 250)',
    },
    border: {
      default: 'oklch(90% 0.005 250)',
      subtle:  'oklch(95% 0.003 250)',
    },
    accent: {
      info:     'oklch(55% 0.12 280)',
      success:  'oklch(55% 0.14 160)',
      warning:  'oklch(65% 0.16 80)',
      danger:   'oklch(52% 0.22 25)',
    },
    chart: {
      normal:   'oklch(55% 0.18 255)',
      warning:  'oklch(65% 0.16 80)',
      danger:   'oklch(52% 0.22 25)',
      success:  'oklch(55% 0.14 160)',
    },
  },
  space: {
    xs:  '4px',
    sm:  '8px',
    md:  '12px',
    lg:  '16px',
    xl:  '24px',
    '2xl':'32px',
    '3xl':'48px',
    '4xl':'64px',
  },
  radius: {
    none:   0,
    card:   '6px',
    button: '6px',
    full:   '9999px',
  },
  font: {
    display: "'Source Serif 4', 'Noto Serif SC', serif",
    body:    "'IBM Plex Sans', 'Noto Sans SC', -apple-system, sans-serif",
    mono:    "'JetBrains Mono', 'SF Mono', monospace",
  },
  fontSize: {
    xs:   '0.75rem',
    sm:   '0.875rem',
    base: '1rem',
    lg:   '1.25rem',
    xl:   '1.5rem',
    '2xl':'2rem',
  },
  shadow: {
    xs: '0 1px 2px rgba(0,0,0,0.03)',
    sm: '0 1px 3px rgba(0,0,0,0.04), 0 2px 8px rgba(0,0,0,0.04)',
    md: '0 2px 4px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.06)',
  },
} as const;
