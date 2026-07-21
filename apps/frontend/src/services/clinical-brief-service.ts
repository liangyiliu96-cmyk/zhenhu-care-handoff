import { apiGet } from '@/core/api-client';

export interface ClinicalBriefItem { label?: string; value?: string | number; unit?: string; }
export interface ClinicalAlertGroup { key: string; title: string; urgency: 'high' | 'medium' | 'low'; items: string[]; count: number; }
export interface LabChange { name: string; current: string | number; previous: string | number; unit: string; delta: number; direction: 'up' | 'down'; recommendation: string; }
export interface ClinicalBrief {
  patient_id: string;
  state_version: number;
  generated_by: 'rule_based_clinical_brief';
  round_preview: { summary: string; latest_vitals: ClinicalBriefItem[]; focus_questions: string[]; pending_reviews: string[]; next_action: string; };
  alert_groups: ClinicalAlertGroup[];
  lab_changes: LabChange[];
  handoff_brief: { current_assessment: string; unresolved_problems: string[]; pending_actions: string[]; next_shift_focus: Array<string | Record<string, unknown>>; };
  discharge_blockers: Array<{ reason: string; action: string }>;
  education_brief: { topics: string[]; teach_back_questions: string[]; completed_count: number; requires_human_record: boolean; };
}

export const fetchClinicalBrief = (patientId: string) => apiGet<ClinicalBrief>(`/inpatient/${encodeURIComponent(patientId)}/clinical-brief`);
