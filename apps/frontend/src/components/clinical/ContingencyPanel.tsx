import { Box, Card, Chip, Typography } from '@mui/material';
import { ShieldAlert } from 'lucide-react';
import type { DashboardResponse, ScoresResponse } from '@/types/patient-dashboard';

interface Props {
  dashboard: DashboardResponse;
  scores?: ScoresResponse | null;
}

function deriveContingency(d: DashboardResponse, scores?: ScoresResponse | null): string[] {
  const items: string[] = [];
  const news2 = scores?.news2?.score ?? null;
  const qsofa = scores?.qsofa?.score ?? null;

  if (news2 != null && news2 >= 7)
    items.push(`NEWS2=${news2}（高危）—— 需持续监测生命体征，若评分上升应立即通知医生`);
  else if (news2 != null && news2 >= 5)
    items.push(`NEWS2=${news2}（中危）—— 每4小时复查评分，关注意识与呼吸变化`);

  if (qsofa != null && qsofa >= 2)
    items.push(`qSOFA=${qsofa} —— 提示脓毒症风险，需评估感染源并监测乳酸`);

  const lastVs = d.vital_trend?.[d.vital_trend.length - 1];
  if (lastVs?.spo2 != null && lastVs.spo2 < 92)
    items.push(`SpO₂=${lastVs.spo2}% —— 若持续低于90%应考虑氧疗升级或通知呼吸科`);

  const phase = d.phase || '';
  if (phase.startsWith('discharge') || phase === 'handoff' || phase === 'confirm')
    items.push('出院阶段 —— 关注出院条件达标、用药教育完成度和交接事项签收');

  if (!items.length)
    items.push('生命体征平稳，常规护理即可，发现异常及时报告。');

  return items;
}

export default function ContingencyPanel({ dashboard, scores }: Props) {
  const items = deriveContingency(dashboard, scores);
  const hasDanger = items.some(s => s.includes('高危') || s.includes('脓毒症'));

  return (
    <Card variant="outlined" sx={{ borderRadius: 1, borderColor: hasDanger ? 'error.main' : 'warning.main', borderWidth: hasDanger ? 2 : 1, bgcolor: hasDanger ? 'rgba(211,47,47,0.03)' : 'rgba(237,108,2,0.02)' }}>
      <Box sx={{ px: 1.75, py: 1.2, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}>
        <ShieldAlert size={17} color={hasDanger ? '#d32f2f' : '#ed6c02'} />
        <Typography variant="subtitle2" fontWeight={600} sx={{ flex: 1 }}>应急关注</Typography>
        <Chip size="small" color={hasDanger ? 'error' : 'warning'} label="I-PASS S" variant="outlined" sx={{ fontSize: 10, height: 20 }} />
      </Box>
      <Box sx={{ px: 1.75, py: 1.5, display: 'flex', flexDirection: 'column', gap: 1 }}>
        {items.map((item, i) => (
          <Box key={i} sx={{ display: 'flex', gap: 0.75 }}>
            <Typography variant="caption" color={hasDanger ? 'error.main' : 'warning.main'} sx={{ mt: 0.15, flexShrink: 0 }}>
              {hasDanger ? '⚠' : '•'}
            </Typography>
            <Typography variant="body2" sx={{ fontSize: 12.5, lineHeight: 1.6 }}>{item}</Typography>
          </Box>
        ))}
      </Box>
    </Card>
  );
}
