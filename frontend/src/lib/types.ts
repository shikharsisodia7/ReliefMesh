export type Provenance = "LIVE" | "CACHED" | "SANDBOX" | "USER_SUBMITTED" | "SYNTHETIC" | "TEST" | "HYPOTHETICAL" | "BLOCKED_EXTERNAL" | "UNAVAILABLE";
export type PolicyStatus = "PASS" | "WARN" | "NEEDS_REVIEW" | "BLOCK";

export type Requirement = { id?: string; item: string; quantity: number };

// Gemini-extracted form pre-fill. Never a quote: the supplier reviews and submits it themselves.
export type QuoteDraftLine = {
  requirement_id: string; item: string; available_quantity: number | null; unit_price: string | null; delivery_date: string | null;
  source_excerpt: string; grounded: boolean; unverified_fields: ("available_quantity" | "unit_price")[];
};
export type QuoteDraft = {
  lines: QuoteDraftLine[]; shipping_cost: string | null; currency: string | null; expires_at: string | null;
  unmatched_items: string[]; model: string; provenance: "AI_DRAFT"; notice: string;
};

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
  created_by?: string;
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

export type Allocation = { quote_id: string; supplier_id: string; supplier_email: string; item: string; quantity: number; unit_price: string; line_cost: string; delivery_date: string; committed?: boolean; po_number?: string };

export type Plan = {
  id: string;
  version: number;
  status: "feasible" | "approved" | "stale" | "infeasible";
  trigger: string;
  trigger_detail: { kind: string; summary?: string; supplier_id?: string; at?: string }[];
  computed_at: string;
  committed_cost?: string; // units already on active purchase orders, kept fixed by a replan
  new_spend?: string;
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

export type Approval = { id: string; plan_id: string; plan_version: number; status: "active" | "consumed" | "invalidated" | "expired"; amount: string; spending_ceiling?: string; approved_at: string; expires_at: string | null; invalidated_at?: string | null; consumed_at?: string | null; invalidation_reason?: string | null; plan_hash?: string; approver_email?: string | null; requested_by?: string | null; segregation_of_duties?: string };
export type PurchaseOrderEvent = { status: string; at: string; note?: string | null; actor_id?: string | null };
export type PurchaseOrder = {
  id: string; po_number: string; supplier_id?: string; supplier_email: string; status: string; plan_version?: number; subtotal?: string; plan_stale?: boolean; lines: Allocation[];
  created_at?: string; sent_at?: string | null; events?: PurchaseOrderEvent[]; delivery?: { provider?: string | null; status?: string | null; message_id?: string | null } | null;
};
export type Notification = { id: string; kind: string; severity: "info" | "success" | "warning" | "critical"; message: string; created_at: string };
export type AuditEvent = { id: string; sequence: number; action: string; actor_id: string | null; entity_type: string; entity_id: string; metadata: Record<string, unknown>; created_at: string; event_hash: string; previous_hash: string };
export type AuditVerification = { valid: boolean; length: number; head_hash?: string; broken_at: number | null; reason: string | null };
export type Job = { id: string; type: string; status: "queued" | "running" | "succeeded" | "failed"; attempts: number; max_attempts: number; last_error?: string | null; created_at: string; result?: Record<string, unknown> | null; payload?: Record<string, unknown> };
export type Lead = { id: string; name: string; website?: string | null; phone?: string | null; address?: string | null; category?: string | null; rating?: number | null; reviews?: number | null; source_url?: string | null; status: "lead" | "invited" | "onboarded" | "dismissed"; provenance: Provenance; retrieved_at?: string | null; apify_run_id?: string; apify_dataset_id?: string; invited_email?: string };
export type Disruption = { id: string; kind: string; supplier_id: string; supplier_name: string; summary: string; before: Record<string, unknown>; after: Record<string, unknown>; job_id: string | null; created_at: string };

export type ContinuityScenario = {
  supplier_id: string; supplier: string; feasible: boolean; status: "RECOVERABLE" | "UNRECOVERABLE"; label: string;
  replacement_suppliers: string[]; new_cost: string | null; cost_delta: string | null; latest_delivery: string | null;
  deadline_delta_hours: number | null; lost_quantity: number; budget_feasible: boolean; deadline_feasible: boolean;
  shortages: { item: string; shortage: number; reason: string }[];
};
export type ContinuityFrontier = {
  supplier_id: string; supplier: string;
  price: { increase_basis_points: number; increase_percent: number } | null;
  delay: { hours: number } | null;
  capacity: { loss_units: number; units_removed?: number; loss_percent: number | null; method: string } | null;
  note?: string;
};
export type ContinuityAnalysis = {
  id: string; status: "COMPLETE" | "STALE"; provenance: "HYPOTHETICAL"; counterfactual_label: string;
  input_hash: string; created_at: string; plan_id: string; plan_version: number; plan_hash: string;
  baseline: { total_cost: string; remaining_budget: string; latest_delivery: string | null; supplier_concentration: { supplier_id: string; supplier: string; units: number; unit_share: number }[] };
  metrics: {
    n1_survivability: { survives: number; tested: number }; budget_headroom: string; deadline_slack_hours: number | null;
    largest_supplier_concentration: number; alternative_eligible_capacity: number;
    price_shock_tolerance: { increase_basis_points: number; increase_percent: number } | null;
    delay_tolerance: { hours: number } | null;
    capacity_loss_tolerance: { loss_units: number; loss_percent: number | null; method: string } | null;
    critical_supplier: { supplier_id: string; supplier: string; reason: string } | null;
  };
  n1_scenarios: ContinuityScenario[]; failure_frontier: ContinuityFrontier[];
  scope?: { kind: "FULL_MISSION" | "UNCOMMITTED_REMAINDER" | "NO_UNCOMMITTED_REQUIREMENTS"; statement: string; fixed_commitment_cost: string; fixed_commitment_count: number; full_plan_total_cost?: string };
  resilient_alternative: {
    status: "AVAILABLE" | "UNAVAILABLE"; total_cost?: string; added_cost?: string; supplier_count?: number;
    n1_survivability?: { survives: number; tested: number }; improvement?: string; reason?: string;
    constraint?: { max_supplier_share: string };
    allocations?: (Allocation & { supplier?: string })[];
  };
};
export type RealityCheck = {
  supplier_id: string;
  consistent: boolean | null;
  note?: string;
  earlier_stress_test: {
    provenance: "HYPOTHETICAL"; plan_version: number; label?: string; predicted_status?: "RECOVERABLE" | "UNRECOVERABLE";
    predicted_cost?: string | null; predicted_cost_delta?: string | null; crossed?: string[];
    tolerance?: { price_breakpoint_basis_points: number | null; delay_breakpoint_hours: number | null; capacity_breakpoint_units: number | null };
  } | null;
  actual: {
    provenance: "USER_SUBMITTED" | "DEMO_SIMULATION"; supplier: string; kind: "withdrawn" | "updated"; plan_version: number;
    plan_status: string; plan_total_cost: string | null;
    change?: string | { price_change_basis_points: number; price_change_percent: number; capacity_loss_units: number; delay_hours: number };
  };
};
export type ContinuityView = {
  mission_id: string; plan_id: string | null; plan_version: number | null; state: "NOT_READY" | "RUNNING" | "COMPLETE" | "STALE";
  analysis: ContinuityAnalysis | null; active_jobs: { id: string; status: string; created_at: string }[];
  progress: { done: number; total: number | null; label: string } | null;
  reality_check: RealityCheck[];
  digital_twin: { label: string; provenance: string; nodes: { id: string; type: string; label: string; status?: string; quantity?: number }[]; edges: { from: string; to: string; type: string; quantity?: number }[]; disaster_context: EmergencyEvent | null };
};

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

// Operations integrations (Gmail, Google Calendar, Google Drive, Slack). States are computed by the API from
// real provider calls: LIVE only after a call succeeded, BLOCKED when the provider revoked access.
export type IntegrationState = "LIVE" | "DEGRADED" | "NOT_CONFIGURED" | "BLOCKED";
export type CapabilityStatus = { state: IntegrationState; detail: string; last_success?: string | null };
export type DeliveryStatus = "PENDING" | "SENDING" | "RETRYING" | "SENT" | "FAILED" | "NOT_CONFIGURED" | "TEST" | "DISABLED" | "SUPPRESSED" | "SKIPPED";
export type OperationsDelivery = {
  id: string; event_type: string; mission_id: string | null; channel: "gmail" | "slack" | "calendar" | "drive"; target: string;
  summary: string | null; subject?: string | null; operation?: string | null; status: DeliveryStatus; attempts: number; max_attempts: number;
  provider: string | null; provider_id: string | null; provider_url: string | null; last_error: string | null; next_retry_at: string | null;
  sent_at: string | null; created_at: string; updated_at: string;
};
export type IntegrationsView = {
  organization_id: string; membership_role: string;
  email: { mode: "disabled" | "test" | "live"; transport: "gmail" | "resend" | "none"; allowlist_active: boolean };
  google: {
    oauth_configured: boolean; status: string; account_email: string | null; connected_at: string | null; granted_scopes: string[];
    calendar_id: string | null; capabilities: Record<"gmail" | "calendar" | "drive", CapabilityStatus>;
  };
  slack: CapabilityStatus & { oauth_configured: boolean; status: string; mode: "bot" | "webhook" | null; team_name: string | null; channel_name: string | null; connected_at: string | null };
  deliveries: OperationsDelivery[];
};
export type Organization = { id: string; name: string; membership_role: string; is_demo?: boolean };
