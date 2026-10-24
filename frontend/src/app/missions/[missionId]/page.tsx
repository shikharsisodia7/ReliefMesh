import { MissionWorkspace } from "@/components/mission-workspace";

export const instant = false;

export default async function MissionPage({ params }: { params: Promise<{ missionId: string }> }) {
  const { missionId } = await params;
  return <MissionWorkspace missionId={missionId} />;
}
