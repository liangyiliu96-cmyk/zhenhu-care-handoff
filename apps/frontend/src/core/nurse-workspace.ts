export type NurseBoardTab = 'overview' | 'tasks' | 'patients' | 'overdue' | 'shift' | 'checklist';

export function nurseBoardTab(value: string | null): NurseBoardTab {
  return value === 'tasks' || value === 'patients' || value === 'overdue' || value === 'shift' || value === 'checklist' ? value : 'overview';
}
