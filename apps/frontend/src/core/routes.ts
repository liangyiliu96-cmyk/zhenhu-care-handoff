export const ROUTES = {
  home: '/',
  login: '/login',
  callback: '/callback',
  workbench: '/workbench',
  patientTemplate: '/patient/:id',
  dischargeTemplate: '/patient/:id/discharge',
  nurse: '/nurse',
  admin: '/admin',
  departmentDoctorTemplate: '/department/:department/doctor',
  departmentNurseTemplate: '/department/:department/nurse',
  departmentManagementTemplate: '/department/:department/management',
} as const;

function withQuery(path: string, key: string, value?: string) {
  return value ? `${path}?${key}=${encodeURIComponent(value)}` : path;
}

export function workbenchRoute(view?: string) {
  return withQuery(ROUTES.workbench, 'view', view);
}

export function workbenchReviewRoute(patientId: string, reviewType: string) {
  const params = new URLSearchParams({
    view: 'today',
    reviewPatient: patientId,
    reviewType,
  });
  return `${ROUTES.workbench}?${params.toString()}`;
}

export function patientRoute(patientId: string) {
  return `/patient/${encodeURIComponent(patientId)}`;
}

export function patientWorkspaceRoute(patientId: string, section?: string, focus?: string) {
  const path = withQuery(patientRoute(patientId), 'section', section);
  return focus ? `${path}${section ? '&' : '?'}focus=${encodeURIComponent(focus)}` : path;
}

export function dischargeRoute(patientId: string, focus?: 'handoff' | 'contact') {
  return withQuery(`${patientRoute(patientId)}/discharge`, 'focus', focus);
}

export function nurseRoute(tab?: string) {
  return withQuery(ROUTES.nurse, 'tab', tab);
}

export function adminRoute(tab?: string) {
  return withQuery(ROUTES.admin, 'tab', tab);
}

function departmentPath(department: string, workspace: 'doctor' | 'nurse' | 'management') {
  return `/department/${encodeURIComponent(department)}/${workspace}`;
}

export function departmentDoctorRoute(department: string, view?: string) {
  return withQuery(departmentPath(department, 'doctor'), 'view', view);
}

export function departmentNurseRoute(department: string, tab?: string) {
  return withQuery(departmentPath(department, 'nurse'), 'tab', tab);
}

export function departmentManagementRoute(department: string, tab?: string) {
  return withQuery(departmentPath(department, 'management'), 'tab', tab);
}
