import { Badge, Box, List, ListItemButton, ListItemIcon, ListItemText, Typography } from '@mui/material';
import { Activity, AlertTriangle, ArrowLeft, BarChart2, BookOpen, CalendarCheck, ClipboardCheck, ClipboardList, Clock3, Files, FileText, GitCompare, Handshake, History, LayoutDashboard, ListChecks, ListOrdered, Network, Pill, Stethoscope, Users, type LucideIcon } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

import { adminTabsFor } from '@/core/admin-tabs';
import { patientIdFromPath, resolveDoctorWorkbenchView, resolvePatientWorkspaceSection } from '@/core/doctor-workspace';
import { departmentDoctorRoute, departmentNurseRoute, dischargeRoute, nurseRoute, patientWorkspaceRoute, ROUTES, workbenchRoute } from '@/core/routes';
import { useAuthStore } from '@/stores/auth-store';

interface NavItem {
  label: string;
  path: string;
  icon: string;
  badge?: number;
}

const DOCTOR_NAV: NavItem[] = [
  { label: '今日工作', path: workbenchRoute('today'), icon: 'clipboard-list', badge: 0 },
  { label: '查房顺序', path: workbenchRoute('rounds'), icon: 'list-ordered' },
  { label: '病区患者', path: workbenchRoute('patients'), icon: 'users' },
  { label: '临床告警', path: workbenchRoute('alerts'), icon: 'alert-triangle' },
  { label: '出院协同', path: workbenchRoute('discharge'), icon: 'handshake' },
];

const NURSE_NAV: NavItem[] = [
  { label: '班次总览', path: nurseRoute(), icon: 'layout-dashboard', badge: 0 },
  { label: '护理任务', path: nurseRoute('tasks'), icon: 'clipboard-check' },
  { label: '在院患者', path: nurseRoute('patients'), icon: 'users' },
  { label: '逾期监测', path: nurseRoute('overdue'), icon: 'clock-3' },
  { label: '交接班', path: nurseRoute('shift'), icon: 'git-compare' },
  { label: '制度执行', path: nurseRoute('checklist'), icon: 'list-checks' },
];

DOCTOR_NAV.push({ label: '出院随访', path: workbenchRoute('followup'), icon: 'calendar-check' });

const ICONS: Record<string, LucideIcon> = {
  'clipboard-list': ClipboardList,
  'layout-dashboard': LayoutDashboard,
  'clipboard-check': ClipboardCheck,
  'git-compare': GitCompare,
  'clock-3': Clock3,
  'book-open': BookOpen,
  files: Files,
  users: Users,
  'bar-chart-2': BarChart2,
  'list-checks': ListChecks,
  'list-ordered': ListOrdered,
  'alert-triangle': AlertTriangle,
  handshake: Handshake,
  'calendar-check': CalendarCheck,
  activity: Activity,
  history: History,
  'file-text': FileText,
  pill: Pill,
  stethoscope: Stethoscope,
  network: Network,
};

export default function LeftNav() {
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((state) => state.user);

  if (!user) return null;

  const isAdminPage = location.pathname.startsWith(ROUTES.admin) || location.pathname.endsWith('/management');
  const isDoctorWorkspace = location.pathname === ROUTES.workbench || location.pathname.endsWith('/doctor');
  const patientId = user.role === 'doctor' ? patientIdFromPath(location.pathname) : null;
  const isPatientPage = Boolean(patientId);
  const doctorNav = user.department
    ? DOCTOR_NAV.map((item) => ({ ...item, path: departmentDoctorRoute(user.department, new URLSearchParams(item.path.split('?')[1]).get('view') ?? undefined) }))
    : DOCTOR_NAV;
  const nurseNav = user.department
    ? NURSE_NAV.map((item) => ({ ...item, path: departmentNurseRoute(user.department, new URLSearchParams(item.path.split('?')[1]).get('tab') ?? undefined) }))
    : NURSE_NAV;
  const items: NavItem[] = isAdminPage
    ? adminTabsFor(user).map((tab) => ({ ...tab }))
    : user.role === 'nurse' ? nurseNav
      : patientId ? [
        { label: '临床概览', path: patientWorkspaceRoute(patientId, 'overview'), icon: 'layout-dashboard' },
        { label: '查房管理', path: patientWorkspaceRoute(patientId, 'rounds'), icon: 'stethoscope' },
        { label: '监测与检验', path: patientWorkspaceRoute(patientId, 'monitoring'), icon: 'activity' },
        { label: '医嘱与协同', path: patientWorkspaceRoute(patientId, 'orders'), icon: 'pill' },
        { label: '文书与病程', path: patientWorkspaceRoute(patientId, 'records'), icon: 'file-text' },
        { label: '出院交接', path: dischargeRoute(patientId), icon: 'handshake' },
      ] : doctorNav;
  const currentPath = `${location.pathname}${location.search}`;

  const selected = (item: NavItem) => {
    if (isDoctorWorkspace) {
      const target = resolveDoctorWorkbenchView(item.path.includes('?') ? item.path.slice(item.path.indexOf('?')) : '');
      return resolveDoctorWorkbenchView(location.search) === target;
    }
    if (patientId && item.path.includes('/discharge')) return location.pathname.endsWith('/discharge');
    if (patientId && item.path.includes('section=')) {
      const target = resolvePatientWorkspaceSection(item.path.slice(item.path.indexOf('?')));
      return !location.pathname.endsWith('/discharge') && resolvePatientWorkspaceSection(location.search) === target;
    }
    return item.path === currentPath;
  };

  return (
    <Box sx={{ width: 264, flexShrink: 0, borderRight: '1px solid', borderColor: 'divider', bgcolor: 'background.paper', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ px: 2, py: 2.1, borderBottom: '1px solid', borderColor: 'divider', bgcolor: 'rgba(11, 100, 114, 0.035)' }}>
        <Typography variant="overline" color="text.secondary">
          {isAdminPage ? '管理控制台' : user.role === 'doctor' ? isPatientPage ? '患者临床工作区' : '医生病区工作台' : '护理看板'}
        </Typography>
        {!isAdminPage ? <Typography variant="body2" fontWeight={600} sx={{ mt: 0.35 }}>{user.department || '未分配科室'}</Typography> : null}
      </Box>

      {isPatientPage ? <Box sx={{ px: 1, pt: 1 }}><ListItemButton onClick={() => navigate(user.department ? departmentDoctorRoute(user.department, 'today') : workbenchRoute('today'))} sx={{ borderRadius: 1 }}><ListItemIcon sx={{ minWidth: 30 }}><ArrowLeft size={16} /></ListItemIcon><ListItemText primary="返回病区工作台" primaryTypographyProps={{ fontSize: 12.5 }} /></ListItemButton></Box> : null}

      <List dense sx={{ flex: 1, py: 1.5 }}>
        {items.map((item) => {
          const Icon = ICONS[item.icon] ?? LayoutDashboard;
          return (
            <ListItemButton key={item.path} selected={selected(item)} onClick={() => navigate(item.path)} sx={{ mx: 1.1, px: 1.25, borderRadius: 1, mb: 0.5, minHeight: 44, '&:hover': { bgcolor: 'rgba(11, 100, 114, 0.055)' }, '&.Mui-selected': { bgcolor: 'rgba(11, 100, 114, 0.11)', color: 'primary.dark', '&::before': { content: '""', width: 3, height: 24, borderRadius: '0 2px 2px 0', bgcolor: 'primary.main', position: 'absolute', left: 0 } } }}>
              <ListItemIcon sx={{ minWidth: 32, color: 'inherit' }}><Icon size={17} strokeWidth={selected(item) ? 2.25 : 1.8} /></ListItemIcon>
              <ListItemText primary={item.label} primaryTypographyProps={{ fontSize: 13, fontWeight: selected(item) ? 700 : 500 }} />
              {item.badge ? <Badge badgeContent={item.badge} color="error" sx={{ mr: 1 }} /> : null}
            </ListItemButton>
          );
        })}
      </List>
      <Box sx={{ mx: 1.25, mb: 1.5, px: 0.75, pt: 1.35, borderTop: '1px solid', borderColor: 'divider' }}>
        <Typography variant="overline" color="text.secondary">{user.role === 'doctor' ? 'Clinical workspace' : 'Nursing workspace'}</Typography>
        <Typography variant="caption" display="block" color="text.secondary" sx={{ mt: 0.15 }}>{user.title}</Typography>
      </Box>

    </Box>
  );
}
