export type CareAction = 'medication' | 'investigation' | 'mdt' | 'education' | 'followup';

export function canSubmitCareAction(action: CareAction, fields: Record<string, string>): boolean {
  if (action === 'medication') return Boolean(fields.medication?.trim() && fields.dose?.trim() && fields.frequency?.trim());
  if (action === 'investigation') return Boolean(fields.testName?.trim() && fields.reason?.trim());
  if (action === 'mdt') return Boolean(fields.reason?.trim() && fields.specialties?.split(',').some((item) => item.trim()));
  if (action === 'education') return Boolean(fields.topic?.trim() && fields.recipient?.trim());
  return Boolean(fields.title?.trim() && fields.dueAt?.trim());
}

export function careActionLabel(action: CareAction): string {
  return { medication: '新增医嘱', investigation: '开立检查', mdt: '发起 MDT', education: '记录宣教', followup: '创建随访' }[action];
}
