import { Alert, Box, CircularProgress, Divider, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { fetchPatientEvidence } from '@/services/evidence-service';
import { EmptyState } from '@/components/shared/Feedback';

interface EvidencePanelProps {
  patientId: string;
  enabled: boolean;
}

function citationText(citation: Record<string, unknown>) {
  return String(
    citation.excerpt ?? citation.content ?? citation.citation ?? citation.text ?? '未提供引用片段'
  );
}

export default function EvidencePanel({ patientId, enabled }: EvidencePanelProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['evidence', patientId],
    queryFn: () => fetchPatientEvidence(patientId),
    enabled,
    staleTime: 30_000,
  });

  if (!enabled) return null;
  if (isLoading) {
    return <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}><CircularProgress size={24} /></Box>;
  }
  if (error) {
    return <Alert severity="warning">临床证据暂时无法加载，请结合原始病历与当前临床记录继续判断。</Alert>;
  }
  if (!data || data.count === 0) {
    return <EmptyState icon="" title="暂无已保存的临床证据" description="此处仅展示患者状态中已持久化的引用来源。" />;
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      {data.citations.map((citation, index) => (
        <Box key={`${citation.source ?? 'citation'}-${index}`} sx={{ py: 1 }}>
          <Typography variant="body2" fontWeight={600}>
            {String(citation.title ?? citation.source ?? `证据 ${index + 1}`)}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, lineHeight: 1.6 }}>
            {citationText(citation)}
          </Typography>
          {citation.version ? <Typography variant="caption" color="text.secondary">版本 {String(citation.version)}</Typography> : null}
          {index < data.citations.length - 1 ? <Divider sx={{ mt: 1 }} /> : null}
        </Box>
      ))}
    </Box>
  );
}
