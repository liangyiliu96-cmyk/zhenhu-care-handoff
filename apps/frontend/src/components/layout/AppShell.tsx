import { Box } from '@mui/material';
import TopBar from './TopBar';
import LeftNav from './LeftNav';
import type { ReactNode } from 'react';
import GlobalAssistantLauncher from './GlobalAssistantLauncher';

interface AppShellProps {
  title: string;
  children: ReactNode;
  adminLink?: string;
  adminLabel?: string;
  backTo?: string;
  backLabel?: string;
  rightPanel?: ReactNode;
  showGlobalAssistant?: boolean;
}

export default function AppShell({
  title, children, adminLink, adminLabel, backTo, backLabel, rightPanel, showGlobalAssistant = true,
}: AppShellProps) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh', minHeight: 0, bgcolor: 'background.default' }}>
      <TopBar
        title={title}
        adminLink={adminLink}
        adminLabel={adminLabel}
        backTo={backTo}
        backLabel={backLabel}
      />
      <Box sx={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden', bgcolor: 'background.default' }}>
        <LeftNav />
        <Box
          component="main"
          sx={{
            flex: 1, minWidth: 0, overflow: 'auto',
            p: { xs: 2, lg: 2.5, xl: 3 },
            bgcolor: 'background.default',
          }}
        >
          {children}
        </Box>
        {rightPanel && (
          <Box
            sx={{
              width: 360, flexShrink: 0,
              borderLeft: '1px solid', borderColor: 'divider', bgcolor: 'background.paper',
              overflow: 'auto', p: 2, boxShadow: '-1px 0 0 rgba(20, 40, 44, 0.015)',
            }}
          >
            {rightPanel}
          </Box>
        )}
      </Box>
      {showGlobalAssistant ? <GlobalAssistantLauncher /> : null}
    </Box>
  );
}
