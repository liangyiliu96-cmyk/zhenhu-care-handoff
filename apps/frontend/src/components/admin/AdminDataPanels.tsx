import { Alert, Box, Button, Card, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, IconButton, InputAdornment, LinearProgress, ListItemButton, MenuItem, Select, Stack, TextField, Tooltip, Typography } from '@mui/material';
import { AlertTriangle, Building2, ClipboardCheck, Database, HeartPulse, PlugZap, RefreshCw, Search, SearchCheck, ShieldCheck, Stethoscope, UsersRound, Zap } from 'lucide-react';
import { useMemo, useState } from 'react';

import { CardSkeleton, EmptyState, ErrorBanner } from '@/components/shared/Feedback';
import { useAdminWorkload, useCdsIntegrationStatus, useMaintenanceLog, useOrganization, useRagDashboard, useRagEntries, useRagSemanticPreview, useWardInsights } from '@/hooks/use-admin';
import { useWardAlertOverview, useWardVisitOrder } from '@/hooks/use-ward';
import { useNursingKpi, useShiftReport } from '@/hooks/use-nurse-management';
import type { AdminTabId } from '@/core/admin-tabs';
import { describeApiError } from '@/core/api-client';
import type { AdminWorkloadRow, MaintenanceTask, OrgStaffMember, RagEntry } from '@/types/admin';
import { nursePatientDisplayName } from '@/utils/nurse-patient-utils';
import { reindexKnowledge } from '@/services/admin-service';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import SystemOperationsPanel from './SystemOperationsPanel';
import DiseaseTemplatePanel from './DiseaseTemplatePanel';
import EvidenceGraphPanel from './EvidenceGraphPanel';

export default function AdminDataPanels({ tab, role, onOpenPatient }: { tab: Extract<AdminTabId, 'overview' | 'knowledge' | 'evidence_graph' | 'templates' | 'organization' | 'ward' | 'integrations' | 'operations'>; role: 'doctor' | 'nurse'; onOpenPatient?: (patientId: string) => void }) {
  if (tab === 'overview') return <ManagementOverviewPanel role={role} onOpenPatient={onOpenPatient} />;
  if (tab === 'operations') return <SystemOperationsPanel />;
  if (tab === 'integrations') return <IntegrationStatusPanel />;
  if (tab === 'knowledge') return <KnowledgePanel />;
  if (tab === 'evidence_graph') return <EvidenceGraphPanel />;
  if (tab === 'templates') return <DiseaseTemplatePanel />;
  if (tab === 'organization') return <OrganizationPanel />;
  return <WardManagementPanel onOpenPatient={onOpenPatient} />;
}

function ManagementOverviewPanel({ role, onOpenPatient }: { role: 'doctor' | 'nurse'; onOpenPatient?: (patientId: string) => void }) {
  const workload = useAdminWorkload();
  const insights = useWardInsights();
  const alerts = useWardAlertOverview();
  const organization = useOrganization();
  const handoff = useShiftReport(true);
  const nursingKpi = useNursingKpi(role === 'nurse');
  const visitOrder = useWardVisitOrder(role === 'doctor');
  if (workload.isLoading) return <CardSkeleton height={520} />;
  if (workload.error || !workload.data) return <ErrorBanner message="病区负荷数据加载失败" onRetry={() => void workload.refetch()} />;

  const summary = workload.data;
  const insight = insights.data;
  const leadership = organization.data?.leadership;
  const departmentName = organization.data?.your_department || leadership?.department || '当前科室';
  const department = summary.departments.find((item) => item.department === departmentName) ?? summary.departments[0];
  const focusPatients = handoff.data?.high_focus ?? [];
  const dischargePatients = handoff.data?.discharge_today ?? [];
  const alertRows = alerts.data?.alerts ?? [];
  const nurseQuality = nursingKpi.data;
  const roundingPatients = visitOrder.data?.visit_order ?? [];
  const unavailable = [
    insights.error ? '运营洞察' : '',
    alerts.error ? '风险告警' : '',
    organization.error ? '组织信息' : '',
    handoff.error ? '交接队列' : '',
    role === 'nurse' && nursingKpi.error ? '护理质控' : '',
    role === 'doctor' && visitOrder.error ? '查房排序' : '',
  ].filter(Boolean);
  const retryDegraded = () => {
    void insights.refetch();
    void alerts.refetch();
    void organization.refetch();
    void handoff.refetch();
    if (role === 'nurse') void nursingKpi.refetch();
    if (role === 'doctor') void visitOrder.refetch();
  };

  return <Stack spacing={2}>
    <Alert severity={summary.total_high_risk || summary.total_pending || alerts.data?.critical ? 'warning' : 'success'} icon={<ShieldCheck size={18} />}>{insight?.insight || '当前管理范围内暂无需要升级处理的风险事项。'}</Alert>
    {unavailable.length ? <Alert severity="warning" action={<Button color="inherit" size="small" onClick={retryDegraded}>重试</Button>}>{unavailable.join('、')}暂时不可用，其他管理数据仍可继续处理。</Alert> : null}
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', lg: 'repeat(4, minmax(0, 1fr))' }, gap: 1.5 }}>
      <Metric label="活跃患者" value={summary.total_active} icon={<UsersRound size={18} />} />
      <Metric label="高风险患者" value={summary.total_high_risk} icon={<AlertTriangle size={18} />} />
      <Metric label="待审核事项" value={summary.total_pending} icon={<ClipboardCheck size={18} />} />
      <Metric label="危急告警" value={alerts.data?.critical ?? 0} icon={<AlertTriangle size={18} />} />
    </Box>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1.2fr) minmax(340px, 0.8fr)' }, gap: 1.5, alignItems: 'start' }}>
      <Card variant="outlined" sx={{ borderRadius: 1 }}>
        <Box sx={{ px: 1.75, py: 1.2, display: 'flex', gap: 0.75, alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}><Building2 size={18} /><Box sx={{ minWidth: 0, flex: 1 }}><Typography variant="subtitle2" fontWeight={600}>{departmentName} 运行态势</Typography><Typography variant="caption" color="text.secondary">当前管理范围内的负荷与风险分布</Typography></Box><Chip size="small" color={department?.high_risk || department?.pending_review ? 'warning' : 'success'} label={department?.high_risk || department?.pending_review ? '需要关注' : '运行平稳'} /></Box>
        <Box sx={{ px: 1.75, py: 1.35, display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 1.25 }}>
          <OverviewValue label="在院" value={department ? `${department.active}/${department.total}` : '0/0'} />
          <OverviewValue label="体征逾期" value={department?.vital_overdue ?? 0} tone={department?.vital_overdue ? 'warning' : 'default'} />
          <OverviewValue label="待审核" value={department?.pending_review ?? 0} tone={department?.pending_review ? 'warning' : 'default'} />
          <OverviewValue label="告警" value={department?.total_alerts ?? 0} tone={department?.total_alerts ? 'error' : 'default'} />
        </Box>
        <Divider />
        <Box sx={{ px: 1.75, py: 1.25, display: 'flex', gap: 1.25, flexWrap: 'wrap' }}>
          <LeadershipValue label="科主任" member={leadership?.medical_director} />
          <LeadershipValue label="护士长" member={leadership?.head_nurse} />
          <LeadershipValue label="重点科室" member={insight?.top_departments[0] ? { name: insight.top_departments[0].department, title: `${insight.top_departments[0].patients} 名患者` } : undefined} />
        </Box>
      </Card>
      {role === 'nurse' ? <Card variant="outlined" sx={{ borderRadius: 1 }}>
        <Box sx={{ px: 1.5, py: 1.15, display: 'flex', gap: 0.75, alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}><HeartPulse size={18} /><Typography variant="subtitle2" fontWeight={600}>护理执行质量</Typography><Chip size="small" color={(nurseQuality?.overdue_tasks ?? 0) ? 'warning' : 'success'} label={`近 ${nurseQuality?.window_hours ?? 24} 小时`} sx={{ ml: 'auto' }} /></Box>
        <Box sx={{ p: 1.5, display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 1.25 }}>
          <OverviewValue label="完成任务" value={nurseQuality?.completed_tasks ?? 0} tone="success" />
          <OverviewValue label="开放任务" value={nurseQuality?.open_tasks ?? 0} tone={(nurseQuality?.open_tasks ?? 0) ? 'warning' : 'default'} />
          <OverviewValue label="逾期任务" value={nurseQuality?.overdue_tasks ?? 0} tone={(nurseQuality?.overdue_tasks ?? 0) ? 'error' : 'default'} />
          <OverviewValue label="完成率" value={`${Math.round((nurseQuality?.completion_rate ?? 0) * 100)}%`} tone="success" />
        </Box>
        {nurseQuality?.recent_completions.length ? <><Divider />{nurseQuality.recent_completions.slice(0, 3).map((item, index) => <ListItemButton key={item.id} onClick={() => onOpenPatient?.(item.patient_id)} disabled={!onOpenPatient} sx={{ px: 1.5, py: 0.85, borderBottom: index === Math.min(nurseQuality.recent_completions.length, 3) - 1 ? 0 : '1px solid', borderColor: 'divider' }}><Box sx={{ minWidth: 0 }}><Typography variant="body2" fontWeight={600}>{nursePatientDisplayName({ patient_id: item.patient_id, name: item.patient_name })}</Typography><Typography variant="caption" color="text.secondary">{item.title} · {item.completed_at}</Typography></Box></ListItemButton>)}</> : null}
      </Card> : <Card variant="outlined" sx={{ borderRadius: 1 }}>
        <Box sx={{ px: 1.5, py: 1.15, display: 'flex', gap: 0.75, alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}><Stethoscope size={18} /><Typography variant="subtitle2" fontWeight={600}>医疗决策状态</Typography><Chip size="small" color={summary.total_pending ? 'warning' : 'success'} label={summary.total_pending ? '有待审核事项' : '无待审核事项'} sx={{ ml: 'auto' }} /></Box>
        <Box sx={{ p: 1.5, display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 1.25 }}>
          <OverviewValue label="今日重点患者" value={focusPatients.length} tone={focusPatients.length ? 'warning' : 'success'} />
          <OverviewValue label="今日出院" value={dischargePatients.length} tone={dischargePatients.length ? 'info' : 'default'} />
          <OverviewValue label="管理科室" value={summary.total_departments} />
          <OverviewValue label="风险占比" value={department?.high_risk_ratio == null ? '--' : `${Math.round(department.high_risk_ratio * 100)}%`} tone={department?.high_risk ? 'warning' : 'success'} />
        </Box>
        {roundingPatients.length ? <><Divider />{roundingPatients.slice(0, 3).map((patient, index) => <ListItemButton key={patient.patient_id} onClick={() => onOpenPatient?.(patient.patient_id)} disabled={!onOpenPatient} sx={{ px: 1.5, py: 0.85, borderBottom: index === Math.min(roundingPatients.length, 3) - 1 ? 0 : '1px solid', borderColor: 'divider' }}><Box sx={{ minWidth: 0 }}><Typography variant="body2" fontWeight={600}>查房顺序 {index + 1} · {patient.name}</Typography><Typography variant="caption" color="text.secondary">风险 {patient.risk ?? '未分层'} · 告警 {patient.alerts} · NEWS2 {patient.news2 ?? '未评分'}</Typography></Box></ListItemButton>)}</> : null}
      </Card>}
    </Box>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1.1fr) minmax(320px, 0.9fr)' }, gap: 1.5, alignItems: 'start' }}>
      <Card variant="outlined" sx={{ borderRadius: 1 }}>
        <Box sx={{ px: 1.5, py: 1.15, display: 'flex', gap: 0.75, alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}><UsersRound size={18} /><Typography variant="subtitle2" fontWeight={600}>交接重点队列</Typography><Chip size="small" label={focusPatients.length} color={focusPatients.length ? 'warning' : 'default'} sx={{ ml: 'auto' }} /></Box>
        {focusPatients.length ? focusPatients.slice(0, 6).map((patient, index) => <ListItemButton key={patient.patient_id} onClick={() => onOpenPatient?.(patient.patient_id)} disabled={!onOpenPatient} sx={{ px: 1.5, py: 1.05, borderBottom: index === Math.min(focusPatients.length, 6) - 1 ? 0 : '1px solid', borderColor: 'divider' }}><Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center', flexWrap: 'wrap' }}><Typography variant="body2" fontWeight={600}>{patient.name}</Typography>{patient.alerts ? <Chip size="small" color="error" label={`${patient.alerts} 告警`} /> : null}</Box><Typography variant="caption" color="text.secondary">NEWS2 {patient.news2 ?? '未评分'}{patient.shift_summary ? ` · ${patient.shift_summary}` : ''}</Typography></ListItemButton>) : <Box sx={{ p: 1.5 }}><Typography variant="body2" color="text.secondary">当前没有进入重点交接队列的患者。</Typography></Box>}
      </Card>
      <Card variant="outlined" sx={{ borderRadius: 1 }}>
        <Box sx={{ px: 1.5, py: 1.15, display: 'flex', gap: 0.75, alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}><AlertTriangle size={18} /><Typography variant="subtitle2" fontWeight={600}>风险告警处置</Typography><Chip size="small" color={alerts.data?.critical ? 'error' : 'success'} label={`危急 ${alerts.data?.critical ?? 0}`} sx={{ ml: 'auto' }} /></Box>
        {alertRows.length ? alertRows.slice(0, 6).map((item, index) => <ListItemButton key={`${item.patient_id}:${index}`} onClick={() => onOpenPatient?.(item.patient_id)} disabled={!onOpenPatient} sx={{ px: 1.5, py: 1.05, borderBottom: index === Math.min(alertRows.length, 6) - 1 ? 0 : '1px solid', borderColor: 'divider' }}><Typography variant="body2" fontWeight={600}>{item.patient_name} · {item.disease}</Typography><Typography variant="caption" color={item.is_critical ? 'error.main' : 'text.secondary'}>{typeof item.alert === 'string' ? item.alert : String((item.alert as { message?: string })?.message ?? '临床告警')}</Typography></ListItemButton>) : <Box sx={{ p: 1.5 }}><Typography variant="body2" color="text.secondary">当前没有需要升级处理的病区告警。</Typography></Box>}
      </Card>
    </Box>
  </Stack>;
}

function OverviewValue({ label, value, tone = 'default' }: { label: string; value: string | number; tone?: 'default' | 'info' | 'success' | 'warning' | 'error' }) {
  return <Box sx={{ minWidth: 0 }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="h6" color={tone === 'default' ? 'text.primary' : `${tone}.main`} sx={{ mt: 0.3, overflowWrap: 'anywhere' }}>{value}</Typography></Box>;
}

function LeadershipValue({ label, member }: { label: string; member?: { name?: string; title?: string } | null }) {
  return <Box sx={{ minWidth: 120, flex: 1 }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="body2" fontWeight={600} sx={{ mt: 0.25 }}>{member?.name || '未配置'}</Typography><Typography variant="caption" color="text.secondary">{member?.title || '待维护'}</Typography></Box>;
}

function IntegrationStatusPanel() {
  const status = useCdsIntegrationStatus();
  if (status.isLoading) return <CardSkeleton height={300} />;
  if (status.error || !status.data) return <ErrorBanner message="临床集成状态加载失败" onRetry={() => void status.refetch()} />;
  const data = status.data;
  return <Stack spacing={2}>
    <Alert severity="success" icon={<ShieldCheck size={18} />}>{data.standard} 服务发现、处理器与患者访问控制均已就绪。</Alert>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 1fr))' }, gap: 1.5 }}>
      <Metric label="CDS 服务" value={data.service_count} icon={<PlugZap size={18} />} />
      <Metric label="运行环境" value={data.environment} icon={<Database size={18} />} />
      <Metric label="认证模式" value={data.auth_mode} icon={<ShieldCheck size={18} />} />
    </Box>
    <Card variant="outlined" sx={{ borderRadius: 1 }}>
      <Box sx={{ px: 1.5, py: 1.1, display: 'flex', gap: 0.75, alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}><PlugZap size={18} /><Typography variant="subtitle2" fontWeight={600}>CDS Hooks 服务</Typography><Chip size="small" color="success" label="已就绪" sx={{ ml: 'auto' }} /></Box>
      {data.services.map((service, index) => <Box key={service.id} sx={{ px: 1.5, py: 1.2, borderBottom: index === data.services.length - 1 ? 0 : '1px solid', borderColor: 'divider', display: 'grid', gridTemplateColumns: { xs: '1fr', md: '150px minmax(0, 1fr) 120px' }, gap: 1.25, alignItems: 'center' }}>
        <Box><Typography variant="body2" fontWeight={600}>{service.title}</Typography><Chip size="small" variant="outlined" label={service.hook} sx={{ mt: 0.5 }} /></Box>
        <Box sx={{ minWidth: 0 }}><Typography variant="body2" color="text.secondary">{service.description}</Typography><Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.35, overflowWrap: 'anywhere' }}>{service.endpoint}</Typography></Box>
        <Chip size="small" color={service.patient_access_enforced ? 'success' : 'info'} label={service.patient_access_enforced ? '患者权限校验' : '病区聚合'} />
      </Box>)}
    </Card>
    <Typography variant="caption" color="text.secondary">服务发现地址：{data.discovery_url}</Typography>
  </Stack>;
}

function KnowledgePanel() {
  const [entryDraft, setEntryDraft] = useState('');
  const [search, setSearch] = useState('');
  const [layer, setLayer] = useState('');
  const [previewDraft, setPreviewDraft] = useState('');
  const [previewQuery, setPreviewQuery] = useState('');
  const dashboard = useRagDashboard();
  const entries = useRagEntries(search, layer);
  const maintenance = useMaintenanceLog();
  const preview = useRagSemanticPreview(previewQuery, layer);
  const entryRows = useMemo(() => Object.entries(entries.data?.layers ?? {}).flatMap(([layerKey, group]) => (group.items ?? []).map((entry) => ({ layer: layerKey, entry }))), [entries.data]);
  const failedLayers = entries.data?.failed_layers ?? [];
  const runEntrySearch = () => {
    const nextSearch = entryDraft.trim();
    if (nextSearch === search) void entries.refetch();
    else setSearch(nextSearch);
  };
  const runPreview = () => {
    const nextQuery = previewDraft.trim();
    if (nextQuery.length < 2) return;
    if (nextQuery === previewQuery) void preview.refetch();
    else setPreviewQuery(nextQuery);
  };

  if (dashboard.isLoading || entries.isLoading || maintenance.isLoading) return <CardSkeleton height={360} />;
  if (dashboard.error || entries.error || maintenance.error) return <ErrorBanner message="知识库管理数据加载失败" onRetry={() => { void dashboard.refetch(); void entries.refetch(); void maintenance.refetch(); }} />;
  const data = dashboard.data;
  if (!data) return <EmptyState title="暂无知识库状态" />;

  const layerEntries = Object.entries(data.layers);
  const healthyLayers = layerEntries.filter(([, s]) => s.health === 'ok').length;
  const runtime = data.runtime;
  return <Stack spacing={2}>
    {/* 总体状态 */}
    {data.needs_attention
      ? <Alert severity="warning" icon={<AlertTriangle size={18} />}>发现 {data.issues.length} 项知识库完整性问题，请检查下方维护任务。</Alert>
      : <Alert severity="success">知识库 16 层索引正常 ({healthyLayers}/{layerEntries.length} 层健康)，共 {data.total_documents} 条知识。</Alert>}

    {/* 指标卡 */}
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(4, minmax(0, 1fr))' }, gap: 1.5 }}>
      <Metric label="索引文档" value={data.total_documents} icon={<Database size={18} />} />
      <Metric label="健康层数" value={`${healthyLayers}/${layerEntries.length}`} icon={<ShieldCheck size={18} />} />
      <Metric label="待维护" value={maintenance.data?.tasks?.length ?? 0} icon={<AlertTriangle size={18} />} />
      <Metric label="缓存后端" value={runtime?.cache.backend === 'redis' ? 'Redis' : '本地'} icon={<Zap size={18} />} />
    </Box>

    {runtime ? <Card variant="outlined" sx={{ p: 1.25, borderRadius: 1, bgcolor: 'action.hover' }}>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, minmax(0, 1fr))' }, gap: 1.25 }}>
        <RuntimeValue label="索引版本" value={`v${runtime.index_revision}`} />
        <RuntimeValue label="查询缓存" value={`${runtime.process_cache.search_hits} 命中 / ${runtime.process_cache.search_misses} 未命中`} />
        <RuntimeValue label="嵌入缓存" value={`${runtime.process_cache.embedding_hits} 命中 / ${runtime.process_cache.embedding_misses} 未命中`} />
        <RuntimeValue label="编码模型" value={`${runtime.model} · ${runtime.dimension}d`} />
      </Box>
    </Card> : null}

    {/* 分层热力图 + 维护任务 */}
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1.2fr) minmax(320px, 0.8fr)' }, gap: 2, alignItems: 'start' }}>
      <Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="subtitle2" fontWeight={600}>16 层知识热力图</Typography>
          <Typography variant="caption" color="text.secondary">点击层卡片筛选条目</Typography>
        </Box>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' }, gap: 1 }}>
          {layerEntries.map(([itemLayer, status]) => <LayerStatus key={itemLayer} layer={itemLayer} status={status} selected={layer === itemLayer} onSelect={() => setLayer((current) => current === itemLayer ? '' : itemLayer)} />)}
        </Box>
      </Box>
      {/* 维护任务 + 快捷操作 */}
      <Stack spacing={1.5}>
        <MaintenanceList tasks={maintenance.data?.tasks ?? []} />
        <QuickActions selectedLayer={layer} />
      </Stack>
    </Box>

    <Card variant="outlined" sx={{ borderRadius: 1 }}>
      <Box sx={{ px: 1.5, py: 1.1, borderBottom: '1px solid', borderColor: 'divider', display: 'flex', alignItems: 'center', gap: 0.75 }}>
        <SearchCheck size={18} /><Typography variant="subtitle2" fontWeight={600}>语义检索验证</Typography>
        {preview.data ? <Chip size="small" label={`${preview.data.count} 条 · ${preview.data.latency_ms} ms`} color="info" variant="outlined" sx={{ ml: 'auto' }} /> : null}
      </Box>
      <Box sx={{ p: 1.25 }}>
        <TextField value={previewDraft} onChange={(event) => setPreviewDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') runPreview(); }} size="small" fullWidth placeholder="输入临床问题验证真实召回" slotProps={{ input: { startAdornment: <InputAdornment position="start"><Search size={16} /></InputAdornment>, endAdornment: <InputAdornment position="end"><Tooltip title="执行语义检索"><span><IconButton size="small" aria-label="执行语义检索" disabled={previewDraft.trim().length < 2 || preview.isFetching} onClick={runPreview}><SearchCheck size={16} /></IconButton></span></Tooltip></InputAdornment> } }} />
        {preview.isFetching ? <LinearProgress sx={{ mt: 1 }} /> : null}
        {preview.error ? <Alert severity="error" sx={{ mt: 1 }} action={<Button color="inherit" size="small" onClick={runPreview}>重试</Button>}>{describeApiError(preview.error, '语义检索验证失败')}</Alert> : null}
        {preview.data && !preview.isFetching && preview.data.results.length === 0 ? <Alert severity="info" sx={{ mt: 1 }}>未召回匹配知识，请更换临床关键词或检查所选知识层。</Alert> : null}
        {preview.data?.results.length ? <Stack spacing={0.75} sx={{ mt: 1.25 }}>{preview.data.results.map((item, index) => <Box key={`${item.layer}:${item.topic}:${index}`} sx={{ pl: 1, borderLeft: '2px solid', borderColor: 'info.light' }}><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6, flexWrap: 'wrap' }}><Typography variant="body2" fontWeight={600}>{item.topic}</Typography><Chip size="small" label={item.layer ?? 'RAG'} variant="outlined" /><Typography variant="caption" color="text.secondary">相关度 {Math.round((item.score ?? 0) * 100)}%</Typography></Box><Typography variant="caption" color="text.secondary">{item.text}</Typography></Box>)}</Stack> : null}
      </Box>
    </Card>

    {/* 知识条目检索 */}
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
        <Typography variant="subtitle2" fontWeight={600}>知识条目浏览</Typography>
        <Typography variant="caption" color="text.secondary">当前匹配 {entryRows.length} 条知识源 · 显示前 20</Typography>
      </Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 150px', gap: 1, mb: 1.25 }}>
        <TextField value={entryDraft} onChange={(event) => setEntryDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') runEntrySearch(); }} size="small" fullWidth placeholder="按主题、内容、来源、病种或科室检索" slotProps={{ input: { startAdornment: <InputAdornment position="start"><Search size={16} /></InputAdornment>, endAdornment: <InputAdornment position="end"><Tooltip title="检索知识条目"><span><IconButton size="small" aria-label="检索知识条目" disabled={entries.isFetching} onClick={runEntrySearch}><Search size={16} /></IconButton></span></Tooltip></InputAdornment> } }} />
        <Select size="small" value={layer} displayEmpty onChange={(event) => setLayer(event.target.value)} inputProps={{ 'aria-label': '筛选知识层级' }}>
          <MenuItem value="">全部层级</MenuItem>
          {layerEntries.map(([l]) => <MenuItem key={l} value={l}>{l} ({data.layers[l]?.actual ?? data.layers[l]?.expected ?? 0})</MenuItem>)}
        </Select>
      </Box>
      {entries.isFetching ? <LinearProgress sx={{ mb: 1 }} /> : null}
      {failedLayers.length ? <Alert severity="warning" sx={{ mb: 1 }}>以下知识层查询失败：{failedLayers.join('、')}。已保留其余层结果，可重试或检查 Milvus 状态。</Alert> : null}
      {entryRows.length === 0 && !failedLayers.length
        ? <EmptyState title="暂无匹配知识条目" description="可调整检索词或层级筛选后重试。" />
        : <Card variant="outlined" sx={{ borderRadius: 1 }}>
            {entryRows.slice(0, 20).map(({ layer: l, entry }, index) => <KnowledgeEntry key={`${l}:${entry.id}:${index}`} layer={l} entry={entry} last={index === Math.min(entryRows.length, 20) - 1} />)}
          </Card>
      }
    </Box>
  </Stack>;
}

function QuickActions({ selectedLayer }: { selectedLayer: string }) {
  const queryClient = useQueryClient();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const reindex = useMutation({
    mutationFn: () => reindexKnowledge(selectedLayer ? [selectedLayer] : []),
    onSuccess: async () => {
      setConfirmOpen(false);
      await queryClient.invalidateQueries({ queryKey: ['admin', 'rag'] });
    },
  });

  return (
    <>
      <Box>
        <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 1 }}>快捷维护</Typography>
        <Card variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
          <Stack spacing={1}>
            <Button
              size="small"
              variant="outlined"
              color="warning"
              startIcon={<RefreshCw size={14} />}
              onClick={() => setConfirmOpen(true)}
              disabled={reindex.isPending}
              fullWidth
            >
              {reindex.isPending ? '索引重建中...' : selectedLayer ? `重建 ${selectedLayer} 索引` : '重新索引全部知识库'}
            </Button>
            {reindex.error && (
              <Typography variant="caption" color="error">
                {reindex.error instanceof Error ? reindex.error.message : '索引失败'}
              </Typography>
            )}
          </Stack>
        </Card>
      </Box>
      <Dialog open={confirmOpen} onClose={() => setConfirmOpen(false)}>
        <DialogTitle>重新索引知识库</DialogTitle>
        <DialogContent>
          <Typography variant="body2">确认重建{selectedLayer ? ` ${selectedLayer} 层` : '全部 16 层'}临床知识索引？索引期间该范围的检索可能暂时降级。</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            完成后会自动切换索引版本，旧检索缓存立即失效。
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmOpen(false)}>取消</Button>
          <Button color="warning" variant="contained" onClick={() => reindex.mutate()} disabled={reindex.isPending}>
            确认执行
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

function LayerStatus({ layer, status, selected, onSelect }: { layer: string; status: { actual?: number; expected?: number; health: string; category?: string; error?: string }; selected: boolean; onSelect: () => void }) {
  const color = status.health === 'ok' ? 'success' : status.health === 'error' ? 'error' : status.health === 'incomplete' ? 'warning' : 'default';
  const value = status.expected ? Math.min(100, Math.round(((status.actual ?? 0) / status.expected) * 100)) : 0;
  return <Card variant="outlined" onClick={onSelect} sx={{ p: 1.25, borderRadius: 1, cursor: 'pointer', borderColor: selected ? 'primary.main' : 'divider', bgcolor: selected ? 'action.selected' : 'background.paper' }}><Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, alignItems: 'center' }}><Typography variant="body2" fontWeight={600}>{layer} {status.category ? `· ${status.category}` : ''}</Typography><Chip size="small" color={color} label={status.health === 'ok' ? '正常' : status.health === 'incomplete' ? '待补全' : status.health === 'missing' ? '缺失' : '异常'} /></Box><Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>{status.error ?? `${status.actual ?? 0} / ${status.expected ?? 0} 条`}</Typography><LinearProgress variant="determinate" value={value} color={color === 'default' ? 'inherit' : color} sx={{ mt: 0.75, height: 4, borderRadius: 1 }} /></Card>;
}

function RuntimeValue({ label, value }: { label: string; value: string }) {
  return <Box sx={{ minWidth: 0 }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="body2" fontWeight={600} sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{value}</Typography></Box>;
}

function KnowledgeEntry({ layer, entry, last }: { layer: string; entry: RagEntry; last: boolean }) {
  return <Box sx={{ px: 1.5, py: 1.25, borderBottom: last ? 0 : '1px solid', borderColor: 'divider' }}><Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center', flexWrap: 'wrap' }}><Typography variant="body2" fontWeight={600}>{entry.topic || '未命名条目'}</Typography><Chip label={layer} size="small" variant="outlined" /></Box><Typography variant="caption" color="text.secondary">{[entry.category, entry.disease_id, entry.department].filter(Boolean).join(' · ') || '未标注分类'}</Typography>{entry.text ? <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, lineHeight: 1.55 }}>{entry.text}</Typography> : null}</Box>;
}

function MaintenanceList({ tasks }: { tasks: MaintenanceTask[] }) {
  return <Box><Typography variant="subtitle2" fontWeight={600} sx={{ mb: 1 }}>维护任务</Typography>{tasks.length === 0 ? <EmptyState title="暂无维护任务" /> : <Stack spacing={1}>{tasks.map((task, index) => <Card key={`${task.task}:${index}`} variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}><Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center' }}><Chip size="small" label={task.priority === 'high' ? '高优先级' : task.priority === 'low' ? '低优先级' : '提示'} color={task.priority === 'high' ? 'error' : task.priority === 'low' ? 'default' : 'info'} /><Typography variant="body2" fontWeight={600}>{task.task}</Typography></Box><Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>{task.detail}</Typography><Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}>{task.action}</Typography></Card>)}</Stack>}</Box>;
}

function OrganizationPanel() {
  const [search, setSearch] = useState('');
  const organization = useOrganization();
  if (organization.isLoading) return <CardSkeleton height={300} />;
  if (organization.error) return <ErrorBanner message="组织结构加载失败" onRetry={() => void organization.refetch()} />;
  const departments = organization.data?.departments ?? [];
  const normalizedSearch = search.trim().toLowerCase();
  const visibleDepartments = departments.filter((department) => !normalizedSearch || [department.department, ...department.doctors.flatMap((staff) => [staff.name, staff.title, staff.job_number]), ...department.nurses.flatMap((staff) => [staff.name, staff.title, staff.job_number])].some((value) => String(value ?? '').toLowerCase().includes(normalizedSearch)));
  return <Stack spacing={2}>
    <Alert severity="info" icon={<Building2 size={18} />}>{organization.data?.scope ?? '管理范围'} · {organization.data?.your_title ?? '管理人员'}</Alert>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 1fr))' }, gap: 1.5 }}>
      <Metric label="科室数量" value={departments.length} icon={<Building2 size={18} />} />
      <Metric label="人员总数" value={departments.reduce((sum, department) => sum + department.total, 0)} icon={<UsersRound size={18} />} />
      <Metric label="本属科室" value={organization.data?.your_department ?? '未指定'} icon={<Building2 size={18} />} />
    </Box>
    <TextField value={search} onChange={(event) => setSearch(event.target.value)} size="small" fullWidth placeholder="按科室、姓名、职称或工号搜索" slotProps={{ input: { startAdornment: <InputAdornment position="start"><Search size={16} /></InputAdornment> } }} />
    {visibleDepartments.length === 0 ? <EmptyState title={normalizedSearch ? '暂无匹配人员或科室' : '暂无可管理的组织结构'} /> : <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' }, gap: 1.5 }}>{visibleDepartments.map((department) => <Card key={department.department} variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}><Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, alignItems: 'center', mb: 1 }}><Typography variant="subtitle2" fontWeight={600}>{department.department}</Typography><Chip size="small" label={`${department.total} 人`} /></Box><Divider /><StaffGroup title="医疗线" staff={department.doctors} role="doctor" /><StaffGroup title="护理线" staff={department.nurses} role="nurse" /></Card>)}</Box>}
  </Stack>;
}

function StaffGroup({ title, staff, role }: { title: string; staff: OrgStaffMember[]; role: 'doctor' | 'nurse' }) {
  const ordered = [...staff].sort((left, right) => Number(Boolean(right.is_manager)) - Number(Boolean(left.is_manager)) || staffRank(left.title, role) - staffRank(right.title, role) || String(left.name ?? '').localeCompare(String(right.name ?? ''), 'zh-CN'));
  const Icon = role === 'doctor' ? Stethoscope : HeartPulse;
  const leader = ordered.find((member) => member.is_manager) ?? ordered[0];
  const members = leader ? ordered.filter((member) => member !== leader) : [];
  const teamLabel = role === 'doctor' ? '医疗组' : '责任班组';
  return <Box sx={{ mt: 1.4 }}><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.65 }}><Icon size={16} /><Typography variant="caption" color="text.secondary">{title} · {staff.length} 人</Typography></Box>{staff.length === 0 ? <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>暂无人员</Typography> : <Box sx={{ mt: 0.75, pl: 1.1, borderLeft: '2px solid', borderColor: role === 'doctor' ? 'info.light' : 'success.light' }}><Typography variant="caption" color="text.secondary">{leader?.is_manager ? (role === 'doctor' ? '科室负责人' : '护理负责人') : teamLabel}</Typography>{leader ? <Box sx={{ display: 'flex', gap: 0.65, alignItems: 'center', mt: 0.2, flexWrap: 'wrap' }}><Typography variant="body2" fontWeight={600}>{leader.name ?? leader.job_number ?? '未命名人员'}</Typography><Chip size="small" color={leader.is_manager ? 'info' : 'default'} variant={leader.is_manager ? 'filled' : 'outlined'} label={leader.title ?? (leader.is_manager ? '负责人' : teamLabel)} />{leader.specialty ? <Typography variant="caption" color="text.secondary">{leader.specialty}</Typography> : null}</Box> : null}{members.length ? <Box sx={{ mt: 0.8, display: 'flex', gap: 0.55, flexWrap: 'wrap' }}>{members.map((member, index) => <Chip key={`${member.job_number ?? member.name ?? title}:${index}`} size="small" variant="outlined" label={`${member.name ?? member.job_number ?? '未命名人员'}${member.title ? ` · ${member.title}` : ''}`} />)}</Box> : null}</Box>}</Box>;
}

function staffRank(title: string | undefined, role: 'doctor' | 'nurse') {
  const value = title ?? '';
  if (role === 'doctor') return value.includes('主任') ? 0 : value.includes('副主任') ? 1 : value.includes('主治') ? 2 : value.includes('住院') ? 3 : 4;
  return value.includes('护士长') ? 0 : value.includes('主管') ? 1 : value.includes('护师') ? 2 : value.includes('护士') ? 3 : 4;
}

function WardManagementPanel({ onOpenPatient }: { onOpenPatient?: (patientId: string) => void }) {
  const workload = useAdminWorkload();
  const insights = useWardInsights();
  const alerts = useWardAlertOverview();
  if (workload.isLoading) return <CardSkeleton height={300} />;
  if (workload.error || !workload.data) return <ErrorBanner message="病区负荷数据加载失败" onRetry={() => void workload.refetch()} />;
  const summary = workload.data;
  const insight = insights.data;
  const unavailable = [
    insights.error ? '运营洞察' : '',
    alerts.error ? '全病区告警' : '',
  ].filter(Boolean);
  const retryDegraded = () => {
    void insights.refetch();
    void alerts.refetch();
  };
  return <Stack spacing={2}>
    <Alert severity="info">{insight?.insight || '运营洞察暂不可用时，仍可依据当前病区负荷继续安排处置。'}</Alert>
    {unavailable.length ? <Alert severity="warning" action={<Button color="inherit" size="small" onClick={retryDegraded}>重试</Button>}>{unavailable.join('、')}暂时不可用，病区负荷数据仍可继续使用。</Alert> : null}
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(4, minmax(0, 1fr))' }, gap: 1.5 }}>
      <Metric label="活跃患者" value={summary.total_active} icon={<UsersRound size={18} />} />
      <Metric label="高风险" value={summary.total_high_risk} icon={<AlertTriangle size={18} />} />
      <Metric label="待审核" value={summary.total_pending} icon={<AlertTriangle size={18} />} />
      <Metric label="科室数量" value={summary.total_departments} icon={<Building2 size={18} />} />
    </Box>
    <DepartmentLoadBoard departments={summary.departments} />
    <Card variant="outlined" sx={{ borderRadius: 1 }}><Box sx={{ px: 1.5, py: 1.1, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}><AlertTriangle size={18} /><Typography variant="subtitle2" fontWeight={600}>全病区告警</Typography><Chip size="small" color={alerts.data?.critical ? 'error' : 'default'} label={`危急 ${alerts.data?.critical ?? 0}`} sx={{ ml: 'auto' }} /></Box>{alerts.error ? <Box sx={{ p: 1.25 }}><Typography variant="body2" color="text.secondary">告警数据暂时不可用，请使用上方重试恢复。</Typography></Box> : alerts.data?.alerts.length ? alerts.data.alerts.slice(0, 6).map((item, index) => <ListItemButton key={`${item.patient_id}-${index}`} onClick={() => onOpenPatient?.(item.patient_id)} disabled={!onOpenPatient} sx={{ px: 1.5, py: 1, borderBottom: index === Math.min(alerts.data.alerts.length, 6) - 1 ? 0 : '1px solid', borderColor: 'divider' }}><Typography variant="body2" fontWeight={600}>{item.patient_name} · {item.disease}</Typography><Typography variant="caption" color={item.is_critical ? 'error.main' : 'text.secondary'}>{typeof item.alert === 'string' ? item.alert : String((item.alert as { message?: string })?.message ?? '临床告警')}</Typography></ListItemButton>) : <Box sx={{ p: 1.5 }}><Typography variant="body2" color="text.secondary">当前没有需要升级的病区告警。</Typography></Box>}</Card>
    {insight?.top_departments.length ? <Card variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}><Typography variant="subtitle2" fontWeight={600}>重点科室负荷</Typography><Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mt: 1 }}>{insight.top_departments.slice(0, 3).map((department, index) => <Chip key={department.department} color={index === 0 ? 'warning' : 'default'} label={`${index + 1}. ${department.department} ${department.patients} 人`} />)}</Box></Card> : null}
    {summary.departments.length === 0 ? <EmptyState title="暂无病区负载记录" /> : <Card variant="outlined" sx={{ borderRadius: 1, overflow: 'auto' }}><Box component="table" sx={{ width: '100%', borderCollapse: 'collapse', minWidth: 780, '& th, & td': { textAlign: 'left', px: 1.5, py: 1.15, borderBottom: '1px solid', borderColor: 'divider', fontSize: 13 }, '& th': { color: 'text.secondary', fontWeight: 500, bgcolor: 'background.default' }, '& tr:last-child td': { borderBottom: 0 } }}><thead><tr><th>排名</th><th>科室</th><th>在院</th><th>高风险</th><th>待审核</th><th>体征逾期</th><th>告警</th><th>风险占比</th><th>逾期率</th></tr></thead><tbody>{summary.departments.map((department, index) => <tr key={department.department}><td>{index + 1}</td><td><Typography variant="body2" fontWeight={index < 3 ? 600 : 400}>{department.department}</Typography></td><td>{department.active}/{department.total}</td><td>{department.high_risk}</td><td>{department.pending_review}</td><td>{department.vital_overdue}</td><td>{department.total_alerts}</td><td>{percent(department.high_risk_ratio)}</td><td>{percent(department.overdue_ratio)}</td></tr>)}</tbody></Box></Card>}
  </Stack>;
}

function DepartmentLoadBoard({ departments }: { departments: AdminWorkloadRow[] }) {
  const ranked = departments.slice(0, 6);
  const maxLoad = Math.max(...ranked.map((department) => department.high_risk * 2 + department.pending_review * 2 + department.vital_overdue + department.total_alerts), 1);
  return <Card variant="outlined" sx={{ overflow: 'hidden' }}>
    <Box sx={{ px: 1.75, py: 1.35, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}><HeartPulse size={18} /><Box><Typography variant="subtitle2" fontWeight={600}>科室风险与负荷</Typography><Typography variant="caption" color="text.secondary">按高危、待审核、监测逾期与告警密度排序</Typography></Box><Chip size="small" label={`${departments.length} 个科室`} sx={{ ml: 'auto' }} /></Box>
    {ranked.length === 0 ? <EmptyState title="暂无科室负荷数据" /> : <Box>{ranked.map((department, index) => {
      const load = department.high_risk * 2 + department.pending_review * 2 + department.vital_overdue + department.total_alerts;
      const percentLoad = Math.round(load / maxLoad * 100);
      const tone = index === 0 && load > 0 ? 'error.main' : department.vital_overdue > 0 || department.pending_review > 0 ? 'warning.main' : 'success.main';
      return <Box key={department.department} sx={{ display: 'grid', gridTemplateColumns: 'minmax(150px, 0.65fr) minmax(230px, 1.5fr) minmax(160px, 0.75fr)', gap: 1.5, alignItems: 'center', px: 1.75, py: 1.25, borderBottom: index === ranked.length - 1 ? 0 : '1px solid', borderColor: 'divider' }}><Box sx={{ minWidth: 0 }}><Typography variant="body2" fontWeight={700} noWrap>{department.department}</Typography><Typography variant="caption" color="text.secondary">在院 {department.active}/{department.total} · 查房 {department.total_rounds ?? 0}</Typography></Box><Box><Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, mb: 0.5 }}><Typography variant="caption" color="text.secondary">综合负荷</Typography><Typography variant="caption" fontWeight={700} color={tone}>{percentLoad}</Typography></Box><Box sx={{ height: 7, borderRadius: 4, bgcolor: 'background.default', overflow: 'hidden' }}><Box sx={{ width: `${percentLoad}%`, height: '100%', borderRadius: 4, bgcolor: tone }} /></Box></Box><Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 0.5, flexWrap: 'wrap' }}>{department.high_risk ? <Chip size="small" color="error" label={`高危 ${department.high_risk}`} /> : null}{department.pending_review ? <Chip size="small" color="info" label={`待审 ${department.pending_review}`} /> : null}{department.vital_overdue ? <Chip size="small" color="warning" label={`逾期 ${department.vital_overdue}`} /> : <Chip size="small" variant="outlined" label={`告警 ${department.total_alerts}`} />}</Box></Box>;
    })}</Box>}
  </Card>;
}

function Metric({ label, value, icon }: { label: string; value: string | number; icon: React.ReactNode }) {
  return <Card variant="outlined" sx={{ p: 1.6, bgcolor: 'background.paper' }}><Box sx={{ display: 'flex', gap: 0.8, alignItems: 'center', color: 'primary.main' }}><Box sx={{ width: 32, height: 32, borderRadius: 1, display: 'grid', placeItems: 'center', bgcolor: 'primary.light' }}>{icon}</Box><Typography variant="caption" color="text.secondary">{label}</Typography></Box><Typography variant="h5" sx={{ mt: 0.85, overflowWrap: 'anywhere' }}>{value}</Typography></Card>;
}

function percent(value?: number) { return value == null ? '—' : `${Math.round(value * 100)}%`; }
