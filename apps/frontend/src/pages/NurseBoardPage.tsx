import { Alert, Box, Button, Card, Chip, Typography } from '@mui/material';
import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ClipboardCheck, Clock3, GitCompare, HeartPulse, LayoutDashboard, ListChecks, UsersRound, type LucideIcon } from 'lucide-react';

import NurseManagementPanel from '@/components/admin/NurseManagementPanel';
import NursePatientDrawer from '@/components/clinical/NursePatientDrawer';
import { NurseShiftOverview } from '@/components/clinical/NurseWorkspacePanels';
import NursePatientDirectoryPanel from '@/components/clinical/NursePatientDirectoryPanel';
import AppShell from '@/components/layout/AppShell';
import WorkspaceHeader from '@/components/shared/WorkspaceHeader';
import WorkspaceWelcome from '@/components/shared/WorkspaceWelcome';
import DepartmentLeadershipStrip from '@/components/shared/DepartmentLeadershipStrip';
import { useMonitoringOverdue, useNurseTasks } from '@/hooks/use-nurse-management';
import { usePageAuth } from '@/hooks/use-page-auth';
import NursingEntryDialog from '@/components/clinical/NursingEntryDialog';
import NursingTaskCompletionDialog, { type NursingTaskSelection } from '@/components/clinical/NursingTaskCompletionDialog';
import { nurseBoardTab, type NurseBoardTab } from '@/core/nurse-workspace';
import { emitOpenGlobalAssistant } from '@/core/runtime-events';
import type { MonitoringOverduePatient, NursePatientDetail, NurseTask } from '@/types/nurse-management';

const VIEW_CONFIG: Array<{ id: NurseBoardTab; label: string; description: string; icon: LucideIcon; panel?: 'nursing' | 'handoff' | 'checklist' }> = [
  { id: 'overview', label: '班次总览', description: '先处理高优先级护理任务，再核对监测风险和交班重点。', icon: LayoutDashboard },
  { id: 'tasks', label: '护理任务', description: '按患者风险和任务优先级完成生命体征、护理措施与用药核对。', icon: ClipboardCheck, panel: 'nursing' },
  { id: 'patients', label: '在院患者', description: '按患者查看护理状态、床旁风险、最近体征和护理记录。', icon: UsersRound },
  { id: 'overdue', label: '逾期监测', description: '集中处理超过监测周期的患者，优先补录严重逾期体征。', icon: Clock3 },
  { id: 'shift', label: '交接班', description: '核对智能交班摘要、重点患者、今日出院及稳定患者队列。', icon: GitCompare, panel: 'handoff' },
  { id: 'checklist', label: '制度执行', description: '根据本班患者任务、逾期监测与护理记录完成制度闭环。', icon: ListChecks, panel: 'checklist' },
];

export default function NurseBoardPage() {
  const auth = usePageAuth('nurse');
  const [searchParams] = useSearchParams();
  const activeTab = nurseBoardTab(searchParams.get('tab'));
  const tasks = useNurseTasks(true);
  const overdue = useMonitoringOverdue(activeTab === 'overdue');
  const [recordingTask, setRecordingTask] = useState<NurseTask | null>(null);
  const [completingTask, setCompletingTask] = useState<NursingTaskSelection | null>(null);
  const [selectedPatient, setSelectedPatient] = useState<NursePatientDetail | null>(null);

  if (auth.redirect) return auth.redirect;
  const config = VIEW_CONFIG.find((tab) => tab.id === activeTab)!;
  const ActiveIcon = config.icon;
  const status = activeTab === 'overview' || activeTab === 'tasks'
    ? tasks.data?.open_task_count ?? tasks.data?.total
    : activeTab === 'overdue'
      ? overdue.data?.total
      : undefined;
  const statusLabel = status == null
    ? undefined
    : activeTab === 'overview' || activeTab === 'tasks'
      ? `待处理 ${status}`
      : activeTab === 'overdue'
        ? `逾期 ${status} 人`
        : undefined;
  const statusColor = activeTab === 'overdue' && (status ?? 0) > 0
    ? 'error'
    : 'info';
  const openPatient = (patient: NurseTask | NursePatientDetail) => setSelectedPatient('writable' in patient ? patient : { ...patient, writable: true });
  const openPatientById = (patientId: string) => {
    const task = tasks.data?.tasks.find((item) => item.patient_id === patientId);
    if (task) {
      setSelectedPatient({ ...task, writable: true });
      return;
    }
    const overduePatient = overdue.data?.patients.find((item) => item.patient_id === patientId);
    if (overduePatient) setSelectedPatient({ ...asNursingTask(overduePatient), writable: true });
  };

  return (
    <AppShell title="护理看板">
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, maxWidth: 1380, mx: 'auto', width: '100%' }}>
        <WorkspaceHeader
          eyebrow="护理工作台 / 当前班次"
          title={config.label}
          description={config.description}
          icon={<ActiveIcon size={20} />}
          tags={[auth.user?.department || '当前科室']}
          status={statusLabel ? <Chip size="small" color={statusColor} label={statusLabel} /> : undefined}
          actions={<Button size="small" variant="outlined" startIcon={<HeartPulse size={16} />} onClick={() => emitOpenGlobalAssistant('nurse')}>护理助手</Button>}
          welcome={auth.user ? <WorkspaceWelcome user={auth.user} workspace="nurse" /> : undefined}
        />
        <DepartmentLeadershipStrip />
        {activeTab === 'overview' ? <NurseShiftOverview tasks={tasks.data} loading={tasks.isLoading} error={tasks.error} onRetry={() => void tasks.refetch()} onOpenPatient={openPatient} onRecord={setRecordingTask} onComplete={(patient, task) => setCompletingTask({ patient, task })} /> : null}
        {activeTab === 'patients' ? <NursePatientDirectoryPanel tasks={tasks.data} tasksError={tasks.error} onOpenPatient={openPatient} onRecord={setRecordingTask} /> : null}
        {activeTab === 'overdue' ? <MonitoringOverduePanel patients={overdue.data?.patients} critical={overdue.data?.critical_overdue ?? 0} loading={overdue.isLoading} error={overdue.error} onRetry={() => void overdue.refetch()} onRecord={setRecordingTask} onOpenPatient={openPatientById} fallbackTasks={tasks.data?.tasks ?? []} /> : null}
        {activeTab === 'tasks' || activeTab === 'shift' || activeTab === 'checklist' ? <NurseManagementPanel tab={config.panel!} onOpenPatient={openPatientById} onRecordNursing={activeTab === 'tasks' || activeTab === 'checklist' ? setRecordingTask : undefined} onCompleteTask={activeTab === 'tasks' || activeTab === 'checklist' ? (patient, task) => setCompletingTask({ patient, task }) : undefined} /> : null}
      </Box>
      <NursingEntryDialog task={recordingTask} onClose={() => setRecordingTask(null)} />
      <NursingTaskCompletionDialog selection={completingTask} onClose={() => setCompletingTask(null)} />
      <NursePatientDrawer patient={selectedPatient} onClose={() => setSelectedPatient(null)} onRecord={setRecordingTask} onComplete={(patient, task) => setCompletingTask({ patient, task })} />
    </AppShell>
  );
}

function MonitoringOverduePanel({ patients, critical, loading, error, onRetry, onRecord, onOpenPatient, fallbackTasks }: { patients?: MonitoringOverduePatient[]; critical: number; loading: boolean; error: unknown; onRetry: () => void; onRecord: (task: NurseTask) => void; onOpenPatient: (patientId: string) => void; fallbackTasks: NurseTask[] }) {
  if (loading) return <Card variant="outlined" sx={{ p: 2, borderRadius: 1 }}><Typography color="text.secondary">正在加载逾期监测队列...</Typography></Card>;
  if (error) {
    const dueTasks = fallbackTasks.filter((task) => task.vital_signs_due);
    return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}><Alert severity="warning" action={<Button color="inherit" size="small" onClick={onRetry}>重试</Button>}>逾期服务暂时不可用。以下体征待测患者仍可直接补录护理，恢复后会显示精确逾期时长。</Alert>{dueTasks.length ? <Card variant="outlined" sx={{ borderRadius: 1 }}>{dueTasks.map((task, index) => <Box key={task.patient_id} sx={{ px: 1.75, py: 1.2, display: 'flex', gap: 1, alignItems: 'center', borderBottom: index === dueTasks.length - 1 ? 0 : '1px solid', borderColor: 'divider' }}><Box sx={{ flex: 1, minWidth: 0 }}><Button size="small" sx={{ p: 0, minWidth: 0, fontWeight: 600 }} onClick={() => onOpenPatient(task.patient_id)}>{task.name}</Button><Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{task.disease} · 体征待测</Typography></Box><Button size="small" variant="outlined" onClick={() => onRecord(task)}>补录护理</Button></Box>)}</Card> : <Alert severity="info">当前护理任务中没有标记为体征待测的患者。</Alert>}</Box>;
  }
  if (!patients?.length) return <Alert severity="success">当前没有逾期未上报的体征。</Alert>;
  const sortedPatients = [...patients].sort((left, right) => right.overdue_by_hours - left.overdue_by_hours);
  const withAlerts = patients.filter((patient) => patient.alert_count > 0).length;
  return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 1fr))' }, gap: 1.5 }}>
      <OverdueMetric label="逾期患者" value={patients.length} tone="info" />
      <OverdueMetric label="严重逾期" value={critical} tone={critical ? 'error' : 'default'} />
      <OverdueMetric label="伴随告警" value={withAlerts} tone={withAlerts ? 'warning' : 'default'} />
    </Box>
    <Card variant="outlined" sx={{ borderRadius: 1 }}>
    <Box sx={{ px: 2, py: 1.25, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}><Clock3 size={18} /><Typography variant="subtitle2" fontWeight={600}>逾期监测队列</Typography><Chip size="small" color={critical ? 'error' : 'warning'} label={`严重逾期 ${critical}`} sx={{ ml: 'auto' }} /></Box>
    {sortedPatients.map((patient, index) => <Box key={patient.patient_id} sx={{ display: 'grid', gridTemplateColumns: { xs: 'minmax(0, 1fr) auto', md: 'minmax(180px, 1fr) minmax(220px, 1.2fr) auto auto' }, alignItems: 'center', gap: 1.5, px: 2, py: 1.25, borderBottom: index === sortedPatients.length - 1 ? 0 : '1px solid', borderColor: 'divider' }}><Box sx={{ minWidth: 0 }}><Button size="small" sx={{ p: 0, minWidth: 0, fontWeight: 600 }} onClick={() => onOpenPatient(patient.patient_id)}>{patient.name}</Button><Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{patient.disease} · {patient.department}</Typography></Box><Box sx={{ minWidth: 0, display: { xs: 'none', md: 'block' } }}><Typography variant="body2" color={patient.overdue_by_hours >= 4 ? 'error.main' : 'text.primary'}>已逾期 {patient.overdue_by_hours} 小时</Typography><Typography variant="caption" color="text.secondary">上次记录 {patient.hours_since_last_vs} 小时前 · 周期 {patient.monitoring_interval_hours} 小时</Typography></Box>{patient.alert_count ? <Chip size="small" color="warning" label={`${patient.alert_count} 告警`} /> : <Chip size="small" variant="outlined" label="无伴随告警" sx={{ display: { xs: 'none', md: 'inline-flex' } }} />}<Button size="small" variant="outlined" onClick={() => onRecord(asNursingTask(patient))}>补录护理</Button></Box>)}
    </Card>
  </Box>;
}

function OverdueMetric({ label, value, tone }: { label: string; value: number; tone: 'info' | 'error' | 'warning' | 'default' }) {
  return <Card variant="outlined" sx={{ p: 1.5, borderRadius: 1, borderColor: tone === 'default' ? 'divider' : `${tone}.light` }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="h5" color={tone === 'default' ? 'text.primary' : `${tone}.main`} sx={{ mt: 0.5 }}>{value}</Typography></Card>;
}

function asNursingTask(patient: MonitoringOverduePatient): NurseTask {
  return { patient_id: patient.patient_id, state_version: patient.state_version, name: patient.name, disease: patient.disease, department: patient.department, risk_level: patient.risk_level, vital_signs_due: true, alert_count: patient.alert_count, pending_nursing_actions: [], pending_medications: [] };
}
