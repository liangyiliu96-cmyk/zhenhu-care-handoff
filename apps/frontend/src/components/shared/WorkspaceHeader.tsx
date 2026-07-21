import { Box, Chip, Typography } from '@mui/material';
import type { ReactNode } from 'react';

interface WorkspaceHeaderProps {
  eyebrow: string;
  title: string;
  description: string;
  icon?: ReactNode;
  status?: ReactNode;
  tags?: string[];
  actions?: ReactNode;
  welcome?: ReactNode;
}

export default function WorkspaceHeader({ eyebrow, title, description, icon, status, tags = [], actions, welcome }: WorkspaceHeaderProps) {
  return (
    <Box
      component="header"
      sx={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        gap: 2,
        px: { xs: 0, md: 0.5 },
        py: { xs: 0.5, md: 1.25 },
      }}
    >
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="overline" color="text.secondary">{eyebrow}</Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.15, mt: 0.4 }}>
          {icon ? <Box sx={{ width: 38, height: 38, borderRadius: 1, bgcolor: 'primary.light', color: 'primary.dark', display: 'grid', placeItems: 'center', flexShrink: 0 }}>{icon}</Box> : null}
          <Typography variant="h5" component="h1">{title}</Typography>
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.8, maxWidth: 840, lineHeight: 1.7 }}>
          {description}
        </Typography>
        {welcome}
      </Box>
      <Box sx={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 0.75, flexWrap: 'wrap', flexShrink: 0, pt: 0.35 }}>
        {tags.map((tag) => <Chip key={tag} label={tag} size="small" variant="outlined" />)}
        {status}
        {actions}
      </Box>
    </Box>
  );
}
