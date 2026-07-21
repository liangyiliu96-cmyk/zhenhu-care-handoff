import { Box, Typography } from '@mui/material';
import { workspaceWelcomeFor, type WorkspaceKind } from '@/core/workspace-welcome';
import type { UserIdentity } from '@/types/auth';

interface WorkspaceWelcomeProps {
  user: UserIdentity;
  workspace: WorkspaceKind;
}

export default function WorkspaceWelcome({ user, workspace }: WorkspaceWelcomeProps) {
  const copy = workspaceWelcomeFor(user, workspace);

  return (
    <Box sx={{ mt: 1.15, pl: 1.25, borderLeft: '3px solid', borderColor: 'primary.main' }}>
      <Typography sx={{ fontFamily: 'var(--font-display)', fontSize: '1.06rem', fontWeight: 600, color: 'text.primary', lineHeight: 1.35 }}>
        {copy.headline}
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25, lineHeight: 1.55 }}>
        {copy.detail}
      </Typography>
    </Box>
  );
}
