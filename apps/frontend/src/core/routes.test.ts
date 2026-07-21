import { describe, expect, it } from 'vitest';

import { adminRoute, departmentDoctorRoute, departmentManagementRoute, departmentNurseRoute, dischargeRoute, nurseRoute, patientRoute, patientWorkspaceRoute, ROUTES, workbenchReviewRoute, workbenchRoute } from './routes';

describe('routes', () => {
  it('keeps static application paths stable', () => {
    expect(ROUTES).toMatchObject({ home: '/', login: '/login', workbench: '/workbench', nurse: '/nurse', admin: '/admin' });
  });

  it('encodes dynamic patient identifiers and query values', () => {
    expect(patientRoute('patient/1')).toBe('/patient/patient%2F1');
    expect(patientWorkspaceRoute('patient/1', 'rounds and monitoring')).toBe('/patient/patient%2F1?section=rounds%20and%20monitoring');
    expect(patientWorkspaceRoute('patient/1', 'monitoring', 'vital_signs_stable')).toBe('/patient/patient%2F1?section=monitoring&focus=vital_signs_stable');
    expect(dischargeRoute('patient/1', 'contact')).toBe('/patient/patient%2F1/discharge?focus=contact');
    expect(dischargeRoute('patient/1')).toBe('/patient/patient%2F1/discharge');
  });

  it('does not add an empty query parameter', () => {
    expect(workbenchRoute()).toBe(ROUTES.workbench);
    expect(workbenchRoute('alerts')).toBe('/workbench?view=alerts');
    expect(workbenchReviewRoute('patient/1', 'med_confirm')).toBe('/workbench?view=today&reviewPatient=patient%2F1&reviewType=med_confirm');
    expect(nurseRoute('overdue')).toBe('/nurse?tab=overdue');
    expect(adminRoute('ward')).toBe('/admin?tab=ward');
  });

  it('creates independently addressable department workspaces', () => {
    expect(departmentDoctorRoute('呼吸科', 'rounds')).toBe('/department/%E5%91%BC%E5%90%B8%E7%A7%91/doctor?view=rounds');
    expect(departmentNurseRoute('肾内科', 'tasks')).toBe('/department/%E8%82%BE%E5%86%85%E7%A7%91/nurse?tab=tasks');
    expect(departmentManagementRoute('骨科')).toBe('/department/%E9%AA%A8%E7%A7%91/management');
  });
});
