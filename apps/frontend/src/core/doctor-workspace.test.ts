import { describe, expect, it } from 'vitest';

import { patientIdFromPath, patientWorkflowStage, resolveDoctorWorkbenchView, resolvePatientWorkspaceSection } from './doctor-workspace';

describe('doctor workspace navigation', () => {
  it('keeps the legacy overview query compatible with the patient registry view', () => {
    expect(resolveDoctorWorkbenchView('?tab=overview')).toBe('patients');
    expect(resolveDoctorWorkbenchView('?view=rounds')).toBe('rounds');
    expect(resolveDoctorWorkbenchView('')).toBe('today');
  });

  it('resolves patient workspace sections without inventing unknown views', () => {
    expect(resolvePatientWorkspaceSection('?section=orders')).toBe('orders');
    expect(resolvePatientWorkspaceSection('?section=monitoring')).toBe('monitoring');
    expect(resolvePatientWorkspaceSection('?section=unknown')).toBe('overview');
  });

  it('extracts patient context and maps clinical phases to a visible workflow stage', () => {
    expect(patientIdFromPath('/patient/patient-1')).toBe('patient-1');
    expect(patientIdFromPath('/patient/patient-1/discharge')).toBe('patient-1');
    expect(patientWorkflowStage('monitoring')).toBe(1);
    expect(patientWorkflowStage('handoff')).toBe(2);
  });
});
