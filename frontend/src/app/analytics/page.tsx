import { Page, PageHeader } from "@/components/layout/page-header";

// Placeholder until figures computed from real mission data are added.
export default function AnalyticsPage() {
  return (
    <Page>
      <PageHeader title="Analytics" />
      <p className="mt-8 max-w-2xl text-sm text-muted-foreground">Coming soon: figures computed from your missions, such as quotes received, replan times, and purchase orders delivered.</p>
    </Page>
  );
}
