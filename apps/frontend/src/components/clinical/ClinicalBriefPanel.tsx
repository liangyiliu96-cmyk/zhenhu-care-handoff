import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { AlertTriangle, ClipboardCheck, FlaskConical, MessageSquareText, Stethoscope } from 'lucide-react';
import { Alert, Box, Card, Chip, CircularProgress, Divider, Typography } from '@mui/material';

import { fetchClinicalBrief, type ClinicalBrief } from '@/services/clinical-brief-service';
import { ErrorBanner, EmptyState } from '@/components/shared/Feedback';
import { formatBriefValue, localizeClinicalText } from '@/utils/clinical-brief-utils';

interface ClinicalBriefPanelProps {
  patientId: string;
  compact?: boolean;
}

export default function ClinicalBriefPanel({ patientId, compact = false }: ClinicalBriefPanelProps) {
  const query = useQuery({ queryKey: ['clinical-brief', patientId], queryFn: () => fetchClinicalBrief(patientId), enabled: Boolean(patientId), refetchInterval: 30_000 });
  if (query.isLoading) return <Card variant="outlined" sx={{ p: 2, borderRadius: 1 }}><CircularProgress size={20} /></Card>;
  if (query.error || !query.data) return <ErrorBanner message="临床减负摘要加载失败" onRetry={() => void query.refetch()} />;
  const brief = query.data;
  return <Card variant="outlined" sx={{ borderRadius: 1, overflow: 'hidden' }}>
    <Header title="本轮临床摘要" icon={<Stethoscope size={18} />} caption="基于已记录数据自动归并，需结合原始病历判断" />
    <Box sx={{ p: 1.75, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      <Typography variant="body2" fontWeight={600}>{formatBriefValue(brief.round_preview.summary)}</Typography>
      {brief.round_preview.latest_vitals.length ? <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.65 }}>{brief.round_preview.latest_vitals.map((item) => <Chip key={item.label} size="small" variant="outlined" label={`${item.label} ${item.value}${item.unit || ''}`} />)}</Box> : null}
      <LineList title="查房核对点" items={brief.round_preview.focus_questions.map(localizeClinicalText)} />
      {brief.round_preview.pending_reviews.length ? <Alert severity="warning" icon={false} sx={{ py: 0.3 }}>{brief.round_preview.pending_reviews.map(localizeClinicalText).join('；')}</Alert> : null}
      {!compact ? <><Divider /><AlertGroups groups={brief.alert_groups} /><LabChanges changes={brief.lab_changes} /><HandoffAndDischarge brief={brief} /></> : null}
    </Box>
  </Card>;
}

function Header({ title, icon, caption }: { title: string; icon: ReactNode; caption?: string }) { return <Box sx={{ px: 1.75, py: 1.2, display: 'flex', gap: 0.75, alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}><Box>{icon}</Box><Box><Typography variant="subtitle2" fontWeight={600}>{title}</Typography>{caption ? <Typography variant="caption" color="text.secondary">{caption}</Typography> : null}</Box></Box>; }
function LineList({ title, items }: { title: string; items: string[] }) { return <Box><Typography variant="caption" color="text.secondary">{title}</Typography>{items.length ? items.map((item) => <Typography key={item} variant="body2" sx={{ mt: 0.35 }}>• {item}</Typography>) : <Typography variant="body2" color="text.secondary">暂无待核对事项</Typography>}</Box>; }
function AlertGroups({ groups }: { groups: ClinicalBrief['alert_groups'] }) { return <Box><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.65, mb: 0.65 }}><AlertTriangle size={16} /><Typography variant="subtitle2">异常归并与优先级</Typography></Box>{groups.length ? <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>{groups.map((group) => <Box key={group.key} sx={{ borderLeft: '3px solid', borderColor: group.urgency === 'high' ? 'error.main' : group.urgency === 'medium' ? 'warning.main' : 'divider', pl: 1 }}><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6 }}><Typography variant="body2" fontWeight={600}>{group.title}</Typography><Chip size="small" color={group.urgency === 'high' ? 'error' : group.urgency === 'medium' ? 'warning' : 'default'} label={`${group.count} 项`} /></Box><Typography variant="caption" color="text.secondary">{group.items.slice(0, 2).join('；')}</Typography></Box>)}</Box> : <EmptyState icon="" title="暂无需归并的告警" />}</Box>; }
function LabChanges({ changes }: { changes: ClinicalBrief['lab_changes'] }) { return <Box><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.65, mb: 0.65 }}><FlaskConical size={16} /><Typography variant="subtitle2">检验变化解读</Typography></Box>{changes.length ? changes.slice(0, 3).map((item) => <Box key={item.name} sx={{ py: 0.55, borderTop: '1px solid', borderColor: 'divider' }}><Typography variant="body2" fontWeight={600}>{item.name}：{item.previous} → {item.current} {item.unit}</Typography><Typography variant="caption" color="text.secondary">{item.direction === 'up' ? '上升' : '下降'} {Math.abs(item.delta)} · {item.recommendation}</Typography></Box>) : <Typography variant="body2" color="text.secondary">缺少同项目的连续检验结果，暂不生成趋势解读。</Typography>}</Box>; }
function HandoffAndDischarge({ brief }: { brief: ClinicalBrief }) { return <><Divider /><Box><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.65, mb: 0.65 }}><MessageSquareText size={16} /><Typography variant="subtitle2">交班与患者教育</Typography></Box><Typography variant="body2">{formatBriefValue(brief.handoff_brief.current_assessment)}</Typography><LineList title="下一班关注" items={brief.handoff_brief.unresolved_problems} /><LineList title="回授问题" items={brief.education_brief.teach_back_questions} /></Box><Box><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.65, mb: 0.65 }}><ClipboardCheck size={16} /><Typography variant="subtitle2">出院阻塞项</Typography></Box>{brief.discharge_blockers.length ? brief.discharge_blockers.map((item) => <Box key={item.reason} sx={{ py: 0.55, borderTop: '1px solid', borderColor: 'divider' }}><Typography variant="body2">{formatBriefValue(item.reason)}</Typography><Typography variant="caption" color="text.secondary">下一步：{formatBriefValue(item.action)}</Typography></Box>) : <Typography variant="body2" color="success.main">当前未发现规则化出院阻塞项。</Typography>}</Box></>; }
