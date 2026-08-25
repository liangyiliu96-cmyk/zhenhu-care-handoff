export interface EvidenceGraphStatusResponse {
  configured: boolean;
  reachable: boolean;
  database: string;
  nodes: Record<string, number>;
  relationships: number;
  needs_rebuild?: boolean;
  last_rebuild?: {
    rebuilt_at?: string;
    evidence: number;
    rules: number;
    evidence_sources: Record<string, number>;
    knowledge_source_enabled: boolean;
  } | null;
  knowledge_sync?: {
    enabled: boolean;
    requires_rebuild?: boolean;
    latest_change_at?: string | null;
    latest_change_event?: string | null;
    latest_changed_document_id?: string | null;
    reason?: string | null;
    status?: string;
  };
  error?: string;
}

export interface EvidenceGraphRule {
  relation: 'HAS_DISCHARGE_CRITERION' | 'HAS_MEDICATION_RULE' | 'HAS_MONITORING_RULE' | 'HAS_CARE_TASK' | string;
  labels: string[];
  key: string;
  content: string;
  disease_name?: string;
  department?: string;
}

export interface EvidenceGraphEvidence {
  id: string;
  layer: string;
  source: string;
  category: string;
  topic: string;
  text: string;
  version?: string;
  source_type?: string;
  evidence_level?: string;
  guideline_year?: number | string;
  source_credibility?: number | string;
  evidence_metadata_origin?: string;
}

export interface PatientEvidenceGraphResponse {
  patient_id: string;
  disease_id?: string;
  available: boolean;
  reason?: string;
  evidence: EvidenceGraphEvidence[];
  rules: EvidenceGraphRule[];
}

export interface DiseaseEvidenceGraphResponse {
  disease_id: string;
  evidence: EvidenceGraphEvidence[];
  rules: EvidenceGraphRule[];
}

export type EvidenceGraphNodeKind = 'disease' | 'evidence' | 'rule' | 'source' | 'layer' | 'department';

export interface EvidenceGraphVisualizationNode {
  id: string;
  kind: EvidenceGraphNodeKind;
  label: string;
  disease_id?: string;
  department?: string;
  source?: string;
  layer?: string;
  category?: string;
  text?: string;
  version?: string;
  key?: string;
  content?: string;
  labels?: string[];
  relation?: string;
}

export interface EvidenceGraphVisualizationEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
}

export interface EvidenceGraphVisualizationResponse {
  disease_id: string;
  root_id: string;
  nodes: EvidenceGraphVisualizationNode[];
  edges: EvidenceGraphVisualizationEdge[];
}
