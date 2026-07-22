export interface DischargeCriteriaStatus {
  all_met?: boolean;
  checked?: string[];
  unmet?: Array<string | number> | string;
  met_count?: number;
  total_count?: number;
  details?: Array<{
    key: string;
    label: string;
    met: boolean;
    category: 'monitoring' | 'orders' | 'records' | 'discharge' | string;
    action: string;
  }>;
  [key: string]: unknown;
}

export interface DashboardResponse {
  patient_id: string;
  patient_name: string;
  state_version: number;
  is_on_hold: boolean;
  phase: string;
  template_name: string;
  template_id?: string;
  vital_trend: Array<{ timestamp: string; heart_rate?: number; blood_pressure?: string; spo2?: number; temperature?: number }>;
  vital_trend_direction: Record<string, string>;
  soap_summary?: Record<string, unknown> | null;
  ddx_top3: Array<Record<string, unknown>>;
  abnormal_labs: Array<{ name: string; value: string; unit?: string; ref_range?: string | null }>;
  medication_current: Array<Record<string, unknown>>;
  complication_alerts: string[];
  discharge_criteria_status?: DischargeCriteriaStatus | null;
  discharge_blockers: Array<{
    key?: string;
    reason: string;
    action: string;
    target?: 'monitoring' | 'orders' | 'records' | 'discharge' | 'handoff' | 'contact' | string;
    status?: 'blocking' | 'resolved' | string;
  }>;
  nursing_summary: Record<string, unknown>;
  last_updated: string;
  delta_summary: { summary?: string; detail?: string[]; new_alerts?: number; total_rounds?: number };
  medication_journey: Array<{ drug?: string; action?: string; detail?: string; source?: string }>;
  pain_gcs_trend: { pain_latest?: number; pain_trend?: string; pain_location?: string; gcs_latest?: number; gcs_trend?: string | null };
  action_history: Array<{ action?: string; decision?: string; by?: string }>;
  ai_recommendation: string;
  decision_checklist: Array<{ task?: string; urgency?: string; status?: string; action?: string; source?: string }>;
  discharge_readiness: { score?: number; status?: string; deductions?: string[] };
  icd10_codes: Array<{ diagnosis?: string; icd10_code?: string | null }>;
  medication_safety: MedicationSafety;
  pending_review_type: string;
  pending_review_id: string;
  discharge_sign_status: string;
  handoff_acknowledged: boolean;
  patient_confirmation_status: string;
  patient_confirmation_requirements: string[];
  patient_confirmation_evidence: Array<Record<string, unknown>>;
  bridge_status: string;
  bridge_error: string;
}

export interface MedicationSafetyConflict {
  drug_pair: string;
  severity: 'contraindicated' | 'major' | 'moderate' | 'minor' | string;
  mechanism: string;
  consequence: string;
  recommendation: string;
  evidence: string;
  source: string;
  model_suggested: boolean;
}

export interface MedicationSafety {
  status: 'complete' | 'not_run' | string;
  conflicts: MedicationSafetyConflict[];
  allergy_contraindications: Array<{ medication: string; allergen: string; severity: string; recommendation: string }>;
  gaps: string[];
  duplications: string[];
  warnings: string[];
}

export interface ScoresResponse {
  patient_id: string;
  news2: ClinicalScore;
  qsofa: ClinicalScore;
  padua: ClinicalScore;
  score_source?: string | null;
  calculated_at?: string | null;
  vte_prophylaxis: 'checked' | 'pending' | 'not_applicable';
  stroke_antithrombotic: 'checked' | 'pending' | 'not_applicable';
  mdt: 'triggered' | 'not triggered';
}

export interface ClinicalScore {
  score?: number | null;
  risk?: string | null;
  status: 'available' | 'not_available' | string;
  reason?: string | null;
  basis?: string[];
}

export interface TimelineResponse {
  patient_id: string;
  phase?: string;
  round_count: number;
  events: Array<{ key: string; label: string; icon?: string; order?: number }>;
  alerts: unknown[];
  ai_recommendation?: string;
}

export interface VitalTrendsResponse {
  patient_id: string;
  total_measurements: number;
  trends: Record<string, { unit: string; latest: number; min: number; max: number; avg: number; direction: string; data: Array<{ value: number; timestamp: string; round?: number }> }>;
}

export interface LabTrendsResponse {
  patient_id: string;
  total_labs: number;
  lab_trends: Record<string, {
    unit: string;
    ref_range?: string | null;
    latest: number;
    min: number;
    max: number;
    abnormal_count: number;
    total_count: number;
    values: Array<{ index?: number; value: number | null; is_abnormal: boolean }>;
  }>;
}

export interface ClinicalNoteResponse {
  patient_id: string;
  chief_complaint?: string;
  hpi_narrative?: string;
  pe_narrative?: string;
  allergies?: unknown[];
  ros_findings?: unknown;
  pmh?: unknown;
  fh?: unknown;
  sh?: unknown;
}

export interface NursingRecord {
  timestamp?: string;
  recorded_at?: string;
  action?: string;
  nursing_actions?: string;
  intake_ml?: number;
  output_ml?: number;
  medications_administered?: Array<Record<string, unknown>>;
  alerts?: string[];
  citations?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface NursingRecordsResponse {
  patient_id: string;
  total: number;
  records: NursingRecord[];
}

export interface PatientQueryResponse {
  patient_id: string;
  question: string;
  answer: string;
  citations: Array<Record<string, unknown>>;
}

export interface DoctorCommandResponse {
  patient_id: string;
  action: string;
  status: 'held' | 'executed' | 'pending_review';
  phase: string;
  message: string;
}

export interface CareManagementResponse {
  patient_id: string;
  care_management: {
    medication_orders: Array<Record<string, unknown>>;
    investigation_orders?: Array<Record<string, unknown>>;
    mdt_requests: Array<Record<string, unknown>>;
    education_plans?: Array<Record<string, unknown>>;
    education_records: Array<Record<string, unknown>>;
    follow_up_tasks: Array<Record<string, unknown>>;
  };
}

export interface WorkflowBrief {
  kind: 'mdt' | 'follow_up' | 'transfer' | string;
  title: string;
  content: string;
  citations: Array<Record<string, unknown>>;
  generation_source: 'llm_rag' | 'rule_based' | string;
  generated_at: string;
  status: 'draft' | string;
}

export interface WorkflowBriefsResponse {
  patient_id: string;
  state_version: number;
  briefs: Partial<Record<'mdt' | 'follow_up' | 'transfer', WorkflowBrief>>;
}

export interface DischargeSummaryResponse {
  patient_id: string;
  primary_diagnosis: string;
  secondary_diagnoses: string[];
  hospital_course: string[];
  discharge_medications: Array<Record<string, unknown>>;
  follow_up_plan: Array<Record<string, unknown>>;
  critical_events: string[];
  discharge_decision: string;
  handoff_summary: Array<Record<string, unknown>>;
  last_updated: string;
  narrative: string;
  completeness?: { coverage?: number; missing?: string[]; warning?: string };
}

export interface RoundRecord {
  type?: string;
  format?: string;
  subjective?: unknown;
  objective?: unknown;
  assessment?: unknown;
  plan?: unknown;
  round_number?: number;
  timestamp?: string;
  generation_source?: 'llm_assisted' | 'rule_based' | 'agent_generated_legacy' | string;
  review_status?: 'requires_clinician_review' | 'reviewed' | string;
  reviewed_at?: string;
  reviewed_by?: string;
  review_comment?: string;
  doctor_revision?: { subjective?: string; objective?: string; assessment?: string; plan?: string; attention?: string };
  edited_at?: string;
  edited_by?: string;
  ai_recommendation?: string;
  citations?: Array<Record<string, unknown>>;
  source_nodes?: string[];
}

export interface RoundsResponse {
  patient_id: string;
  state_version?: number;
  round_count: number;
  total: number;
  rounds: RoundRecord[];
  latest_soap: RoundRecord;
  phase?: string;
}

export interface RoundMutationResponse {
  patient_id: string;
  state_version: number;
  round: RoundRecord;
  idempotent?: boolean;
}

export interface PreRoundBriefResponse {
  patient_id: string;
  state_version: number;
  attention_items: Array<{
    kind: string;
    priority: 'high' | 'medium' | 'low' | string;
    title: string;
    action: string;
    facts: Array<{ source_type: string; source_id: string; observed_at?: string; field: string; value: unknown }>;
  }>;
  history_gaps: Array<{ field: string; label: string; status: 'needs_input' | string; prompt: string }>;
}

export interface ProgressNoteDraftResponse {
  patient_id: string;
  state_version: number;
  generation_source: string;
  write_back: string;
  sections: Record<'subjective' | 'objective' | 'assessment' | 'plan', { text: string; status: 'draft' | 'needs_input' | string; facts: Array<Record<string, unknown>> }>;
}
