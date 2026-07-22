import { useMemo, memo } from 'react';
import { Alert, Box, Button, Card, Chip, Divider, LinearProgress, Typography } from '@mui/material';
import { Activity, AlertTriangle, BookOpen, ClipboardList, FileText, HeartPulse, Pill, Stethoscope } from 'lucide-react';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import AppShell from '@/components/layout/AppShell';
import { ApiClientError, describeApiError } from '@/core/api-client';
import CommandBar from '@/components/clinical/CommandBar';
import CareManagementPanel from '@/components/clinical/CareManagementPanel';
import WorkflowBriefsPanel from '@/components/clinical/WorkflowBriefsPanel';
import MedicationSafetyPanel from '@/components/clinical/MedicationSafetyPanel';
import PatientAssistantPanel from '@/components/clinical/PatientAssistantPanel';
import AlertLifecyclePanel from '@/components/clinical/AlertLifecyclePanel';
import ClinicalIntakePanel from '@/components/clinical/ClinicalIntakePanel';
import ClinicalMonitoringEntryPanel from '@/components/clinical/ClinicalMonitoringEntryPanel';
import ClinicalBriefPanel from '@/components/clinical/ClinicalBriefPanel';
import AgentFlowPanel from '@/components/clinical/AgentFlowPanel';
import NursingRecordsPanel from '@/components/clinical/NursingRecordsPanel';
import PatientClinicalQueryPanel from '@/components/clinical/PatientClinicalQueryPanel';
import EvidencePanel from '@/components/clinical/EvidencePanel';
import EvidenceGraphPathPanel from '@/components/clinical/EvidenceGraphPathPanel';
import RoundsManagementPanel, { LatestRoundSummary } from '@/components/clinical/RoundsManagementPanel';
import DischargeWorkflowPanel from '@/components/clinical/DischargeWorkflowPanel';
import PatientActionPlan from '@/components/clinical/PatientActionPlan';
import { CardSkeleton, EmptyState, ErrorBanner, LoadingSkeleton } from '@/components/shared/Feedback';
import { PanelErrorBoundary } from '@/components/shared/AppRuntimeGuards';
import { usePageAuth } from '@/hooks/use-page-auth';
import { usePatientDashboard } from '@/hooks/use-patient-dashboard';
import type { DashboardResponse, LabTrendsResponse, ScoresResponse, VitalTrendsResponse } from '@/types/patient-dashboard';
import { displayValue, readinessPercent, scoreTone } from '@/utils/dashboard-utils';
import { patientWorkflowStage, resolvePatientWorkspaceSection, type PatientWorkspaceSection } from '@/core/doctor-workspace';
import { dischargeRoute, patientWorkspaceRoute, workbenchReviewRoute, workbenchRoute } from '@/core/routes';
import { clinicalMetricLabel, labTrendMetrics, medicationDetail } from '@/utils/patient-detail-utils';
import { clinicalPhaseLabel } from '@/utils/round-display';
import type { PatientActionPlanItem } from '@/utils/patient-action-plan';

export default function DashboardPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const auth = usePageAuth('doctor');
  const patient = usePatientDashboard(id);

  if (auth.redirect) return auth.redirect;
  if (!id) return <EmptyState icon="" title="未指定患者" description="请从医生工作台的患者列表进入详情。" />;
  if (patient.dashboard.isLoading) return <DashboardLoading />;
  if (patient.dashboard.error || !patient.dashboard.data) {
    const expired = patient.dashboard.error instanceof ApiClientError && patient.dashboard.error.code === 'NOT_FOUND';
    return <AppShell title="医生工作台 / 患者详情" showGlobalAssistant={false}><Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25, maxWidth: 680 }}><ErrorBanner message={expired ? '患者状态已过期或已被清理，请返回患者列表刷新后重新进入。' : describeApiError(patient.dashboard.error, '患者全貌加载失败，请稍后重试。')} onRetry={() => void patient.dashboard.refetch()} />{patient.dashboard.error instanceof ApiClientError && ['FORBIDDEN', 'NOT_FOUND'].includes(patient.dashboard.error.code) ? <Button variant="outlined" onClick={() => navigate(workbenchRoute('patients'), { replace: true })}>返回本科室患者列表</Button> : null}</Box></AppShell>;
  }

  const dashboard = patient.dashboard.data;
  const section = resolvePatientWorkspaceSection(`?${searchParams.toString()}`);
  const openPatientAction = (action: PatientActionPlanItem) => {
    if (action.target === 'review') {
      navigate(workbenchReviewRoute(id, dashboard.pending_review_type));
      return;
    }
    if (action.target === 'discharge' || action.target === 'handoff' || action.target === 'contact') {
      navigate(dischargeRoute(id, action.target === 'discharge' ? undefined : action.target));
      return;
    }
    navigate(patientWorkspaceRoute(id, action.target, action.focus));
  };
  return (
    <AppShell title="医生工作台 / 患者详情" showGlobalAssistant={false}>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, maxWidth: 1460, mx: 'auto' }}>
        <Box sx={{ position: 'sticky', top: 0, zIndex: 5, bgcolor: 'background.default', pb: 0.25 }}>
          <PatientHeader dashboard={dashboard} scores={patient.scores.data} />
          <Box sx={{ px: 1.75, py: 1.1, border: '1px solid', borderTop: 0, borderColor: 'divider', bgcolor: 'background.paper' }}>
            <CommandBar patientId={id} stateVersion={dashboard.state_version} isOnHold={dashboard.is_on_hold} canStartDischarge={dashboard.discharge_criteria_status?.all_met === true} onOpenDischarge={() => navigate(dischargeRoute(id))} />
          </Box>
        </Box>
        <PatientWorkspaceHeader section={section} />
        <PatientActionPlan dashboard={dashboard} rounds={patient.rounds.data} onOpen={openPatientAction} />
        <PatientWorkspaceContent patientId={id} section={section} focus={searchParams.get('focus')} dashboard={dashboard} patient={patient} />
      </Box>
    </AppShell>
  );
}

const PATIENT_SECTION_META: Record<PatientWorkspaceSection, { title: string; description: string; icon: React.ReactNode }> = {
  overview: { title: '临床概览', description: '聚合当前病情、最新变化、风险评分和下一步临床行动。', icon: <Stethoscope size={18} /> },
  rounds: { title: '查房管理', description: '核对 Agent 生成的结构化 SOAP、证据来源和本轮临床行动。', icon: <Stethoscope size={18} /> },
  monitoring: { title: '监测与检验', description: '录入并回看生命体征、检验趋势、异常结果与护理观察。', icon: <Activity size={18} /> },
  orders: { title: '医嘱与协同', description: '处理用药、检查、随访、MDT 和 AI 操作草稿。', icon: <Pill size={18} /> },
  records: { title: '文书与病程', description: '回看入院资料、护理记录、查房病程和住院事件。', icon: <FileText size={18} /> },
};

const PatientWorkspaceHeader = memo(function PatientWorkspaceHeader({ section }: { section: PatientWorkspaceSection }) {
  const meta = PATIENT_SECTION_META[section];
  return <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}><Box sx={{ mt: 0.25 }}>{meta.icon}</Box><Box><Typography variant="h6" fontWeight={600}>{meta.title}</Typography><Typography variant="body2" color="text.secondary">{meta.description}</Typography></Box></Box>;
});

function PatientWorkspaceContent({ patientId, section, focus, dashboard, patient }: {
  patientId: string;
  section: PatientWorkspaceSection;
  focus: string | null;
  dashboard: DashboardResponse;
  patient: ReturnType<typeof usePatientDashboard>;
}) {
  const navigate = useNavigate();
  const focusNotice = <WorkflowFocusNotice focus={focus} />;

  if (section === 'rounds') return <WorkspaceGrid
    main={<PanelErrorBoundary name="查房管理"><>
      <RoundsManagementPanel
        patientId={patientId}
        stateVersion={dashboard.state_version}
        loading={patient.rounds.isLoading}
        rounds={patient.rounds.data}
        preRoundBrief={patient.preRoundBrief.data}
        preRoundBriefLoading={patient.preRoundBrief.isLoading}
        preRoundBriefError={patient.preRoundBrief.error instanceof Error ? patient.preRoundBrief.error.message : undefined}
        onOpenMonitoring={() => navigate(patientWorkspaceRoute(patientId, 'monitoring'))}
        onOpenOrders={() => navigate(patientWorkspaceRoute(patientId, 'orders'))}
      />
    </></PanelErrorBoundary>}
    side={<>
      <ClinicalBriefPanel patientId={patientId} compact />
      <NursingRecordsPanel data={patient.nursingRecords.data} loading={patient.nursingRecords.isLoading} error={patient.nursingRecords.error} onRetry={() => void patient.nursingRecords.refetch()} />
      <PatientClinicalQueryPanel patientId={patientId} />
      <Section title="临床证据与引用" icon={<BookOpen size={18} />}><EvidencePanel patientId={patientId} enabled /></Section>
    </>}
  />;

  if (section === 'monitoring') return <WorkspaceGrid
    main={<>
      {focusNotice}
      <ClinicalMonitoringEntryPanel patientId={patientId} stateVersion={dashboard.state_version} />
      <VitalsPanel loading={patient.vitalTrends.isLoading} trends={patient.vitalTrends.data} />
      <LabTrendsPanel loading={patient.labTrends.isLoading} trends={patient.labTrends.data} />
      <LabsPanel labs={dashboard.abnormal_labs} />
    </>}
    side={<>
      <ClinicalBriefPanel patientId={patientId} compact />
      <ScoresPanel loading={patient.scores.isLoading} scores={patient.scores.data} />
      <NursingRecordsPanel data={patient.nursingRecords.data} loading={patient.nursingRecords.isLoading} error={patient.nursingRecords.error} onRetry={() => void patient.nursingRecords.refetch()} />
    </>}
  />;

  if (section === 'orders') return <WorkspaceGrid
    main={<>
      {focusNotice}
      <MedicationPanel dashboard={dashboard} />
      <MedicationSafetyPanel safety={dashboard.medication_safety} />
      <WorkflowBriefsPanel patientId={patientId} stateVersion={dashboard.state_version} />
      <CareManagementPanel patientId={patientId} stateVersion={dashboard.state_version} defaultOpen />
    </>}
    side={<>
      <ChecklistPanel items={dashboard.decision_checklist} />
      <PatientAssistantPanel patientId={patientId} assistantMode="doctor" availableModes={['doctor', 'pharmacist', 'integrative']} defaultOpen onOpenClinicalRecord={() => navigate(patientWorkspaceRoute(patientId, 'orders'))} />
    </>}
  />;

  if (section === 'records') return <WorkspaceGrid
    main={<>
      {focusNotice}
      <ClinicalBriefPanel patientId={patientId} />
      <DischargeWorkflowPanel
        dashboard={dashboard}
        onNavigateTarget={(blocker) => navigate(
          blocker.target === 'handoff' || blocker.target === 'contact'
            ? dischargeRoute(patientId, blocker.target)
            : blocker.target === 'discharge'
              ? dischargeRoute(patientId)
              : patientWorkspaceRoute(patientId, blocker.target, blocker.key),
        )}
        onOpenReview={(reviewType) => navigate(workbenchReviewRoute(patientId, reviewType))}
        onOpenDischarge={() => navigate(dischargeRoute(patientId))}
        onReturnToWorkbench={() => navigate(workbenchRoute('today'))}
      />
      <AgentFlowPanel patientId={patientId} onOpenReview={(reviewType) => navigate(workbenchReviewRoute(patientId, reviewType))} />
      <AdmissionPanel loading={patient.clinicalNote.isLoading} note={patient.clinicalNote.data} />
      <ClinicalIntakePanel patientId={patientId} stateVersion={dashboard.state_version} historyGaps={patient.preRoundBrief.data?.history_gaps} />
      <TimelinePanel loading={patient.timeline.isLoading} timeline={patient.timeline.data} />
    </>}
    side={<>
      <LatestRoundSummary loading={patient.rounds.isLoading} rounds={patient.rounds.data} onOpen={() => navigate(patientWorkspaceRoute(patientId, 'rounds'))} />
      <NursingRecordsPanel data={patient.nursingRecords.data} loading={patient.nursingRecords.isLoading} error={patient.nursingRecords.error} onRetry={() => void patient.nursingRecords.refetch()} />
      <Section title="临床证据与引用" icon={<BookOpen size={18} />}><EvidencePanel patientId={patientId} enabled /></Section>
    </>}
  />;

  return <WorkspaceGrid
    main={<>
      {focusNotice}
      <PanelErrorBoundary name="临床摘要"><ClinicalBriefPanel patientId={patientId} /></PanelErrorBoundary>
      <PanelErrorBoundary name="Agent流程"><AgentFlowPanel patientId={patientId} onOpenReview={(reviewType) => navigate(workbenchReviewRoute(patientId, reviewType))} /></PanelErrorBoundary>
      <AdmissionPanel loading={patient.clinicalNote.isLoading} note={patient.clinicalNote.data} />
      <LatestRoundSummary loading={patient.rounds.isLoading} rounds={patient.rounds.data} onOpen={() => navigate(patientWorkspaceRoute(patientId, 'rounds'))} />
      <MedicationPanel dashboard={dashboard} />
      <AlertLifecyclePanel patientId={patientId} />
    </>}
    side={<>
       <ScoresPanel loading={patient.scores.isLoading} scores={patient.scores.data} />
       <ReadinessPanel readiness={dashboard.discharge_readiness} criteria={dashboard.discharge_criteria_status} />
       <EvidenceGraphPathPanel patientId={patientId} />
       <ChecklistPanel items={dashboard.decision_checklist} />
      <PatientAssistantPanel patientId={patientId} assistantMode="doctor" availableModes={['doctor', 'pharmacist', 'integrative']} onOpenClinicalRecord={() => navigate(patientWorkspaceRoute(patientId, 'orders'))} />
    </>}
  />;
}

function WorkflowFocusNotice({ focus }: { focus: string | null }) {
  if (!focus) return null;
  return <Alert severity="info">
    已定位到待处理区域：{workflowFocusLabel(focus)}。完成录入或审核后，系统会根据最新患者状态重新评估出院流程。
  </Alert>;
}

function workflowFocusLabel(focus: string): string {
  return ({
    discharge_precheck: '出院前评估',
    vital_signs_stable: '生命体征复评估',
    bp_stable_24h: '血压稳定性复评估',
    stable_hemodynamics: '血流动力学复评估',
    medication_titrated: '用药方案确认',
    self_care_education_done: '患者教育记录',
    criteria_missing: '出院标准配置核对',
  } as Record<string, string>)[focus] ?? '当前临床待办';
}

function WorkspaceGrid({ main, side }: { main: React.ReactNode; side: React.ReactNode }) {
  return <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', xl: 'minmax(0, 1.25fr) minmax(340px, 0.75fr)' }, gap: 2, alignItems: 'start' }}>
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>{main}</Box>
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>{side}</Box>
  </Box>;
}

function PatientHeader({ dashboard, scores }: { dashboard: DashboardResponse; scores?: ScoresResponse }) {
  const readiness = readinessPercent(dashboard.discharge_readiness);
  const news2 = scores?.news2.score;
  return <Box sx={{ px: { xs: 1.5, sm: 2 }, py: 1.5, border: '1px solid', borderColor: 'divider', bgcolor: 'background.paper' }}><Box sx={{ display: 'flex', gap: 2, alignItems: { xs: 'flex-start', sm: 'center' }, flexWrap: 'wrap' }}>
    <Box sx={{ flex: 1, minWidth: 220 }}>
      <Typography variant="h6" sx={{ fontFamily: 'var(--font-display)', fontWeight: 500 }}>{dashboard.patient_name || dashboard.patient_id}</Typography>
      <Box sx={{ display: 'flex', gap: 0.75, mt: 0.75, flexWrap: 'wrap' }}><Chip label={dashboard.template_name || '未标注病种'} size="small" /><Chip label={clinicalPhaseLabel(dashboard.phase)} size="small" variant="outlined" /></Box>
    </Box>
    <HeaderMetric label="NEWS2" value={news2 ?? '未评分'} tone={scoreTone(news2)} />
    <HeaderMetric label="出院准备度" value={readiness == null ? '评估中' : `${readiness}%`} tone={readiness != null && readiness < 60 ? 'error' : readiness != null && readiness < 85 ? 'warning' : 'success'} />
    <Box sx={{ minWidth: 110 }}><Typography variant="caption" color="text.secondary">状态版本</Typography><Typography variant="body2" fontFamily="var(--font-mono)">v{dashboard.state_version}</Typography></Box>
  </Box><WorkflowStageBarView phase={dashboard.phase} /></Box>;
}

function WorkflowStageBar({ phase }: { phase: string }) {
  const active = patientWorkflowStage(phase);
  const stages = ['入院评估', '住院管理', '出院准备', '交接完成'];
  return <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', mt: 1.35, borderTop: '1px solid', borderColor: 'divider', pt: 1 }}>
    {stages.map((stage, index) => <Box key={stage} sx={{ display: 'flex', alignItems: 'center', gap: 0.75, color: index <= active ? 'text.primary' : 'text.disabled', minWidth: 0 }}><Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: index < active ? 'success.main' : index === active ? 'info.main' : 'divider' }} /><Typography variant="caption" fontWeight={index === active ? 600 : 400} noWrap>{stage}</Typography>{index < stages.length - 1 ? <Box sx={{ height: 1, bgcolor: index < active ? 'success.main' : 'divider', flex: 1, minWidth: 12 }} /> : null}</Box>)}
  </Box>;
}
const WorkflowStageBarView = memo(WorkflowStageBar);

function HeaderMetric({ label, value, tone }: { label: string; value: string | number; tone: 'error' | 'warning' | 'success' | 'default' }) {
  const color = tone === 'default' ? 'default' : tone;
  return <Box sx={{ minWidth: 90 }}><Typography variant="caption" color="text.secondary">{label}</Typography><Chip label={value} size="small" color={color} sx={{ display: 'flex', mt: 0.4, width: 'fit-content' }} /></Box>;
}

function Section({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return <Card variant="outlined" sx={{ borderRadius: 1 }}><Box sx={{ px: 1.75, py: 1.25, display: 'flex', gap: 0.75, alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}>{icon}<Typography variant="subtitle2" fontWeight={600}>{title}</Typography></Box><Box sx={{ p: 1.75 }}>{children}</Box></Card>;
}

function AdmissionPanel({ loading, note }: { loading: boolean; note?: { chief_complaint?: string; hpi_narrative?: string; pe_narrative?: string; allergies?: unknown[]; pmh?: unknown } }) {
  return <Section title="入院临床记录" icon={<Stethoscope size={18} />}>
    {loading ? <LoadingSkeleton lines={4} height={18} /> : !note ? <EmptyState icon="" title="临床记录暂不可用" /> : <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}><Detail label="主诉" value={note.chief_complaint} /><Detail label="现病史" value={note.hpi_narrative} /><Detail label="体格检查" value={note.pe_narrative} /><Detail label="过敏史" value={note.allergies} /><Detail label="既往史" value={note.pmh} /></Box>}
  </Section>;
}

function Detail({ label, value }: { label: string; value: unknown }) { return <Box><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="body2" sx={{ mt: 0.2, lineHeight: 1.55 }}>{displayValue(value)}</Typography></Box>; }

function TimelinePanel({ loading, timeline }: { loading: boolean; timeline?: { round_count: number; events: Array<{ key: string; label: string; icon?: string }> } }) {
  return <Section title="住院时间线" icon={<ClipboardList size={18} />}>
    {loading ? <LoadingSkeleton lines={4} height={18} /> : !timeline || timeline.events.length === 0 ? <EmptyState icon="" title="暂无住院事件" /> : <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.1 }}>{timeline.events.map((event, index) => <Box key={`${event.key}-${index}`} sx={{ display: 'flex', gap: 1.25, alignItems: 'center' }}><Box sx={{ width: 22, height: 22, display: 'grid', placeItems: 'center', border: '1px solid', borderColor: index === timeline.events.length - 1 ? 'info.main' : 'divider', color: 'info.main', fontSize: 12 }}>{event.icon || '•'}</Box><Typography variant="body2">{event.label}</Typography></Box>)}<Typography variant="caption" color="text.secondary">已完成查房 {timeline.round_count} 次</Typography></Box>}
  </Section>;
}

function MedicationPanel({ dashboard }: { dashboard: DashboardResponse }) {
  const current = dashboard.medication_current.map(medicationDetail);
  const journey = dashboard.medication_journey.slice(-3);
  return <Section title="用药与变化" icon={<Pill size={18} />}>
    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>{dashboard.delta_summary.summary || '暂无变化摘要'}</Typography>
    {current.length ? <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Typography variant="caption" color="text.secondary">当前用药调整记录</Typography>
      {current.slice(-6).map((item, index) => <Box key={`${item.name}-${index}`} sx={{ borderLeft: '3px solid', borderColor: 'info.main', pl: 1.25 }}>
        <Typography variant="body2" fontWeight={600}>{item.name}</Typography>
        <Typography variant="caption" display="block">{item.schedule}</Typography>
        <Typography variant="caption" color="text.secondary" display="block">{item.context}</Typography>
        {item.metadata ? <Typography variant="caption" color="text.secondary" display="block">{item.metadata}</Typography> : null}
      </Box>)}
    </Box> : null}
    {current.length && journey.length ? <Divider sx={{ my: 1.25 }} /> : null}
    {journey.length ? <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Typography variant="caption" color="text.secondary">最近变更</Typography>
      {journey.map((item, index) => <Box key={`${item.drug}-${index}`} sx={{ pb: 1, borderBottom: index === journey.length - 1 ? 0 : '1px solid', borderColor: 'divider' }}><Typography variant="body2" fontWeight={600}>{item.drug || '未命名药物'} · {item.action || '调整'}</Typography><Typography variant="caption" color="text.secondary">{item.detail || '未提供调整说明'} · {item.source || '系统'}</Typography></Box>)}
    </Box> : !current.length ? <EmptyState icon="" title="暂无用药调整记录" /> : null}
  </Section>;
}

function ScoresPanel({ loading, scores }: { loading: boolean; scores?: ScoresResponse }) {
  const scoreCards = scores ? [
    { label: 'NEWS2', value: scores.news2 },
    { label: 'qSOFA', value: scores.qsofa },
    { label: 'Padua', value: scores.padua },
  ] : [];
  const qualityLabel = (label: string, status: string) => `${label} ${status === 'checked' ? '已核查' : status === 'not_applicable' ? '不适用' : '待核查'}`;
  const riskLabel = (risk?: string | null) => risk === 'low' ? '低风险' : risk === 'medium' ? '中风险' : risk === 'high' ? '高风险' : '规则待计算';

  return <Section title="临床评分" icon={<HeartPulse size={18} />}>
    {loading ? <CardSkeleton height={180} /> : !scores ? <EmptyState icon="" title="评分暂不可用" /> : <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 1 }}>
      {scoreCards.map(({ label, value }) => <Box key={label} sx={{ border: '1px solid', borderColor: 'divider', p: 1.1, minWidth: 0 }}>
        <Typography variant="caption" color="text.secondary">{label}</Typography>
        <Typography variant="h6">{value.status === 'available' ? value.score : '待计算'}</Typography>
        <Typography variant="caption" color={value.status === 'available' && value.risk === 'high' ? 'error.main' : 'text.secondary'} display="block">{value.status === 'available' ? riskLabel(value.risk) : '尚无足够评分输入'}</Typography>
        {value.status !== 'available' && value.reason ? <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5, lineHeight: 1.45 }}>{value.reason}</Typography> : null}
        {value.basis?.length ? <Box component="details" sx={{ mt: 0.7, '& > summary': { cursor: 'pointer', color: 'primary.main', fontSize: 12 }, '&[open] > summary': { mb: 0.5 } }}>
          <Box component="summary">查看评分依据</Box>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.35 }}>{value.basis.map((item, index) => <Typography key={`${label}-${index}`} variant="caption" color="text.secondary" sx={{ lineHeight: 1.4 }}>{item}</Typography>)}</Box>
        </Box> : null}
      </Box>)}
      <Box sx={{ gridColumn: '1 / -1', display: 'flex', gap: 0.75, flexWrap: 'wrap', mt: 0.5 }}>
        <Chip size="small" label={qualityLabel('VTE', scores.vte_prophylaxis)} color={scores.vte_prophylaxis === 'checked' ? 'success' : scores.vte_prophylaxis === 'pending' ? 'warning' : 'default'} />
        <Chip size="small" label={qualityLabel('卒中抗栓', scores.stroke_antithrombotic)} color={scores.stroke_antithrombotic === 'checked' ? 'success' : scores.stroke_antithrombotic === 'pending' ? 'warning' : 'default'} />
        <Chip size="small" label={scores.mdt === 'triggered' ? 'MDT 已触发' : 'MDT 未触发'} />
      </Box>
      {scores.score_source === 'demo_deterministic_projection' ? <Typography sx={{ gridColumn: '1 / -1' }} variant="caption" color="text.secondary">演示病例：按当前结构化体征和病史的规则投影生成。</Typography> : null}
    </Box>}
  </Section>;
}

function ReadinessPanel({ readiness, criteria }: { readiness: DashboardResponse['discharge_readiness']; criteria?: Record<string, unknown> | null }) {
  const percent = readinessPercent(readiness);
  const deductions = readiness.deductions ?? [];
  return <Section title="出院准备度" icon={<ClipboardList size={18} />}><Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2 }}><Box><Typography variant="h5">{percent == null ? '—' : `${percent}%`}</Typography><Typography variant="caption" color="text.secondary">{readiness.status || '尚未评估'}</Typography></Box><Typography variant="caption" color="text.secondary" sx={{ textAlign: 'right' }}>{criteria?.all_met === true ? '出院标准已达标' : '仍有待处理条件'}</Typography></Box><LinearProgress variant={percent == null ? 'indeterminate' : 'determinate'} value={percent ?? 0} color={percent != null && percent < 60 ? 'error' : percent != null && percent < 85 ? 'warning' : 'success'} sx={{ mt: 1.25, height: 6 }} />{deductions.length ? <Box sx={{ mt: 1.25 }}>{deductions.map((item) => <Typography key={item} variant="caption" color="text.secondary" display="block">{item}</Typography>)}</Box> : null}</Section>;
}

function VitalsPanel({ loading, trends }: { loading: boolean; trends?: VitalTrendsResponse }) {
  const chartData = useMemo(() => toChartData(trends), [trends]);
  return <Section title="体征趋势" icon={<Activity size={18} />}>{loading ? <CardSkeleton height={190} /> : chartData.length < 2 ? <EmptyState icon="" title="体征趋势数据不足" /> : <Box sx={{ height: 190 }}><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}><XAxis dataKey="label" tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 10 }} /><Tooltip /><Line type="monotone" dataKey="spo2" name="SpO2" stroke="#2977b9" strokeWidth={2} dot={false} connectNulls /><Line type="monotone" dataKey="heartRate" name="心率" stroke="#c77924" strokeWidth={2} dot={false} connectNulls /></LineChart></ResponsiveContainer></Box>}</Section>;
}

function toChartData(trends?: VitalTrendsResponse) {
  const rows = new Map<string, { label: string; spo2?: number; heartRate?: number }>();
  const add = (key: 'spo2' | 'heartRate', data?: Array<{ value: number; timestamp: string; round?: number }>) => data?.forEach((point, index) => { const id = point.timestamp || String(point.round ?? index); const row = rows.get(id) ?? { label: point.round ? `#${point.round}` : String(index + 1) }; row[key] = point.value; rows.set(id, row); });
  add('spo2', trends?.trends.spo2?.data);
  add('heartRate', trends?.trends.heart_rate?.data);
  return Array.from(rows.values());
}

function LabsPanel({ labs }: { labs: DashboardResponse['abnormal_labs'] }) { return <Section title="异常检验" icon={<AlertTriangle size={18} />}>{labs.length === 0 ? <EmptyState icon="" title="暂无异常检验" /> : <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.9 }}>{labs.map((lab, index) => <Box key={`${lab.name}-${lab.value}-${lab.unit}-${index}`} sx={{ display: 'flex', justifyContent: 'space-between', gap: 1 }}><Typography variant="body2">{clinicalMetricLabel(lab.name)}</Typography><Typography variant="body2" color="error.main">{lab.value} {lab.unit}</Typography><Typography variant="caption" color="text.secondary">{lab.ref_range || '无参考范围'}</Typography></Box>)}</Box>}</Section>; }

function LabTrendsPanel({ loading, trends }: { loading: boolean; trends?: LabTrendsResponse }) {
  const metrics = useMemo(() => labTrendMetrics(trends), [trends]);
  return <Section title="检验趋势" icon={<Activity size={18} />}>
    {loading ? <CardSkeleton height={180} /> : metrics.length === 0 ? <EmptyState icon="" title="暂无检验趋势数据" /> : <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      <Typography variant="caption" color="text.secondary">按检验采样序列展示，参考范围以原始检验项目为准</Typography>
      {metrics.slice(0, 6).map((metric) => <Box key={metric.name} sx={{ border: '1px solid', borderColor: 'divider', p: 1.25 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}><Box><Typography variant="body2" fontWeight={600}>{metric.name}</Typography><Typography variant="caption" color="text.secondary">参考范围 {metric.refRange || '未提供'}</Typography></Box><Box sx={{ textAlign: 'right' }}><Typography variant="body2" color={metric.abnormalCount ? 'error.main' : 'text.primary'}>{metric.latest} {metric.unit}</Typography><Typography variant="caption" color="text.secondary">异常 {metric.abnormalCount}/{metric.totalCount}</Typography></Box></Box>
        {metric.values.length > 1 ? <Box sx={{ height: 86, mt: 0.75 }}><ResponsiveContainer width="100%" height="100%"><LineChart data={metric.values}><XAxis dataKey="index" tick={{ fontSize: 10 }} tickFormatter={(value) => `#${value}`} /><YAxis hide domain={['auto', 'auto']} /><Tooltip labelFormatter={(value) => `第 ${value} 次采样`} formatter={(value) => [`${value} ${metric.unit}`, metric.name]} /><Line type="monotone" dataKey="value" stroke={metric.abnormalCount ? '#b33b3b' : '#2977b9'} strokeWidth={2} dot={{ r: 2 }} connectNulls /></LineChart></ResponsiveContainer></Box> : <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.75 }}>仅有 1 次采样，暂不绘制走势</Typography>}
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>最小 {metric.min} · 最大 {metric.max}</Typography>
      </Box>)}
    </Box>}
  </Section>;
}

function ChecklistPanel({ items }: { items: DashboardResponse['decision_checklist'] }) { return <Section title="临床行动清单" icon={<ClipboardList size={18} />}>{items.length === 0 ? <EmptyState icon="" title="暂无待处理行动" /> : <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>{items.map((item, index) => <Box key={`${item.task}-${index}`} sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}><Chip label={item.urgency === 'high' ? '高' : item.urgency === 'medium' ? '中' : '低'} size="small" color={item.urgency === 'high' ? 'error' : item.urgency === 'medium' ? 'warning' : 'default'} /><Box><Typography variant="body2">{item.task || '未命名任务'}</Typography><Typography variant="caption" color="text.secondary">{item.action || item.status || ''}</Typography></Box></Box>)}</Box>}</Section>; }

function DashboardLoading() { return <AppShell title="医生工作台 / 患者详情" showGlobalAssistant={false}><Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}><CardSkeleton height={100} /><Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1.15fr 0.85fr' }, gap: 2 }}><CardSkeleton height={420} /><CardSkeleton height={420} /></Box></Box></AppShell>; }
