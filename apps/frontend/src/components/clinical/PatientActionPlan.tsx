import { ArrowRight, CheckCircle2, CircleAlert, ClipboardCheck, Stethoscope } from 'lucide-react';
import { Box, Button, Card, Chip, Typography } from '@mui/material';

import type { DashboardResponse, RoundsResponse } from '@/types/patient-dashboard';
import { patientActionPlan, type PatientActionPlanItem } from '@/utils/patient-action-plan';

interface PatientActionPlanProps {
  dashboard: DashboardResponse;
  rounds?: RoundsResponse;
  onOpen: (action: PatientActionPlanItem) => void;
}

const URGENCY_META = {
  high: { label: '优先处理', color: 'error' as const, Icon: CircleAlert },
  medium: { label: '本轮处理', color: 'warning' as const, Icon: ClipboardCheck },
  low: { label: '后续安排', color: 'default' as const, Icon: Stethoscope },
};

const KIND_LABEL: Record<PatientActionPlanItem['kind'], string> = {
  safety: '安全核对',
  review: '医生审核',
  data: '资料补全',
  discharge: '出院流程',
  routine: '常规监测',
};

export default function PatientActionPlan({ dashboard, rounds, onOpen }: PatientActionPlanProps) {
  const actions = patientActionPlan(dashboard, rounds);
  const current = actions[0];
  if (!current) {
    return <Card variant="outlined" sx={{ borderRadius: 1, overflow: 'hidden' }}>
      <Box sx={{ px: 1.75, py: 1.25, display: 'flex', alignItems: 'center', gap: 0.75 }}>
        <CheckCircle2 size={18} />
        <Box><Typography variant="subtitle2" fontWeight={600}>临床行动</Typography><Typography variant="caption" color="text.secondary">当前没有待处理行动。</Typography></Box>
      </Box>
    </Card>;
  }
  const CurrentIcon = URGENCY_META[current.urgency].Icon;

  return <Card variant="outlined" sx={{ borderRadius: 1, overflow: 'hidden' }}>
    <Box sx={{ px: 1.75, py: 1.25, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}>
      <CheckCircle2 size={18} />
      <Box sx={{ flex: 1 }}><Typography variant="subtitle2" fontWeight={600}>临床下一步</Typography><Typography variant="caption" color="text.secondary">按当前患者状态排序；完成标准来自系统状态，临床决策仍需医生确认。</Typography></Box>
      <Chip size="small" variant="outlined" label={`${actions.length} 项`} />
    </Box>
    <Box sx={{ p: 1.5, bgcolor: 'rgba(11, 100, 114, 0.035)' }}>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
        <Box sx={{ mt: 0.15, color: current.urgency === 'high' ? 'error.main' : current.urgency === 'medium' ? 'warning.main' : 'text.secondary' }}><CurrentIcon size={18} /></Box>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center', flexWrap: 'wrap' }}><Typography variant="subtitle2">当前下一步：{current.title}</Typography><Chip size="small" variant="outlined" label={KIND_LABEL[current.kind]} /><Chip size="small" color={URGENCY_META[current.urgency].color} label={URGENCY_META[current.urgency].label} /></Box>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.35 }}>{current.detail}</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}><strong>完成标准：</strong>{current.completion}</Typography>
        </Box>
        <Button size="small" variant="contained" endIcon={<ArrowRight size={15} />} onClick={() => onOpen(current)} sx={{ whiteSpace: 'nowrap' }}>进入处理</Button>
      </Box>
    </Box>
    {actions.slice(1).map((action, index) => <Box key={action.key} sx={{ px: 1.75, py: 1.05, display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr) auto', gap: 1, alignItems: 'center', borderTop: '1px solid', borderColor: 'divider' }}>
      <Typography variant="caption" color="text.secondary">{index + 2}</Typography>
      <Box minWidth={0}><Box sx={{ display: 'flex', gap: 0.6, alignItems: 'center', flexWrap: 'wrap' }}><Typography variant="body2" fontWeight={600}>{action.title}</Typography><Chip size="small" variant="outlined" label={KIND_LABEL[action.kind]} /></Box><Typography variant="caption" color="text.secondary">{action.detail}</Typography><Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>完成标准：{action.completion}</Typography></Box>
      <Button size="small" variant="text" endIcon={<ArrowRight size={14} />} onClick={() => onOpen(action)}>查看</Button>
    </Box>)}
  </Card>;
}
