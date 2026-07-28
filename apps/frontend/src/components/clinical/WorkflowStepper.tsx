import { Box, Chip, Typography } from '@mui/material';
import { CheckCircle2, Circle } from 'lucide-react';
import { patientWorkflowStage } from '@/core/doctor-workspace';

interface Props {
  phase: string;
  readinessPercent?: number | null;
}

const STAGES = ['入院评估', '住院管理', '出院准备', '交接完成'] as const;

export default function WorkflowStepper({ phase, readinessPercent }: Props) {
  const active = patientWorkflowStage(phase);
  const pct = readinessPercent ?? null;

  return (
    <Box sx={{ px: 1.5, py: 1.2, border: '1px solid', borderColor: 'divider', borderRadius: 1, bgcolor: 'background.paper' }}>
      <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', mb: 0.8 }}>
        <Typography variant="caption" color="text.secondary" fontWeight={600}>当前阶段</Typography>
        <Chip size="small" label={STAGES[active]} color={active >= 3 ? 'success' : active >= 2 ? 'info' : 'primary'} sx={{ height: 20, fontSize: 11 }} />
        {pct != null && (
          <Chip size="small" label={`出院准备 ${pct}%`} color={pct >= 80 ? 'success' : pct >= 60 ? 'warning' : 'error'} variant="outlined" sx={{ height: 20, fontSize: 10, ml: 'auto' }} />
        )}
      </Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 0.25 }}>
        {STAGES.map((stage, index) => (
          <Box key={stage} sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0.35, color: index <= active ? 'text.primary' : 'text.disabled' }}>
            <Box sx={{ width: 18, height: 18, borderRadius: '50%', bgcolor: index < active ? 'success.main' : index === active ? 'primary.main' : 'divider', display: 'grid', placeItems: 'center' }}>
              {index < active ? <CheckCircle2 size={10} color="#fff" /> : <Circle size={8} color={index === active ? '#fff' : '#999'} fill={index === active ? '#fff' : 'transparent'} />}
            </Box>
            <Typography variant="caption" fontWeight={index === active ? 600 : 400} sx={{ fontSize: 9.5, textAlign: 'center' }}>{stage}</Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
