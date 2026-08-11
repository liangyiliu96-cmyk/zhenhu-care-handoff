import type { DashboardResponse, RoundRecord, RoundsResponse } from '@/types/patient-dashboard';
import { dischargeBlockerDetails, dischargeStarted, operationalDischargeBlockers, reviewTypeLabel } from '@/utils/discharge-workflow';

export type PatientActionTarget = 'review' | 'rounds' | 'monitoring' | 'orders' | 'records' | 'discharge' | 'handoff' | 'contact';

export interface PatientActionPlanItem {
  key: string;
  title: string;
  detail: string;
  kind: 'safety' | 'review' | 'data' | 'discharge' | 'routine';
  completion: string;
  target: PatientActionTarget;
  urgency: 'high' | 'medium' | 'low';
  focus?: string;
}

export function patientActionPlan(dashboard: DashboardResponse, rounds?: RoundsResponse): PatientActionPlanItem[] {
  const actions: PatientActionPlanItem[] = [];
  const alerts = dashboard.complication_alerts.filter(Boolean);
  const latestRound = getLatestRound(rounds);
  const started = dischargeStarted(dashboard);
  const blockers = [
    ...(started ? dischargeBlockerDetails(dashboard.discharge_criteria_status).filter((item) => !item.met) : []),
    ...operationalDischargeBlockers(dashboard),
  ];

  if (alerts.length) {
    actions.push({
      key: 'active-alerts',
      title: '先核对未关闭的临床告警',
      detail: alerts.slice(0, 2).join('；'),
      kind: 'safety',
      completion: '相关告警已完成核对并关闭，或明确记录后续处置计划',
      target: 'monitoring',
      urgency: 'high',
    });
  }

  if (dashboard.pending_review_type) {
    actions.push({
      key: `review-${dashboard.pending_review_type}`,
      title: `完成${reviewTypeLabel(dashboard.pending_review_type)}`,
      detail: '审核提交后，系统将根据最新状态继续后续临床流程。',
      kind: 'review',
      completion: '待审核状态消失，并在操作记录中留下审核结果',
      target: 'review',
      urgency: 'high',
    });
  }

  if (!latestRound) {
    actions.push({
      key: 'first-round',
      title: '生成并核对本轮查房摘要',
      detail: '基于当前病史、体征、检验、用药和病程形成可编辑的 SOAP 草稿。',
      kind: 'data',
      completion: '形成查房记录，并由医生完成核对或修改后保存',
      target: 'rounds',
      urgency: 'medium',
    });
  } else if (latestRound.review_status !== 'reviewed') {
    actions.push({
      key: `review-round-${latestRound.round_number ?? 'latest'}`,
      title: '核对最新查房摘要',
      detail: '医生核对后可保留修订并进入后续医嘱、监测或出院决策。',
      kind: 'review',
      completion: '查房记录状态变为已核对，并保留必要的医生修订',
      target: 'rounds',
      urgency: 'medium',
    });
  }

  if (blockers.length) {
    const blocker = blockers[0];
    actions.push({
      key: `blocker-${blocker.key}`,
      title: `处理：${blocker.label}`,
      detail: blocker.action,
      kind: 'discharge',
      completion: '回到患者概览确认该阻塞项消失或变为已完成',
      target: blocker.target,
      urgency: 'medium',
      focus: blocker.key,
    });
  } else if (dashboard.discharge_criteria_status?.all_met === true && !started) {
    actions.push({
      key: 'initiate-discharge',
      title: '发起正式出院流程',
      detail: '发起后将创建出院签字审核与后续交接闭环，仍需医生确认。',
      kind: 'discharge',
      completion: '出院流程状态进入进行中，并出现对应审核卡点',
      target: 'discharge',
      urgency: 'low',
    });
  }

  if (!actions.some((action) => action.target === 'monitoring') && !started) {
    actions.push({
      key: 'routine-monitoring',
      title: '继续住院监测与临床记录',
      detail: '录入新的体征、检验或护理观察后，系统会重新评估风险与出院准备度。',
      kind: 'routine',
      completion: '最新观察数据已保存，患者状态更新时间得到刷新',
      target: 'monitoring',
      urgency: 'low',
    });
  }

  return uniqueActions(actions).slice(0, 3);
}

function getLatestRound(rounds?: RoundsResponse): RoundRecord | undefined {
  return rounds?.latest_soap ?? rounds?.rounds?.[rounds.rounds.length - 1];
}

function uniqueActions(actions: PatientActionPlanItem[]): PatientActionPlanItem[] {
  const seen = new Set<string>();
  return actions.filter((action) => {
    const key = action.target === 'review' ? action.key : action.target;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
