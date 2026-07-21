import { useQuery } from '@tanstack/react-query';
import { fetchOverview, fetchPending, fetchWorkspaceAlerts, fetchWardAlertOverview, fetchWardPatients, fetchAiSummary, fetchWardLabSummary, fetchWardPriority, fetchWardTrends, fetchWardVisitOrder, fetchWardVitals } from '@/services/ward-service';
import { useAuthStore } from '@/stores/auth-store';
import type { WardVitalMetric } from '@/types/ward';

function useWardScope() {
  const user = useAuthStore((state) => state.user);
  return `${user?.actor_id ?? 'anonymous'}:${user?.department ?? 'unassigned'}`;
}

export function useWardPending() {
  const scope = useWardScope();
  return useQuery({
    queryKey: ['ward', 'pending', scope],
    queryFn: fetchPending,
    staleTime: 10_000,
    refetchInterval: 30_000,
  });
}

export function useWardAlerts() {
  const scope = useWardScope();
  return useQuery({
    queryKey: ['ward', 'alerts', scope],
    queryFn: fetchWorkspaceAlerts,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
}

export function useWardPatients() {
  const scope = useWardScope();
  return useQuery({
    queryKey: ['ward', 'patients', scope],
    queryFn: () => fetchWardPatients(),
    staleTime: 5_000,
    refetchOnMount: 'always',
  });
}

export function useWardAiSummary() {
  const scope = useWardScope();
  return useQuery({
    queryKey: ['ward', 'ai-summary', scope],
    queryFn: fetchAiSummary,
    staleTime: 60_000,
  });
}

export function useWardOverview() {
  const scope = useWardScope();
  return useQuery({ queryKey: ['ward', 'overview', scope], queryFn: fetchOverview, staleTime: 20_000, refetchInterval: 30_000 });
}

export function useWardAlertOverview(enabled = true) {
  const scope = useWardScope();
  return useQuery({ queryKey: ['ward', 'alert-overview', scope], queryFn: fetchWardAlertOverview, enabled, staleTime: 15_000, refetchInterval: 30_000 });
}

export function useWardVitals(vital: WardVitalMetric, enabled = true) {
  const scope = useWardScope();
  return useQuery({ queryKey: ['ward', 'vitals', vital, scope], queryFn: () => fetchWardVitals(vital), enabled, staleTime: 15_000, refetchInterval: 30_000 });
}

export function useWardTrends(enabled = true) {
  const scope = useWardScope();
  return useQuery({ queryKey: ['ward', 'trends', scope], queryFn: fetchWardTrends, enabled, staleTime: 15_000, refetchInterval: 30_000 });
}

export function useWardVisitOrder(enabled = true) {
  const scope = useWardScope();
  return useQuery({ queryKey: ['ward', 'visit-order', scope], queryFn: fetchWardVisitOrder, enabled, staleTime: 20_000, refetchInterval: 30_000 });
}

export function useWardPriority(enabled = true) {
  const scope = useWardScope();
  return useQuery({ queryKey: ['ward', 'priority', scope], queryFn: () => fetchWardPriority(), enabled, staleTime: 20_000, refetchInterval: 30_000 });
}

export function useWardLabSummary(enabled = true) {
  const scope = useWardScope();
  return useQuery({ queryKey: ['ward', 'lab-summary', scope], queryFn: fetchWardLabSummary, enabled, staleTime: 15_000, refetchInterval: 30_000 });
}
