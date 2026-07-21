export type DoctorWorkbenchView = 'today' | 'rounds' | 'patients' | 'alerts' | 'discharge' | 'followup';
export type PatientWorkspaceSection = 'overview' | 'rounds' | 'monitoring' | 'orders' | 'records';

export function resolveDoctorWorkbenchView(search: string): DoctorWorkbenchView {
  const params = new URLSearchParams(search);
  if (params.get('tab') === 'overview') return 'patients';
  const view = params.get('view');
  return isWorkbenchView(view) ? view : 'today';
}

export function resolvePatientWorkspaceSection(search: string): PatientWorkspaceSection {
  const section = new URLSearchParams(search).get('section');
  return isPatientSection(section) ? section : 'overview';
}

export function patientIdFromPath(pathname: string): string | null {
  const match = pathname.match(/^\/patient\/([^/]+)(?:\/discharge)?$/);
  return match ? decodeURIComponent(match[1]) : null;
}

export function patientWorkflowStage(phase: string): number {
  const normalized = String(phase || '').toLowerCase();
  if (['completed', 'closed', 'archived'].some((value) => normalized.includes(value))) return 3;
  if (['discharge', 'handoff', 'confirm'].some((value) => normalized.includes(value))) return 2;
  if (['monitoring', 'medication', 'review', 'round', 'treatment'].some((value) => normalized.includes(value))) return 1;
  return 0;
}

function isWorkbenchView(value: string | null): value is DoctorWorkbenchView {
  return ['today', 'rounds', 'patients', 'alerts', 'discharge', 'followup'].includes(value ?? '');
}

function isPatientSection(value: string | null): value is PatientWorkspaceSection {
  return ['overview', 'rounds', 'monitoring', 'orders', 'records'].includes(value ?? '');
}
