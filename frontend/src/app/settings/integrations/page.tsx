import { Suspense } from "react";

import { IntegrationsPageClient } from "@/components/operations/integrations-page-client";

// The OAuth callbacks land here with ?org=…&google=connected|error, so the page reads search params at runtime.
export default function IntegrationsPage() {
  return (
    <Suspense fallback={<main className="grid min-h-screen place-items-center bg-background text-muted-foreground">Loading…</main>}>
      <IntegrationsPageClient />
    </Suspense>
  );
}
