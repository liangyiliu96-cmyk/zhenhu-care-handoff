import type { PatientDirectoryPatient } from '@/types/ward';
import type { NursePatientDetail } from '@/types/nurse-management';

export function directoryPatientToNurseDetail(patient: PatientDirectoryPatient, department: string): NursePatientDetail {
  return {
    patient_id: patient.patient_id,
    name: patient.name,
    disease: patient.disease,
    department,
    risk_level: patient.risk_level,
    phase: patient.phase,
    round_count: patient.round_count,
    alert_count: patient.alert_count,
    latest_vital_values: {
      systolic: patient.latest_vs.systolic,
      diastolic: patient.latest_vs.diastolic,
      spo2: patient.latest_vs.spo2,
      temperature: patient.latest_vs.temperature,
    },
    open_task_count: 0,
    task_items: [],
    writable: false,
  };
}

/**
 * Apply a confirmed task completion to the open drawer while invalidated
 * queries are refetching. The server response supplies the new version.
 */
export function applyNursingTaskCompletion(
  patient: NursePatientDetail,
  taskKey: string,
  stateVersion: number,
): NursePatientDetail {
  const taskItems = patient.task_items?.filter((task) => task.task_key !== taskKey);
  const openTaskCount = patient.open_task_count == null
    ? patient.open_task_count
    : Math.max(0, patient.open_task_count - 1);
  return { ...patient, state_version: stateVersion, task_items: taskItems, open_task_count: openTaskCount };
}

export function nursePatientDisplayName(patient: { patient_id: string; name?: string | null }): string {
  const name = patient.name?.trim() ?? '';
  return !name || name === patient.patient_id.slice(0, 10) ? patient.patient_id : name;
}

export function riskLabel(value?: string): string {
  return value === 'high' ? '高风险' : value === 'medium' ? '中风险' : value === 'low' ? '低风险' : '未分层';
}

export function riskColor(value?: string): 'error' | 'warning' | 'success' | 'default' {
  return value === 'high' ? 'error' : value === 'medium' ? 'warning' : value === 'low' ? 'success' : 'default';
}

export function formatBp(systolic?: number | null, diastolic?: number | null): string {
  return systolic == null && diastolic == null ? '--' : `${systolic ?? '--'} / ${diastolic ?? '--'} mmHg`;
}
