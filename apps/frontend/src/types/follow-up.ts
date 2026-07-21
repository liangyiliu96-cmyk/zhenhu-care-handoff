export type FollowUpOverviewFilter = 'pending' | 'overdue' | 'abnormal' | 'high_risk';

export interface FollowUpTaskOverview {
  id: string;
  title: string;
  due_at?: string | null;
  assignee?: string | null;
  status: string;
  note: string;
  is_open: boolean;
  is_overdue: boolean;
  has_abnormal_feedback: boolean;
}

export interface FollowUpPatientOverview {
  patient_id: string;
  name: string;
  disease: string;
  department: string;
  discharge_status: string;
  follow_up_status: 'pending' | 'overdue' | 'completed' | string;
  pending_task_count: number;
  overdue_task_count: number;
  abnormal_feedback_count: number;
  feedback_status: 'abnormal' | 'unreported' | string;
  readmission_risk: 'high' | 'medium' | 'low' | string;
  risk_method: 'rule_based_follow_up_priority';
  risk_basis: string[];
  next_due_at?: string | null;
  contact: { has_contact: boolean; follow_up_consent: boolean; preferred_channel?: string | null; masked_mobile_phone?: string | null };
  tasks: FollowUpTaskOverview[];
}

export interface FollowUpOverviewResponse {
  summary: { total_patients: number; pending_follow_ups: number; overdue_follow_ups: number; abnormal_feedbacks: number; high_readmission_risk: number };
  risk_method: 'rule_based_follow_up_priority';
  filters: { status?: FollowUpOverviewFilter | null };
  patients: FollowUpPatientOverview[];
  pagination: { limit: number; offset: number; returned: number; has_more: boolean };
}
