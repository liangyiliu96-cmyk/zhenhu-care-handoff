import { useQuery } from '@tanstack/react-query';

import { fetchFollowUpOverview } from '@/services/follow-up-service';
import { useAuthStore } from '@/stores/auth-store';
import type { FollowUpOverviewFilter } from '@/types/follow-up';

export function useFollowUpOverview(status?: FollowUpOverviewFilter) {
  const user = useAuthStore((state) => state.user);
  const scope = `${user?.actor_id ?? 'anonymous'}:${user?.department ?? 'unassigned'}`;
  return useQuery({ queryKey: ['follow-up', scope, status], queryFn: () => fetchFollowUpOverview({ status }), staleTime: 20_000, refetchInterval: 60_000 });
}
