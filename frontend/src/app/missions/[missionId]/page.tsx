import { Suspense } from "react";

import { MissionWorkspace } from "@/components/mission-workspace";

export const instant = false;

export default async function MissionPage({ params }: { params: Promise<{ missionId: string }> }) {
  const { missionId } = await params;
  // The stage tab lives in ?tab=, read at runtime.
  return <Suspense><MissionWorkspace missionId={missionId} /></Suspense>;
}
