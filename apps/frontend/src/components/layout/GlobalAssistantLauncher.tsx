import { useEffect, useMemo, useState } from 'react';
import { Box, Drawer, IconButton, Tooltip, Typography } from '@mui/material';
import { X } from 'lucide-react';

import PatientAssistantPanel from '@/components/clinical/PatientAssistantPanel';
import { ASSISTANT_META, defaultAssistantModeForRole, globalAssistantModesForRole, type AssistantMode } from '@/core/assistant-modes';
import { OPEN_GLOBAL_ASSISTANT_EVENT, type OpenAssistantDetail } from '@/core/runtime-events';
import { useAuthStore } from '@/stores/auth-store';

export default function GlobalAssistantLauncher() {
  const [open, setOpen] = useState(false);
  const role = useAuthStore((state) => state.user?.role) ?? sessionStorage.getItem('zhenhu_role');
  const allowedModes = useMemo(() => globalAssistantModesForRole(role), [role]);
  const [assistantMode, setAssistantMode] = useState<AssistantMode>(defaultAssistantModeForRole(role));
  useEffect(() => {
    const openAssistant = (event: Event) => {
      const requested = (event as CustomEvent<OpenAssistantDetail>).detail?.assistantMode;
      if (requested && allowedModes.includes(requested)) setAssistantMode(requested);
      setOpen(true);
    };
    window.addEventListener(OPEN_GLOBAL_ASSISTANT_EVENT, openAssistant as EventListener);
    return () => window.removeEventListener(OPEN_GLOBAL_ASSISTANT_EVENT, openAssistant as EventListener);
  }, [allowedModes]);
  if (role !== 'doctor' && role !== 'nurse') return null;

  const assistantName = ASSISTANT_META[assistantMode].name;

  return <Drawer anchor="right" open={open} onClose={() => setOpen(false)}>
      <Box sx={{ width: { xs: '100vw', sm: 440 }, maxWidth: '100vw', p: 2, minHeight: '100%', bgcolor: 'background.default' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}><Typography variant="subtitle1" fontWeight={600}>{assistantName}</Typography><Tooltip title={`关闭${assistantName}`}><IconButton aria-label={`关闭${assistantName}`} onClick={() => setOpen(false)}><X size={18} /></IconButton></Tooltip></Box>
        <PatientAssistantPanel defaultOpen assistantMode={assistantMode} availableModes={allowedModes} />
      </Box>
    </Drawer>;
}
