import { Box, Chip, Typography } from '@mui/material';
import { Stethoscope, UserRound, UsersRound } from 'lucide-react';

import { useOrganization } from '@/hooks/use-admin';
import { useAuthStore } from '@/stores/auth-store';

function personLabel(name?: string, title?: string) {
  if (!name) return '待配置';
  return title ? `${name} · ${title}` : name;
}

export default function DepartmentLeadershipStrip() {
  const user = useAuthStore((state) => state.user);
  const organization = useOrganization(Boolean(user?.department));
  const leadership = organization.data?.leadership;

  if (!user?.department || organization.isLoading || organization.error || !leadership) return null;

  const items = [
    { label: '科主任', value: personLabel(leadership.medical_director?.name, leadership.medical_director?.title), icon: <Stethoscope size={15} />, tone: '#216a7b' },
    { label: '护士长', value: personLabel(leadership.head_nurse?.name, leadership.head_nurse?.title), icon: <UsersRound size={15} />, tone: '#557a4e' },
    { label: '当前身份', value: personLabel(user.name, user.title), icon: <UserRound size={15} />, tone: '#b3623d' },
  ];

  return <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'auto repeat(3, minmax(150px, max-content))' }, alignItems: 'center', gap: { xs: 1, md: 2.25 }, px: 1.5, py: 1.15, borderTop: '1px solid', borderBottom: '1px solid', borderColor: 'divider', bgcolor: 'rgba(255, 255, 255, 0.64)' }}>
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8 }}><Chip size="small" label={user.department} color="info" variant="outlined" sx={{ bgcolor: 'info.light', borderColor: 'transparent', color: 'info.dark' }} /><Typography variant="caption" color="text.secondary">科室协同</Typography></Box>
    {items.map((item) => <Box key={item.label} sx={{ display: 'flex', alignItems: 'center', gap: 0.65, minWidth: 0, color: item.tone, py: 0.2 }}><Box sx={{ width: 26, height: 26, borderRadius: 0.75, display: 'grid', placeItems: 'center', bgcolor: `${item.tone}16` }}>{item.icon}</Box><Box sx={{ minWidth: 0 }}><Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.25 }}>{item.label}</Typography><Typography variant="caption" fontWeight={700} noWrap sx={{ display: 'block', lineHeight: 1.35 }}>{item.value}</Typography></Box></Box>)}
  </Box>;
}
