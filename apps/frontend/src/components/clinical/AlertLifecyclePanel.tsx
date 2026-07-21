import { Alert, Box, Button, Card, Chip, Stack, Typography } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Check, CircleCheck } from 'lucide-react';

import { ApiClientError } from '@/core/api-client';
import { fetchPatientAlerts, transitionAlert, type ClinicalAlert } from '@/services/alert-service';
import { CardSkeleton, EmptyState, ErrorBanner } from '@/components/shared/Feedback';

export default function AlertLifecyclePanel({ patientId }: { patientId: string }) {
  const queryClient = useQueryClient();
  const alerts = useQuery({ queryKey: ['patient', patientId, 'alerts'], queryFn: () => fetchPatientAlerts(patientId), staleTime: 15_000 });
  const mutation = useMutation({
    mutationFn: ({ alert, action }: { alert: ClinicalAlert; action: 'acknowledge' | 'resolve' }) => transitionAlert(patientId, alert.alert_id, action, alerts.data!.state_version),
    onSuccess: async () => { await Promise.all([queryClient.invalidateQueries({ queryKey: ['patient', patientId] }), queryClient.invalidateQueries({ queryKey: ['ward'] })]); },
    onError: async (cause) => {
      if (cause instanceof ApiClientError && cause.code === 'STATE_VERSION_CONFLICT') await alerts.refetch();
    },
  });
  if (alerts.isLoading) return <CardSkeleton height={140} />;
  if (alerts.error) return <ErrorBanner message="告警状态加载失败" onRetry={() => void alerts.refetch()} />;
  const error = mutation.error instanceof ApiClientError && mutation.error.code === 'STATE_VERSION_CONFLICT' ? '患者状态已更新，已刷新告警列表，请核对后重试。' : mutation.error instanceof Error ? mutation.error.message : '';
  return <Card variant="outlined" sx={{ borderRadius: 1 }}><Box sx={{ px: 1.75, py: 1.25, display: 'flex', gap: 0.75, alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}><AlertTriangle size={18} /><Typography variant="subtitle2" fontWeight={600}>临床告警</Typography></Box><Box sx={{ p: 1.5 }}>{error ? <Alert severity="warning" sx={{ mb: 1.25 }}>{error}</Alert> : null}{!alerts.data?.alerts.length ? <EmptyState title="暂无临床告警" /> : <Stack spacing={1}>{alerts.data.alerts.map((alert) => <AlertRow key={alert.alert_id} alert={alert} pending={mutation.isPending} onAction={(action) => mutation.mutate({ alert, action })} />)}</Stack>}</Box></Card>;
}

function AlertRow({ alert, pending, onAction }: { alert: ClinicalAlert; pending: boolean; onAction: (action: 'acknowledge' | 'resolve') => void }) {
  const severity = alert.severity === 'critical' ? 'error' : alert.severity === 'warning' ? 'warning' : 'info';
  const status = alert.status ?? 'open';
  return <Box sx={{ borderLeft: '3px solid', borderColor: `${severity}.main`, pl: 1.25 }}><Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center', flexWrap: 'wrap' }}><Typography variant="body2" fontWeight={600}>{alert.message}</Typography><Chip size="small" color={status === 'resolved' ? 'success' : status === 'acknowledged' ? 'info' : severity} label={status === 'resolved' ? '已解除' : status === 'acknowledged' ? '已确认' : '待处理'} /></Box>{status !== 'resolved' ? <Box sx={{ display: 'flex', gap: 0.75, mt: 0.75 }}>{status === 'open' ? <Button size="small" startIcon={<Check size={15} />} disabled={pending} onClick={() => onAction('acknowledge')}>确认</Button> : null}<Button size="small" color="success" startIcon={<CircleCheck size={15} />} disabled={pending} onClick={() => onAction('resolve')}>解除</Button></Box> : <Typography variant="caption" color="text.secondary">{alert.resolved_by ? `已由 ${alert.resolved_by} 解除` : '服务端已记录解除'}</Typography>}</Box>;
}
