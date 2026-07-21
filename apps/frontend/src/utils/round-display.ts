import type { RoundRecord } from '@/types/patient-dashboard';

export type RoundSection = 'subjective' | 'objective' | 'assessment' | 'plan';

export interface RoundDisplayRow {
  key: string;
  label: string;
  value: string;
}

const FIELD_LABELS: Record<string, string> = {
  chief_complaint: '本次主诉',
  symptoms_since_last_round: '查房间症状变化',
  vital_signs_latest: '最新生命体征',
  vital_signs_trend: '生命体征趋势',
  lab_count: '已纳入检验结果',
  med_adjust_count: '用药调整次数',
  risk_level: '当前风险等级',
  stability: '病情稳定性',
  response_to_treatment: '治疗反应',
  key_findings: '关键临床发现',
  continue_monitoring: '继续监测',
  consider_discharge: '评估出院条件',
  next_labs: '下一步检验计划',
  heart_rate: '心率',
  respiratory_rate: '呼吸频率',
  spo2: '血氧饱和度',
  temperature: '体温',
  systolic_mmhg: '收缩压',
  diastolic_mmhg: '舒张压',
  blood_pressure: '血压',
  bp: '血压',
  blood_glucose: '血糖',
  weight_kg: '体重',
  height_cm: '身高',
  gcs: '格拉斯哥昏迷评分',
  timestamp: '记录时间',
  round: '查房轮次',
};

const VALUE_LABELS: Record<string, string> = {
  stable: '稳定',
  unstable: '有波动，需继续评估',
  low: '低风险',
  medium: '中风险',
  high: '高风险',
  critical: '危重',
  routine: '常规',
  urgent: '紧急',
  emergent: '急救',
};

const BOOLEAN_LABELS: Record<string, [string, string]> = {
  continue_monitoring: ['继续', '暂不继续'],
  consider_discharge: ['可进入出院条件评估', '暂不具备出院评估条件'],
};

export function roundSectionRows(section: RoundSection, value: unknown): RoundDisplayRow[] {
  if (value == null || value === '') return [];
  if (!isRecord(value)) return [{ key: section, label: sectionLabel(section), value: formatRoundValue(value) }];

  return Object.entries(value).map(([key, item]) => ({
    key,
    label: FIELD_LABELS[key] ?? '补充临床信息',
    value: formatRoundValue(item, key),
  }));
}

export function formatRoundValue(value: unknown, field?: string): string {
  if (value == null || value === '') return '未记录';
  if (typeof value === 'boolean') {
    const labels = field ? BOOLEAN_LABELS[field] : undefined;
    return labels ? labels[value ? 0 : 1] : value ? '是' : '否';
  }
  if (typeof value === 'number') return String(value);
  if (typeof value === 'string') return VALUE_LABELS[value.toLowerCase()] ?? value;
  if (Array.isArray(value)) return value.length ? value.map((item) => formatRoundValue(item)).join('；') : '无';
  if (isRecord(value)) {
    const entries = Object.entries(value).filter(([, item]) => item != null && item !== '');
    if (!entries.length) return '未记录';
    return entries.map(([key, item]) => `${FIELD_LABELS[key] ?? '临床指标'}：${formatRoundValue(item, key)}`).join('；');
  }
  return String(value);
}

export function roundGenerationLabel(record?: RoundRecord): string {
  if (record?.generation_source === 'llm_assisted') return 'Agent + LLM 辅助生成';
  if (record?.generation_source === 'rule_based') return 'Agent 规则摘要';
  return 'Agent 查房摘要';
}

export function roundReviewLabel(record?: RoundRecord): string {
  return record?.review_status === 'reviewed' ? '医生已核对' : '待医生核对';
}

export function clinicalPhaseLabel(value?: string): string {
  return ({
    admission: '入院评估',
    daily_round: '日常查房',
    monitoring: '住院监测',
    medication: '用药管理',
    lab_review: '检验审核',
    review: '临床审核',
    discharge: '出院准备',
    handoff: '出院交接',
    confirm: '患者确认',
    completed: '流程完成',
  } as Record<string, string>)[String(value || '').toLowerCase()] || value || '阶段未记录';
}

export function latestRound(rounds?: { rounds: RoundRecord[]; latest_soap?: RoundRecord }): RoundRecord | undefined {
  if (rounds?.latest_soap && Object.keys(rounds.latest_soap).length) return rounds.latest_soap;
  return rounds?.rounds.at(-1);
}

function sectionLabel(section: RoundSection) {
  return { subjective: '主观情况', objective: '客观数据', assessment: '临床评估', plan: '诊疗计划' }[section];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
