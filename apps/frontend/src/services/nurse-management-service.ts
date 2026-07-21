import { apiGet, apiPost } from '@/core/api-client';
import type {
  DepartmentChecklistResponse,
  ChecklistExecutionResponse,
  ChecklistRuleConfirmationResponse,
  MonitoringOverdueResponse,
  NursingKpiResponse,
  NursingTaskCompletionRequest,
  NursingTaskCompletionResponse,
  NursePriorityResponse,
  NurseTasksResponse,
  ShiftReportResponse,
} from '@/types/nurse-management';

export const fetchNurseTasks = () => apiGet<NurseTasksResponse>('/nurse/tasks');
export const fetchNursePriority = () => apiGet<NursePriorityResponse>('/nurse/ai-priority');
export const fetchDepartmentChecklist = () => apiGet<DepartmentChecklistResponse>('/nurse/department-checklist');
export const fetchChecklistExecution = () => apiGet<ChecklistExecutionResponse>('/nurse/checklist-execution');
export const confirmChecklistRule = (ruleId: string, note: string) => apiPost<ChecklistRuleConfirmationResponse>(`/nurse/checklist-rules/${encodeURIComponent(ruleId)}/confirm`, { note });
export const fetchShiftReport = () => apiGet<ShiftReportResponse>('/ward/shift-report');
export const fetchMonitoringOverdue = () => apiGet<MonitoringOverdueResponse>('/monitoring/overdue');
export const fetchNursingKpi = () => apiGet<NursingKpiResponse>('/nurse/kpi');
export const completeNursingTask = (
  patientId: string,
  payload: NursingTaskCompletionRequest,
  idempotencyKey: string,
) => apiPost<NursingTaskCompletionResponse>(
  `/nurse/tasks/${encodeURIComponent(patientId)}/complete`,
  payload,
  undefined,
  { 'Idempotency-Key': idempotencyKey },
);
