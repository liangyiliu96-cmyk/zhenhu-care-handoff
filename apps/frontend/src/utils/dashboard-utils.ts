type Readiness = { score?: unknown; met_count?: unknown; total_count?: unknown } | undefined;

export function readinessPercent(readiness?: Readiness): number | null {
  if (!readiness) return null;
  const score = Number(readiness.score);
  if (Number.isFinite(score)) return Math.max(0, Math.min(100, Math.round(score)));

  const met = Number(readiness.met_count);
  const total = Number(readiness.total_count);
  if (Number.isFinite(met) && Number.isFinite(total) && total > 0) {
    return Math.max(0, Math.min(100, Math.round((met / total) * 100)));
  }
  return null;
}

export function scoreTone(score: number | null | undefined): 'error' | 'warning' | 'success' | 'default' {
  if (score == null) return 'default';
  if (score >= 7) return 'error';
  if (score >= 5) return 'warning';
  return 'success';
}

export function displayValue(value: unknown, fallback = '未记录'): string {
  if (value == null || value === '') return fallback;
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  if (Array.isArray(value)) return value.map((item) => displayValue(item, '')).filter(Boolean).join('；') || fallback;
  return Object.entries(value as Record<string, unknown>).map(([key, item]) => {
    const text = displayValue(item, '');
    return text ? `${key}: ${text}` : '';
  }).filter(Boolean).join('；') || fallback;
}
