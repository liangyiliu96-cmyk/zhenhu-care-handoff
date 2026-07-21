import type { DashboardResponse, DischargeCriteriaStatus } from '@/types/patient-dashboard';

export type DischargeTarget = 'monitoring' | 'orders' | 'records' | 'discharge' | 'handoff' | 'contact';

export interface DischargeBlockerDetail {
  key: string;
  label: string;
  met: boolean;
  target: DischargeTarget;
  action: string;
}

export interface DischargeWorkflowStep {
  key: string;
  label: string;
  description: string;
  done: boolean;
  failed?: boolean;
}

export function dischargeBlockerDetails(criteria?: DischargeCriteriaStatus | null): DischargeBlockerDetail[] {
  const details = Array.isArray(criteria?.details) ? criteria.details : [];
  if (details.length) {
    return details.map((item) => ({
      key: item.key,
      label: item.label || criterionLabel(item.key),
      met: item.met === true,
      target: normalizeTarget(item.category),
      action: item.action || targetAction(normalizeTarget(item.category)),
    }));
  }
  const unmet = Array.isArray(criteria?.unmet) ? criteria.unmet : [];
  return unmet.map((item) => {
    const key = String(item);
    const target = inferTarget(key);
    return { key, label: criterionLabel(key), met: false, target, action: targetAction(target) };
  });
}

export function dischargeWorkflowSteps(dashboard: DashboardResponse): DischargeWorkflowStep[] {
  const criteriaMet = dashboard.discharge_criteria_status?.all_met === true;
  const pendingType = dashboard.pending_review_type;
  const started = dischargeStarted(dashboard);
  const signed = ['signed', 'approved'].includes(dashboard.discharge_sign_status);
  const bridgeReady = dashboard.bridge_status === 'ok';
  const acknowledged = dashboard.handoff_acknowledged;
  const confirmed = dashboard.patient_confirmation_status === 'confirmed';
  return [
    { key: 'criteria', label: '出院条件评估', description: criteriaMet ? '全部条件已达标' : '仍有条件待处理', done: criteriaMet },
    { key: 'review', label: '临床卡点审核', description: pendingType && pendingType !== 'discharge_sign' ? `等待${reviewTypeLabel(pendingType)}` : '前置审核已完成', done: !pendingType || pendingType === 'discharge_sign' },
    { key: 'initiate', label: '发起出院流程', description: started ? '正式流程已启动' : '等待医生发起', done: started },
    { key: 'sign', label: '医生出院签字', description: signed ? '签字审核已完成' : pendingType === 'discharge_sign' ? '等待医生签字审核' : '尚未进入签字卡点', done: signed },
    {
      key: 'handoff',
      label: '交接签收',
      description: acknowledged ? '接收方已签收' : dashboard.bridge_error ? '协同病例创建失败，需先处理' : bridgeReady ? '等待接收方签收' : '等待创建协同病例',
      done: acknowledged,
      failed: Boolean(dashboard.bridge_error) && !bridgeReady,
    },
    { key: 'confirm', label: '患者回授确认', description: confirmed ? '患者理解确认完成' : '等待真实回授记录', done: confirmed },
  ];
}

export function operationalDischargeBlockers(dashboard: DashboardResponse): DischargeBlockerDetail[] {
  return (dashboard.discharge_blockers ?? [])
    .filter((item) => item.status !== 'resolved')
    .map((item, index) => {
    const target = normalizeTarget(item.target || inferTarget(`${item.reason} ${item.action}`));
    return {
      key: item.key || `legacy-${index}`,
      label: item.reason,
      met: false,
      target,
      action: item.action,
    };
  });
}

export function dischargeStarted(dashboard: DashboardResponse): boolean {
  const phase = String(dashboard.phase || '').toLowerCase();
  const signature = String(dashboard.discharge_sign_status || '').toLowerCase();
  return Boolean(
    dashboard.pending_review_type === 'discharge_sign'
    || ['signed', 'approved', 'completed'].includes(signature)
    || dashboard.bridge_status
    || ['discharge', 'handoff', 'confirm', 'completed', 'follow_up'].some((value) => phase.includes(value))
  );
}

export function reviewTypeLabel(value?: string): string {
  return ({
    doctor_confirm: '入院诊断审核',
    med_confirm: '用药调整审核',
    discharge_sign: '出院签字审核',
  } as Record<string, string>)[value || ''] || '临床审核';
}

function normalizeTarget(value: string): DischargeTarget {
  return ['monitoring', 'orders', 'records', 'discharge', 'handoff', 'contact'].includes(value) ? value as DischargeTarget : 'monitoring';
}

function inferTarget(key: string): DischargeTarget {
  const value = key.toLowerCase();
  if (/(medication|medicine|drug|titrated|med_|用药|药物)/.test(value)) return 'orders';
  if (/(contact|phone|mobile|telephone|联系电话|手机号|手机号码|联系信息)/.test(value)) return 'contact';
  if (/(handoff|acknowledg|bridge|交接|签收|协同病例)/.test(value)) return 'handoff';
  if (/(education|self_care|followup|follow_up|回授|随访|宣教|准备度)/.test(value)) return 'discharge';
  if (/(history|record|document|physical|exam|病史|文书|体格检查)/.test(value)) return 'records';
  return 'monitoring';
}

function targetAction(target: DischargeTarget): string {
  return {
    monitoring: '补充监测数据并重新评估',
    orders: '完成用药方案确认或相关审核',
    records: '补充必要临床记录',
    discharge: '完成出院宣教、随访或交接准备',
    handoff: '检查协同病例状态并完成接收方签收',
    contact: '取得患者授权并登记随访联系方式',
  }[target];
}

function criterionLabel(key: string): string {
  return ({
    criteria_missing: '尚未配置出院标准',
    bp_stable_24h: '血压稳定达到出院要求',
    vital_signs_stable: '生命体征保持稳定',
    stable_hemodynamics: '血流动力学稳定',
    self_care_education_done: '完成患者自我管理教育',
    medication_titrated: '用药方案已确认并达到出院要求',
    clinical_euvolemia_24h: '容量状态稳定达到出院要求',
  } as Record<string, string>)[key] || '待完成的出院条件';
}
