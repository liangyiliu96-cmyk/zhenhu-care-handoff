import { apiGet } from '@/core/api-client';
import type { FollowUpOverviewFilter, FollowUpOverviewResponse } from '@/types/follow-up';

export function fetchFollowUpOverview(filters: { status?: FollowUpOverviewFilter; limit?: number; offset?: number } = {}): Promise<FollowUpOverviewResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set('status', filters.status);
  params.set('limit', String(filters.limit ?? 50));
  params.set('offset', String(filters.offset ?? 0));
  return apiGet<FollowUpOverviewResponse>(`/inpatient/follow-up-overview?${params.toString()}`);
}
