import { useQuery } from '@tanstack/react-query';

import {
  fetchDepartmentChecklist,
  fetchChecklistExecution,
  fetchMonitoringOverdue,
  fetchNursingKpi,
  fetchNursePriority,
  fetchNurseTasks,
  fetchShiftReport,
} from '@/services/nurse-management-service';
import { fetchNursingRecords } from '@/services/patient-service';
import { useAuthStore } from '@/stores/auth-store';

function useNurseScope() {
  const user = useAuthStore((state) => state.user);
  return `${user?.actor_id ?? 'anonymous'}:${user?.department ?? 'unassigned'}`;
}

export function useNurseTasks(enabled: boolean) {
  const scope = useNurseScope();
  return useQuery({ queryKey: ['nurse', 'tasks', scope], queryFn: fetchNurseTasks, enabled, staleTime: 20_000 });
}

export function useNursePriority(enabled: boolean) {
  const scope = useNurseScope();
  return useQuery({ queryKey: ['nurse', 'priority', scope], queryFn: fetchNursePriority, enabled, staleTime: 30_000 });
}

export function useDepartmentChecklist(enabled: boolean) {
  const scope = useNurseScope();
  return useQuery({ queryKey: ['nurse', 'department-checklist', scope], queryFn: fetchDepartmentChecklist, enabled, staleTime: 60_000 });
}

export function useChecklistExecution(enabled: boolean) {
  const scope = useNurseScope();
  return useQuery({ queryKey: ['nurse', 'checklist-execution', scope], queryFn: fetchChecklistExecution, enabled, staleTime: 15_000, refetchInterval: 30_000 });
}

export function useShiftReport(enabled: boolean) {
  const scope = useNurseScope();
  return useQuery({ queryKey: ['nurse', 'shift-report', scope], queryFn: fetchShiftReport, enabled, staleTime: 30_000 });
}

export function useMonitoringOverdue(enabled: boolean) {
  const scope = useNurseScope();
  return useQuery({ queryKey: ['nurse', 'monitoring-overdue', scope], queryFn: fetchMonitoringOverdue, enabled, staleTime: 10_000, refetchInterval: 30_000 });
}

export function useNursingKpi(enabled: boolean) {
  const scope = useNurseScope();
  return useQuery({ queryKey: ['nurse', 'kpi', scope], queryFn: fetchNursingKpi, enabled, staleTime: 20_000 });
}

export function useNursingRecords(patientId?: string) {
  const scope = useNurseScope();
  return useQuery({
    queryKey: ['nurse', 'patient', patientId, 'records', scope],
    queryFn: () => fetchNursingRecords(patientId!),
    enabled: Boolean(patientId),
    staleTime: 15_000,
  });
}
