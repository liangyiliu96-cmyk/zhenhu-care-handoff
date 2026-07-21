import { Alert, Box, Button, Chip, CircularProgress, Divider, Drawer, Typography } from '@mui/material';
import { AlertTriangle, ClipboardCheck, HeartPulse, NotebookPen, X } from 'lucide-react';

import { EmptyState, ErrorBanner } from '@/components/shared/Feedback';
import EvidenceGraphPathPanel from '@/components/clinical/EvidenceGraphPathPanel';
import ClinicalBriefPanel from '@/components/clinical/ClinicalBriefPanel';
import AgentFlowPanel from '@/components/clinical/AgentFlowPanel';
import PatientAssistantPanel from '@/components/clinical/PatientAssistantPanel';
import WorkflowBriefsPanel from '@/components/clinical/WorkflowBriefsPanel';
import { useNursingRecords } from '@/hooks/use-nurse-management';
import { nursePatientDisplayName, riskLabel, riskColor } from '@/utils/nurse-patient-utils';
import type { NursePatientDetail, NurseTask, NursingTaskItem } from '@/types/nurse-management';

interface NursePatientDrawerProps {
  patient: NursePatientDetail | null;
  onClose: () => void;
  onRecord: (patient: NurseTask) => void;
  onComplete: (patient: NurseTask, task: NursingTaskItem) => void;
}

export default function NursePatientDrawer({ patient, onClose, onRecord, onComplete }: NursePatientDrawerProps) {
  const records = useNursingRecords(patient?.patient_id);
  const flags = patient?.bedside_flags;
  const vitals = patient?.latest_vital_values;
  const taskItems = patient?.task_items ?? [];

  return (
    <Drawer anchor="right" open={Boolean(patient)} onClose={onClose} PaperProps={{ sx: { width: { xs: '100%', sm: 520 }, maxWidth: '100%' } }}>
      {!patient ? null : <Box sx={{ height: '100%', overflow: 'auto', bgcolor: 'background.paper' }}>
        <Box sx={{ px: 2.25, py: 2, display: 'flex', gap: 1.25, alignItems: 'flex-start', borderBottom: '1px solid', borderColor: 'divider' }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="caption" color="text.secondary">护理患者详情</Typography>
            <Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center', flexWrap: 'wrap', mt: 0.35 }}>
              <Typography variant="h6" sx={{ fontWeight: 600 }}>{nursePatientDisplayName(patient)}</Typography>
              <Chip size="small" color={riskColor(patient.risk_level)} label={riskLabel(patient.risk_level)} />
            </Box>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.35 }}>{patient.disease} · {patient.department}</Typography>
          </Box>
          <Button aria-label="关闭患者详情" size="small" onClick={onClose} sx={{ minWidth: 34, px: 0.75 }}><X size={18} /></Button>
        </Box>

        <Box sx={{ p: 2.25, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 1 }}>
            <PatientMetric label="阶段" value={phaseLabel(patient.phase)} />
            <PatientMetric label="查房" value={`${patient.round_count ?? 0} 次`} />
            <PatientMetric label="待办" value={`${patient.open_task_count ?? taskItems.length} 项`} tone={(patient.open_task_count ?? taskItems.length) ? 'warning' : 'default'} />
            <PatientMetric label="告警" value={`${patient.alert_count} 条`} tone={patient.alert_count ? 'error' : 'default'} />
          </Box>

          <Box>
            <SectionTitle icon={<HeartPulse size={18} />} title="最近生命体征" />
            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 1, mt: 1 }}>
              <VitalItem label="血压" value={formatBp(vitals?.systolic, vitals?.diastolic)} />
              <VitalItem label="SpO2" value={formatUnit(vitals?.spo2, '%')} />
              <VitalItem label="体温" value={formatUnit(vitals?.temperature, 'C')} />
              <VitalItem label="体征趋势" value={flags?.vs_trend || '暂无趋势'} />
            </Box>
          </Box>

          {(flags?.complication_alerts?.length || flags?.pain_score != null || flags?.fall_risk) ? <Box>
            <SectionTitle icon={<AlertTriangle size={18} />} title="床旁风险提示" />
            <Box sx={{ mt: 1, display: 'flex', flexDirection: 'column', gap: 0.75 }}>
              {flags?.complication_alerts?.map((alert) => <Alert key={alert} severity="warning" icon={<AlertTriangle size={17} />}>{alert}</Alert>)}
              <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
                {flags?.pain_score != null ? <Chip size="small" variant="outlined" label={`疼痛 ${flags.pain_score}${flags.pain_location ? ` · ${flags.pain_location}` : ''}`} /> : null}
                {flags?.fall_risk ? <Chip size="small" variant="outlined" label={`跌倒风险 · ${flags.fall_risk}`} /> : null}
                {flags?.bmi != null ? <Chip size="small" variant="outlined" label={`BMI ${flags.bmi}`} /> : null}
              </Box>
            </Box>
          </Box> : null}

          <EvidenceGraphPathPanel patientId={patient.patient_id} compact framed={false} />
          <ClinicalBriefPanel patientId={patient.patient_id} compact />
          <AgentFlowPanel patientId={patient.patient_id} audience="nurse" />
          <PatientAssistantPanel
            patientId={patient.patient_id}
            title="床旁护理助手"
            assistantMode="nurse"
            availableModes={['nurse']}
          />
          <WorkflowBriefsPanel patientId={patient.patient_id} stateVersion={patient.state_version ?? 1} generatableKinds={['follow_up']} />
          <Divider />
          <Box>
            <SectionTitle icon={<ClipboardCheck size={18} />} title="当前护理任务" action={patient.writable ? <Button size="small" variant="outlined" startIcon={<NotebookPen size={15} />} onClick={() => onRecord(asNurseTask(patient))}>录护理</Button> : undefined} />
            {!patient.writable ? <Alert severity="info" sx={{ mt: 1 }}>该患者当前没有分配给本班的可执行护理任务，仅提供临床状态与护理记录查询。</Alert> : null}
            {taskItems.length === 0 ? <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>当前没有待完成的护理任务。</Typography> : <Box sx={{ mt: 0.75 }}>
              {taskItems.map((task, index) => <Box key={task.task_key} sx={{ py: 1.15, borderBottom: index === taskItems.length - 1 ? 0 : '1px solid', borderColor: 'divider', display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 1, alignItems: 'center' }}><Box sx={{ minWidth: 0 }}><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}><Chip size="small" color={task.priority === 'high' ? 'warning' : 'default'} variant="outlined" label={taskTypeLabel(task.task_type)} /><Typography variant="body2" fontWeight={600}>{task.title}</Typography></Box><Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>{task.description}</Typography></Box>{patient.writable ? <Button size="small" color="success" onClick={() => onComplete(asNurseTask(patient), task)}>完成</Button> : null}</Box>)}
            </Box>}
          </Box>

          <Divider />
          <Box>
            <SectionTitle icon={<NotebookPen size={18} />} title={`护理记录${records.data ? ` · ${records.data.total}` : ''}`} />
            {records.isLoading ? <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}><CircularProgress size={22} /></Box> : null}
            {records.error ? <Box sx={{ mt: 1 }}><ErrorBanner message="护理记录加载失败" onRetry={() => void records.refetch()} /></Box> : null}
            {!records.isLoading && !records.error && !(records.data?.records.length) ? <EmptyState icon="" title="暂无护理记录" description="完成护理记录后会在这里显示。" /> : null}
            {records.data?.records.slice().reverse().slice(0, 8).map((record, index) => <Box key={`${record.timestamp ?? 'record'}:${index}`} sx={{ py: 1.1, borderBottom: index === Math.min(records.data.records.length, 8) - 1 ? 0 : '1px solid', borderColor: 'divider' }}><Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center', flexWrap: 'wrap' }}><Typography variant="body2" fontWeight={600}>{record.nursing_actions || '护理记录'}</Typography>{record.source ? <Chip size="small" variant="outlined" label={record.source === 'agent' ? '智能建议' : '人工记录'} /> : null}</Box><Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.4 }}>{formatRecordTime(record.timestamp)}{record.intake_ml != null ? ` · 入量 ${record.intake_ml}ml` : ''}{record.output_ml != null ? ` · 出量 ${record.output_ml}ml` : ''}</Typography>{record.alerts?.length ? <Typography variant="caption" color="warning.main" sx={{ display: 'block', mt: 0.35 }}>{record.alerts.join('；')}</Typography> : null}</Box>)}
          </Box>
        </Box>
      </Box>}
    </Drawer>
  );
}

function asNurseTask(patient: NursePatientDetail): NurseTask {
  if (!patient.writable || patient.state_version == null) {
    console.warn('asNurseTask called on non-writable patient; returning safe mock task for display.', patient.patient_id);
    return {
      patient_id: patient.patient_id,
      state_version: 1,
      name: patient.name,
      disease: patient.disease,
      department: patient.department,
      risk_level: patient.risk_level,
      phase: patient.phase,
      round_count: patient.round_count,
      vital_signs_due: false,
      latest_vital_values: patient.latest_vital_values,
      alert_count: patient.alert_count,
      pending_nursing_actions: [],
      pending_medications: [],
      open_task_count: patient.open_task_count,
      task_items: patient.task_items,
      bedside_flags: patient.bedside_flags,
    };
  }
  return {
    patient_id: patient.patient_id,
    state_version: patient.state_version,
    name: patient.name,
    disease: patient.disease,
    department: patient.department,
    risk_level: patient.risk_level,
    phase: patient.phase,
    round_count: patient.round_count,
    vital_signs_due: patient.vital_signs_due ?? false,
    latest_vital_values: patient.latest_vital_values,
    alert_count: patient.alert_count,
    pending_nursing_actions: [],
    pending_medications: [],
    open_task_count: patient.open_task_count,
    task_items: patient.task_items,
    bedside_flags: patient.bedside_flags,
  };
}

function SectionTitle({ icon, title, action }: { icon: React.ReactNode; title: string; action?: React.ReactNode }) {
  return <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}><Box sx={{ color: 'text.secondary', display: 'flex' }}>{icon}</Box><Typography variant="subtitle2" fontWeight={600}>{title}</Typography><Box sx={{ ml: 'auto' }}>{action}</Box></Box>;
}

function PatientMetric({ label, value, tone = 'default' }: { label: string; value: string; tone?: 'default' | 'warning' | 'error' }) {
  return <Box sx={{ minWidth: 0 }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="body2" color={tone === 'default' ? 'text.primary' : `${tone}.main`} fontWeight={600} sx={{ mt: 0.25, overflowWrap: 'anywhere' }}>{value}</Typography></Box>;
}

function VitalItem({ label, value }: { label: string; value: string }) {
  return <Box sx={{ px: 1.1, py: 0.9, bgcolor: 'background.default', border: '1px solid', borderColor: 'divider', borderRadius: 1 }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="body2" fontWeight={600} sx={{ mt: 0.25 }}>{value}</Typography></Box>;
}

function phaseLabel(value?: string) { return ({ admission: '入院', monitoring: '住院', discharge: '出院', review: '审核', confirm: '确认' } as Record<string, string>)[value || ''] || '未知'; }
function taskTypeLabel(value: NursingTaskItem['task_type']) { return ({ vital_signs: '生命体征', nursing_action: '护理措施', medication: '用药核对', checklist: '制度执行' } as const)[value]; }
function formatUnit(value: number | null | undefined, unit: string) { return value == null ? '--' : `${value} ${unit}`; }
function formatBp(systolic?: number | null, diastolic?: number | null) { return systolic == null && diastolic == null ? '--' : `${systolic ?? '--'} / ${diastolic ?? '--'} mmHg`; }
function formatRecordTime(value?: string) { if (!value) return '时间未记录'; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }); }
