import type { LabTrendsResponse } from '@/types/patient-dashboard';

type UnknownRecord = Record<string, unknown>;

export interface MedicationDetail {
  name: string;
  schedule: string;
  context: string;
  metadata: string;
}

export interface LabTrendMetric {
  name: string;
  unit: string;
  refRange: string | null;
  latest: number;
  min: number;
  max: number;
  abnormalCount: number;
  totalCount: number;
  values: Array<{ index: number; value: number | null; isAbnormal: boolean }>;
}

export function medicationDetail(record: UnknownRecord): MedicationDetail {
  const name = text(record.medication) || text(record.drug) || text(record.name) || '未命名用药记录';
  const schedule = [text(record.dose), text(record.frequency), text(record.route)].filter(Boolean).join(' · ') || '未提供剂量或频次';
  const context = [text(record.indication), text(record.reason), text(record.action), text(record.type)].filter(Boolean).join(' · ') || '未提供调整原因';
  const metadata = [text(record.status), text(record.source)].filter(Boolean).join(' · ');
  return { name, schedule, context, metadata };
}

export function labTrendMetrics(response?: LabTrendsResponse): LabTrendMetric[] {
  if (!response) return [];
  return Object.entries(response.lab_trends)
    .map(([name, trend]) => ({
      name: clinicalMetricLabel(name),
      unit: trend.unit,
      refRange: trend.ref_range ?? null,
      latest: trend.latest,
      min: trend.min,
      max: trend.max,
      abnormalCount: trend.abnormal_count,
      totalCount: trend.total_count,
      values: trend.values.map((item, index) => ({ index: item.index ?? index + 1, value: item.value, isAbnormal: item.is_abnormal })),
    }))
    .sort((left, right) => right.abnormalCount - left.abnormalCount || left.name.localeCompare(right.name, 'zh-CN'));
}

export function clinicalMetricLabel(value: string): string {
  return ({
    creatinine: '肌酐',
    potassium: '血钾',
    sodium: '血钠',
    glucose: '血糖',
    hemoglobin: '血红蛋白',
    platelet: '血小板',
    wbc: '白细胞计数',
    crp: 'C 反应蛋白',
    alt: '丙氨酸氨基转移酶',
    ast: '天门冬氨酸氨基转移酶',
  } as Record<string, string>)[value.toLowerCase()] || value;
}

function text(value: unknown): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value).trim() : '';
}
