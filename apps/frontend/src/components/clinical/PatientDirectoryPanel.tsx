import { Box, Button, Card, Chip, InputAdornment, MenuItem, TextField, Typography } from '@mui/material';
import { ChevronLeft, ChevronRight, Search } from 'lucide-react';
import { useDeferredValue, useEffect, useState } from 'react';

import { CardSkeleton, EmptyState, ErrorBanner } from '@/components/shared/Feedback';
import { usePatientDirectory } from '@/hooks/use-patient-directory';
import type { PatientDirectoryPhase, PatientDirectoryPatient, PatientDirectorySort } from '@/types/ward';

interface PatientDirectoryPanelProps {
  onOpenPatient: (patientId: string) => void;
  summary?: { total: number; pendingReviews: number; highRisk: number };
}

const PAGE_SIZE = 20;

export default function PatientDirectoryPanel({ onOpenPatient, summary }: PatientDirectoryPanelProps) {
  const [search, setSearch] = useState('');
  const [phase, setPhase] = useState<PatientDirectoryPhase | ''>('');
  const [risk, setRisk] = useState<'low' | 'medium' | 'high' | ''>('');
  const [sort, setSort] = useState<PatientDirectorySort>('risk');
  const [offset, setOffset] = useState(0);
  const deferredSearch = useDeferredValue(search);
  const directory = usePatientDirectory({ search: deferredSearch, phase: phase || undefined, risk_level: risk || undefined, sort, limit: PAGE_SIZE, offset });

  useEffect(() => setOffset(0), [deferredSearch, phase, risk, sort]);

  if (directory.isLoading) return <CardSkeleton height={380} />;
  if (directory.error || !directory.data) return <ErrorBanner message="患者目录加载失败" onRetry={() => void directory.refetch()} />;
  const { patients, pagination, total } = directory.data;
  const start = total === 0 ? 0 : pagination.offset + 1;
  const end = pagination.offset + patients.length;

  return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
    {summary ? <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}><Chip label={`在院 ${summary.total}`} size="small" variant="outlined" /><Chip label={`待审核 ${summary.pendingReviews}`} size="small" color={summary.pendingReviews ? 'warning' : 'default'} variant="outlined" /><Chip label={`高风险 ${summary.highRisk}`} size="small" color={summary.highRisk ? 'error' : 'default'} variant="outlined" /></Box> : null}
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(260px, 1fr) 140px 140px 130px' }, gap: 1 }}>
      <TextField size="small" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索患者、病种或病历号" slotProps={{ input: { startAdornment: <InputAdornment position="start"><Search size={16} /></InputAdornment> } }} />
      <TextField select size="small" label="阶段" value={phase} onChange={(event) => setPhase(event.target.value as PatientDirectoryPhase | '')}><MenuItem value="">全部阶段</MenuItem><MenuItem value="admission">入院</MenuItem><MenuItem value="monitoring">住院监测</MenuItem><MenuItem value="discharge">出院</MenuItem><MenuItem value="review">审核</MenuItem><MenuItem value="confirm">确认</MenuItem></TextField>
      <TextField select size="small" label="风险" value={risk} onChange={(event) => setRisk(event.target.value as typeof risk)}><MenuItem value="">全部风险</MenuItem><MenuItem value="high">高风险</MenuItem><MenuItem value="medium">中风险</MenuItem><MenuItem value="low">低风险</MenuItem></TextField>
      <TextField select size="small" label="排序" value={sort} onChange={(event) => setSort(event.target.value as PatientDirectorySort)}><MenuItem value="risk">风险优先</MenuItem><MenuItem value="phase">阶段</MenuItem><MenuItem value="name">姓名</MenuItem></TextField>
    </Box>
    {patients.length === 0 ? <EmptyState icon="" title="没有匹配的在院患者" description="可调整筛选条件，或确认当前科室的患者分配。" /> : <Card variant="outlined" sx={{ borderRadius: 1 }}>
      <Box sx={{ px: 1.75, py: 1, display: { xs: 'none', lg: 'grid' }, gridTemplateColumns: 'minmax(190px, 0.85fr) minmax(220px, 1fr) minmax(180px, 0.8fr) auto', gap: 1.5, bgcolor: 'background.default', borderBottom: '1px solid', borderColor: 'divider' }}><ColumnTitle>患者</ColumnTitle><ColumnTitle>诊疗状态</ColumnTitle><ColumnTitle>最近生命体征</ColumnTitle><ColumnTitle align="right">操作</ColumnTitle></Box>
      {patients.map((patient, index) => <DirectoryRow key={patient.patient_id} patient={patient} last={index === patients.length - 1} onOpen={() => onOpenPatient(patient.patient_id)} />)}
    </Card>}
    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}><Typography variant="caption" color="text.secondary">显示 {start}-{end} / {total} 名患者</Typography><Box sx={{ display: 'flex', gap: 0.5 }}><Button size="small" startIcon={<ChevronLeft size={15} />} disabled={offset === 0} onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}>上一页</Button><Button size="small" endIcon={<ChevronRight size={15} />} disabled={!pagination.has_more} onClick={() => setOffset((value) => value + PAGE_SIZE)}>下一页</Button></Box></Box>
  </Box>;
}

function DirectoryRow({ patient, last, onOpen }: { patient: PatientDirectoryPatient; last: boolean; onOpen: () => void }) {
  return <Box sx={{ px: 1.75, py: 1.25, display: { xs: 'flex', lg: 'grid' }, flexDirection: 'column', gridTemplateColumns: 'minmax(190px, 0.85fr) minmax(220px, 1fr) minmax(180px, 0.8fr) auto', gap: { xs: 0.75, lg: 1.5 }, alignItems: 'center', borderBottom: last ? 0 : '1px solid', borderColor: 'divider' }}><Box><Box sx={{ display: 'flex', gap: 0.65, alignItems: 'center', flexWrap: 'wrap' }}><Typography variant="body2" fontWeight={600}>{patient.name}</Typography><Chip size="small" color={riskColor(patient.risk_level)} label={riskLabel(patient.risk_level)} /></Box><Typography variant="caption" color="text.secondary">{patient.disease} · 查房 {patient.round_count} 次</Typography></Box><Box><Box sx={{ display: 'flex', gap: 0.6, flexWrap: 'wrap' }}><Chip size="small" variant="outlined" label={phaseLabel(patient.phase)} />{patient.has_pending_review ? <Chip size="small" color="warning" label="待审核" /> : null}{patient.alert_count ? <Chip size="small" color="error" label={`${patient.alert_count} 告警`} /> : null}</Box><Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.45 }}>病历记录 {patient.document_count} 项{patient.discharge_decision ? ` · ${patient.discharge_decision}` : ''}</Typography></Box><Typography variant="body2" color="text.secondary">BP {formatBp(patient.latest_vs.systolic, patient.latest_vs.diastolic)} · SpO2 {patient.latest_vs.spo2 ?? '--'}% · HR {patient.latest_vs.heart_rate ?? '--'}</Typography><Button size="small" onClick={onOpen} endIcon={<ChevronRight size={15} />}>进入患者</Button></Box>;
}

function ColumnTitle({ children, align }: { children: React.ReactNode; align?: 'right' }) { return <Typography variant="caption" color="text.secondary" textAlign={align}>{children}</Typography>; }
function riskLabel(value: string) { return value === 'high' ? '高风险' : value === 'medium' ? '中风险' : value === 'low' ? '低风险' : '未分层'; }
function riskColor(value: string): 'error' | 'warning' | 'success' | 'default' { return value === 'high' ? 'error' : value === 'medium' ? 'warning' : value === 'low' ? 'success' : 'default'; }
function phaseLabel(value: string) { return ({ admission: '入院', monitoring: '住院监测', discharge: '出院', review: '审核', confirm: '确认' } as Record<string, string>)[value] || value || '未知'; }
function formatBp(systolic?: number | null, diastolic?: number | null) { return systolic == null && diastolic == null ? '--' : `${systolic ?? '--'}/${diastolic ?? '--'}`; }
