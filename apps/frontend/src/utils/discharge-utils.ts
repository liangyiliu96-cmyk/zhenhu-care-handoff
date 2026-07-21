import type { DischargeCriteriaStatus } from '@/types/patient-dashboard';

export function canSignDischarge(criteria?: DischargeCriteriaStatus | null): boolean {
  return criteria?.all_met === true;
}

export function dischargeBlockers(criteria?: DischargeCriteriaStatus | null): string[] {
  const unmet = criteria?.unmet;
  return Array.isArray(unmet) ? unmet.map((item) => String(item)).filter(Boolean) : [];
}
