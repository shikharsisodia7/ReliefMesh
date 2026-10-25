import { Suspense } from "react";

import { SettingsClient } from "@/components/settings-client";

// The tab and the OAuth return values come from the query string, read at runtime.
export default function SettingsPage() {
  return (
    <Suspense>
      <SettingsClient />
    </Suspense>
  );
}
