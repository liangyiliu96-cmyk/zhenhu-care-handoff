export type MedicationOrderStatus = 'draft' | 'active' | 'held' | 'discontinued' | 'cancelled';
export type MedicationTransitionStatus = Exclude<MedicationOrderStatus, 'draft'>;
export type InvestigationTransitionStatus = 'scheduled' | 'completed' | 'cancelled';
export type MdtDecision = 'accepted' | 'deferred' | 'declined';
export type FollowUpStatus = 'completed' | 'cancelled';

export function medicationTransitions(status: string): Array<{ status: MedicationTransitionStatus; label: string }> {
  if (status === 'draft') return [{ status: 'active', label: '激活医嘱' }, { status: 'cancelled', label: '取消医嘱' }];
  if (status === 'active') return [{ status: 'held', label: '暂停医嘱' }, { status: 'discontinued', label: '停用医嘱' }];
  if (status === 'held') return [{ status: 'active', label: '恢复医嘱' }, { status: 'discontinued', label: '停用医嘱' }];
  return [];
}

export function investigationTransitions(status: string): Array<{ status: InvestigationTransitionStatus; label: string }> {
  if (status === 'ordered') return [{ status: 'scheduled', label: '安排检查' }, { status: 'completed', label: '标记完成' }, { status: 'cancelled', label: '取消检查' }];
  if (status === 'scheduled') return [{ status: 'completed', label: '标记完成' }, { status: 'cancelled', label: '取消检查' }];
  return [];
}

export function lifecycleStatusLabel(status: unknown): string {
  const normalized = String(status || 'unknown');
  return ({ draft: '草稿', active: '执行中', held: '已暂停', discontinued: '已停用', ordered: '已开立', scheduled: '已安排', cancelled: '已取消', requested: '待处理', resolved: '已处理', pending: '待执行', completed: '已完成' } as Record<string, string>)[normalized] || normalized;
}

export function mdtDecisionLabel(decision: MdtDecision): string {
  return ({ accepted: '采纳', deferred: '暂缓', declined: '不采纳' } as Record<MdtDecision, string>)[decision];
}
