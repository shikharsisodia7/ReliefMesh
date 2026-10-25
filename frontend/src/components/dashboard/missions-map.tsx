import { TileMap, type MapMarker } from "@/components/patterns/tile-map";
import { when } from "@/components/status-badges";
import type { Mission } from "@/lib/types";

// "Wildfire COOLEY, Mendocino, California" → "Wildfire COOLEY".
const shortTitle = (title: string) => title.split(",")[0];

// Linked NASA EONET events on the light gray basemap. Delivery locations have no coordinates from the API, so they
// aren't plotted (and nothing joins them to the events).
export function MissionsMap({ missions }: { missions: Mission[] }) {
  const events = new Map<string, { marker: MapMarker; missions: Mission[] }>();
  for (const mission of missions) {
    const event = mission.emergency_event;
    if (!event?.point) continue;
    const entry = events.get(event.id) ?? {
      missions: [],
      marker: {
        lat: event.point.lat, lon: event.point.lon, kind: "event", label: `${shortTitle(event.title)}${event.closed ? " · archive" : ""}`,
        popup: { title: event.title, category: event.categories[0]?.title, date: event.last_observed ? when(event.last_observed) : undefined, links: event.link ? [{ label: "EONET record", href: event.link, external: true }] : [] },
      },
    };
    entry.missions.push(mission);
    events.set(event.id, entry);
  }
  // Each mission linked to an event gets a link to its Context tab; with several, each link is named.
  for (const { marker, missions: linked } of events.values()) {
    for (const mission of linked) marker.popup!.links.push({ label: linked.length > 1 ? `Open ${mission.name}` : "Open mission", href: `/missions/${mission.id}?tab=context` });
  }
  // West to east; a marker close to the one before it takes its label on the left so the two don't overlap.
  const markers = [...events.values()].map((entry) => entry.marker).sort((a, b) => a.lon - b.lon);
  markers.forEach((marker, index) => {
    const before = markers[index - 1];
    if (before && !before.labelLeft && Math.abs(before.lat - marker.lat) < 1 && marker.lon - before.lon < 2) before.labelLeft = true;
  });
  return (
    <section aria-label="Disaster locations">
      <h2 className="text-base font-semibold">Disaster locations</h2>
      {markers.length === 0 ? <p className="mt-3 text-sm text-muted-foreground">No mission is linked to a located event yet.</p> : (
        <div className="mt-3">
          <TileMap markers={markers} height={460} label={`Map of ${markers.length} linked NASA EONET event${markers.length === 1 ? "" : "s"}`} />
          <p className="mt-2 text-xs text-muted-foreground"><span className="font-medium text-foreground">Triangle: linked NASA EONET event.</span> Delivery locations aren&apos;t geocoded by the API, so they aren&apos;t plotted.</p>
        </div>
      )}
    </section>
  );
}
