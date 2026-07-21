import { useState } from 'react';
import { Alert, Box, Button, Card, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Typography } from '@mui/material';
import { CheckCircle2, Database, Eraser, RefreshCw, RotateCcw, UsersRound } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { CardSkeleton, ErrorBanner } from '@/components/shared/Feedback';
import { clearExpiredState, fetchAdminCapabilities, fetchDatabaseStats, reindexKnowledge, resetDemoPatients, seedAllSystemData, seedOrganization } from '@/services/admin-service';
import type { AdminCapabilitiesResponse, AdminOperationResponse } from '@/types/admin';

type OperationId = 'rag_reindex' | 'organization_seed' | 'seed_all' | 'clear_expired' | 'demo_patient_reset';

const OPERATIONS: Array<{ id: OperationId; title: string; detail: string; impact: string; confirm: string; icon: React.ReactNode; run: () => Promise<AdminOperationResponse> }> = [
  { id: 'rag_reindex', title: '重新索引知识库', detail: '重建 16 层 Milvus 集合 → 重新编码 385 条知识 → 写入向量库', impact: '索引期间检索可能短暂降级约 30-60 秒', confirm: '确认重建全部 16 层临床知识索引？', icon: <RefreshCw size={18} />, run: reindexKnowledge },
  { id: 'organization_seed', title: '导入组织人员', detail: '从 constants.py 导入 54 名人员到 org_staff 表', impact: '已有工号记录按服务端规则处理（不覆盖密码）', confirm: '确认导入组织人员？', icon: <UsersRound size={18} />, run: seedOrganization },
  { id: 'seed_all', title: '导入全部基础数据', detail: '同步人员 (54人) + 病种模板 (22) + 科室清单 (16科67条)', impact: '覆盖 disease_templates 和 dept_checklists 表', confirm: '确认导入全部基础数据？', icon: <Database size={18} />, run: seedAllSystemData },
  { id: 'clear_expired', title: '清理过期热状态', detail: '清除 TTL 过期的 patient_states 缓存记录', impact: '不删除有效患者事务记录', confirm: '确认清理过期热状态？', icon: <Eraser size={18} />, run: clearExpiredState },
  { id: 'demo_patient_reset', title: '重置演示患者', detail: '清空当前开发运行库的历史患者状态并重建心内科、呼吸科各 10 名虚构患者', impact: '仅开发/演示环境可用；不影响知识库、组织、模板或审计数据', confirm: '确认清理当前开发运行库全部历史患者状态，并重建两科共 20 名虚构患者？', icon: <RotateCcw size={18} />, run: resetDemoPatients },
];

export default function SystemOperationsPanel() {
  const queryClient = useQueryClient();
  const capabilities = useQuery({ queryKey: ['admin', 'capabilities'], queryFn: fetchAdminCapabilities, staleTime: 30_000 });
  const database = useQuery({ queryKey: ['admin', 'database-stats'], queryFn: fetchDatabaseStats, enabled: capabilities.data?.operations.database_stats === true, staleTime: 15_000 });
  const [selected, setSelected] = useState<(typeof OPERATIONS)[number] | null>(null);
  const [lastAudit, setLastAudit] = useState('');
  const [lastResult, setLastResult] = useState<AdminOperationResponse | null>(null);
  const mutation = useMutation({ mutationFn: () => selected!.run(), onSuccess: async (result) => { setLastAudit(result.audit_id); setLastResult(result); setSelected(null); await Promise.all([queryClient.invalidateQueries({ queryKey: ['admin'] }), queryClient.invalidateQueries({ queryKey: ['ward'] }), queryClient.invalidateQueries({ queryKey: ['nurse'] }), queryClient.invalidateQueries({ queryKey: ['inpatient'] }), queryClient.invalidateQueries({ queryKey: ['follow-up'] }), queryClient.invalidateQueries({ queryKey: ['dashboard'] })]); } });

  if (capabilities.isLoading) return <CardSkeleton height={300} />;
  if (capabilities.error || !capabilities.data) return <ErrorBanner message="管理运维权限加载失败" onRetry={() => void capabilities.refetch()} />;
  const data = capabilities.data;
  const authorizationMessage = managementAuthorizationMessage(data);
  return <Stack spacing={2}>
    <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}><Button size="small" variant="outlined" startIcon={<RefreshCw size={15} />} onClick={() => { void capabilities.refetch(); void database.refetch(); }} disabled={capabilities.isFetching || database.isFetching}>刷新运行状态</Button></Box>
    <Alert severity={data.writes_enabled ? 'info' : 'warning'}>
      <Typography variant="body2">{authorizationMessage}</Typography>
      <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mt: 0.75 }}>
        <Chip size="small" variant="outlined" label={data.environment === 'production' ? '生产环境' : '本地联调'} />
        <Chip size="small" variant="outlined" color={data.is_manager ? 'success' : 'default'} label={data.is_manager ? '管理身份已识别' : '非管理身份'} />
        <Chip size="small" variant="outlined" color={data.production_switch_enabled ? 'success' : 'default'} label={data.production_switch_enabled ? '运维开关已开启' : '运维开关未开启'} />
      </Box>
    </Alert>
    {lastAudit ? <Alert severity="success" icon={<CheckCircle2 size={18} />}>操作完成，审计编号：{lastAudit}{lastResult ? ` · ${operationResultSummary(lastResult)}` : ''}</Alert> : null}
    {database.data ? <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 1.5 }}><Metric label="热状态条目" value={database.data.memory_entries} /><Metric label="数据库文件" value={`${database.data.file_size_mb} MB`} /></Box> : null}
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'repeat(2, minmax(0, 1fr))' }, gap: 1.5 }}>{OPERATIONS.map((operation) => <OperationCard key={operation.id} operation={operation} capabilities={data} pending={mutation.isPending} onSelect={() => setSelected(operation)} />)}</Box>
    {mutation.error ? <Alert severity="error">{mutation.error instanceof Error ? mutation.error.message : '运维操作失败'}</Alert> : null}
    <Dialog open={Boolean(selected)} onClose={mutation.isPending ? undefined : () => setSelected(null)}><DialogTitle>{selected?.title}</DialogTitle><DialogContent><Typography variant="body2">{selected?.confirm}</Typography></DialogContent><DialogActions><Button onClick={() => setSelected(null)} disabled={mutation.isPending}>取消</Button><Button color="warning" variant="contained" onClick={() => mutation.mutate()} disabled={mutation.isPending}>确认执行</Button></DialogActions></Dialog>
  </Stack>;
}

function OperationCard({ operation, capabilities, pending, onSelect }: { operation: (typeof OPERATIONS)[number]; capabilities: AdminCapabilitiesResponse; pending: boolean; onSelect: () => void }) {
  const allowed = capabilities.operations[operation.id];
  return <Card variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
    <Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center' }}>{operation.icon}<Typography variant="subtitle2" fontWeight={600}>{operation.title}</Typography><Chip size="small" label={allowed ? '已授权' : '未授权'} color={allowed ? 'success' : 'default'} sx={{ ml: 'auto' }} /></Box>
    <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{operation.detail}</Typography>
    <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>影响: {operation.impact}</Typography>
    <Button size="small" variant="outlined" color="warning" onClick={onSelect} disabled={!allowed || pending} sx={{ mt: 1.25 }}>执行</Button></Card>;
}

function Metric({ label, value }: { label: string; value: string | number }) { return <Card variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="h5" sx={{ mt: 0.5 }}>{value}</Typography></Card>; }

function managementAuthorizationMessage(capabilities: AdminCapabilitiesResponse) {
  if (capabilities.writes_enabled) return '科主任或护士长的运维写操作已授权，执行结果会写入审计日志。';
  if (capabilities.authorization_reason === 'manager_role_required' || !capabilities.is_manager) return '当前身份不是科主任或护士长，仅可查看无需管理权限的系统状态。';
  if (capabilities.authorization_reason === 'production_switch_disabled' || !capabilities.production_switch_enabled) return '管理身份已识别，但生产运维总开关尚未开启；请由部署管理员核对运行配置。';
  if (capabilities.authorization_reason === 'permission_claim_missing') return `管理身份已识别，但登录令牌缺少 ${capabilities.required_permission ?? '运维写权限'}。`;
  return '运维写操作未授权，仅可查看系统状态。';
}

function operationResultSummary(result: AdminOperationResponse) {
  const values: string[] = [];
  if (typeof result.total === 'number') values.push(`处理 ${result.total} 条`);
  if (typeof result.imported === 'number') values.push(`导入 ${result.imported} 条`);
  if (typeof result.removed === 'number') values.push(`清理 ${result.removed} 条`);
  if (typeof result.remaining === 'number') values.push(`剩余 ${result.remaining} 条`);
  if (typeof result.staff === 'number') values.push(`人员 ${result.staff}`);
  if (typeof result.templates === 'number') values.push(`模板 ${result.templates}`);
  if (typeof result.checklists === 'number') values.push(`清单 ${result.checklists}`);
  if (typeof result.by_department === 'object' && result.by_department) values.push(`心内科 ${Number((result.by_department as Record<string, number>)['心内科'] ?? 0)} 例，呼吸科 ${Number((result.by_department as Record<string, number>)['呼吸科'] ?? 0)} 例`);
  return values.join('，') || '服务端已完成并记录审计';
}
