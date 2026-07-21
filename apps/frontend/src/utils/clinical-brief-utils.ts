export function formatBriefValue(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string') return localizeClinicalText(value);
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(formatBriefValue).filter(Boolean).join('；');
  if (typeof value === 'object') return Object.entries(value as Record<string, unknown>).map(([key, item]) => { const text = formatBriefValue(item); return text ? `${localizeClinicalText(key)}: ${text}` : ''; }).filter(Boolean).join('；');
  return String(value);
}

export function localizeClinicalText(value: string): string {
  const labels: Record<string, string> = {
    creatinine: '肌酐',
    potassium: '血钾',
    sodium: '血钠',
    glucose: '血糖',
    hemoglobin: '血红蛋白',
    platelet: '血小板',
    med_confirm: '用药调整审核',
    ddx_review: '鉴别诊断审核',
    doctor_confirm: '医生确认',
    discharge_sign: '出院签署',
  };
  return Object.entries(labels).reduce((text, [key, label]) => text.replaceAll(key, label), value);
}
