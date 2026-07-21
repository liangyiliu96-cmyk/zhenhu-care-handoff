import { apiPost } from '@/core/api-client';
import { API_TIMEOUT_AGENT } from '@/config/api';
import type { ReviewSubmission, ReviewSubmissionResult } from '@/types/ward';

export function submitReview(patientId: string, request: ReviewSubmission): Promise<ReviewSubmissionResult> {
  return apiPost<ReviewSubmissionResult>(`/inpatient/review/${encodeURIComponent(patientId)}`, request, API_TIMEOUT_AGENT);
}
