import type { Approval, Mission, Plan, Quote, SupplierPolicy } from "@/lib/types";

// Static demo data for the landing page's product shot. Nothing here is fetched or sent anywhere.
// Times are built in the viewer's own time zone so the shot always reads "2:32 PM" like the story.

const GOLDEN_GATE = "golden-gate";
const SIERRA = "sierra";
const BAYSIDE = "bayside";
const PIONEER = "pioneer";

const names: Record<string, string> = {
  [GOLDEN_GATE]: "Golden Gate Medical Logistics",
  [SIERRA]: "Sierra Backup Provisions",
  [BAYSIDE]: "Bayside Relief Supply Co",
  [PIONEER]: "Pioneer Logistics Supply",
};

const supplier = (id: string, status: SupplierPolicy["status"] = "PASS"): SupplierPolicy => ({ status, decisions: [], legal_name: names[id], is_demo: true });

function line(quoteId: string, supplierId: string, quantity: number, unitPrice: string, delivery: string) {
  return { quote_id: quoteId, supplier_id: supplierId, supplier_email: `${supplierId}@example.com`, item: "blankets", quantity, unit_price: unitPrice, line_cost: (quantity * Number(unitPrice)).toFixed(2), delivery_date: delivery };
}

export function demoPlanData() {
  const at = (day: number, hours: number, minutes: number, seconds = 0, ms = 0) => new Date(2026, 9, day, hours, minutes, seconds, ms).toISOString();
  const deadline = at(28, 17, 0);
  const delivery = at(27, 12, 0);
  const quote = (id: string, supplierId: string, price: string, shipping: string, status = "submitted"): Quote => ({
    id, supplier_id: supplierId, supplier_email: `${supplierId}@example.com`, supplier_name: names[supplierId], status, version: 1, shipping_cost: shipping,
    expires_at: deadline, provenance: "SYNTHETIC", is_demo: true, lines: [{ item: "blankets", unit_price: price, available_quantity: 100, delivery_date: delivery }],
  });
  const quotes = [quote("q-gg", GOLDEN_GATE, "32.40", "75.00"), quote("q-si", SIERRA, "36.60", "25.00"), quote("q-ba", BAYSIDE, "30.00", "100.00", "withdrawn"), quote("q-pi", PIONEER, "25.50", "60.00")];
  const policy = {
    fingerprint: "demo", evaluated_at: at(24, 14, 32, 9), eligible_quote_ids: ["q-gg", "q-si"],
    suppliers: { [GOLDEN_GATE]: supplier(GOLDEN_GATE), [SIERRA]: supplier(SIERRA), [BAYSIDE]: supplier(BAYSIDE), [PIONEER]: supplier(PIONEER, "NEEDS_REVIEW") },
    quotes: { "q-pi": { status: "NEEDS_REVIEW" as const, eligible: false, supplier_id: PIONEER, supplier_status: "NEEDS_REVIEW" as const, decisions: [], version: 1 } },
  };
  const requirements = [{ item: "blankets", quantity: 100 }];
  const base = { shortages: [], binding_constraints: [], supplier_concentration: [], currency: "USD", plan_hash: "demo", latest_delivery: delivery };
  const pioneer = { quote_id: "q-pi", supplier_id: PIONEER, reason: "policy:NEEDS_REVIEW", rules: ["SANCTIONS_POTENTIAL_MATCH"] };
  const v1: Plan = {
    ...base, id: "plan-1", version: 1, status: "stale", trigger: "manual", trigger_detail: [], computed_at: at(24, 14, 18),
    total_cost: "3271.00", shipping_cost: "175.00", remaining_budget: "1729.00", rejected_quotes: [pioneer], policy,
    allocations: [line("q-gg", GOLDEN_GATE, 40, "32.40", delivery), line("q-ba", BAYSIDE, 60, "30.00", delivery)],
    difference: { previous_plan_id: null, previous_version: null, total_cost_before: null, total_cost_after: "3271.00", allocation_changed: true },
    stale_reason: "Bayside Relief Supply Co withdrew its quote",
  };
  const v2: Plan = {
    ...base, id: "plan-2", version: 2, status: "feasible", trigger: "supplier_disruption", computed_at: at(24, 14, 32, 10),
    trigger_detail: [{ kind: "quote_withdrawn", summary: "Bayside Relief Supply Co withdrew", supplier_id: BAYSIDE, at: at(24, 14, 32, 8, 200) }],
    total_cost: "3466.00", shipping_cost: "100.00", remaining_budget: "1534.00", rejected_quotes: [pioneer], policy, constraints: { budget: "5000.00", delivery_deadline: deadline, requirements },
    allocations: [line("q-gg", GOLDEN_GATE, 70, "32.40", delivery), line("q-si", SIERRA, 30, "36.60", delivery)],
    difference: { previous_plan_id: "plan-1", previous_version: 1, total_cost_before: "3271.00", total_cost_after: "3466.00", cost_delta: "195.00", allocation_changed: true },
  };
  const approvals: Approval[] = [{ id: "approval-1", plan_id: "plan-1", plan_version: 1, status: "invalidated", amount: "3271.00", approved_at: at(24, 14, 25), expires_at: null, invalidated_at: at(24, 14, 32, 8) }];
  const mission: Mission = {
    id: "demo", organization_id: "demo", name: "Shelter blankets", status: "active", delivery_location: "Oakland, CA", delivery_deadline: deadline,
    budget: "5000.00", currency: "USD", requirements,
    emergency_event: { id: "demo-event", title: "Wildfire", categories: [], sources: [], provenance: null, retrieved_at: null },
  };
  return { mission, plans: [v2, v1], approvals, quotes };
}
