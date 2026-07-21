import { apiGet, apiPost } from '@/core/api-client';
import { API_TIMEOUT_AGENT } from '@/config/api';
import type {
  AdminCapabilitiesResponse,
  AdminOperationResponse,
  AdminWorkloadResponse,
  DatabaseStatsResponse,
  DiseaseTemplateDetail,
  DiseaseTemplatesResponse,
  CdsIntegrationStatusResponse,
  DemoPatientResetResponse,
  MaintenanceLogResponse,
  OrgResponse,
  RagDashboardResponse,
  RagEntriesResponse,
  RagSemanticPreviewResponse,
  WardInsightsResponse,
} from '@/types/admin';
import type { DiseaseEvidenceGraphResponse, EvidenceGraphStatusResponse, EvidenceGraphVisualizationResponse } from '@/types/evidence-graph';

export const fetchRagDashboard = () => apiGet<RagDashboardResponse>('/admin/rag/dashboard');

export function fetchRagEntries(search = '', layer = '') {
  const params = new URLSearchParams({ page_size: '30' });
  if (search.trim()) params.set('search', search.trim());
  if (layer) params.set('layer', layer);
  return apiGet<RagEntriesResponse>(`/admin/rag/entries?${params}`);
}

export const fetchMaintenanceLog = () => apiGet<MaintenanceLogResponse>('/admin/rag/maintenance-log');
export function previewRagRetrieval(query: string, layers: string[] = []) {
  const params = new URLSearchParams({ query, top_k: '5' });
  if (layers.length) params.set('layers', layers.join(','));
  return apiGet<RagSemanticPreviewResponse>(`/admin/rag/preview?${params}`, API_TIMEOUT_AGENT);
}
export const fetchDiseaseTemplates = () => apiGet<DiseaseTemplatesResponse>('/inpatient/templates');
export const fetchDiseaseTemplateDetail = (diseaseId: string) => apiGet<DiseaseTemplateDetail>(`/inpatient/templates/${encodeURIComponent(diseaseId)}`);
export const fetchOrganization = () => apiGet<OrgResponse>('/inpatient/org');
export const fetchAdminWorkload = () => apiGet<AdminWorkloadResponse>('/ward/workload');
export const fetchWardInsights = () => apiGet<WardInsightsResponse>('/ward/insights');
export const fetchAdminCapabilities = () => apiGet<AdminCapabilitiesResponse>('/inpatient/admin-capabilities');
export const fetchDatabaseStats = () => apiGet<DatabaseStatsResponse>('/inpatient/db-stats');
export const reindexKnowledge = (layers: string[] = []) => {
  const suffix = layers.length ? `?layers=${encodeURIComponent(layers.join(','))}` : '';
  return apiPost<AdminOperationResponse>(`/admin/rag/reindex${suffix}`, undefined, API_TIMEOUT_AGENT);
};
export const seedOrganization = () => apiPost<AdminOperationResponse>('/inpatient/org/seed', undefined, API_TIMEOUT_AGENT);
export const seedAllSystemData = () => apiPost<AdminOperationResponse>('/inpatient/seed-all', undefined, API_TIMEOUT_AGENT);
export const clearExpiredState = () => apiPost<AdminOperationResponse>('/inpatient/clear-expired');
export const resetDemoPatients = () => apiPost<DemoPatientResetResponse>('/inpatient/fixtures/reset-demo', { confirmed: true, purge_runtime: true });
export const fetchCdsIntegrationStatus = () => apiGet<CdsIntegrationStatusResponse>('/cds-services/status');
export const fetchEvidenceGraphStatus = () => apiGet<EvidenceGraphStatusResponse>('/admin/evidence-graph/status');
export const fetchDiseaseEvidenceGraph = (diseaseId: string) => apiGet<DiseaseEvidenceGraphResponse>(`/admin/evidence-graph/diseases/${encodeURIComponent(diseaseId)}`);
export const fetchDiseaseEvidenceGraphVisualization = (diseaseId: string) => apiGet<EvidenceGraphVisualizationResponse>(`/admin/evidence-graph/diseases/${encodeURIComponent(diseaseId)}/visualization`);
export const rebuildEvidenceGraph = () => apiPost<AdminOperationResponse>('/admin/evidence-graph/rebuild', undefined, API_TIMEOUT_AGENT);
