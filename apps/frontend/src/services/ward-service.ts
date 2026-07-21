import { apiGet } from '@/core/api-client';
import type {
  AlertItem,
  WardAlertOverviewResponse,
  PendingResponse,
  WardPatientsResponse,
  WardLabSummaryResponse,
  WardPriorityResponse,
  WardTrendsResponse,
  WardVisitOrderResponse,
  WardVitalMetric,
  WardVitalsResponse,
  WardOverview,
  WorkspaceAlertItem,
  WorkspaceAlertsResponse,
} from '@/types/ward';

export function fetchPending(): Promise<PendingResponse> {
  return apiGet<PendingResponse>('/ward/pending');
}

function semanticSeverity(rawSeverity?: string, workspaceSeverity?: string): AlertItem['severity'] {
  const value = `${rawSeverity ?? ''} ${workspaceSeverity ?? ''}`.toLowerCase();
  if (value.includes('critical') || value.includes('🔴')) return 'critical';
  if (value.includes('warning') || value.includes('🟡')) return 'warning';
  return 'info';
}

export function normalizeWorkspaceAlert(item: WorkspaceAlertItem): AlertItem {
  const alert = item.alert ?? {};
  return {
    patient_id: item.patient_id,
    name: item.name,
    alert_id: alert.alert_id ?? `${item.patient_id}:${alert.message ?? 'alert'}`,
    message: alert.message ?? '未提供告警说明',
    severity: semanticSeverity(alert.severity, item.severity),
    created_at: alert.created_at,
    status: alert.status,
    source: alert.source,
  };
}

export async function fetchWorkspaceAlerts(): Promise<WorkspaceAlertsResponse> {
  const response = await apiGet<Omit<WorkspaceAlertsResponse, 'alerts'> & { alerts: WorkspaceAlertItem[] }>('/ward/workspace/alerts');
  return { ...response, alerts: response.alerts.map(normalizeWorkspaceAlert) };
}

export function fetchWardPatients(department?: string): Promise<WardPatientsResponse> {
  const qs = department ? `?department=${encodeURIComponent(department)}` : '';
  return apiGet<WardPatientsResponse>(`/ward/patients${qs}`);
}

export function fetchAiSummary(): Promise<{ summary: string }> {
  return apiGet<{ summary: string }>('/ward/ai-summary');
}

export function fetchOverview(): Promise<WardOverview> {
  return apiGet<WardOverview>('/ward/overview');
}

export function fetchWardAlertOverview(): Promise<WardAlertOverviewResponse> {
  return apiGet<WardAlertOverviewResponse>('/ward/alerts');
}

export function fetchWardVitals(vital: WardVitalMetric): Promise<WardVitalsResponse> {
  return apiGet<WardVitalsResponse>(`/ward/vitals?vital=${encodeURIComponent(vital)}`);
}

export function fetchWardTrends(): Promise<WardTrendsResponse> {
  return apiGet<WardTrendsResponse>('/ward/trends');
}

export function fetchWardVisitOrder(): Promise<WardVisitOrderResponse> {
  return apiGet<WardVisitOrderResponse>('/ward/visit-order');
}

export function fetchWardPriority(explain = false): Promise<WardPriorityResponse> {
  return apiGet<WardPriorityResponse>(`/ward/priority${explain ? '?explain=true' : ''}`);
}

export function fetchWardLabSummary(): Promise<WardLabSummaryResponse> {
  return apiGet<WardLabSummaryResponse>('/ward/lab-summary');
}
