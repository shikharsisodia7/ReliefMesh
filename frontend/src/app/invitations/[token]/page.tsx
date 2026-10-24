import { InvitationClient } from "@/components/invitation-client";

// Invitation tokens are intentionally runtime-only and must never be statically enumerated.
export const instant = false;

export default async function InvitationPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <InvitationClient token={token} />;
}
