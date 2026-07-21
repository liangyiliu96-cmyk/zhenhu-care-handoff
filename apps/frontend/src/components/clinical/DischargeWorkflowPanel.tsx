import { Alert, Box, Button, Card, Chip, CircularProgress, Typography } from '@mui/material';
import { AlertTriangle, ArrowRight, CheckCircle2, Circle, ClipboardCheck, LockKeyhole, Route } from 'lucide-react';

import type { DashboardResponse } from '@/types/patient-dashboard';
import { dischargeBlockerDetails, dischargeStarted, dischargeWorkflowSteps, operationalDischargeBlockers, reviewTypeLabel, type DischargeBlockerDetail, type DischargeTarget } from '@/utils/discharge-workflow';

interface DischargeWorkflowPanelProps {
  dashboard: DashboardResponse;
  busy?: boolean;
  error?: string;
  onNavigateTarget: (blocker: DischargeBlockerDetail) => void;
  onOpenReview: (reviewType: string) => void;
  onOpenDischarge?: () => void;
  onOpenEducation?: () => void;
  onReturnToWorkbench?: () => void;
  onInitiate?: () => void;
}

export default function DischargeWorkflowPanel({ dashboard, busy = false, error, onNavigateTarget, onOpenReview, onOpenDischarge, onOpenEducation, onReturnToWorkbench, onInitiate }: DischargeWorkflowPanelProps) {
  const steps = dischargeWorkflowSteps(dashboard);
  const started = dischargeStarted(dashboard);
  const criteriaBlockers = started
    ? dischargeBlockerDetails(dashboard.discharge_criteria_status).filter((item) => !item.met)
    : [];
  const blockers = [
    ...criteriaBlockers,
    ...operationalDischargeBlockers(dashboard),
  ].filter((item, index, items) => items.findIndex((candidate) => candidate.label === item.label) === index);
  const pendingReviewType = dashboard.pending_review_type;
  const signed = ['signed', 'approved'].includes(dashboard.discharge_sign_status);
  const activeIndex = Math.max(0, steps.findIndex((step) => !step.done));
  const failedIndex = steps.findIndex((step) => step.failed);

  const nextAction = pendingReviewType
    ? { title: `完成${reviewTypeLabel(pendingReviewType)}`, detail: '审核提交后系统会按原 Agent 链继续运行，并刷新下一卡点。', label: '去审核', onClick: () => onOpenReview(pendingReviewType) }
    : blockers.length
      ? { title: '处理出院阻塞项', detail: blockers[0].action, label: '处理第一项', onClick: () => onNavigateTarget(blockers[0]) }
      : !started
        ? dashboard.discharge_criteria_status?.all_met === true
          ? { title: '发起正式出院流程', detail: '发起后生成出院交接事项并进入医生出院签字审核。', label: '发起出院流程', onClick: onInitiate ?? onOpenDischarge }
          : { title: '当前处于住院监测阶段', detail: '尚未进入出院流程。请继续完成诊疗与监测；达到出院标准后再发起正式流程。', label: '查看监测数据', onClick: () => onNavigateTarget({ key: 'discharge_precheck', label: '出院前评估', met: false, target: 'monitoring', action: '核对最新体征、检验和临床记录后重新评估出院条件' }) }
        : !signed
          ? { title: '等待出院签字卡点', detail: '系统正在形成出院签字审核；刷新后可前往医生工作台处理。', label: '查看出院页', onClick: onOpenDischarge }
          : !dashboard.handoff_acknowledged
            ? { title: '完成交接签收', detail: dashboard.bridge_status === 'ok' ? '协同病例已创建。请在下方「交接闭环状态」面板中点击「确认交接签收」按钮。' : dashboard.bridge_error ? `协同创建失败：${dashboard.bridge_error}。请刷新页面重试。` : '等待系统创建出院协同病例...', label: '跳转到交接面板', onClick: () => document.getElementById('handoff-completion')?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }
            : !['confirmed'].includes(dashboard.patient_confirmation_status || '')
              ? { title: '完成患者回授确认', detail: '交接已签收。记录患者或照护者的真实回授后，系统会自动完成交接闭环。', label: '记录患者回授', onClick: onOpenEducation ?? (() => document.getElementById('discharge-education')?.scrollIntoView({ behavior: 'smooth', block: 'center' })) }
              : { title: '出院交接闭环已完成', detail: '六大步骤全部完成，交接事项已签收，患者已完成回授。', label: '返回工作台', onClick: onReturnToWorkbench ?? onOpenDischarge };

  return <Card variant="outlined" sx={{ borderRadius: 1, overflow: 'hidden' }}>
    <Box sx={{ px: 1.75, py: 1.3, display: 'flex', alignItems: 'center', gap: 0.8, borderBottom: '1px solid', borderColor: 'divider' }}>
      <Route size={18} />
      <Box sx={{ flex: 1 }}><Typography variant="subtitle2">出院流程</Typography><Typography variant="caption" color="text.secondary">条件评估、审核、发起、签字、交接与回授使用同一条正式链路</Typography></Box>
      <Chip
        size="small"
        color={steps.every((step) => step.done) ? 'success' : failedIndex >= 0 ? 'error' : 'info'}
        label={steps.every((step) => step.done) ? '闭环完成' : failedIndex >= 0 ? `阻塞在第 ${failedIndex + 1} 步` : `进行至第 ${activeIndex + 1} 步`}
      />
    </Box>

    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'repeat(6, minmax(0, 1fr))' }, borderBottom: '1px solid', borderColor: 'divider' }}>
      {steps.map((step, index) => {
        const current = index === activeIndex && !step.done && !step.failed;
        const status = step.done ? '已完成' : step.failed ? '失败' : current ? '当前处理' : '未完成';
        return <Box key={step.key} sx={{ px: 1.25, py: 1.35, minHeight: 104, borderRight: { lg: index === steps.length - 1 ? 0 : '1px solid' }, borderBottom: { xs: index === steps.length - 1 ? 0 : '1px solid', lg: 0 }, borderColor: 'divider', bgcolor: step.failed ? 'rgba(211, 47, 47, 0.045)' : current ? 'rgba(237, 246, 247, 0.7)' : 'background.paper' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.65, color: step.done ? 'success.main' : step.failed ? 'error.main' : current ? 'primary.main' : 'text.disabled' }}>{step.done ? <CheckCircle2 size={16} /> : step.failed ? <AlertTriangle size={16} /> : <Circle size={16} />}<Typography variant="caption" fontWeight={700}>第 {index + 1} 步</Typography><Chip size="small" variant="outlined" color={step.done ? 'success' : step.failed ? 'error' : current ? 'info' : 'default'} label={status} sx={{ ml: 'auto', height: 21, '& .MuiChip-label': { px: 0.7 } }} /></Box>
        <Typography variant="body2" fontWeight={600} sx={{ mt: 0.65 }}>{step.label}</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25, lineHeight: 1.45 }}>{step.description}</Typography>
      </Box>;})}
    </Box>

    {dashboard.bridge_error ? <Alert severity="error" sx={{ m: 1.5, mb: blockers.length ? 0 : 1.5 }}>出院协同病例创建失败：{bridgeErrorLabel(dashboard.bridge_error)}。交接签收暂时无法继续，请查看交接闭环状态。</Alert> : null}

    {blockers.length ? <Box sx={{ px: 1.75, py: 1.4, borderBottom: '1px solid', borderColor: 'divider' }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>当前阻塞项（{blockers.length} 项）</Typography>
      {blockers.map((blocker, index) => <Box key={`${blocker.key}-${index}`} sx={{ py: 0.85, display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr auto' }, gap: 1, alignItems: 'flex-start', borderTop: index ? '1px solid' : 0, borderColor: 'divider' }}>
        <Box>
          <Typography variant="body2" fontWeight={600}>{blocker.label}{blocker.met === false ? <Chip size="small" color="error" label="未达标" sx={{ ml: 1, height: 20, fontSize: 11 }} /> : null}</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25 }}>{blocker.action}</Typography>
        </Box>
        <Button size="small" variant="outlined" endIcon={<ArrowRight size={14} />} onClick={() => onNavigateTarget(blocker)} sx={{ alignSelf: 'center', whiteSpace: 'nowrap' }}>
          处理：{blockerLabel(blocker.target)}
        </Button>
      </Box>)}
      {/* 显示完整的出院条件明细 */}
      {dashboard.discharge_criteria_status?.details?.length ? <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid', borderColor: 'divider' }}>
        <Typography variant="caption" fontWeight={600} color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>出院条件明细</Typography>
        {dashboard.discharge_criteria_status.details.map((item) => <Box key={item.key} sx={{ display: 'flex', alignItems: 'center', gap: 0.8, py: 0.3 }}>
          {item.met ? <CheckCircle2 size={14} color="#2e7d32" /> : <AlertTriangle size={14} color="#d32f2f" />}
          <Typography variant="caption" color={item.met ? 'text.secondary' : 'text.primary'} sx={{ flex: 1 }}>{item.label || item.key}</Typography>
          <Chip size="small" variant="outlined" color={item.met ? 'success' : 'error'} label={item.met ? '已达标' : '未达标'} sx={{ height: 20, fontSize: 10 }} />
        </Box>)}
      </Box> : null}
    </Box> : null}

    {!started && !blockers.length ? <Alert severity="info" sx={{ mx: 1.75, mt: 1.5 }}>
      当前患者尚未进入出院流程。交接和随访联系方式等后续事项不会提前标记为阻塞；出院条件将在正式发起前持续预评估。
    </Alert> : null}

    <Box sx={{ px: 1.75, py: 1.4, display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 1fr) auto' }, gap: 1.5, alignItems: 'center', bgcolor: 'rgba(11, 100, 114, 0.035)', mt: !started && !blockers.length ? 1.5 : 0 }}>
      <Box><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.65 }}><LockKeyhole size={16} /><Typography variant="subtitle2">当前下一步：{nextAction.title}</Typography></Box><Typography variant="body2" color="text.secondary" sx={{ mt: 0.4 }}>{nextAction.detail}</Typography>{error ? <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert> : null}</Box>
      {nextAction.onClick ? <Button variant="contained" color={pendingReviewType ? 'warning' : 'primary'} disabled={busy} startIcon={busy ? <CircularProgress size={15} color="inherit" /> : <ClipboardCheck size={16} />} endIcon={!busy ? <ArrowRight size={15} /> : undefined} onClick={nextAction.onClick}>{nextAction.label}</Button> : null}
    </Box>
  </Card>;
}

function bridgeErrorLabel(value: string) {
  return ({
    handoff_items_missing: '缺少可交接事项',
    bridge_unavailable: '出院协同服务暂不可用',
  } as Record<string, string>)[value] ?? value;
}

function blockerLabel(target: DischargeTarget): string {
  return ({
    monitoring: '体征监测',
    orders: '医嘱协同',
    rounds: '查房管理',
    discharge: '出院流程',
    summary: '出院小结',
    history: '病史采集',
    handoff: '交接闭环',
    contact: '随访联系人',
    records: '文书区域',
  } as Record<DischargeTarget, string>)[target] ?? target;
}
