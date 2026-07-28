import { Alert, Box, Button, Card, Chip, CircularProgress, Dialog, DialogContent, DialogTitle, IconButton, Typography } from '@mui/material';
import { AlertTriangle, ArrowRight, CalendarCheck, CalendarClock, CheckCircle2, ClipboardList, HeartPulse, MessageSquareWarning, Phone, X } from 'lucide-react';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import AppShell from '@/components/layout/AppShell';
import { CardSkeleton, EmptyState, ErrorBanner } from '@/components/shared/Feedback';
import WorkspaceHeader from '@/components/shared/WorkspaceHeader';
import { useFollowUpOverview } from '@/hooks/use-follow-up';
import { fetchFollowUpContact } from '@/services/patient-service';
import { apiPatch } from '@/core/api-client';
import type { FollowUpOverviewFilter, FollowUpPatientOverview } from '@/types/follow-up';
const FILTERS: Array<{ value?: FollowUpOverviewFilter; label: string }> = [
  { label: '全部' }, { value: 'pending', label: '待随访' }, { value: 'overdue', label: '已逾期' },
  { value: 'abnormal', label: '异常反馈' }, { value: 'high_risk', label: '高关注' },
];
export default function FollowUpPage() {
  const [filter, setFilter] = useState<FollowUpOverviewFilter>();
  const [selected, setSelected] = useState<FollowUpPatientOverview | null>(null);
  const overview = useFollowUpOverview(filter);
  return (
    <AppShell title="随访协同">
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, maxWidth: 1380, mx: 'auto', width: '100%' }}>
        <WorkspaceHeader
          eyebrow="出院随访管理"
          title="随访协同"
          description="集中管理出院患者的随访任务、联系方式和风险关注等级。"
          icon={<CalendarCheck size={20} />}
        />
        {overview.isLoading ? <CardSkeleton height={420} /> : overview.error ? <ErrorBanner message="出院随访加载失败" onRetry={() => void overview.refetch()} /> : !overview.data ? null : (
          <>
            {/* ── 指标卡片 ── */}
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', lg: 'repeat(4, minmax(0, 1fr))' }, gap: 1.5 }}>
              <MetricCard label="待随访" value={overview.data.summary.pending_follow_ups} icon={<CalendarClock size={20} />} tone="info" active={filter === 'pending'} onClick={() => setFilter(f => f === 'pending' ? undefined : 'pending')} />
              <MetricCard label="已逾期" value={overview.data.summary.overdue_follow_ups} icon={<AlertTriangle size={20} />} tone="warning" active={filter === 'overdue'} onClick={() => setFilter(f => f === 'overdue' ? undefined : 'overdue')} />
              <MetricCard label="异常反馈" value={overview.data.summary.abnormal_feedbacks} icon={<MessageSquareWarning size={20} />} tone="error" active={filter === 'abnormal'} onClick={() => setFilter(f => f === 'abnormal' ? undefined : 'abnormal')} />
              <MetricCard label="高关注" value={overview.data.summary.high_readmission_risk} icon={<HeartPulse size={20} />} tone="error" active={filter === 'high_risk'} onClick={() => setFilter(f => f === 'high_risk' ? undefined : 'high_risk')} />
            </Box>
            {/* ── 筛选标签 ── */}
            <Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center', flexWrap: 'wrap' }}>
              {FILTERS.map(item => <Chip key={item.label} size="small" label={item.label} clickable color={filter === item.value ? 'info' : 'default'} variant={filter === item.value ? 'filled' : 'outlined'} onClick={() => setFilter(item.value)} />)}
              <Chip size="small" variant="outlined" label={`共 ${overview.data.pagination.returned} 人`} sx={{ ml: { lg: 'auto' } }} />
            </Box>
            {/* ── 患者列表 ── */}
            {overview.data.patients.length === 0 ? (
              <EmptyState icon="" title={filter ? '没有符合筛选条件的随访患者' : '暂无已出院随访任务'} description={filter ? '可切换筛选查看其他随访队列。' : '在患者出院协同页创建随访任务后，会自动汇总到这里。'} />
            ) : (
              <Card variant="outlined" sx={{ borderRadius: 1 }}>
                <Box sx={{ px: 2, py: 1.1, display: { xs: 'none', lg: 'grid' }, gridTemplateColumns: 'minmax(200px, 0.7fr) minmax(220px, 0.9fr) minmax(160px, 0.6fr) 100px', gap: 1.5, bgcolor: 'background.default', borderBottom: '1px solid', borderColor: 'divider' }}>
                  <ColHead>患者 · 诊断</ColHead>
                  <ColHead>随访任务</ColHead>
                  <ColHead>风险 · 联系方式</ColHead>
                  <ColHead align="right">操作</ColHead>
                </Box>
                {overview.data.patients.map((p, i) => (
                  <FollowUpRow key={p.patient_id} patient={p} last={i === overview.data.patients.length - 1} onOpen={() => setSelected(p)} />
                ))}
              </Card>
            )}
          </>
        )}
      </Box>
      {/* ── 患者详情抽屉 ── */}
      <PatientDetailDrawer patient={selected} onClose={() => setSelected(null)} />
    </AppShell>
  );
}
/* ───── 指标卡片 ───── */
function MetricCard({ label, value, icon, tone, active, onClick }: { label: string; value: number; icon: React.ReactNode; tone: string; active: boolean; onClick: () => void }) {
  return (
    <Card variant="outlined" onClick={onClick} sx={{ borderRadius: 1, p: 1.5, cursor: 'pointer', borderColor: active ? `${tone}.main` : 'divider', borderWidth: active ? 2 : 1, bgcolor: active ? `${tone}.light` : 'background.paper', '&:hover': { borderColor: `${tone}.main` } }}>
      <Box sx={{ display: 'flex', gap: 0.7, alignItems: 'center', color: 'text.secondary' }}>{icon}<Typography variant="caption">{label}</Typography></Box>
      <Typography variant="h4" color={`${tone}.main`} sx={{ mt: 0.6 }}>{value}</Typography>
    </Card>
  );
}
/* ───── 患者行 ───── */
function FollowUpRow({ patient, last, onOpen }: { patient: FollowUpPatientOverview; last: boolean; onOpen: () => void }) {
  const firstTask = patient.tasks.find(t => t.is_open) ?? patient.tasks[0];
  return (
    <Box onClick={onOpen} sx={{ px: 2, py: 1.35, display: { xs: 'flex', lg: 'grid' }, flexDirection: 'column', gridTemplateColumns: 'minmax(200px, 0.7fr) minmax(220px, 0.9fr) minmax(160px, 0.6fr) 100px', gap: { xs: 0.75, lg: 1.5 }, alignItems: 'center', borderBottom: last ? 0 : '1px solid', borderColor: 'divider', cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' } }}>
      <Box>
        <Typography variant="body2" fontWeight={600}>{patient.name}</Typography>
        <Typography variant="caption" color="text.secondary">{patient.disease} · {patient.department}</Typography>
      </Box>
      <Box>
        <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
          {patient.pending_task_count > 0 && <Chip size="small" color="info" label={`${patient.pending_task_count}项待办`} />}
          {patient.overdue_task_count > 0 && <Chip size="small" color="warning" label={`${patient.overdue_task_count}项逾期`} />}
          {patient.tasks.length === 0 && <Chip size="small" variant="outlined" label="未建随访" />}
        </Box>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.3 }}>
          {firstTask?.title ?? '请在出院协同页创建'} {patient.next_due_at ? `· 截止${fmtDate(patient.next_due_at)}` : ''}
        </Typography>
      </Box>
      <Box>
        <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
          <Chip size="small" color={riskColor(patient.readmission_risk)} label={riskLabel(patient.readmission_risk)} sx={{ height: 22, fontSize: 11 }} />
          {patient.contact.has_contact ? (
            <Chip size="small" color="success" variant="outlined" icon={<Phone size={11} />} label={patient.contact.masked_mobile_phone ?? '已授权'} sx={{ height: 22, fontSize: 11 }} />
          ) : (
            <Chip size="small" color="warning" variant="outlined" label="未授权" sx={{ height: 22, fontSize: 11 }} />
          )}
        </Box>
      </Box>
      <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Button size="small" endIcon={<ArrowRight size={15} />}>详情</Button>
      </Box>
    </Box>
  );
}
/* ───── 患者详情抽屉 ───── */
function PatientDetailDrawer({ patient, onClose }: { patient: FollowUpPatientOverview | null; onClose: () => void }) {
  const contact = useQuery({
    queryKey: ['patient', patient?.patient_id ?? '', 'follow-up-contact'],
    queryFn: () => fetchFollowUpContact(patient!.patient_id),
    enabled: !!patient?.patient_id,
    staleTime: 30_000,
  });
  const cd = contact.data?.contact;
  const qc = useQueryClient();
  const completeTask = useMutation({
    mutationFn: (taskId: string) => apiPatch(`/inpatient/${patient!.patient_id}/care/follow-up-tasks/${taskId}`, { status: 'completed', note: '随访完成' }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['follow-up'] }); qc.invalidateQueries({ queryKey: ['patient'] }); },
  });
  return (
    <Dialog open={!!patient} onClose={onClose} fullWidth maxWidth="sm">
      {patient && (
        <>
          <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <ClipboardList size={20} />
            <Box sx={{ flex: 1 }}>
              <Typography variant="h6" fontSize={18}>{patient.name}</Typography>
              <Typography variant="caption" color="text.secondary">{patient.disease} · {patient.department} · 出院状态：{patient.discharge_status}</Typography>
            </Box>
            <IconButton onClick={onClose} size="small"><X size={18} /></IconButton>
          </DialogTitle>
          <DialogContent sx={{ pt: '8px !important' }}>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {/* ── 联系方式（联通出院保存数据） ── */}
              <Card variant="outlined" sx={{ borderRadius: 1 }}>
                <Box sx={{ px: 1.75, py: 1.1, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}>
                  <Phone size={16} /><Typography variant="subtitle2" fontWeight={600}>联系方式</Typography>
                  {patient.contact.has_contact ? <Chip size="small" color="success" label="已登记" sx={{ ml: 'auto' }} /> : <Chip size="small" color="warning" label="未登记" sx={{ ml: 'auto' }} />}
                </Box>
                <Box sx={{ p: 1.75 }}>
                  {cd ? (
                    <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1.5 }}>
                      <Field label="联系电话" value={cd.mobile_phone ?? '—'} />
                      <Field label="备用联系人" value={cd.alternate_contact_name || '—'} />
                      <Field label="备用关系" value={cd.alternate_contact_relation || '—'} />
                      <Field label="备用电话" value={cd.alternate_contact_phone ?? '—'} />
                      <Field label="首选通道" value={cd.preferred_channel ?? patient.contact.preferred_channel ?? '电话'} />
                      <Field label="随访授权" value={cd.follow_up_consent ? '已授权' : '未授权'} />
                    </Box>
                  ) : patient.contact.has_contact ? (
                    <Typography variant="body2">联系电话：{patient.contact.masked_mobile_phone ?? '已脱敏'}</Typography>
                  ) : (
                    <Alert severity="info" sx={{ py: 0 }}>该患者出院时未登记随访联系方式。可在患者出院协同页补充。</Alert>
                  )}
                </Box>
              </Card>
              {/* ── 随访任务 ── */}
              <Card variant="outlined" sx={{ borderRadius: 1 }}>
                <Box sx={{ px: 1.75, py: 1.1, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}>
                  <CalendarClock size={16} /><Typography variant="subtitle2" fontWeight={600}>随访任务</Typography>
                  <Chip size="small" label={`${patient.tasks.length} 项`} sx={{ ml: 'auto' }} />
                </Box>
                <Box sx={{ p: 1.75 }}>
                  {patient.tasks.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">暂无随访任务。请在患者出院时创建随访计划。</Typography>
                  ) : (
                    patient.tasks.map(task => (
                      <Box key={task.id} sx={{ py: 1, borderBottom: '1px solid', borderColor: 'divider', '&:last-child': { borderBottom: 0 } }}>
                        <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', flexWrap: 'wrap' }}>
                          <Typography variant="body2" fontWeight={600}>{task.title}</Typography>
                          {task.is_open ? <Chip size="small" color="info" label="待完成" sx={{ height: 20, fontSize: 11 }} /> : <Chip size="small" variant="outlined" label="已完成" sx={{ height: 20, fontSize: 11 }} />}
                          {task.is_overdue && <Chip size="small" color="error" label="逾期" sx={{ height: 20, fontSize: 11 }} />}
                          {task.is_open ? <Button size="small" color="success" variant="outlined" startIcon={completeTask.isPending ? <CircularProgress size={12} /> : <CheckCircle2 size={13} />} onClick={() => completeTask.mutate(task.id)} disabled={completeTask.isPending} sx={{ ml: 'auto', minWidth: 0 }}>完成随访</Button> : null}
                        </Box>
                        <Typography variant="caption" color="text.secondary">
                          负责人：{task.assignee || '未指派'} · 截止：{task.due_at ? fmtDate(task.due_at) : '未设定'}
                        </Typography>
                        {task.note && <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.3 }}>{task.note}</Typography>}
                      </Box>
                    ))
                  )}
                </Box>
              </Card>
              {/* ── 风险关注 ── */}
              <Card variant="outlined" sx={{ borderRadius: 1 }}>
                <Box sx={{ px: 1.75, py: 1.1, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}>
                  <HeartPulse size={16} /><Typography variant="subtitle2" fontWeight={600}>风险关注等级</Typography>
                  <Chip size="small" color={riskColor(patient.readmission_risk)} label={riskLabel(patient.readmission_risk)} sx={{ ml: 'auto' }} />
                </Box>
                <Box sx={{ p: 1.75 }}>
                  {patient.risk_basis.length > 0 ? (
                    patient.risk_basis.map((item, i) => (
                      <Typography key={i} variant="body2" sx={{ fontSize: 12.5, lineHeight: 1.6 }}>• {item}</Typography>
                    ))
                  ) : (
                    <Typography variant="body2" color="text.secondary">暂无风险关注依据。</Typography>
                  )}
                </Box>
              </Card>
            </Box>
          </DialogContent>
        </>
      )}
    </Dialog>
  );
}
/* ───── 工具 ───── */
function Field({ label, value }: { label: string; value: string }) { return <Box><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="body2" fontWeight={500}>{value}</Typography></Box>; }
function ColHead({ children, align }: { children: React.ReactNode; align?: 'right' }) { return <Typography variant="caption" color="text.secondary" textAlign={align}>{children}</Typography>; }
function riskLabel(v: string) { return v === 'high' ? '高关注' : v === 'medium' ? '中关注' : '常规随访'; }
function riskColor(v: string): 'error' | 'warning' | 'success' { return v === 'high' ? 'error' : v === 'medium' ? 'warning' : 'success'; }
function fmtDate(v: string) { const d = new Date(v); return isNaN(d.getTime()) ? v : d.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
