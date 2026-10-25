import { TileMap, fitView, type MapMarker } from "@/components/patterns/tile-map";
import type { Mission } from "@/lib/types";

// "Wildfire COOLEY, Mendocino, California" → "Wildfire COOLEY".
const shortTitle = (title: string) => title.split(",")[0];

// Linked NASA EONET events on the light gray basemap. Delivery locations have no coordinates from the API, so they
// aren't plotted (and nothing joins them to the events).
export function MissionsMap({ missions }: { missions: Mission[] }) {
  const events = new Map<string, MapMarker>();
  for (const mission of missions) {
    const event = mission.emergency_event;
    if (!event?.point || events.has(event.id)) continue;
    events.set(event.id, { lat: event.point.lat, lon: event.point.lon, kind: "event", label: `${shortTitle(event.title)}${event.closed ? " · archive" : ""}` });
  }
  // West to east; a marker close to the one before it takes its label on the left so the two don't overlap.
  const markers = [...events.values()].sort((a, b) => a.lon - b.lon);
  markers.forEach((marker, index) => {
    const before = markers[index - 1];
    if (before && !before.labelLeft && Math.abs(before.lat - marker.lat) < 1 && marker.lon - before.lon < 2) before.labelLeft = true;
  });
  return (
    <section aria-label="Disaster locations">
      <h2 className="text-base font-semibold">Disaster locations</h2>
      {markers.length === 0 ? <p className="mt-3 text-sm text-muted-foreground">No mission is linked to a located event yet.</p> : (
        <div className="mt-3">
          <TileMap {...fitView(markers, 360, 460)} markers={markers} height={460} label={`Map of ${markers.length} linked NASA EONET event${markers.length === 1 ? "" : "s"}`} />
          <p className="mt-1 text-xs font-medium">Triangle: linked event</p>
          <p className="mt-0.5 text-xs text-muted-foreground">NASA EONET events. Delivery locations aren&apos;t geocoded by the API, so they aren&apos;t plotted.</p>
        </div>
      )}
    </section>
  );
}
