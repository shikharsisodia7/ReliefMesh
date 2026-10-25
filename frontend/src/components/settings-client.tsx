"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { Page, PageHeader } from "@/components/layout/page-header";
import { MembersPanel } from "@/components/members-panel";
import { IntegrationsSettings } from "@/components/operations/integrations-settings";
import { OrganizationForm } from "@/components/organization-form";
import { TabPanel, UnderlineTabs } from "@/components/patterns/underline-tabs";
import { useCreateOrganization, useOrganizations } from "@/hooks/use-organizations";
import { useHydrated, useSession } from "@/hooks/use-session";
import type { ApiError } from "@/lib/api";
import { clearSession, signInUrl } from "@/lib/session";
import type { Organization } from "@/lib/types";

const roleWords: Record<string, string> = { admin: "Administrator", approver: "Approver", coordinator: "Coordinator" };

const tabs = [
  { value: "organization", label: "Organization" },
  { value: "members", label: "Members" },
  { value: "integrations", label: "Integrations" },
];

// The API's OAuth return lands here with ?org=…&google|slack=connected|error&reason=…
function oauthNotice(params: URLSearchParams): string | null {
  for (const provider of ["google", "slack"] as const) {
    const outcome = params.get(provider);
    const name = provider === "google" ? "Google" : "Slack";
    if (outcome === "connected") return `${name} connected. Use “Send test” to make a first real call.`;
    if (outcome === "error") return `${name} connection was not completed: ${params.get("reason") ?? "unknown error"}`;
  }
  return null;
}

export function SettingsClient() {
  const router = useRouter();
  const params = useSearchParams();
  const session = useSession();
  const hydrated = useHydrated();
  const [error, setError] = useState<string | null>(null);
  const requested = params.get("tab");
  const tab = tabs.some((item) => item.value === requested) ? requested! : "organization";
  const orgParam = params.get("org");
  useEffect(() => { if (hydrated && (!session || session.user.role !== "coordinator")) router.replace(signInUrl()); }, [hydrated, router, session]);
  const { organizations, current, select } = useOrganizations(session?.token);
  const createOrganization = useCreateOrganization(session?.token);
  // A link that names an organization (the OAuth return does) makes it the current one.
  useEffect(() => { if (orgParam) select(orgParam); }, [orgParam, select]);
  const expired = (organizations.error as ApiError | null)?.status === 401;
  // A token for a deleted or revoked account must not leave a blank settings page: start a fresh sign-in.
  useEffect(() => { if (expired) { clearSession(); router.replace(signInUrl()); } }, [expired, router]);
  if (!session) return <Page><p className="text-sm text-muted-foreground">Loading…</p></Page>;
  const token = session.token;

  const create = async (values: { name: string; demo: boolean }) => {
    setError(null);
    try { await createOrganization(values); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not create organization"); }
  };
  // Panels that need an organization wait for the list, then ask for one if there is none.
  const withOrganization = (render: (organization: Organization) => ReactNode) =>
    organizations.isLoading ? <p className="text-sm text-muted-foreground">Loading…</p>
      : current ? render(current)
        : <p className="text-sm text-muted-foreground">Create an organization first on the Organization tab.</p>;

  return (
    <Page>
      <PageHeader title="Settings" meta={current ? <>{current.name}{current.is_demo && " · DEMO ORG"}</> : undefined} />
      {organizations.isError && !expired && <p role="alert" className="mt-4 text-sm text-critical">{organizations.error.message}</p>}
      <div className="mt-8">
        <UnderlineTabs label="Settings" value={tab} onValueChange={(next) => router.replace(`/settings?tab=${next}`, { scroll: false })} items={tabs}>
          <TabPanel value="organization">
            <div className="max-w-xl space-y-10">
              {current && (
                <dl className="text-sm">
                  <Fact label="Name">{current.name}</Fact>
                  <Fact label="Type">{current.is_demo ? "Demo organization (labeled self-approval)" : "Standard: plans need an independent approver"}</Fact>
                  <Fact label="Your role">{roleWords[current.membership_role] ?? current.membership_role}</Fact>
                </dl>
              )}
              <section>
                <h2 className="text-base font-semibold">{current ? "Create another organization" : "Create your organization"}</h2>
                <p className="mt-1 text-sm text-muted-foreground">The buyer organization owns its missions, quotes, plans, and approvals. Switch between organizations from your avatar menu.</p>
                <div className="mt-4"><OrganizationForm onSubmit={create} /></div>
                {error && <p role="alert" className="mt-3 text-sm text-critical">{error}</p>}
              </section>
            </div>
          </TabPanel>
          <TabPanel value="members">
            {withOrganization((organization) => <MembersPanel key={organization.id} organizationId={organization.id} token={token} isAdmin={organization.membership_role === "admin"} />)}
          </TabPanel>
          <TabPanel value="integrations">
            {withOrganization((organization) => (
              <div className="space-y-8">
                <p className="max-w-3xl text-sm text-muted-foreground">Carry the procurement workflow into the tools your team already uses: RFQs and purchase orders by Gmail, deadlines on Google Calendar, alerts in Slack, and document copies in Drive. These are notification layers only. ReliefMesh remains the record, and money moves only after approval inside ReliefMesh.</p>
                <IntegrationsSettings key={organization.id} organizationId={organization.id} token={token} notice={organization.id === orgParam ? oauthNotice(params) : null} />
              </div>
            ))}
          </TabPanel>
        </UnderlineTabs>
      </div>
    </Page>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return <div className="flex justify-between gap-6 border-b py-3"><dt className="text-muted-foreground">{label}</dt><dd className="text-right">{children}</dd></div>;
}
