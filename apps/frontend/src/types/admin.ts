export interface RagLayerStatus {
  collection?: string;
  expected?: number;
  actual?: number;
  health: 'ok' | 'incomplete' | 'missing' | 'error';
  category?: string;
  error?: string;
}

export interface RagDashboardResponse {
  total_documents: number;
  total_layers: number;
  layers: Record<string, RagLayerStatus>;
  issues: string[];
  needs_attention: boolean;
  last_indexed?: string;
  runtime?: RagRuntimeStatus;
}

export interface RagRuntimeStatus {
  index_revision: string;
  last_reindex?: { indexed_at?: number; documents?: number; layers?: Record<string, number> } | null;
  cache: { backend: 'redis' | 'memory'; available: boolean; hits: number; misses: number; writes: number; errors: number; memory_entries: number };
  query_cache_ttl_seconds: number;
  embedding_cache_ttl_seconds: number;
  model: string;
  dimension: number;
  process_cache: { embedding_hits: number; embedding_misses: number; search_hits: number; search_misses: number };
}

export interface RagSemanticPreviewResponse {
  query: string;
  layers: string[];
  results: Array<RagEntry & { layer?: string; score?: number; source?: string; version?: string }>;
  count: number;
  latency_ms: number;
  index_revision: string;
}

export interface RagEntry {
  id: string | number;
  topic: string;
  category: string;
  disease_id?: string;
  department?: string;
  text?: string;
  indexed_at?: string;
}

export interface RagEntriesResponse {
  layers: Record<string, { collection?: string; count?: number; items?: RagEntry[]; error?: string }>;
  search: string;
  page: number;
  page_size?: number;
  failed_layers?: string[];
}

export interface DiseaseTemplate {
  disease_id: string;
  name: string;
  department: string;
  updated_at?: string | number | null;
}

export interface DiseaseTemplatesResponse {
  templates: DiseaseTemplate[];
  count: number;
}

export interface DiseaseTemplateDetail extends DiseaseTemplate {
  monitoring_interval_hours?: number | null;
  vital_signs: Array<{ name?: string; unit?: string; alert_above?: number; alert_below?: number; alert_if?: string }>;
  risk_factors: string[];
  discharge_criteria: Array<{ condition?: string; description?: string }>;
  handoff_instructions: Array<{ type?: string; content?: string }>;
  followup_questions: Array<{ id?: string; question?: string; clinical_intent?: string }>;
  requires_doctor_review: boolean;
}

export interface MaintenanceTask {
  priority: 'high' | 'low' | 'info' | string;
  task: string;
  detail: string;
  action: string;
}

export interface MaintenanceLogResponse {
  tasks: MaintenanceTask[];
  source_file?: string;
}

export interface OrgStaffMember {
  name?: string;
  title?: string;
  job_number?: string;
  department?: string;
  role?: 'doctor' | 'nurse';
  specialty?: string;
  shift?: string;
  is_manager?: boolean;
}

export interface DepartmentLeadership {
  department?: string;
  medical_director?: OrgStaffMember | null;
  head_nurse?: OrgStaffMember | null;
}

export interface OrgDepartment {
  department: string;
  doctors: OrgStaffMember[];
  nurses: OrgStaffMember[];
  total: number;
}

export interface OrgResponse {
  scope: string;
  your_department?: string;
  department?: string;
  your_title?: string;
  leadership?: DepartmentLeadership;
  departments?: OrgDepartment[];
  summary?: Record<string, number>;
}

export interface AdminWorkloadRow {
  department: string;
  total: number;
  active: number;
  high_risk: number;
  pending_review: number;
  vital_overdue: number;
  total_alerts: number;
  high_risk_ratio?: number;
  overdue_ratio?: number;
  avg_alerts_per_patient?: number;
  total_rounds?: number;
}

export interface AdminWorkloadResponse {
  total_departments: number;
  total_active: number;
  total_high_risk: number;
  total_pending: number;
  departments: AdminWorkloadRow[];
}

export interface WardInsightsResponse {
  insight: string;
  stats: {
    total_active: number;
    high_risk: number;
    pending_review: number;
    total_alerts: number;
  };
  top_departments: Array<{ department: string; patients: number }>;
}

export interface AdminCapabilitiesResponse {
  is_manager: boolean;
  environment: 'development' | 'production';
  auth_mode?: string;
  writes_enabled: boolean;
  production_switch_enabled: boolean;
  authorization_reason?: 'authorized' | 'manager_role_required' | 'production_switch_disabled' | 'permission_claim_missing';
  required_permission?: string | null;
  operations: Record<'rag_reindex' | 'organization_seed' | 'seed_all' | 'clear_expired' | 'demo_patient_reset' | 'database_stats' | 'evidence_graph_rebuild', boolean>;
}

export interface DatabaseStatsResponse {
  memory_entries: number;
  file_size_mb: number;
  [key: string]: string | number | null;
}

export interface AdminOperationResponse {
  audit_id: string;
  [key: string]: unknown;
}

export interface DemoPatientResetResponse extends AdminOperationResponse {
  pack_version: string;
  removed: number;
  total: number;
  by_department: Record<string, number>;
  patient_ids: string[];
}

export interface CdsIntegrationStatusResponse {
  standard: string;
  environment: string;
  auth_mode: string;
  discovery_url: string;
  service_count: number;
  services: Array<{
    id: string;
    hook: string;
    title: string;
    description: string;
    endpoint: string;
    patient_access_enforced: boolean;
  }>;
  checks: Record<'discovery' | 'handlers' | 'patient_access', 'ready' | 'enforced' | string>;
}
