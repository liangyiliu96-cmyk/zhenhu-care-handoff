import { apiGet } from '@/core/api-client';

export interface ClinicalCitation {
  source?: string;
  title?: string;
  content?: string;
  excerpt?: string;
  citation?: string;
  version?: string;
  [key: string]: unknown;
}

export interface EvidenceResponse {
  patient_id: string;
  citations: ClinicalCitation[];
  count: number;
}

export function fetchPatientEvidence(patientId: string): Promise<EvidenceResponse> {
  return apiGet<EvidenceResponse>(`/inpatient/${encodeURIComponent(patientId)}/evidence`);
}
