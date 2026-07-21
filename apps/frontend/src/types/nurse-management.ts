export interface NurseTask {
  patient_id: string;
  state_version: number;
  name: string;
  disease: string;
  department: string;
  risk_level?: string;
  phase?: string;
  round_count?: number;
  vital_signs_due: boolean;
  last_vs_time?: string;
  latest_vital_values?: {
    systolic?: number | null;
    diastolic?: number | null;
    spo2?: number | null;
    temperature?: number | null;
  };
  alert_count: number;
  pending_nursing_actions: string[];
  pending_medications: string[];
  open_task_count?: number;
  task_items?: NursingTaskItem[];
  department_checklist?: string[];
  bedside_flags?: {
    vs_trend?: string;
    complication_alerts?: string[];
    pain_score?: number | null;
    pain_location?: string;
    bmi?: number | null;
    fall_risk?: string;
  };
}

/**
 * Nursing patient detail can be backed either by an actionable nursing task or
 * by the read-only patient directory. Only task-backed records may write.
 */
export interface NursePatientDetail {
  patient_id: string;
  name: string;
  disease: string;
  department: string;
  risk_level?: string;
  phase?: string;
  round_count?: number;
  alert_count: number;
  latest_vital_values?: NurseTask['latest_vital_values'];
  bedside_flags?: NurseTask['bedside_flags'];
  open_task_count?: number;
  task_items?: NursingTaskItem[];
  writable: boolean;
  state_version?: number;
  vital_signs_due?: boolean;
}

export type NursingTaskType = 'vital_signs' | 'nursing_action' | 'medication' | 'checklist';

export interface NursingTaskItem {
  task_key: string;
  task_type: NursingTaskType;
  title: string;
  description: string;
  priority: 'normal' | 'high';
}

export interface NurseTasksResponse {
  total: number;
  open_task_count?: number;
  vital_signs_overdue: number;
  with_alerts: number;
  tasks: NurseTask[];
}

export interface MonitoringOverduePatient {
  patient_id: string;
  state_version: number;
  name: string;
  disease: string;
  department: string;
  risk_level?: string;
  alert_count: number;
  monitoring_interval_hours: number;
  hours_since_last_vs: number;
  overdue_by_hours: number;
  last_vs_values: Record<string, number>;
  phase?: string;
}

export interface MonitoringOverdueResponse {
  total: number;
  critical_overdue: number;
  patients: MonitoringOverduePatient[];
}

export interface NursePriorityResponse {
  advice: string;
  total_patients?: number;
  ranked: Array<{ name: string; risk?: string; news2?: number; alerts?: number; dept?: string }>;
}

export interface DepartmentChecklistResponse {
  departments?: Record<string, string[]>;
  department?: string;
  checklist?: string[];
}

export interface ChecklistRuleConfirmation {
  audit_id: string;
  actor_id?: string | null;
  actor_name?: string | null;
  note?: string;
  confirmed_at: string;
}

export interface ChecklistExecutionRule {
  rule_id: string;
  title: string;
  task_types: NursingTaskType[];
  status: 'confirmed' | 'action_required' | 'not_triggered';
  patient_count: number;
  task_count: number;
  overdue_count: number;
  patients: Array<NurseTask & { matched_tasks: NursingTaskItem[] }>;
  confirmation?: ChecklistRuleConfirmation | null;
}

export interface ChecklistExecutionResponse {
  department: string;
  window_date: string;
  rules: ChecklistExecutionRule[];
  summary: { total: number; confirmed: number; action_required: number; not_triggered: number; overdue: number };
}

export interface ChecklistRuleConfirmationResponse {
  rule_id: string;
  status: 'confirmed';
  confirmation: ChecklistRuleConfirmation;
  idempotent: boolean;
}

export interface ShiftPatient {
  patient_id: string;
  name: string;
  risk?: string;
  news2?: number;
  alerts: number;
  shift_summary?: string;
}

export interface ShiftReportResponse {
  total: number;
  today_discharge: number;
  high_focus: ShiftPatient[];
  stable: ShiftPatient[];
  discharge_today: ShiftPatient[];
  ai_report: string;
}

export interface NursingTaskCompletionRequest {
  task_type: NursingTaskType;
  task_key: string;
  note: string;
  expected_version: number;
}

export interface NursingTaskCompletion {
  id: string;
  task_key: string;
  task_type: NursingTaskType;
  title: string;
  note: string;
  completed_at: string;
  actor_id?: string;
  actor_name?: string;
}

export interface NursingTaskCompletionResponse {
  completion: NursingTaskCompletion;
  state_version: number;
}

export interface NursingKpiResponse {
  scope: { departments: string[]; patient_count: number };
  window_hours: number;
  window_started_at: string;
  open_tasks: number;
  completed_tasks: number;
  overdue_tasks: number;
  completion_rate: number;
  by_type: Record<NursingTaskType, { open: number; completed: number }>;
  recent_completions: Array<NursingTaskCompletion & {
    patient_id: string;
    patient_name: string;
    department: string;
  }>;
}
