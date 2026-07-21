import { useQuery } from '@tanstack/react-query';

import { fetchPatientDirectory } from '@/services/patient-directory-service';
import { useAuthStore } from '@/stores/auth-store';
import type { PatientDirectoryFilters } from '@/types/ward';

export function usePatientDirectory(filters: PatientDirectoryFilters) {
  const user = useAuthStore((state) => state.user);
  const scope = `${user?.actor_id ?? 'anonymous'}:${user?.department ?? 'unassigned'}`;
  return useQuery({
    queryKey: ['patients', scope, filters],
    queryFn: () => fetchPatientDirectory(filters),
    staleTime: 5_000,
    refetchOnMount: 'always',
    refetchInterval: 30_000,
  });
}
