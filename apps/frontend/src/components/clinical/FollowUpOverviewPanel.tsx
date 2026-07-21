import { Box, Button, ButtonBase, Card, Chip, Typography } from '@mui/material';
import { AlertTriangle, ArrowRight, CalendarClock, HeartPulse, MessageSquareWarning } from 'lucide-react';
import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';

import { CardSkeleton, EmptyState, ErrorBanner } from '@/components/shared/Feedback';
import { patientWorkspaceRoute } from '@/core/routes';
import { useFollowUpOverview } from '@/hooks/use-follow-up';
import type { FollowUpOverviewFilter, FollowUpPatientOverview } from '@/types/follow-up';

const FILTERS: Array<{ value?: FollowUpOverviewFilter; label: string }> = [
  { label: '全部' }, { value: 'pending', label: '待随访' }, { value: 'overdue', label: '已逾期' }, { value: 'abnormal', label: '异常反馈' }, { value: 'high_risk', label: '高关注' },
];

export default function FollowUpOverviewPanel() {
  const [filter, setFilter] = useState<FollowUpOverviewFilter>();
  const overview = useFollowUpOverview(filter);
  if (overview.isLoading) return <CardSkeleton height={360} />;
  if (overview.error || !overview.data) return <ErrorBanner message="出院随访总览加载失败" onRetry={() => void overview.refetch()} />;
  const { summary, patients } = overview.data;

  return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', lg: 'repeat(4, minmax(0, 1fr))' }, gap: 1.25 }}>
      <Metric label="待随访" value={summary.pending_follow_ups} icon={<CalendarClock size={18} />} tone={summary.pending_follow_ups ? 'info' : 'default'} onClick={() => setFilter('pending')} />
      <Metric label="已逾期" value={summary.overdue_follow_ups} icon={<AlertTriangle size={18} />} tone={summary.overdue_follow_ups ? 'warning' : 'default'} onClick={() => setFilter('overdue')} />
      <Metric label="异常反馈" value={summary.abnormal_feedbacks} icon={<MessageSquareWarning size={18} />} tone={summary.abnormal_feedbacks ? 'error' : 'default'} onClick={() => setFilter('abnormal')} />
      <Metric label="再入院高关注" value={summary.high_readmission_risk} icon={<HeartPulse size={18} />} tone={summary.high_readmission_risk ? 'error' : 'default'} onClick={() => setFilter('high_risk')} />
    </Box>
    <Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center', flexWrap: 'wrap' }}>
      {FILTERS.map((item) => <Chip key={item.label} size="small" label={item.label} clickable color={filter === item.value ? 'info' : 'default'} variant={filter === item.value ? 'filled' : 'outlined'} onClick={() => setFilter(item.value)} />)}
      <Typography variant="caption" color="text.secondary" sx={{ ml: { lg: 'auto' } }}>再入院关注等级基于住院风险、告警、既往住院史和多病共存规则汇总，不构成预测结论。</Typography>
    </Box>
    {patients.length === 0 ? <EmptyState icon="" title={filter ? '没有符合筛选条件的出院随访患者' : '暂无已出院随访任务'} description={filter ? '可切换筛选查看其他随访队列。' : '在患者协同页创建随访任务并完成出院后，会自动汇总到这里。'} /> : <Card variant="outlined" sx={{ borderRadius: 1 }}>
      <Box sx={{ px: 1.75, py: 1, display: { xs: 'none', lg: 'grid' }, gridTemplateColumns: 'minmax(200px, 0.8fr) minmax(250px, 1fr) minmax(180px, 0.75fr) auto', gap: 1.5, bgcolor: 'background.default', borderBottom: '1px solid', borderColor: 'divider' }}><ColumnTitle>患者</ColumnTitle><ColumnTitle>随访状态</ColumnTitle><ColumnTitle>风险与反馈</ColumnTitle><ColumnTitle align="right">操作</ColumnTitle></Box>
      {patients.map((patient, index) => <FollowUpRow key={patient.patient_id} patient={patient} last={index === patients.length - 1} />)}
    </Card>}
  </Box>;
}

function FollowUpRow({ patient, last }: { patient: FollowUpPatientOverview; last: boolean }) {
  const firstTask = patient.tasks.find((task) => task.is_open) ?? patient.tasks[0];
  const taskState = patient.pending_task_count ? <Chip size="small" color="info" label={`${patient.pending_task_count} 项待随访`} /> : patient.tasks.length ? <Chip size="small" variant="outlined" label="随访已完成" /> : <Chip size="small" color="warning" variant="outlined" label="未建随访" />;
  return <Box sx={{ px: 1.75, py: 1.25, display: { xs: 'flex', lg: 'grid' }, flexDirection: 'column', gridTemplateColumns: 'minmax(200px, 0.8fr) minmax(250px, 1fr) minmax(180px, 0.75fr) auto', gap: { xs: 0.75, lg: 1.5 }, alignItems: 'center', borderBottom: last ? 0 : '1px solid', borderColor: 'divider' }}><Box><Typography variant="body2" fontWeight={600}>{patient.name}</Typography><Typography variant="caption" color="text.secondary">{patient.disease} · {patient.department}</Typography></Box><Box><Box sx={{ display: 'flex', gap: 0.55, flexWrap: 'wrap' }}>{taskState}{patient.overdue_task_count ? <Chip size="small" color="warning" label={`${patient.overdue_task_count} 项逾期`} /> : null}</Box><Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.45 }}>{firstTask?.title ?? '请在协同页创建随访任务'}{patient.next_due_at ? ` · 截止 ${formatDate(patient.next_due_at)}` : ''}</Typography></Box><Box><Box sx={{ display: 'flex', gap: 0.55, flexWrap: 'wrap' }}><Chip size="small" color={riskColor(patient.readmission_risk)} label={riskLabel(patient.readmission_risk)} />{patient.contact.has_contact ? <Chip size="small" color="success" variant="outlined" label={patient.contact.masked_mobile_phone ?? '已授权联系'} /> : <Chip size="small" color="warning" variant="outlined" label="未授权联系" />}{patient.abnormal_feedback_count ? <Chip size="small" color="error" label={`${patient.abnormal_feedback_count} 条异常`} /> : null}</Box><Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.45 }}>{patient.risk_basis.join(' · ')}</Typography></Box><Button component={RouterLink} to={patientWorkspaceRoute(patient.patient_id, 'orders')} size="small" endIcon={<ArrowRight size={15} />}>进入随访协同</Button></Box>;
}

function Metric({ label, value, icon, tone, onClick }: { label: string; value: number; icon: React.ReactNode; tone: 'default' | 'info' | 'warning' | 'error'; onClick: () => void }) { return <ButtonBase onClick={onClick} aria-label={`筛选${label}`} sx={{ display: 'block', textAlign: 'left', borderRadius: 1, overflow: 'hidden' }}><Card variant="outlined" sx={{ p: 1.5, width: '100%', borderRadius: 1, '&:hover': { borderColor: 'primary.main', bgcolor: 'action.hover' } }}><Box sx={{ display: 'flex', gap: 0.7, alignItems: 'center', color: 'text.secondary' }}>{icon}<Typography variant="caption">{label}</Typography></Box><Typography variant="h5" color={tone === 'default' ? 'text.primary' : `${tone}.main`} sx={{ mt: 0.6 }}>{value}</Typography></Card></ButtonBase>; }
function ColumnTitle({ children, align }: { children: React.ReactNode; align?: 'right' }) { return <Typography variant="caption" color="text.secondary" textAlign={align}>{children}</Typography>; }
function riskLabel(value: string) { return value === 'high' ? '再入院高关注' : value === 'medium' ? '再入院中关注' : '常规随访'; }
function riskColor(value: string): 'error' | 'warning' | 'success' { return value === 'high' ? 'error' : value === 'medium' ? 'warning' : 'success'; }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false }); }
