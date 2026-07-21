import { forwardRef, useEffect, useRef, useState, type ReactNode } from 'react';
import { Alert, Box, Button, Card, Chip, CircularProgress, Divider, Tab, Tabs, Typography } from '@mui/material';
import { BookOpenCheck, CheckCircle2, Circle, ClipboardCheck, Download, FileText, Handshake, ShieldAlert } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import AppShell from '@/components/layout/AppShell';
import { patientWorkspaceRoute, ROUTES, workbenchReviewRoute, workbenchRoute } from '@/core/routes';
import EvidencePanel from '@/components/clinical/EvidencePanel';
import MedicationSafetyPanel from '@/components/clinical/MedicationSafetyPanel';
import DischargeEducationPanel from '@/components/clinical/DischargeEducationPanel';
import PatientAssistantPanel from '@/components/clinical/PatientAssistantPanel';
import FollowUpContactPanel from '@/components/clinical/FollowUpContactPanel';
import DischargeWorkflowPanel from '@/components/clinical/DischargeWorkflowPanel';
import { CardSkeleton, ErrorBanner, LoadingSkeleton } from '@/components/shared/Feedback';
import { ApiClientError, describeApiError } from '@/core/api-client';
import { usePageAuth } from '@/hooks/use-page-auth';
import { acknowledgeHandoff, auditDischargePdfExport, fetchDischargeSummary, fetchPatientDashboard, initiateDischarge } from '@/services/patient-service';
import type { DashboardResponse, DischargeSummaryResponse } from '@/types/patient-dashboard';
import { canSignDischarge } from '@/utils/discharge-utils';
import { dischargePdfFilename, exportDischargeElementToPdf } from '@/utils/discharge-pdf';
import type { DischargeBlockerDetail } from '@/utils/discharge-workflow';

export default function DischargePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const auth = usePageAuth('doctor');
  const queryClient = useQueryClient();
  const [showEvidence, setShowEvidence] = useState(false);
  const [workflowError, setWorkflowError] = useState('');
  const [workflowFocus, setWorkflowFocus] = useState<Pick<DischargeBlockerDetail, 'target' | 'action'> | null>(null);
  const [exportError, setExportError] = useState('');
  const [educationRecordRequest, setEducationRecordRequest] = useState(0);
  const printableRef = useRef<HTMLDivElement>(null);
  const dashboard = useQuery({ queryKey: ['patient', id, 'dashboard'], queryFn: () => fetchPatientDashboard(id!), enabled: Boolean(id), staleTime: 20_000 });
  const summary = useQuery({ queryKey: ['patient', id, 'discharge-summary'], queryFn: () => fetchDischargeSummary(id!), enabled: Boolean(id), staleTime: 20_000 });
  const summaryUnavailable = Boolean(summary.error || !summary.data);
  const requestedFocus = searchParams.get('focus');

  useEffect(() => {
    if (!dashboard.data || !summary.data || !requestedFocus) return;
    const targetId = requestedFocus === 'handoff' ? 'handoff-completion' : requestedFocus === 'contact' ? 'follow-up-contact' : 'discharge-preparation';
    const scrollToRequestedFocus = () => document.getElementById(targetId)?.scrollIntoView({ behavior: 'auto', block: 'start' });
    const frame = window.requestAnimationFrame(scrollToRequestedFocus);
    const layoutCorrection = window.setTimeout(scrollToRequestedFocus, 300);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(layoutCorrection);
    };
  }, [dashboard.data, requestedFocus, summary.data]);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['patient', id] }),
      queryClient.invalidateQueries({ queryKey: ['ward'] }),
    ]);
  };
  const openEducationRecording = () => {
    setEducationRecordRequest((value) => value + 1);
    document.getElementById('discharge-education')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
  const initiationMutation = useMutation({
    mutationFn: () => initiateDischarge(id!, { reason: '患者出院条件已核对，发起正式出院流程', expected_version: dashboard.data!.state_version }),
    onSuccess: async () => {
      await refresh();
      setWorkflowError('');
    },
    onError: (cause) => {
      if (cause instanceof ApiClientError && cause.code === 'STATE_VERSION_CONFLICT') {
        setWorkflowError('患者状态已更新。已刷新最新数据，请重新核对出院条件后操作。');
        void refresh();
        return;
      }
      setWorkflowError(cause instanceof Error ? cause.message : '出院流程发起失败，请稍后重试。');
    },
  });
  const handoffMutation = useMutation({
    mutationFn: () => acknowledgeHandoff(id!),
    onSuccess: async () => {
      await refresh();
      setWorkflowError('');
    },
    onError: (cause) => {
      if (cause instanceof ApiClientError && cause.code === 'STATE_VERSION_CONFLICT') {
        setWorkflowError('患者状态已更新。已刷新最新数据，请重新确认交接状态。');
        void refresh();
        return;
      }
      setWorkflowError(cause instanceof Error ? cause.message : '交接操作失败，请稍后重试。');
    },
  });
  const exportMutation = useMutation({
    mutationFn: async () => {
      const isDraft = !['signed', 'approved'].includes(dashboard.data!.discharge_sign_status);
      await auditDischargePdfExport(id!, isDraft ? 'draft' : 'final');
      if (!printableRef.current) throw new Error('出院小结导出区域尚未就绪');
      await exportDischargeElementToPdf(
        printableRef.current,
        dischargePdfFilename(dashboard.data?.patient_name ?? '', id!, isDraft),
      );
    },
    onMutate: () => setExportError(''),
    onError: (cause) => setExportError(cause instanceof Error ? cause.message : 'PDF 导出失败，请稍后重试。'),
  });

  if (auth.redirect) return auth.redirect;
  if (!id) return <AppShell title="出院小结" backTo={ROUTES.workbench} backLabel="医生工作台" showGlobalAssistant={false}><ErrorBanner message="未指定患者" /></AppShell>;
  if (dashboard.isLoading || summary.isLoading) return <DischargeLoading />;
  if (dashboard.error || !dashboard.data) {
    return <AppShell title="出院小结" showGlobalAssistant={false}><Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25, maxWidth: 680 }}><ErrorBanner message={describeApiError(dashboard.error, '患者状态加载失败')} onRetry={() => void dashboard.refetch()} />{dashboard.error instanceof ApiClientError && ['FORBIDDEN', 'NOT_FOUND'].includes(dashboard.error.code) ? <Button variant="outlined" onClick={() => navigate(ROUTES.workbench, { replace: true })}>返回医生工作台</Button> : null}</Box></AppShell>;
  }

  const dischargeSummary = summary.data ?? emptyDischargeSummary(id);

  return <AppShell title="出院小结" showGlobalAssistant={false}>
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <DischargeHeader dashboard={dashboard.data} exportPending={exportMutation.isPending} onExport={() => exportMutation.mutate()} />
      {exportError ? <Alert severity="error">{exportError}</Alert> : null}
      {summaryUnavailable ? <Alert severity="warning" action={<Button color="inherit" size="small" onClick={() => void summary.refetch()}>重试小结</Button>}>出院小结服务暂时不可用，流程状态仍可继续查看；小结相关内容恢复后将自动显示。{describeApiError(summary.error, '')}</Alert> : null}
      <DischargeWorkflowPanel
        dashboard={dashboard.data}
        busy={initiationMutation.isPending}
        error={workflowError}
        onNavigateTarget={(blocker) => {
          if (blocker.target === 'discharge' || blocker.target === 'handoff' || blocker.target === 'contact') {
            setWorkflowFocus(blocker);
            scrollToDischargeTarget(blocker.target);
          } else {
            navigate(patientWorkspaceRoute(id, blocker.target, blocker.key));
          }
        }}
        onOpenReview={(reviewType) => navigate(workbenchReviewRoute(id, reviewType))}
        onOpenDischarge={() => document.getElementById('discharge-preparation')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
        onOpenEducation={openEducationRecording}
        onReturnToWorkbench={() => navigate(workbenchRoute('today'))}
        onInitiate={() => initiationMutation.mutate()}
      />
      {workflowFocus ? <Alert severity="info">
        已定位到{dischargeTargetLabel(workflowFocus.target)}：{workflowFocus.action}。完成后会按最新状态刷新出院闭环。
      </Alert> : null}
      <Box id="discharge-preparation" sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1.15fr) minmax(320px, 0.85fr)' }, gap: 2, alignItems: 'start', scrollMarginTop: 16 }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <SummaryPanel summary={dischargeSummary} />
          <MedicationSafetyPanel safety={dashboard.data.medication_safety} />
          <Box id="discharge-education" sx={{ scrollMarginTop: 16 }}><DischargeEducationPanel patientId={id} stateVersion={dashboard.data.state_version} disease={dashboard.data.template_name} diseaseId={dashboard.data.template_id} openRecordRequest={educationRecordRequest} /></Box>
        </Box>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <HandoffPanel summary={dischargeSummary} />
          <Box id="handoff-completion" sx={{ scrollMarginTop: 16 }}><HandoffCompletionPanel dashboard={dashboard.data} pending={handoffMutation.isPending} error={handoffMutation.isError ? workflowError : ''} onAcknowledge={() => handoffMutation.mutate()} onOpenEducation={openEducationRecording} /></Box>
          <Box id="follow-up-contact" sx={{ scrollMarginTop: 16 }}><FollowUpContactPanel patientId={id} /></Box>
          <PatientAssistantPanel
            patientId={id}
            assistantMode="integrative"
            availableModes={['integrative', 'pharmacist', 'patient']}
            defaultOpen
            onOpenClinicalRecord={() => navigate(patientWorkspaceRoute(id, 'orders'))}
          />
          <EvidenceCard patientId={id} shown={showEvidence} onToggle={() => setShowEvidence((value) => !value)} />
        </Box>
      </Box>
    </Box>
    <PrintableDischargeSummary ref={printableRef} dashboard={dashboard.data} summary={dischargeSummary} isDraft={!['signed', 'approved'].includes(dashboard.data.discharge_sign_status)} />
  </AppShell>;
}

function DischargeHeader({ dashboard, exportPending, onExport }: { dashboard: DashboardResponse; exportPending: boolean; onExport: () => void }) {
  const readiness = Number(dashboard.discharge_readiness.score ?? 0);
  const allCriteriaMet = canSignDischarge(dashboard.discharge_criteria_status);
  const isDraft = !['signed', 'approved'].includes(dashboard.discharge_sign_status);
  return <Card variant="outlined" sx={{ borderRadius: 1 }}><Box sx={{ p: 1.75, display: 'flex', gap: 2, alignItems: { xs: 'flex-start', sm: 'center' }, flexWrap: 'wrap' }}>
    <Box sx={{ flex: 1, minWidth: 220 }}><Typography variant="h6" fontWeight={600}>{dashboard.patient_name || dashboard.patient_id}</Typography><Typography variant="body2" color="text.secondary">{dashboard.template_name || '未标注病种'} · 出院准备度</Typography></Box>
    <Box><Typography variant="h5">{readiness}%</Typography><Chip size="small" color={allCriteriaMet ? 'success' : 'warning'} label={allCriteriaMet ? '条件已达标' : '仍有待处理条件'} /></Box>
    <Button variant="outlined" color={isDraft ? 'warning' : 'primary'} startIcon={exportPending ? <CircularProgress size={15} /> : <Download size={16} />} disabled={exportPending} onClick={onExport}>{isDraft ? '导出打印草稿' : '导出 PDF'}</Button>
    {isDraft ? <Typography variant="caption" color="warning.dark" sx={{ width: { xs: '100%', sm: 'auto' } }}>草稿仅用于线下打印签字；完成签字后请重新导出正式文书。</Typography> : null}
  </Box></Card>;
}

const PrintableDischargeSummary = forwardRef<HTMLDivElement, { dashboard: DashboardResponse; summary: DischargeSummaryResponse; isDraft: boolean }>(function PrintableDischargeSummary({ dashboard, summary, isDraft }, ref) {
  return <Box ref={ref} aria-hidden sx={{ position: 'fixed', left: -10000, top: 0, width: 794, bgcolor: '#fff', color: '#111', p: '48px', fontFamily: '"Noto Sans SC", sans-serif', '& h1, & h2, & p': { m: 0 } }}>
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 2, mb: 0.75 }}><Typography component="h1" sx={{ fontSize: 26, fontWeight: 600 }}>出院小结</Typography>{isDraft ? <Typography sx={{ fontSize: 13, color: '#9a5b12', border: '1px solid #c9873e', px: 1, py: 0.4 }}>草稿 - 待医生签字</Typography> : null}</Box>
    <Typography sx={{ fontSize: 13, color: '#555', mb: 3 }}>{dashboard.patient_name || dashboard.patient_id} · {dashboard.template_name || '未标注病种'} · 患者编号 {summary.patient_id}</Typography>
    <PrintableSection title="主要诊断"><PrintableLines values={[summary.primary_diagnosis, ...summary.secondary_diagnoses]} /></PrintableSection>
    <PrintableSection title="住院经过"><PrintableLines values={summary.hospital_course} /></PrintableSection>
    <PrintableSection title="关键事件"><PrintableLines values={summary.critical_events} empty="无关键异常事件" /></PrintableSection>
    <PrintableSection title="出院用药"><PrintableRecords records={summary.discharge_medications} empty="暂无出院用药记录" /></PrintableSection>
    <PrintableSection title="随访计划"><PrintableRecords records={summary.follow_up_plan} empty="暂无随访计划" /></PrintableSection>
    <PrintableSection title="交接事项"><PrintableRecords records={summary.handoff_summary} empty="暂无交接事项" /></PrintableSection>
    <Box sx={{ mt: 4, pt: 1.5, borderTop: '1px solid #bbb', display: 'flex', justifyContent: 'space-between' }}><Typography sx={{ fontSize: 12, color: isDraft ? '#9a5b12' : '#666' }}>签字状态：{isDraft ? '待医生签字（打印草稿）' : dashboard.discharge_sign_status}</Typography><Typography sx={{ fontSize: 12, color: '#666' }}>生成时间：{new Date().toLocaleString('zh-CN', { hour12: false })}</Typography></Box>
  </Box>;
});

function PrintableSection({ title, children }: { title: string; children: ReactNode }) {
  return <Box sx={{ mb: 2.5, breakInside: 'avoid' }}><Typography component="h2" sx={{ fontSize: 16, fontWeight: 600, pb: 0.5, mb: 1, borderBottom: '1px solid #ccc' }}>{title}</Typography>{children}</Box>;
}

function PrintableLines({ values, empty = '暂无记录' }: { values: string[]; empty?: string }) {
  const items = values.filter(Boolean);
  return items.length ? <Box>{items.map((item, index) => <Typography key={`${item}-${index}`} sx={{ fontSize: 13, lineHeight: 1.75, mb: 0.5 }}>{item}</Typography>)}</Box> : <Typography sx={{ fontSize: 13, color: '#666' }}>{empty}</Typography>;
}

function PrintableRecords({ records, empty }: { records: Array<Record<string, unknown>>; empty: string }) {
  return records.length ? <Box>{records.map((record, index) => <Box key={String(record.id ?? index)} sx={{ mb: 1 }}><Typography sx={{ fontSize: 13, fontWeight: 600 }}>{recordTitle(record)}</Typography><Typography sx={{ fontSize: 12, color: '#555', lineHeight: 1.6 }}>{recordDetail(record)}</Typography></Box>)}</Box> : <Typography sx={{ fontSize: 13, color: '#666' }}>{empty}</Typography>;
}

function SummaryPanel({ summary }: { summary: DischargeSummaryResponse }) {
  const [tab, setTab] = useState(0);
  const sections = [
    { label: '诊断与经过', content: <><DetailList label="主要诊断" values={[summary.primary_diagnosis]} /><DetailList label="次要诊断" values={summary.secondary_diagnoses} /><DetailList label="住院经过" values={summary.hospital_course} /><DetailList label="关键事件" values={summary.critical_events} /></> },
    { label: '出院用药', content: <RecordList records={summary.discharge_medications} empty="暂无出院用药记录" /> },
    { label: '随访交接', content: <RecordList records={[...summary.follow_up_plan, ...summary.handoff_summary]} empty="暂无随访或交接记录" /> },
  ];
  return <Card variant="outlined" sx={{ borderRadius: 1 }}><Box sx={{ px: 1.75, pt: 1.25, display: 'flex', gap: 0.75, alignItems: 'center' }}><FileText size={18} /><Typography variant="subtitle2" fontWeight={600}>出院小结</Typography></Box><Tabs value={tab} onChange={(_, value) => setTab(value)} variant="scrollable" allowScrollButtonsMobile sx={{ px: 1 }}><Tab label="诊断与经过" /><Tab label="出院用药" /><Tab label="随访交接" /></Tabs><Divider /><Box sx={{ p: 1.75 }}>{sections[tab].content}{summary.completeness?.warning ? <Alert severity="warning" sx={{ mt: 1.5 }}>{summary.completeness.warning}</Alert> : null}</Box></Card>;
}

function DetailList({ label, values }: { label: string; values: string[] }) {
  const items = values.filter(Boolean);
  if (!items.length) return null;
  return <Box sx={{ mb: 1.5 }}><Typography variant="caption" color="text.secondary">{label}</Typography>{items.map((item, index) => <Typography key={`${item}-${index}`} variant="body2" sx={{ mt: 0.35, lineHeight: 1.6 }}>{item}</Typography>)}</Box>;
}

function RecordList({ records, empty }: { records: Array<Record<string, unknown>>; empty: string }) {
  if (!records.length) return <Typography variant="body2" color="text.secondary">{empty}</Typography>;
  return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>{records.map((record, index) => <Box key={String(record.id ?? index)} sx={{ borderLeft: '3px solid', borderColor: 'info.main', pl: 1.25 }}><Typography variant="body2" fontWeight={600}>{recordTitle(record)}</Typography><Typography variant="caption" color="text.secondary" display="block">{recordDetail(record)}</Typography></Box>)}</Box>;
}

function HandoffPanel({ summary }: { summary: DischargeSummaryResponse }) {
  return <Card variant="outlined" sx={{ borderRadius: 1 }}><Box sx={{ px: 1.75, py: 1.25, display: 'flex', gap: 0.75, alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}><ClipboardCheck size={18} /><Typography variant="subtitle2" fontWeight={600}>交接与风险提示</Typography></Box><Box sx={{ p: 1.75 }}><RecordList records={summary.handoff_summary} empty="暂无交接事项" /></Box></Card>;
}

function HandoffCompletionPanel({ dashboard, pending, error, onAcknowledge, onOpenEducation }: { dashboard: DashboardResponse; pending: boolean; error?: string; onAcknowledge: () => void; onOpenEducation: () => void }) {
  const signed = dashboard.discharge_sign_status === 'signed' || dashboard.discharge_sign_status === 'approved';
  const bridgeReady = dashboard.bridge_status === 'ok';
  const acknowledged = dashboard.handoff_acknowledged;
  const confirmed = dashboard.patient_confirmation_status === 'confirmed';
  const bridgeFailed = Boolean(dashboard.bridge_error) && !bridgeReady;
  const steps: Array<{ label: string; key: string; status: 'completed' | 'pending' | 'failed' }> = [
    { key: 'sign', label: '医生完成出院签字', status: signed ? 'completed' : 'pending' },
    { key: 'bridge', label: '出院协同病例创建成功', status: bridgeReady ? 'completed' : bridgeFailed ? 'failed' : 'pending' },
    { key: 'acknowledge', label: '接收方确认交接事项', status: acknowledged ? 'completed' : 'pending' },
    { key: 'confirm', label: '患者或照护者完成回授', status: confirmed ? 'completed' : 'pending' },
  ];

  return <Card variant="outlined" sx={{ borderRadius: 1 }}>
    <Box sx={{ px: 1.75, py: 1.25, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}>
      <Handshake size={18} />
      <Typography variant="subtitle2" fontWeight={600}>交接闭环状态</Typography>
      <Chip size="small" color={confirmed ? 'success' : bridgeFailed ? 'error' : acknowledged ? 'info' : 'warning'} label={confirmed ? '已完成' : bridgeFailed ? '存在阻塞' : acknowledged ? '交接已签收' : '进行中'} sx={{ ml: 'auto' }} />
    </Box>
    <Box sx={{ p: 1.75, display: 'flex', flexDirection: 'column', gap: 1 }}>
      {dashboard.bridge_error ? <Alert severity="error">出院协同创建失败：{handoffBridgeErrorLabel(dashboard.bridge_error)}</Alert> : null}
      {error ? <Alert severity="error" sx={{ mt: 0.5 }}>{error}</Alert> : null}
      {!signed && !bridgeFailed ? <Alert severity="info">请先在医生工作台完成<a href={`/patient/${dashboard.patient_id}/discharge`} style={{ fontWeight: 600 }}>出院签字</a>审核，审核通过后自动触发交接闭环。</Alert> : null}
      {signed && !bridgeReady && !bridgeFailed ? <Alert severity="info" action={<Button color="inherit" size="small" onClick={() => window.location.reload()}>刷新状态</Button>}>出院已签字，等待系统创建协同病例（通常几秒内完成）。如长时间未完成请刷新。</Alert> : null}
      {steps.map((step) => {
        const completed = step.status === 'completed';
        const failed = step.status === 'failed';
        return <Box key={step.key} sx={{ display: 'flex', alignItems: 'center', gap: 1, minHeight: 28 }}>
          <Box sx={{ display: 'flex', color: completed ? 'success.main' : failed ? 'error.main' : 'text.disabled' }}>{completed ? <CheckCircle2 size={17} /> : failed ? <ShieldAlert size={17} /> : <Circle size={17} />}</Box>
          <Typography variant="body2" color={completed ? 'text.primary' : failed ? 'error.main' : 'text.secondary'} sx={{ flex: 1 }}>{step.label}</Typography>
          <Chip size="small" variant="outlined" color={completed ? 'success' : failed ? 'error' : 'default'} label={completed ? '已完成' : failed ? '失败' : '未完成'} sx={{ minWidth: 62 }} />
        </Box>;
      })}
      {dashboard.patient_confirmation_requirements.length ? <Typography variant="caption" color="text.secondary">当前缺项：{dashboard.patient_confirmation_requirements.map(confirmationRequirementLabel).join('、')}</Typography> : null}
      {/* 步骤3: 接收方签收 */}
      {!acknowledged ? <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {!signed || !bridgeReady ? <Alert severity="info">
          {!signed ? '等待医生完成出院签字审核。请前往医生工作台处理出院签字卡点。' : '等待协同病例创建完成（通常几秒内自动完成）。如长时间未创建，请刷新页面。'}
        </Alert> : null}
        <Button variant="contained" color="primary" disabled={!signed || !bridgeReady || pending} onClick={onAcknowledge} startIcon={pending ? <CircularProgress size={15} /> : <Handshake size={16} />} sx={{ alignSelf: 'flex-start' }}>
          {pending ? '处理中...' : '确认交接签收'}
        </Button>
      </Box> : null}
      {/* 步骤4: 回授 — 已签收但未确认 */}
      {acknowledged && !confirmed ? <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        <Alert severity="warning">交接已签收。下一步请记录患者或照护者的真实回授；保存后系统会自动判定交接闭环，无需再次确认。</Alert>
        <Button variant="contained" color="success" disabled={pending} onClick={onOpenEducation} startIcon={<BookOpenCheck size={16} />} sx={{ alignSelf: 'flex-start' }}>前往记录患者回授</Button>
      </Box> : null}
      {confirmed && <Alert severity="success">交接闭环已完成。患者已签收交接事项并完成回授。</Alert>}
    </Box>
  </Card>;
}

function scrollToDischargeTarget(target: 'discharge' | 'handoff' | 'contact') {
  const targetId = target === 'handoff' ? 'handoff-completion' : target === 'contact' ? 'follow-up-contact' : 'discharge-preparation';
  document.getElementById(targetId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function dischargeTargetLabel(target: DischargeBlockerDetail['target']): string {
  return ({ discharge: '出院准备', handoff: '交接闭环', contact: '随访联系人' } as Record<string, string>)[target] ?? '当前处理区域';
}

function handoffBridgeErrorLabel(value: string) {
  return ({
    handoff_items_missing: '缺少可交接事项',
    bridge_unavailable: '出院协同服务暂不可用',
  } as Record<string, string>)[value] ?? value;
}

function EvidenceCard({ patientId, shown, onToggle }: { patientId: string; shown: boolean; onToggle: () => void }) {
  return <Card variant="outlined" sx={{ borderRadius: 1 }}><Box sx={{ p: 1.5, display: 'flex', alignItems: 'center', gap: 1 }}><ShieldAlert size={18} /><Typography variant="subtitle2" fontWeight={600} sx={{ flex: 1 }}>临床证据</Typography><Button size="small" variant="text" onClick={onToggle}>{shown ? '收起' : '查看'}</Button></Box>{shown ? <Box sx={{ px: 1.75, pb: 1.75 }}><EvidencePanel patientId={patientId} enabled /></Box> : null}</Card>;
}

function recordTitle(record: Record<string, unknown>) { return text(record.medication) || text(record.title) || text(record.type) || text(record.content) || '未命名记录'; }
function recordDetail(record: Record<string, unknown>) { return [text(record.dose), text(record.frequency), text(record.route), text(record.indication), text(record.content), text(record.due_at), text(record.assignee)].filter(Boolean).join(' · ') || '未提供详情'; }
function text(value: unknown) { return typeof value === 'string' || typeof value === 'number' ? String(value) : ''; }
function confirmationRequirementLabel(value: string) { return ({ handoff_acknowledgement: '交接签收', teach_back: '回授记录', discharge_bridge: '出院协同创建', doctor_signature: '医生签字' } as Record<string, string>)[value] ?? value; }
function DischargeLoading() { return <AppShell title="出院小结" showGlobalAssistant={false}><Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}><CardSkeleton height={110} /><CardSkeleton height={360} /><LoadingSkeleton lines={2} /></Box></AppShell>; }

function emptyDischargeSummary(patientId: string): DischargeSummaryResponse {
  return { patient_id: patientId, primary_diagnosis: '', secondary_diagnoses: [], hospital_course: [], discharge_medications: [], follow_up_plan: [], critical_events: [], discharge_decision: '', handoff_summary: [], last_updated: '', narrative: '' };
}
