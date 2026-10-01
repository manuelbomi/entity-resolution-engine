// These mirror the shapes returned by the FastAPI backend (see
// backend/app/main.py). Keeping them in one file makes it obvious when the
// frontend and backend have drifted apart.

export interface SourceSummary {
  source_name: string
  record_count: number
}

export interface FieldValue {
  value: string
  source_name: string
  source_id: string
}

export interface EntitySummary {
  entity_id: string
  member_keys: string[]
  source_count: number
  fields: Record<string, FieldValue>
}

export interface AuditEntry {
  timestamp: string
  action: string
  detail: string
}

export interface EntityDetail extends EntitySummary {
  audit_log: AuditEntry[]
}

export interface EntityListResponse {
  total: number
  page: number
  page_size: number
  items: EntitySummary[]
}

export interface SourceRecordView {
  record_key: string
  source_name: string
  hostname: string
  ip_address: string | null
  owner: string | null
  environment: string | null
  os: string | null
  last_seen: string
}

export interface CandidateMatch {
  candidate_id: string
  status: string
  composite_score: number
  field_scores: Record<string, number | null>
  record_a: SourceRecordView
  record_b: SourceRecordView
}

export interface Metrics {
  total_source_records: number
  total_entities: number
  multi_source_entities: number
  match_rate: number
  pending_review_count: number
  confidence_distribution: Record<string, number>
  records_per_source: Record<string, number>
}
