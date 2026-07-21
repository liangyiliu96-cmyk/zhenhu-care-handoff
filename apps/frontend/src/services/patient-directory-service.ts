import { apiGet } from '@/core/api-client';
import type { PatientDirectoryFilters, PatientDirectoryResponse } from '@/types/ward';

export function fetchPatientDirectory(filters: PatientDirectoryFilters = {}): Promise<PatientDirectoryResponse> {
  const params = new URLSearchParams();
  if (filters.phase) params.set('phase', filters.phase);
  if (filters.risk_level) params.set('risk_level', filters.risk_level);
  if (filters.disease?.trim()) params.set('disease', filters.disease.trim());
  if (filters.search?.trim()) params.set('search', filters.search.trim());
  params.set('sort', filters.sort ?? 'risk');
  params.set('limit', String(filters.limit ?? 20));
  params.set('offset', String(filters.offset ?? 0));
  return apiGet<PatientDirectoryResponse>(`/patients?${params.toString()}`);
}
