import { Alert, Box, Card, Chip, Divider, Typography } from '@mui/material';
import { ClipboardPlus } from 'lucide-react';

import { CardSkeleton, EmptyState } from '@/components/shared/Feedback';
import type { NursingRecord, NursingRecordsResponse } from '@/types/patient-dashboard';

interface NursingRecordsPanelProps {
  data?: NursingRecordsResponse;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
}

export default function NursingRecordsPanel({ data, loading, error, onRetry }: NursingRecordsPanelProps) {
  if (loading) return <CardSkeleton height={180} />;
  if (error || !data) return <Alert severity="warning" action={<Chip size="small" label="重试" onClick={onRetry} clickable />}>护理记录暂时无法加载。</Alert>;
  return <Card variant="outlined" sx={{ borderRadius: 1 }}>
    <Box sx={{ px: 1.75, py: 1.25, display: 'flex', gap: 0.75, alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}><ClipboardPlus size={18} /><Typography variant="subtitle2" fontWeight={600}>护理记录</Typography><Chip size="small" label={`${data.total} 条`} sx={{ ml: 'auto' }} /></Box>
    {data.records.length === 0 ? <EmptyState icon="" title="暂无护理记录" /> : <Box sx={{ px: 1.75, py: 0.25 }}>{data.records.slice(-5).reverse().map((record, index) => <NursingRecordRow key={`${record.timestamp ?? record.recorded_at ?? 'record'}-${index}`} record={record} divider={index < Math.min(data.records.length, 5) - 1} />)}</Box>}
  </Card>;
}

function NursingRecordRow({ record, divider }: { record: NursingRecord; divider: boolean }) {
  const action = text(record.nursing_actions ?? record.action) || '未记录护理措施';
  const timestamp = text(record.recorded_at ?? record.timestamp);
  const intakeOutput = [numberLabel('入', record.intake_ml), numberLabel('出', record.output_ml)].filter(Boolean).join(' · ');
  const medications = Array.isArray(record.medications_administered) ? record.medications_administered.length : 0;
  return <Box sx={{ py: 1.1 }}><Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, alignItems: 'baseline' }}><Typography variant="body2" fontWeight={600}>{action}</Typography>{timestamp ? <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>{timestamp}</Typography> : null}</Box><Box sx={{ display: 'flex', gap: 0.75, mt: 0.6, flexWrap: 'wrap' }}>{intakeOutput ? <Chip size="small" variant="outlined" label={intakeOutput} /> : null}{medications ? <Chip size="small" variant="outlined" label={`给药 ${medications} 项`} /> : null}{record.alerts?.length ? <Chip size="small" color="warning" label={`${record.alerts.length} 项异常`} /> : null}</Box>{divider ? <Divider sx={{ mt: 1.1 }} /> : null}</Box>;
}

function text(value: unknown) { return typeof value === 'string' ? value.trim() : ''; }
function numberLabel(label: string, value: unknown) { return typeof value === 'number' ? `${label}${value}ml` : ''; }
