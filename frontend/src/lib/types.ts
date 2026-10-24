export type Provenance = "LIVE" | "CACHED" | "SANDBOX" | "USER_SUBMITTED" | "SYNTHETIC" | "TEST" | "BLOCKED_EXTERNAL" | "UNAVAILABLE";
export type PolicyStatus = "PASS" | "WARN" | "NEEDS_REVIEW" | "BLOCK";

export type Requirement = { item: string; quantity: number };

export type EmergencyEvent = {
  id: string;
  title: string;
  description?: string | null;
  categories: { id: string; title: string }[];
  sources: { id: string; url: string }[];
  link?: string;
  first_observed?: string | null;
  last_observed?: string | null;
  latest_geometry?: { type: string; date: string; coordinates: unknown; magnitude_value?: number | null; magnitude_unit?: string | null } | null;
  point?: { lat: number; lon: number } | null;
  state?: string | null;
  provenance: Provenance | null;
  retrieved_at: string | null;
  source_url?: string | null;
};

export type Mission = {
  id: string;
  organization_id: string;
  name: string;
  status: string;
  delivery_location: string;
  delivery_deadline: string;
  budget: string;
  currency: string;
  requirements: Requirement[];
  max_supplier_share?: string | null;
  single_source_only?: boolean;
  emergency_event_id?: string | null;
  emergency_event?: EmergencyEvent | null;
  emergency_event_error?: string | null;
  created_via?: string;
};

export type QuoteLine = { item: string; unit_price: string; available_quantity: number; delivery_date: string; restrictions?: string | null };
export type Quote = {
  id: string;
  supplier_id: string;
  supplier_email: string;
  supplier_name?: string | null;
  status: string;
  version: number;
  currency?: string;
  shipping_cost: string;
  expires_at: string;
  provenance?: Provenance;
  is_demo?: boolean;
  lines: QuoteLine[];
};

export type Decision = {
  rule_id: string;
  status: PolicyStatus;
  severity: string;
  reason: string;
  subject: "supplier" | "quote";
  subject_id: string;
  evidence_ids: string[];
};

export type SupplierPolicy = { status: PolicyStatus; decisions: Decision[]; legal_name?: string | null; email?: string | null; is_demo: boolean };
export type QuotePolicy = { status: PolicyStatus; eligible: boolean; supplier_id: string; supplier_status: PolicyStatus; decisions: Decision[]; version: number };

export type Evidence = {
  id: string;
  subject_id: string;
  subject_name?: string | null;
  type: string;
  provider: string;
  status: string;
  summary: string;
  confidence?: number | null;
  source_url?: string | null;
  retrieved_at?: string | null;
  expires_at?: string | null;
  provenance: Provenance;
  adapter_status?: string;
  adapter_error?: string | null;
  raw_reference: Record<string, unknown>;
  created_at: string;
};

export type Review = { id: string; action: "clear" | "block" | "unblock"; rule_id?: string | null; reason: string; reviewer_id: string; created_at: string; evidence_ids: string[] };

export type SupplierRow = {
  supplier: { id: string; email?: string; legal_name?: string | null; website?: string | null; country?: string | null; is_demo?: boolean; data_origin?: string; lead_id?: string | null };
  policy: SupplierPolicy;
  quotes: { id: string; status: string; version: number; policy: QuotePolicy }[];
  latest_evidence: Record<string, Evidence>;
  evidence_history: Evidence[];
  reviews: Review[];
};

export type Allocation = { quote_id: string; supplier_id: string; supplier_email: string; item: string; quantity: number; unit_price: string; line_cost: string; delivery_date: string };

export type Plan = {
  id: string;
  version: number;
  status: "feasible" | "approved" | "stale" | "infeasible";
  trigger: string;
  trigger_detail: { kind: string; summary?: string; supplier_id?: string; at?: string }[];
  computed_at: string;
  total_cost: string;
  shipping_cost: string;
  remaining_budget: string;
  currency?: string;
  latest_delivery?: string | null;
  allocations: Allocation[];
  shortages: { item: string; required: number; available: number; shortage: number; reason: string }[];
  rejected_quotes: { quote_id: string; supplier_id?: string; supplier_email?: string; reason: string; rules?: string[]; explanations?: string[] }[];
  binding_constraints: string[];
  supplier_concentration: { supplier_id: string; share: number }[];
  constraints?: { budget: string; delivery_deadline: string; max_supplier_share?: string | null; single_source_only?: boolean; requirements: Requirement[] };
  policy: { fingerprint: string; evaluated_at: string; eligible_quote_ids: string[]; suppliers: Record<string, SupplierPolicy>; quotes: Record<string, QuotePolicy> };
  difference: {
    previous_plan_id: string | null;
    previous_version: number | null;
    previous_status?: string | null;
    total_cost_before: string | null;
    total_cost_after: string;
    cost_delta?: string | null;
    allocation_changed: boolean;
    supplier_delta?: { supplier_id: string; supplier: string; units_before: number; units_after: number; cost_before: string; cost_after: string }[];
    why?: string[];
  };
  plan_hash: string;
  stale_reason?: string;
};

export type Approval = { id: string; plan_id: string; plan_version: number; status: "active" | "consumed" | "invalidated" | "expired"; amount: string; spending_ceiling?: string; approved_at: string; expires_at: string | null; invalidation_reason?: string | null; plan_hash?: string };
export type PurchaseOrder = { id: string; po_number: string; supplier_email: string; status: string; plan_version?: number; subtotal?: string; plan_stale?: boolean; lines: Allocation[] };
export type Notification = { id: string; kind: string; severity: "info" | "success" | "warning" | "critical"; message: string; created_at: string };
export type AuditEvent = { id: string; sequence: number; action: string; actor_id: string | null; entity_type: string; entity_id: string; metadata: Record<string, unknown>; created_at: string; event_hash: string; previous_hash: string };
export type AuditVerification = { valid: boolean; length: number; head_hash?: string; broken_at: number | null; reason: string | null };
export type Job = { id: string; type: string; status: "queued" | "running" | "succeeded" | "failed"; attempts: number; max_attempts: number; last_error?: string | null; created_at: string; result?: Record<string, unknown> | null; payload?: Record<string, unknown> };
export type Lead = { id: string; name: string; website?: string | null; phone?: string | null; address?: string | null; category?: string | null; rating?: number | null; reviews?: number | null; source_url?: string | null; status: "lead" | "invited" | "onboarded" | "dismissed"; provenance: Provenance; retrieved_at?: string | null; apify_run_id?: string; apify_dataset_id?: string; invited_email?: string };
export type Disruption = { id: string; kind: string; supplier_id: string; supplier_name: string; summary: string; before: Record<string, unknown>; after: Record<string, unknown>; job_id: string | null; created_at: string };

export type ContextSection<T> = { status: "OK" | "BLOCKED_EXTERNAL" | "UNAVAILABLE"; provenance: Provenance | null; retrieved_at: string | null; source_url: string | null; error: string | null; data: T; note?: string; scope?: string; meta?: Record<string, unknown> };
export type NwsAlert = { id: string; event: string; headline: string | null; severity: string; urgency: string; certainty: string; effective: string; expires: string; area: string; sender: string; source_url: string };
export type FirmsDetection = { latitude: number; longitude: number; acquired_at: string; satellite: string; confidence: string; frp: number | null; sensor: string };
export type FemaDeclaration = { declaration_number: string; incident_type: string; title: string; declaration_date: string; designated_area: string; incident_begin: string; source_url: string };
export type MissionContext = {
  mission_id: string;
  delivery_state: string | null;
  point: { lat: number; lon: number } | null;
  event: ContextSection<EmergencyEvent> | null;
  nws: ContextSection<NwsAlert[]> | null;
  firms: ContextSection<FirmsDetection[]> | null;
  fema: ContextSection<FemaDeclaration[]> | null;
};

export type IntegrationCheck = { id: string; name: string; category: string; status: "ok" | "degraded" | "not_configured" | "error"; detail: string; provenance: string | null; latency_ms: number; checked_at: string };

export type Payment = { id: string; supplier_id: string; subject_name: string; protocol: string; scheme: string; network: string; network_label: string; asset_symbol: string; amount_display: string; payer: string; pay_to: string; transaction: string; explorer_url: string; status: string; verified: boolean; dossier_sha256: string; evidence_id: string; created_at: string };
