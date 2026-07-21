import type { DischargeCriteriaStatus } from './patient-dashboard';

export interface DifferentialDiagnosis {
  diagnosis?: string;
  likelihood?: 'high' | 'moderate' | 'low' | string;
  key_findings?: string[] | string;
  source?: string;
  [key: string]: unknown;
}

export interface ReviewAllergy {
  name?: string;
  allergen?: string;
  severity?: string;
  reaction?: string;
  [key: string]: unknown;
}

export interface ClinicalAlertPayload {
  message?: string;
  severity?: string;
  source?: string;
  [key: string]: unknown;
}

export interface MedicationAdjustmentPayload {
  drug?: string;
  medication?: string;
  dose?: string;
  frequency?: string;
  route?: string;
  action?: string;
  reason?: string;
  [key: string]: unknown;
}

export interface AbnormalLabPayload {
  name?: string;
  value?: string | number;
  unit?: string;
  ref_range?: string;
  direction?: 'high' | 'low' | string;
  [key: string]: unknown;
}

export interface VitalTrendPayload {
  timestamp?: string;
  heart_rate?: number;
  spo2?: number;
  temperature?: number;
  [key: string]: unknown;
}

export interface HandoffItem {
  type?: string;
  content?: string;
  priority?: string;
  [key: string]: unknown;
}

export interface DoctorReviewPayload {
  patient_id?: string;
  chief_complaint?: string;
  hpi_narrative?: string;
  pe_narrative?: string;
  ddx_list?: DifferentialDiagnosis[];
  allergies?: ReviewAllergy[];
  clinical_alerts?: ClinicalAlertPayload[];
  clinical_assessments?: Record<string, unknown>;
}

export interface MedicationReviewPayload {
  medication_adjustments?: MedicationAdjustmentPayload[];
  recent_alerts?: ClinicalAlertPayload[];
  vital_trend?: VitalTrendPayload[];
  abnormal_labs?: AbnormalLabPayload[];
  current_meds?: MedicationAdjustmentPayload[];
}

export interface DischargeReviewPayload {
  discharge_criteria_check?: DischargeCriteriaStatus;
  complication_risks?: ClinicalAlertPayload[];
  medication_current?: MedicationAdjustmentPayload[];
  latest_soap?: Record<string, unknown>;
  handoff_items?: HandoffItem[];
}

export interface PendingReviewPayload extends DoctorReviewPayload, MedicationReviewPayload, DischargeReviewPayload {
  [key: string]: unknown;
}

export interface PendingItem {
  type: 'ddx_confirm' | 'med_confirm' | 'discharge_sign';
  label: string;
  review_type: ReviewType;
  review_id: string;
  payload?: PendingReviewPayload;
}

export type ReviewType = 'doctor_confirm' | 'med_confirm' | 'discharge_sign';
export type ReviewDecision = 'approved' | 'rejected' | 'signed';

export interface PendingPatient {
  patient_id: string;
  name: string;
  disease: string;
  phase: string;
  state_version: number;
  items: PendingItem[];
}

export interface PendingResponse {
  department: string;
  pending: PendingPatient[];
  count: number;
  summary: {
    total_patients: number;
    total_items: number;
    ddx_pending: number;
    med_pending: number;
    discharge_pending: number;
  };
}

export interface RawClinicalAlert {
  alert_id?: string;
  message?: string;
  severity?: string;
  status?: string;
  created_at?: string;
  source?: string;
}

export interface WorkspaceAlertItem {
  patient_id: string;
  name: string;
  severity?: string;
  alert: RawClinicalAlert;
}

export interface AlertItem {
  patient_id: string;
  name: string;
  alert_id: string;
  message: string;
  severity: 'critical' | 'warning' | 'info';
  created_at?: string;
  status?: string;
  source?: string;
}

export interface WorkspaceAlertsResponse {
  department: string;
  alerts: AlertItem[];
  count: number;
  summary: {
    total: number;
    red: number;
    yellow: number;
  };
}

export interface WardPatient {
  patient_id: string;
  name: string;
  disease: string;
  department: string;
  phase: string;
  risk_level?: string;
  news2_score?: number;
  discharge_ready?: boolean;
  alert_count?: number;
  updated_at?: number | string;
}

export interface WardPatientsResponse {
  department: string;
  patients: WardPatient[];
  count: number;
  summary: {
    total: number;
    high_risk: number;
    news2_high: number;
    discharge_ready: number;
  };
}

export type PatientDirectoryPhase = 'admission' | 'monitoring' | 'discharge' | 'confirm' | 'review';
export type PatientDirectorySort = 'risk' | 'phase' | 'name';

export interface PatientDirectoryFilters {
  phase?: PatientDirectoryPhase;
  risk_level?: 'low' | 'medium' | 'high';
  disease?: string;
  search?: string;
  sort?: PatientDirectorySort;
  limit?: number;
  offset?: number;
}

export interface PatientDirectoryPatient {
  patient_id: string;
  name: string;
  disease: string;
  phase: string;
  risk_level: string;
  round_count: number;
  discharge_decision?: string | null;
  has_pending_review: boolean;
  pending_review_type?: ReviewType | null;
  alert_count: number;
  latest_vs: {
    systolic?: number | null;
    diastolic?: number | null;
    heart_rate?: number | null;
    spo2?: number | null;
    temperature?: number | null;
  };
  document_count: number;
}

export interface PatientDirectoryResponse {
  total: number;
  filters: Pick<PatientDirectoryFilters, 'phase' | 'risk_level' | 'disease' | 'search'>;
  patients: PatientDirectoryPatient[];
  pagination: {
    limit: number;
    offset: number;
    returned: number;
    has_more: boolean;
  };
}

export interface DdxEdit {
  action: 'add' | 'remove' | 'reorder';
  diagnosis?: string;
  item?: DifferentialDiagnosis;
  new_order?: string[];
}

export interface HandoffEdit {
  action: 'add' | 'remove' | 'edit';
  index?: number;
  item?: HandoffItem;
}

export interface MedicationDoctorOrder {
  medication: string;
  dose?: string;
  frequency?: string;
}

export interface LabDoctorOrder {
  labs: Array<{ name: string }>;
}

export type DoctorOrders = MedicationDoctorOrder | LabDoctorOrder;

export interface ReviewSubmission {
  review_type: ReviewType;
  decision: ReviewDecision;
  comment?: string;
  reject_reason?: string;
  expected_version: number;
  edits?: {
    hpi_narrative?: string;
    pe_narrative?: string;
    chief_complaint?: string;
    ddx_edits?: DdxEdit[];
    allergies?: ReviewAllergy[];
  };
  handoff_edits?: HandoffEdit[];
  doctor_action?: 'continue' | 'adjust' | 'new_labs' | 'discharge';
  doctor_orders?: DoctorOrders;
}

export interface ReviewSubmissionResult {
  patient_id: string;
  review_type: ReviewType;
  decision: ReviewDecision;
  status: 'resumed' | 'pending_review';
  phase?: string;
  discharge_decision?: string | null;
}

export interface WardOverview {
  total: number;
  pending_reviews: number;
  by_risk: { high: number; medium: number; low: number };
  patients: WardPatient[];
}

export interface WardAlertOverviewItem {
  patient_id: string;
  patient_name: string;
  disease: string;
  risk_level?: string;
  alert: unknown;
  is_critical: boolean;
  phase?: string;
}

export interface WardAlertOverviewResponse {
  total: number;
  critical: number;
  patients_with_alerts: number;
  alerts: WardAlertOverviewItem[];
}

export type WardVitalMetric = 'spo2' | 'systolic' | 'heart_rate' | 'temperature';

export interface WardVitalPatient {
  patient_id: string;
  name: string;
  disease: string;
  risk_level?: string;
  vital_values: Array<number | string | null>;
  trend: 'improving' | 'stable' | 'declining';
  alert_count: number;
}

export interface WardVitalsResponse {
  total: number;
  vital: WardVitalMetric;
  summary: { improving: number; stable: number; declining: number };
  patients: WardVitalPatient[];
}

export interface WardTrendPatient {
  patient_id: string;
  name: string;
  disease: string;
  risk?: string;
  round: number;
  bp_sys: string;
  bp_trend: string;
  spo2: number | string;
  spo2_trend: string;
  hr: number | string;
  hr_trend: string;
  temp: number | string;
  temp_trend: string;
  alerts: number;
}

export interface WardTrendsResponse {
  total: number;
  deteriorating: number;
  patients: WardTrendPatient[];
}

export interface WardVisitPatient {
  patient_id: string;
  name: string;
  risk?: string;
  news2?: number | null;
  alerts: number;
  has_pending: boolean;
  deteriorating: boolean;
  spo2?: number | null;
  hr?: number | null;
  round_count: number;
  department: string;
}

export interface WardVisitOrderResponse {
  reason: string;
  total: number;
  urgent: number;
  stable: number;
  visit_order: WardVisitPatient[];
}

export interface WardPriorityPatient {
  patient_id: string;
  name: string;
  disease: string;
  risk?: string | null;
  news2?: number | null;
  padua?: number | null;
  alerts: number;
  round: number;
  bp?: number | null;
  spo2?: number | null;
  discharge?: string | null;
}

export interface WardPriorityResponse {
  total: number;
  top_patients: WardPriorityPatient[];
  reasoning: string;
}

export interface WardAbnormalLab {
  patient_id: string;
  patient_name: string;
  disease: string;
  department: string;
  risk?: string | null;
  lab_name: string;
  value: number;
  unit: string;
  ref_range: string;
  direction: 'high' | 'low';
  deviation: number;
}

export interface WardLabSummaryResponse {
  total: number;
  patients_affected: number;
  departments_affected: number;
  abnormal_labs: WardAbnormalLab[];
}

export interface WorkloadRow {
  department: string;
  total: number;
  high_risk: number;
  pending: number;
  overdue: number;
  load_score?: number;
}
