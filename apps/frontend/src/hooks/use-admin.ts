import { useQuery } from '@tanstack/react-query';

import {
  fetchAdminWorkload,
  fetchCdsIntegrationStatus,
  fetchDiseaseTemplates,
  fetchDiseaseTemplateDetail,
  fetchDiseaseEvidenceGraph,
  fetchDiseaseEvidenceGraphVisualization,
  fetchEvidenceGraphStatus,
  fetchMaintenanceLog,
  fetchOrganization,
  fetchRagDashboard,
  fetchRagEntries,
  fetchWardInsights,
  previewRagRetrieval,
} from '@/services/admin-service';
import { useAuthStore } from '@/stores/auth-store';

function useAdminScope() {
  const user = useAuthStore((state) => state.user);
  return `${user?.actor_id ?? 'anonymous'}:${user?.department ?? 'unassigned'}:${user?.title ?? 'untitled'}`;
}

export function useRagDashboard(enabled = true) {
  const scope = useAdminScope();
  return useQuery({ queryKey: ['admin', 'rag', 'dashboard', scope], queryFn: fetchRagDashboard, enabled, staleTime: 60_000 });
}

export function useRagEntries(search: string, layer = '', enabled = true) {
  const scope = useAdminScope();
  return useQuery({ queryKey: ['admin', 'rag', 'entries', search, layer, scope], queryFn: () => fetchRagEntries(search, layer), enabled, staleTime: 30_000 });
}

export function useMaintenanceLog(enabled = true) {
  const scope = useAdminScope();
  return useQuery({ queryKey: ['admin', 'rag', 'maintenance', scope], queryFn: fetchMaintenanceLog, enabled, staleTime: 60_000 });
}

export function useRagSemanticPreview(query: string, layer = '', enabled = true) {
  const scope = useAdminScope();
  const normalizedQuery = query.trim();
  return useQuery({
    queryKey: ['admin', 'rag', 'preview', normalizedQuery, layer, scope],
    queryFn: () => previewRagRetrieval(normalizedQuery, layer ? [layer] : []),
    enabled: enabled && normalizedQuery.length >= 2,
    staleTime: 30_000,
  });
}

export function useDiseaseTemplates(enabled = true) {
  const scope = useAdminScope();
  return useQuery({ queryKey: ['admin', 'disease-templates', scope], queryFn: fetchDiseaseTemplates, enabled, staleTime: 60_000 });
}

export function useDiseaseTemplateDetail(diseaseId?: string) {
  const scope = useAdminScope();
  return useQuery({ queryKey: ['admin', 'disease-template', diseaseId, scope], queryFn: () => fetchDiseaseTemplateDetail(diseaseId!), enabled: Boolean(diseaseId), staleTime: 60_000 });
}

export function useOrganization(enabled = true) {
  const scope = useAdminScope();
  return useQuery({ queryKey: ['admin', 'organization', scope], queryFn: fetchOrganization, enabled, staleTime: 60_000 });
}

export function useAdminWorkload(enabled = true) {
  const scope = useAdminScope();
  return useQuery({ queryKey: ['admin', 'ward', 'workload', scope], queryFn: fetchAdminWorkload, enabled, staleTime: 30_000 });
}

export function useWardInsights(enabled = true) {
  const scope = useAdminScope();
  return useQuery({ queryKey: ['admin', 'ward', 'insights', scope], queryFn: fetchWardInsights, enabled, staleTime: 30_000 });
}

export function useCdsIntegrationStatus(enabled = true) {
  const scope = useAdminScope();
  return useQuery({ queryKey: ['admin', 'integrations', 'cds-hooks', scope], queryFn: fetchCdsIntegrationStatus, enabled, staleTime: 60_000 });
}

export function useEvidenceGraphStatus(enabled = true) {
  const scope = useAdminScope();
  return useQuery({ queryKey: ['admin', 'evidence-graph', 'status', scope], queryFn: fetchEvidenceGraphStatus, enabled, staleTime: 30_000 });
}

export function useDiseaseEvidenceGraph(diseaseId: string, enabled = true) {
  const scope = useAdminScope();
  return useQuery({ queryKey: ['admin', 'evidence-graph', 'disease', diseaseId, scope], queryFn: () => fetchDiseaseEvidenceGraph(diseaseId), enabled: enabled && Boolean(diseaseId), staleTime: 30_000 });
}

export function useDiseaseEvidenceGraphVisualization(diseaseId: string, enabled = true) {
  const scope = useAdminScope();
  return useQuery({
    queryKey: ['admin', 'evidence-graph', 'visualization', diseaseId, scope],
    queryFn: () => fetchDiseaseEvidenceGraphVisualization(diseaseId),
    enabled: enabled && Boolean(diseaseId),
    staleTime: 30_000,
  });
}
