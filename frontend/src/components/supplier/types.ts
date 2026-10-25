import type { Requirement } from "@/lib/types";

// The supplier's own view of the records the API returns for them.
export type SupplierMission = { id: string; name: string; delivery_location: string; delivery_deadline: string; requirements: Requirement[] };
export type SupplierInvitation = { id: string; status: string; mission: SupplierMission };
export type SupplierQuote = {
  id: string; mission_id: string; status: string; version: number; shipping_cost: string; expires_at: string; supplier_name?: string | null; is_demo?: boolean;
  lines: { requirement_id?: string; item: string; available_quantity: number; unit_price: string; delivery_date: string }[];
};
export type SupplierOrder = {
  id: string; po_number: string; status: string; subtotal?: string; buyer_organization: string; delivery_location: string; sent_at?: string | null;
  lines: { item: string; quantity: number; delivery_date?: string }[]; events: { status: string; note?: string | null; at: string }[];
};

// Status codes as the words a supplier reads.
export const orderWords: Record<string, string> = {
  draft: "Draft", sent: "Awaiting response", supplier_accepted: "Accepted", supplier_declined: "Declined",
  in_fulfillment: "Shipped", completed: "Delivered", cancelled: "Cannot fulfill",
};
export const quoteWords: Record<string, string> = { submitted: "Submitted", withdrawn: "Withdrawn", expired: "Expired", superseded: "Superseded" };
export const word = (map: Record<string, string>, code: string) => map[code] ?? code.charAt(0).toUpperCase() + code.slice(1).replace(/_/g, " ");
