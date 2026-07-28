import { Alert, Box, Button, Card, Chip, Collapse, Typography } from '@mui/material';
import { AlertTriangle, Bot, Brain, ChevronDown, ChevronUp, ClipboardList, Sparkles, Stethoscope } from 'lucide-react';
import { useState } from 'react';

interface PendingSummary {
  ddx_pending: number;
  med_pending: number;
  discharge_pending: number;
  total_items: number;
}

interface Props {
  pending?: { summary?: PendingSummary; pending?: unknown[] };
  alerts?: number;
  aiSummary?: { summary?: string; alert_count?: number };
  patientsCount: number;
  highRisk?: number;
  dischargeReady?: number;
  onOpenReview?: () => void;
  onOpenRounds?: () => void;
  onOpenDischarge?: () => void;
  onOpenFollowUp?: () => void;
}

export default function AiDailyBrief({ pending, alerts, aiSummary, patientsCount, highRisk = 0, dischargeReady = 0, onOpenReview, onOpenRounds, onOpenDischarge, onOpenFollowUp }: Props) {
  const [expanded, setExpanded] = useState(true);
  const s = pending?.summary;

  if (!s && !alerts && !aiSummary?.summary && !patientsCount) return null;

  const totalPending = (s?.total_items ?? 0) + (aiSummary?.alert_count ?? 0) + (alerts ?? 0);
  const hasActionable = totalPending > 0;

  return (
    <Card variant="outlined" sx={{ borderRadius: 1, borderColor: hasActionable ? 'warning.main' : 'primary.main', borderWidth: hasActionable ? 2 : 1, bgcolor: hasActionable ? 'rgba(237, 108, 2, 0.03)' : 'rgba(11, 100, 114, 0.02)' }}>
      <Box sx={{ px: 2, py: 1.5, display: 'flex', alignItems: 'center', gap: 1.5, cursor: 'pointer' }} onClick={() => setExpanded(!expanded)}>
        <Box sx={{ width: 32, height: 32, borderRadius: 1, display: 'grid', placeItems: 'center', bgcolor: hasActionable ? 'warning.main' : 'primary.main', color: '#fff' }}>
          <Brain size={18} />
        </Box>
        <Box sx={{ flex: 1 }}>
          <Typography variant="subtitle1" fontWeight={600}>
            {hasActionable ? `AI 今日简报 · ${totalPending} 项待处理` : 'AI 今日简报'}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {hasActionable
              ? `${s?.ddx_pending ?? 0} 诊断审核 · ${s?.med_pending ?? 0} 用药审核 · ${s?.discharge_pending ?? 0} 出院审核 · ${patientsCount} 人在院`
              : `${patientsCount} 名患者在院，目前无待处理事项`}
          </Typography>
        </Box>
        <Chip size="small" icon={<Sparkles size={14} />} label="AI 驱动" color={hasActionable ? 'warning' : 'info'} variant="outlined" />
        {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </Box>

      <Collapse in={expanded}>
        <Box sx={{ px: 2, pb: 2, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          {/* 待审核摘要 */}
          {s && (
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              <ActionChip icon={<ClipboardList size={14} />} label={`${s.ddx_pending ?? 0} 诊断`} color={s.ddx_pending ? 'error' : 'default'} />
              <ActionChip icon={<ClipboardList size={14} />} label={`${s.med_pending ?? 0} 用药`} color={s.med_pending ? 'warning' : 'default'} />
              <ActionChip icon={<ClipboardList size={14} />} label={`${s.discharge_pending ?? 0} 出院`} color={s.discharge_pending ? 'info' : 'default'} />
              {onOpenReview && totalPending > 0 && (
                <Button size="small" variant="contained" color="warning" onClick={onOpenReview} sx={{ ml: 'auto' }}>
                  查看待审核
                </Button>
              )}
            </Box>
          )}

          {/* AI 病区摘要 */}
          {aiSummary?.summary && (
            <Box sx={{ pl: 1.5, borderLeft: '3px solid', borderColor: 'primary.main' }}>
              <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Bot size={13} /> AI 病区摘要
              </Typography>
              <Typography variant="body2" sx={{ mt: 0.4, lineHeight: 1.65 }}>{aiSummary.summary}</Typography>
            </Box>
          )}

          {/* 告警 / 无事项 */}
          {alerts ? (
            <Alert severity="warning" icon={<AlertTriangle size={16} />} sx={{ py: 0 }}>
              <Typography variant="caption">当前有 {alerts} 条活跃告警需要关注</Typography>
            </Alert>
          ) : !s?.total_items && !alerts ? (
            <Alert severity="success" sx={{ py: 0 }}>
              <Typography variant="caption">当前无待审核项与活跃告警，在院患者状态平稳。</Typography>
            </Alert>
          ) : null}

          {/* 快速操作 — 合并自 DoctorWorkflowCockpit */}
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', pt: 0.5 }}>
            {onOpenReview && (s?.total_items ?? 0) > 0 && (
              <Button size="small" variant="contained" color="warning" onClick={onOpenReview} startIcon={<ClipboardList size={14} />}>审核待办（{s?.total_items ?? 0}）</Button>
            )}
            {onOpenRounds && (
              <Button size="small" variant="outlined" onClick={onOpenRounds} startIcon={<Stethoscope size={14} />}>查房顺序{highRisk > 0 ? `（${highRisk}高危）` : ''}</Button>
            )}
            {onOpenDischarge && dischargeReady > 0 && (
              <Button size="small" variant="outlined" color="success" onClick={onOpenDischarge}>出院协同（{dischargeReady}）</Button>
            )}
            {onOpenFollowUp && (
              <Button size="small" variant="outlined" onClick={onOpenFollowUp}>随访总览</Button>
            )}
          </Box>
        </Box>
      </Collapse>
    </Card>
  );
}

function ActionChip({ icon, label, color }: { icon: React.ReactNode; label: string; color: 'error' | 'warning' | 'info' | 'default' }) {
  return (
    <Chip size="small" icon={icon as React.ReactElement} label={label} color={color} variant={color === 'default' ? 'outlined' : 'filled'} />
  );
}
