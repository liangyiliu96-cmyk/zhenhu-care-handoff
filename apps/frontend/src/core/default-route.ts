import { ROUTES } from './routes';
import { departmentDoctorRoute, departmentManagementRoute, departmentNurseRoute } from './routes';

export interface RouteIdentity {
  role: 'doctor' | 'nurse';
  title: string;
  department?: string;
}

export function isManagementUser(user: RouteIdentity): boolean {
  return user.title.includes('科主任') || user.title.includes('护士长');
}

export function defaultRouteFor(user: RouteIdentity): string {
  const department = user.department?.trim();
  if (department) {
    if (isManagementUser(user)) return departmentManagementRoute(department);
    return user.role === 'doctor' ? departmentDoctorRoute(department) : departmentNurseRoute(department);
  }
  if (isManagementUser(user)) return ROUTES.admin;
  return user.role === 'doctor' ? ROUTES.workbench : ROUTES.nurse;
}
