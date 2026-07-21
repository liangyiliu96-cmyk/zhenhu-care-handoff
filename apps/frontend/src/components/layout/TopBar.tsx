import { Avatar, Box, Typography, IconButton, Button, Chip, Tooltip } from '@mui/material';
import { ArrowLeft, LogOut, Moon, Sun } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth-store';
import { ROUTES } from '@/core/routes';
import { useThemeStore } from '@/stores/theme-store';

interface TopBarProps {
  title: string;
  adminLink?: string;
  adminLabel?: string;
  backTo?: string;
  backLabel?: string;
}

export default function TopBar({ title, adminLink, adminLabel, backTo, backLabel }: TopBarProps) {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const mode = useThemeStore((s) => s.mode);
  const toggleMode = useThemeStore((s) => s.toggleMode);
  const handleLogout = () => {
    logout();
    navigate(ROUTES.home, { replace: true });
  };

  return (
    <Box
      sx={{
        minHeight: 68,
        display: 'flex',
        alignItems: 'center',
        px: { xs: 2, lg: 2.5 },
        borderBottom: '1px solid',
        borderColor: 'divider',
        bgcolor: 'background.paper',
        boxShadow: '0 1px 0 rgba(20, 40, 44, 0.025)',
        flexShrink: 0,
      }}
    >
      <Box
        onClick={() => navigate(ROUTES.home)}
        sx={{ display: 'flex', alignItems: 'center', gap: 1.1, cursor: 'pointer', mr: { xs: 2, lg: 3.5 }, minWidth: 164 }}
      >
        <Box
          sx={{
            width: 34, height: 34, bgcolor: 'primary.main', borderRadius: 1,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'white', fontSize: 13, fontWeight: 700,
          }}
        >
          臻
        </Box>
        <Typography
          sx={{ fontFamily: 'var(--font-display)', fontSize: 17, fontWeight: 600, color: 'text.primary' }}
        >
          zhenhu
        </Typography>
      </Box>

      <Typography sx={{ fontSize: 14, fontWeight: 700, color: 'text.primary', flex: 1, pl: 0.25 }}>
        {title}
      </Typography>

      {backTo && (
        <Button size="small" variant="text" startIcon={<ArrowLeft size={15} />} onClick={() => navigate(backTo)} sx={{ mr: 1, textTransform: 'none' }}>
          {backLabel || '返回'}
        </Button>
      )}
      {adminLink && user?.title.includes('主任') && (
        <Button size="small" variant="outlined" onClick={() => navigate(adminLink)} sx={{ mr: 1 }}>
          {adminLabel || '管理控制台'}
        </Button>
      )}

      <Tooltip title={mode === 'dark' ? '切换浅色模式' : '切换深色护眼模式'}>
        <IconButton size="small" onClick={toggleMode} aria-label={mode === 'dark' ? '切换浅色模式' : '切换深色护眼模式'} sx={{ mr: user ? 0.25 : 0 }}>
          {mode === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </IconButton>
      </Tooltip>

      {user && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, pl: 1.25, ml: 0.5, borderLeft: '1px solid', borderColor: 'divider' }}>
          <Avatar sx={{ width: 28, height: 28, bgcolor: 'primary.light', color: 'primary.dark', fontSize: 13, fontWeight: 700 }}>{user.name.slice(0, 1)}</Avatar>
          <Chip
            label={`${user.department} · ${user.name} · ${user.title}`}
            size="small"
            variant="outlined"
            sx={{ borderRadius: 1, bgcolor: 'rgba(11, 100, 114, 0.025)', borderColor: 'rgba(11, 100, 114, 0.16)', fontWeight: 600 }}
          />
          <Tooltip title="退出登录"><IconButton size="small" onClick={handleLogout} aria-label="退出登录"><LogOut size={18} /></IconButton></Tooltip>
        </Box>
      )}
    </Box>
  );
}
