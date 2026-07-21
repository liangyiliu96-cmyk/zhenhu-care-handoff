import { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Box, Button, ButtonBase, Card, Chip, Tab, Tabs, TextField, Typography } from '@mui/material';
import { Activity, AlertTriangle, ArrowRight, Bot, CheckCircle2, CircleAlert, ClipboardList, Info, Search } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import DiffPanel from '@/components/clinical/DiffPanel';
import AdmissionLauncher from '@/components/clinical/AdmissionLauncher';
import PatientDirectoryPanel from '@/components/clinical/PatientDirectoryPanel';
import FollowUpOverviewPanel from '@/components/clinical/FollowUpOverviewPanel';
import WardClinicalBoard from '@/components/clinical/WardClinicalBoard';
import AppShell from '@/components/layout/AppShell';
import DepartmentLeadershipStrip from '@/components/shared/DepartmentLeadershipStrip';
import WorkspaceWelcome from '@/components/shared/WorkspaceWelcome';
import { CardSkeleton, EmptyState, ErrorBanner } from '@/components/shared/Feedback';
import { resolveDoctorWorkbenchView, type DoctorWorkbenchView } from '@/core/doctor-workspace';
import { dischargeRoute, patientRoute, patientWorkspaceRoute, ROUTES, workbenchRoute } from '@/core/routes';
import { emitOpenGlobalAssistant } from '@/core/runtime-events';
import { usePageAuth } from '@/hooks/use-page-auth';
import { useWardAiSummary, useWardAlerts, useWardOverview, useWardPatients, useWardPending } from '@/hooks/use-ward';
import type { AlertItem, PendingItem, PendingPatient, WardPatient } from '@/types/ward';
import type { UserIdentity } from '@/types/auth';

interface SelectedReview {
  patientId: string;
  reviewId: string;
}

export default function WorkbenchPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const auth = usePageAuth('doctor');
  const [activeTab, setActiveTab] = useState(0);
  const [selectedReview, setSelectedReview] = useState<SelectedReview | null>(null);

  const { data: pending, isLoading: pendingLoading, error: pendingError, refetch: refetchPending } = useWardPending();
  const { data: alerts, isLoading: alertsLoading, error: alertsError, refetch: refetchAlerts } = useWardAlerts();
  const { data: patients, isLoading: patientsLoading } = useWardPatients();
  const { data: aiSummary } = useWardAiSummary();
  const overview = useWardOverview();
  const view = resolveDoctorWorkbenchView(`?${searchParams.toString()}`);
  const linkedPatientId = searchParams.get('reviewPatient');
  const linkedReviewType = searchParams.get('reviewType');

  useEffect(() => {
    if (!pending || !linkedPatientId || !linkedReviewType) return;
    const patient = pending.pending.find((entry) => entry.patient_id === linkedPatientId);
    const item = patient?.items.find((entry) => entry.review_type === linkedReviewType);
    if (!patient || !item) return;
    setActiveTab(linkedReviewType === 'med_confirm' ? 1 : linkedReviewType === 'discharge_sign' ? 2 : 0);
    setSelectedReview((current) => current?.reviewId === item.review_id ? current : { patientId: patient.patient_id, reviewId: item.review_id });
  }, [linkedPatientId, linkedReviewType, pending]);

  const closeReview = () => {
    setSelectedReview(null);
    if (searchParams.has('reviewPatient') || searchParams.has('reviewType')) {
      const next = new URLSearchParams(searchParams);
      next.delete('reviewPatient');
      next.delete('reviewType');
      setSearchParams(next, { replace: true });
    }
  };

  const selected = useMemo(() => {
    if (!selectedReview || !pending) return { patient: null, item: null };
    const patient = pending.pending.find((entry) => entry.patient_id === selectedReview.patientId) ?? null;
    const item = patient?.items.find((entry) => entry.review_id === selectedReview.reviewId) ?? null;
    return { patient, item };
  }, [pending, selectedReview]);

  const onNavToday = useCallback(() => navigate(workbenchRoute('today')), [navigate]);
  const onNavAlerts = useCallback(() => navigate(workbenchRoute('alerts')), [navigate]);
  const onNavPatients = useCallback(() => navigate(workbenchRoute('patients')), [navigate]);
  const onNavDischarge = useCallback(() => navigate(workbenchRoute('discharge')), [navigate]);
  const onNavRounds = useCallback(() => navigate(workbenchRoute('rounds')), [navigate]);

  if (auth.redirect) return auth.redirect;
  const user = auth.user!;
  const tabs = [
    { label: '入院诊断', count: pending?.summary.ddx_pending ?? 0 },
    { label: '用药', count: pending?.summary.med_pending ?? 0 },
    { label: '出院', count: pending?.summary.discharge_pending ?? 0 },
  ];
  const filteredPending = (pending?.pending ?? []).filter((patient) => {
    if (activeTab === 0) return patient.items.some((item) => item.type === 'ddx_confirm');
    if (activeTab === 1) return patient.items.some((item) => item.type === 'med_confirm');
    if (activeTab === 2) return patient.items.some((item) => item.type === 'discharge_sign');
    return patient.items.some((item) => item.type === 'discharge_sign');
  });

  return (
    <AppShell
      title="医生工作台"
      adminLink={ROUTES.admin}
      adminLabel="管理控制台"
      rightPanel={<RightPanel patients={patients?.patients} loading={patientsLoading} aiSummary={aiSummary} onNavigate={(id) => navigate(patientRoute(id))} />}
    >
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, maxWidth: 1380, mx: 'auto' }}>
        <WorkbenchHeader view={view} user={user} onCreate={(patientId) => navigate(patientRoute(patientId))} />
        <DepartmentLeadershipStrip />
        <ShiftSummary
          pending={pending?.summary.total_items ?? 0}
          alerts={alerts?.count ?? 0}
          highRisk={patients?.summary.high_risk ?? 0}
          dischargeReady={patients?.summary.discharge_ready ?? 0}
          onOpenPending={onNavToday}
          onOpenAlerts={onNavAlerts}
          onOpenHighRisk={onNavPatients}
          onOpenDischarge={onNavDischarge}
        />

        {view === 'today' ? <>
          {!alertsLoading && alerts && alerts.count > 0 ? <AlertBar alerts={alerts.alerts} onOpen={() => navigate(workbenchRoute('alerts'))} /> : null}
          {alertsError ? <Alert severity="warning" action={<Button color="inherit" size="small" onClick={() => void refetchAlerts()}>重试</Button>}>病区告警暂时无法加载，其他患者和审核功能仍可继续使用。</Alert> : null}
          <TodayActionQueue
            alerts={alerts?.alerts ?? []}
            pending={pending?.pending ?? []}
            patients={patients?.patients ?? []}
            onOpenPatient={(patientId) => navigate(patientRoute(patientId))}
            onOpenReview={(patient, item) => {
              setActiveTab(item.type === 'med_confirm' ? 1 : item.type === 'discharge_sign' ? 2 : 0);
              setSelectedReview({ patientId: patient.patient_id, reviewId: item.review_id });
            }}
            onOpenDischarge={(patientId) => navigate(dischargeRoute(patientId))}
          />
          <PendingQueue
            tabs={tabs}
            activeTab={activeTab}
            onTabChange={setActiveTab}
            patients={filteredPending}
            loading={pendingLoading}
            error={pendingError}
            onRetry={() => void refetchPending()}
            onSelect={(patient, item) => setSelectedReview({ patientId: patient.patient_id, reviewId: item.review_id })}
            onOpenRounds={onNavRounds}
            onOpenPatients={onNavPatients}
          />
        </> : null}
        {view === 'rounds' ? <WardClinicalBoard onOpenPatient={(id) => navigate(patientWorkspaceRoute(id, 'rounds'))} /> : null}
        {view === 'patients' ? <PatientDirectoryPanel onOpenPatient={(id) => navigate(patientRoute(id))} summary={overview.data ? { total: overview.data.total, pendingReviews: overview.data.pending_reviews, highRisk: overview.data.by_risk.high } : undefined} /> : null}
        {view === 'alerts' ? <WorkspacePanel title="临床告警" icon={<AlertTriangle size={18} />} description="按严重程度查看全病区未解决告警，进入患者后完成确认或处置。">{alertsLoading ? <Box sx={{ p: 2 }}><CardSkeleton height={220} /></Box> : alertsError ? <Box sx={{ p: 2 }}><ErrorBanner message="病区告警加载失败" onRetry={() => void refetchAlerts()} /></Box> : <AlertList alerts={alerts?.alerts ?? []} onNavigate={(id) => navigate(patientRoute(id))} />}</WorkspacePanel> : null}
        {view === 'discharge' ? <DischargeCoordinationView patients={patients?.patients ?? []} pending={pending?.pending ?? []} loading={patientsLoading || pendingLoading} onNavigate={(id) => navigate(dischargeRoute(id))} /> : null}
        {view === 'followup' ? <FollowUpOverviewPanel /> : null}
      </Box>
      <DiffPanel patient={selected.patient} item={selected.item} onClose={closeReview} onRefresh={async () => { await refetchPending(); }} />
    </AppShell>
  );
}

const VIEW_META: Record<DoctorWorkbenchView, { title: string; description: string }> = {
  followup: { title: '出院随访', description: '汇总出院患者的待随访、逾期、异常反馈和规则化再入院关注等级。' },
  today: { title: '今日工作', description: '先处理高风险告警与待审核事项，再进入患者诊疗。' },
  rounds: { title: '查房顺序', description: '按病情变化、NEWS2、告警和待审核状态组织本轮查房。' },
  patients: { title: '病区患者', description: '浏览本科室在院患者、风险分层与当前诊疗阶段。' },
  alerts: { title: '临床告警', description: '集中查看尚未解决的风险信号，并进入患者完成处置。' },
  discharge: { title: '出院协同', description: '查看准备出院和等待签署交接的患者。' },
};

function WorkbenchHeader({ view, user, onCreate }: { view: DoctorWorkbenchView; user: UserIdentity; onCreate: (patientId: string) => void }) {
  const meta = VIEW_META[view];
  return <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2, p: { xs: 2, md: 2.5 }, border: '1px solid', borderColor: 'divider', borderRadius: 1, bgcolor: 'background.paper', boxShadow: '0 1px 2px rgba(20, 40, 44, 0.025)' }}>
    <Box><Typography variant="h5" sx={{ fontFamily: 'var(--font-display)', fontWeight: 500 }}>{meta.title}</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 0.45 }}>{user.department || '当前科室'} · {meta.description}</Typography><WorkspaceWelcome user={user} workspace="doctor" /></Box>
    <Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}><Button size="small" variant="outlined" startIcon={<Bot size={16} />} onClick={() => emitOpenGlobalAssistant('doctor')}>{view === 'rounds' ? '查房助手' : '临床助手'}</Button><AdmissionLauncher onCreated={onCreate} /></Box>
  </Box>;
}

function ShiftSummary({ pending, alerts, highRisk, dischargeReady, onOpenPending, onOpenAlerts, onOpenHighRisk, onOpenDischarge }: {
  pending: number;
  alerts: number;
  highRisk: number;
  dischargeReady: number;
  onOpenPending: () => void;
  onOpenAlerts: () => void;
  onOpenHighRisk: () => void;
  onOpenDischarge: () => void;
}) {
  const items = [
    { label: '待医生审核', value: pending, tone: pending ? 'info.main' : 'text.primary', icon: ClipboardList, onOpen: onOpenPending },
    { label: '未解决告警', value: alerts, tone: alerts ? 'error.main' : 'text.primary', icon: AlertTriangle, onOpen: onOpenAlerts },
    { label: '高风险患者', value: highRisk, tone: highRisk ? 'warning.main' : 'text.primary', icon: Activity, onOpen: onOpenHighRisk },
    { label: '可进入出院协同', value: dischargeReady, tone: dischargeReady ? 'success.main' : 'text.primary', icon: CheckCircle2, onOpen: onOpenDischarge },
  ];
  return <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', xl: 'repeat(4, minmax(0, 1fr))' }, gap: 1.25 }}>
    {items.map((item) => <ButtonBase key={item.label} onClick={item.onOpen} aria-label={`查看${item.label}`} sx={{ display: 'block', textAlign: 'left', borderRadius: 1, overflow: 'hidden' }}><Card variant="outlined" sx={{ px: 1.75, py: 1.4, display: 'flex', gap: 1.15, alignItems: 'center', minWidth: 0, width: '100%', bgcolor: 'background.paper', '&:hover': { borderColor: 'primary.main', bgcolor: 'action.hover' } }}><Box sx={{ width: 34, height: 34, borderRadius: 1.2, display: 'grid', placeItems: 'center', bgcolor: item.tone === 'error.main' ? 'error.light' : item.tone === 'warning.main' ? 'warning.light' : item.tone === 'success.main' ? 'success.light' : 'info.light', color: item.tone }}><item.icon size={17} /></Box><Box><Typography variant="h6" color={item.tone}>{item.value}</Typography><Typography variant="caption" color="text.secondary">{item.label}</Typography></Box></Card></ButtonBase>)}
  </Box>;
}

function TodayActionQueue({ alerts, pending, patients, onOpenPatient, onOpenReview, onOpenDischarge }: {
  alerts: AlertItem[];
  pending: PendingPatient[];
  patients: WardPatient[];
  onOpenPatient: (patientId: string) => void;
  onOpenReview: (patient: PendingPatient, item: PendingItem) => void;
  onOpenDischarge: (patientId: string) => void;
}) {
  const criticalAlert = alerts.find((item) => item.severity === 'critical') ?? alerts[0];
  const pendingReview = pending.flatMap((patient) => patient.items.map((item) => ({ patient, item })))[0];
  const highRisk = patients.find((patient) => patient.risk_level === 'high');
  const dischargeCandidate = patients.find((patient) => patient.discharge_ready);
  const actions = [
    criticalAlert ? { key: `alert-${criticalAlert.alert_id}`, title: '优先核对病区临床告警', detail: `${criticalAlert.name}：${criticalAlert.message}`, label: '进入患者', tone: 'error' as const, onOpen: () => onOpenPatient(criticalAlert.patient_id) } : null,
    pendingReview ? { key: `review-${pendingReview.item.review_id}`, title: `完成${pendingReview.item.label}`, detail: `${pendingReview.patient.name} · ${pendingReview.patient.disease}`, label: '开始审核', tone: 'warning' as const, onOpen: () => onOpenReview(pendingReview.patient, pendingReview.item) } : null,
    highRisk ? { key: `risk-${highRisk.patient_id}`, title: '查看高风险患者本轮变化', detail: `${highRisk.name} · ${highRisk.disease}${highRisk.news2_score != null ? ` · NEWS2 ${highRisk.news2_score}` : ''}`, label: '进入患者', tone: 'warning' as const, onOpen: () => onOpenPatient(highRisk.patient_id) } : null,
    dischargeCandidate ? { key: `discharge-${dischargeCandidate.patient_id}`, title: '推进已达标患者的出院协同', detail: `${dischargeCandidate.name} · ${dischargeCandidate.disease}`, label: '进入出院', tone: 'success' as const, onOpen: () => onOpenDischarge(dischargeCandidate.patient_id) } : null,
  ].filter((item): item is NonNullable<typeof item> => Boolean(item)).slice(0, 3);

  if (!actions.length) return null;
  const current = actions[0];
  return <Card variant="outlined" sx={{ borderRadius: 1, overflow: 'hidden' }}>
    <Box sx={{ px: 1.75, py: 1.25, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}><CircleAlert size={18} /><Box><Typography variant="subtitle2" fontWeight={600}>本班优先路径</Typography><Typography variant="caption" color="text.secondary">按告警、医生审核、高风险患者和出院准备度排序。</Typography></Box></Box>
    <Box sx={{ p: 1.5, bgcolor: 'rgba(11, 100, 114, 0.035)', display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'minmax(0, 1fr) auto' }, gap: 1.25, alignItems: 'center' }}><Box><Chip size="small" color={current.tone} label="当前优先" sx={{ mb: 0.6 }} /><Typography variant="subtitle2">{current.title}</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 0.3 }}>{current.detail}</Typography></Box><Button variant="contained" color={current.tone === 'error' ? 'error' : 'primary'} endIcon={<ArrowRight size={15} />} onClick={current.onOpen}>{current.label}</Button></Box>
    {actions.slice(1).map((action, index) => <Box key={action.key} sx={{ px: 1.75, py: 1, display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr) auto', gap: 1, alignItems: 'center', borderTop: '1px solid', borderColor: 'divider' }}><Typography variant="caption" color="text.secondary">随后 {index + 1}</Typography><Box minWidth={0}><Typography variant="body2" fontWeight={600}>{action.title}</Typography><Typography variant="caption" color="text.secondary">{action.detail}</Typography></Box><Button size="small" variant="text" endIcon={<ArrowRight size={14} />} onClick={action.onOpen}>{action.label}</Button></Box>)}
  </Card>;
}

function PendingQueue({ tabs, activeTab, onTabChange, patients, loading, error, onRetry, onSelect, onOpenRounds, onOpenPatients }: {
  tabs: Array<{ label: string; count: number }>;
  activeTab: number;
  onTabChange: (value: number) => void;
  patients: PendingPatient[];
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  onSelect: (patient: PendingPatient, item: PendingItem) => void;
  onOpenRounds: () => void;
  onOpenPatients: () => void;
}) {
  return <WorkspacePanel title="待审核队列" icon={<ClipboardList size={18} />} description="仅展示需要医生确认的临床节点，提交后继续沿用现有审核和版本控制链路。">
    <Tabs value={activeTab} onChange={(_, value) => onTabChange(value)} sx={{ px: 1.5, borderBottom: '1px solid', borderColor: 'divider' }}>
      {tabs.map((tab) => <Tab key={tab.label} label={<Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>{tab.label}{tab.count > 0 ? <Chip label={tab.count} size="small" color="info" sx={{ height: 19, fontSize: 11 }} /> : null}</Box>} sx={{ textTransform: 'none', fontSize: 13, minWidth: 92 }} />)}
    </Tabs>
    {error ? <Box sx={{ p: 2 }}><ErrorBanner message="待审核队列加载失败" onRetry={onRetry} /></Box> : loading ? <Box sx={{ p: 2 }}><CardSkeleton height={220} /></Box> : patients.length === 0 ? <Box sx={{ minHeight: 190, display: 'grid', placeItems: 'center', p: 2 }}><Box sx={{ textAlign: 'center' }}><CheckCircle2 size={28} /><Typography variant="subtitle2" sx={{ mt: 1 }}>当前类别没有待审核事项</Typography><Box sx={{ display: 'flex', gap: 1, justifyContent: 'center', mt: 1.5 }}><Button size="small" variant="outlined" onClick={onOpenRounds}>进入查房顺序</Button><Button size="small" variant="text" onClick={onOpenPatients}>查看病区患者</Button></Box></Box></Box> : <Box>{patients.map((patient) => <PendingRow key={patient.patient_id} patient={patient} onSelect={(item) => onSelect(patient, item)} />)}</Box>}
  </WorkspacePanel>;
}

function WorkspacePanel({ title, icon, description, children }: { title: string; icon: React.ReactNode; description?: string; children: React.ReactNode }) {
  return <Card variant="outlined" sx={{ borderRadius: 1, overflow: 'hidden' }}><Box sx={{ px: 1.75, py: 1.35, display: 'flex', gap: 1, alignItems: 'flex-start', borderBottom: '1px solid', borderColor: 'divider' }}><Box sx={{ mt: 0.15 }}>{icon}</Box><Box><Typography variant="subtitle2" fontWeight={600}>{title}</Typography>{description ? <Typography variant="caption" color="text.secondary">{description}</Typography> : null}</Box></Box>{children}</Card>;
}

function DischargeCoordinationView({ patients, pending, loading, onNavigate }: { patients: WardPatient[]; pending: PendingPatient[]; loading: boolean; onNavigate: (id: string) => void }) {
  const pendingIds = new Set(pending.filter((patient) => patient.items.some((item) => item.type === 'discharge_sign')).map((patient) => patient.patient_id));
  const candidates = patients.filter((patient) => patient.discharge_ready || pendingIds.has(patient.patient_id) || patient.phase.includes('discharge') || patient.phase.includes('handoff'));
  return <WorkspacePanel title="出院协同队列" icon={<CheckCircle2 size={18} />} description="聚合已满足出院条件、进入交接阶段或等待医生签署的患者。">
    {loading ? <Box sx={{ p: 2 }}><CardSkeleton height={220} /></Box> : candidates.length === 0 ? <EmptyState icon="" title="暂无出院协同患者" description="患者达到出院条件后会出现在这里。" /> : <Box>{candidates.map((patient, index) => <Button key={patient.patient_id} color="inherit" onClick={() => onNavigate(patient.patient_id)} sx={{ width: '100%', px: 1.75, py: 1.35, justifyContent: 'flex-start', textAlign: 'left', textTransform: 'none', borderRadius: 0, borderBottom: index === candidates.length - 1 ? 0 : '1px solid', borderColor: 'divider' }}><Box sx={{ flex: 1, minWidth: 0 }}><Typography variant="body2" fontWeight={600}>{patient.name}</Typography><Typography variant="caption" color="text.secondary">{patient.disease} · {patient.phase}</Typography></Box><Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>{patient.discharge_ready ? <Chip size="small" color="success" label="条件达标" /> : null}{pendingIds.has(patient.patient_id) ? <Chip size="small" color="warning" label="待签署" /> : null}<ArrowRight size={16} /></Box></Button>)}</Box>}
  </WorkspacePanel>;
}

function AlertBar({ alerts, onOpen }: { alerts: AlertItem[]; onOpen: () => void }) {
  const top = alerts[0];
  return (
    <Alert severity={top?.severity === 'critical' ? 'error' : 'warning'} icon={<AlertTriangle size={19} />} action={<Chip label="查看告警" size="small" onClick={onOpen} clickable />}>
      {alerts.length} 条未解决告警 · {top?.name}：{top?.message}
    </Alert>
  );
}

function PendingRow({ patient, onSelect }: { patient: PendingPatient; onSelect: (item: PendingItem) => void }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, px: 2, py: 1.5, borderBottom: '1px solid', borderColor: 'divider' }}>
      <Box sx={{ width: 3, alignSelf: 'stretch', bgcolor: 'info.main' }} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="body2" fontWeight={600}>{patient.name}</Typography>
        <Typography variant="caption" color="text.secondary">{patient.disease} · {patient.phase}</Typography>
      </Box>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'flex-end', gap: 0.5 }}>
        {patient.items.map((item) => <Chip key={item.review_id} label={item.label} size="small" color="info" variant="outlined" onClick={() => onSelect(item)} clickable />)}
      </Box>
    </Box>
  );
}

function AlertList({ alerts, onNavigate }: { alerts: AlertItem[]; onNavigate: (patientId: string) => void }) {
  if (alerts.length === 0) return <EmptyState icon="" title="暂无未解决告警" description="病区当前没有需要关注的告警。" />;
  return (
    <Box>{alerts.map((alert, index) => {
      const Icon = alert.severity === 'critical' ? CircleAlert : alert.severity === 'warning' ? AlertTriangle : Info;
      const color = alert.severity === 'critical' ? 'error.main' : alert.severity === 'warning' ? 'warning.main' : 'info.main';
      return <Box key={`${alert.alert_id}:${alert.patient_id}:${index}`} role="button" tabIndex={0} onClick={() => onNavigate(alert.patient_id)} onKeyDown={(event) => { if (event.key === 'Enter') onNavigate(alert.patient_id); }} sx={{ display: 'flex', gap: 1.25, px: 2, py: 1.5, cursor: 'pointer', borderBottom: '1px solid', borderColor: 'divider', '&:hover': { bgcolor: 'action.hover' } }}><Icon size={18} color="currentColor" style={{ color: color, marginTop: 2 }} /><Box><Typography variant="body2" fontWeight={600}>{alert.name}</Typography><Typography variant="body2" color="text.secondary">{alert.message}</Typography></Box></Box>;
    })}</Box>
  );
}

function RightPanel({ patients, loading, aiSummary, onNavigate }: { patients?: WardPatient[]; loading: boolean; aiSummary?: { summary: string }; onNavigate: (patientId: string) => void }) {
  const [search, setSearch] = useState('');
  const visiblePatients = (patients ?? []).filter((patient) => `${patient.name} ${patient.disease}`.toLowerCase().includes(search.trim().toLowerCase()));
  return (
    <Box>
      {aiSummary?.summary ? <Box sx={{ mb: 2, pl: 1.25, borderLeft: '3px solid', borderColor: 'info.main' }}><Typography variant="caption" color="text.secondary" fontWeight={600}>AI 病区摘要</Typography><Typography variant="body2" sx={{ mt: 0.35, lineHeight: 1.6 }}>{aiSummary.summary}</Typography></Box> : null}
      <Box sx={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 1, mb: 1 }}><Typography variant="subtitle2" fontWeight={600}>患者快速切换</Typography><Typography variant="caption" color="text.secondary">{visiblePatients.length} 人</Typography></Box>
      <TextField value={search} onChange={(event) => setSearch(event.target.value)} size="small" fullWidth placeholder="按姓名或病种搜索" slotProps={{ input: { startAdornment: <Search size={16} style={{ marginRight: 8 }} /> } }} sx={{ mb: 1.5 }} />
      {loading ? <CardSkeleton height={200} /> : visiblePatients.length === 0 ? <Typography variant="body2" color="text.secondary">暂无匹配患者</Typography> : <Box sx={{ borderTop: '1px solid', borderColor: 'divider' }}>{visiblePatients.map((patient) => <Button key={patient.patient_id} color="inherit" onClick={() => onNavigate(patient.patient_id)} sx={{ width: '100%', px: 0.5, py: 1.05, justifyContent: 'flex-start', textAlign: 'left', textTransform: 'none', borderRadius: 0, borderBottom: '1px solid', borderColor: 'divider' }}><Box sx={{ flex: 1, minWidth: 0 }}><Typography variant="body2" fontWeight={600} noWrap>{patient.name}</Typography><Typography variant="caption" color="text.secondary" noWrap display="block">{patient.disease} · {patient.phase}{patient.news2_score != null ? ` · NEWS2 ${patient.news2_score}` : ''}</Typography></Box>{patient.alert_count ? <Chip size="small" color="warning" label={patient.alert_count} /> : patient.discharge_ready ? <Chip size="small" color="success" label="可出院" /> : null}</Button>)}</Box>}
    </Box>
  );
}
