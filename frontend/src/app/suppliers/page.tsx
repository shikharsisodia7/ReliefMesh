import { Page, PageHeader } from "@/components/layout/page-header";

// Placeholder until the cross-mission supplier table is built.
export default function SuppliersPage() {
  return (
    <Page>
      <PageHeader title="Suppliers" />
      <p className="mt-8 max-w-2xl text-sm text-muted-foreground">A table of every supplier across your missions is coming soon. For now, each mission lists its suppliers and their evidence.</p>
    </Page>
  );
}
