import { Box, Card, Collapse, Typography } from '@mui/material';
import { ChevronDown, ChevronUp, type LucideIcon } from 'lucide-react';
import { useState } from 'react';

interface Props {
  title: string;
  icon?: LucideIcon;
  defaultExpanded?: boolean;
  badge?: string;
  children: React.ReactNode;
}

export default function CollapsibleSection({ title, icon: Icon, defaultExpanded = true, badge, children }: Props) {
  const [open, setOpen] = useState(defaultExpanded);

  return (
    <Card variant="outlined" sx={{ borderRadius: 1 }}>
      <Box
        onClick={() => setOpen(!open)}
        sx={{ px: 1.75, py: 1.15, display: 'flex', alignItems: 'center', gap: 0.75, cursor: 'pointer', userSelect: 'none', '&:hover': { bgcolor: 'action.hover' } }}
      >
        {Icon && <Icon size={16} />}
        <Typography variant="subtitle2" fontWeight={600} sx={{ flex: 1 }}>{title}</Typography>
        {badge && <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>{badge}</Typography>}
        {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
      </Box>
      <Collapse in={open}>
        <Box sx={{ px: 1.75, pb: 1.5 }}>{children}</Box>
      </Collapse>
    </Card>
  );
}
