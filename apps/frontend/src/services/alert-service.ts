import { apiGet, apiPost } from '@/core/api-client';

export interface ClinicalAlert {
  alert_id: string;
  message: string;
  severity?: 'critical' | 'warning' | 'info' | string;
  status?: 'open' | 'acknowledged' | 'resolved' | string;
  acknowledged_at?: string;
  acknowledged_by?: string;
  resolved_at?: string;
  resolved_by?: string;
}

export interface PatientAlertsResponse { patient_id: string; state_version: number; alerts: ClinicalAlert[]; }

export const fetchPatientAlerts = (patientId: string) => apiGet<PatientAlertsResponse>(`/inpatient/${encodeURIComponent(patientId)}/alerts`);
export const transitionAlert = (patientId: string, alertId: string, action: 'acknowledge' | 'resolve', expectedVersion: number) => apiPost<{ patient_id: string; state_version: number; alert: ClinicalAlert }>(`/inpatient/${encodeURIComponent(patientId)}/alerts/${encodeURIComponent(alertId)}/${action}`, { expected_version: expectedVersion });
