import Link from "next/link";

import { day } from "@/components/status-badges";
import type { SupplierInvitation, SupplierQuote } from "@/components/supplier/types";

// Every RFQ sent to this supplier's email. Accepting and quoting happen on the signed link from the RFQ email.
export function RfqsTab({ invitations, quotes }: { invitations: SupplierInvitation[]; quotes: SupplierQuote[] }) {
  const quoted = new Set(quotes.map((quote) => quote.mission_id));
  return (
    <section aria-label="RFQs">
      <h2 className="border-b pb-3 text-xl font-semibold">Requests for quotation</h2>
      {invitations.length === 0 ? <p className="mt-6 text-sm text-muted-foreground">No RFQs for this email yet. When a buyer invites you, open the link in the RFQ email.</p> : (
        <ul>
          {invitations.map((invitation) => {
            const mission = invitation.mission;
            const hasQuote = quoted.has(mission.id);
            const state = hasQuote ? "Quoted" : invitation.status === "accepted" ? "Accepted · no quote yet" : "Not accepted yet";
            return (
              <li key={invitation.id} className="grid gap-x-8 gap-y-2 border-b py-6 md:grid-cols-[1.4fr_0.8fr_auto] md:items-start">
                <div>
                  <p className="text-lg font-semibold">{mission.name}</p>
                  <p className="mt-0.5 text-sm text-muted-foreground">{mission.requirements.map((row) => `${row.quantity.toLocaleString("en-US")} ${row.item}`).join(", ")} · {mission.delivery_location} · Deliver by {day(mission.delivery_deadline)}</p>
                </div>
                <p className="font-medium">{state}</p>
                {hasQuote ? <Link href="/supplier?tab=quotes" className="text-sm font-medium hover:underline">View quote →</Link> : <span className="text-sm text-muted-foreground">Open the link in your RFQ email</span>}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
