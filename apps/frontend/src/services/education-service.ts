import { apiGet } from '@/core/api-client';

export interface EducationResource {
  topic?: string;
  text?: string;
  source?: string;
  layer?: string;
  disease_id?: string;
  [key: string]: unknown;
}

export interface EducationSearchResponse {
  query: string;
  layer?: string | null;
  results: EducationResource[];
  count: number;
}

export function fetchEducationResources(query: string, diseaseId = ''): Promise<EducationSearchResponse> {
  const params = new URLSearchParams({ query, layer: 'L9', top_k: '5' });
  if (diseaseId.trim()) params.set('disease_id', diseaseId.trim());
  return apiGet<EducationSearchResponse>(`/inpatient/rag/search?${params.toString()}`);
}
