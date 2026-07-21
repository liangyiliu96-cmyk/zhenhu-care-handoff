export type DoctorCommandAction = 'discharge' | 'transfer' | 'consult' | 'hold' | 'resume';

export function commandNeedsTarget(action: DoctorCommandAction): boolean {
  return action === 'transfer' || action === 'consult';
}

export function commandRequiresReason(action: DoctorCommandAction): boolean {
  return action !== 'resume';
}

export function commandLabel(action: DoctorCommandAction): string {
  return {
    discharge: '发起出院',
    transfer: '转科',
    consult: '发起会诊',
    hold: '暂停流程',
    resume: '恢复流程',
  }[action];
}
