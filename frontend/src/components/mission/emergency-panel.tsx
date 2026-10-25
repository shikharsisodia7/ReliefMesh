"use client";

import type { ReactNode } from "react";

import { TileMap, type MapMarker } from "@/components/patterns/tile-map";
import { Provenance, day, when } from "@/components/status-badges";
import type { ContextSection, Mission, MissionContext } from "@/lib/types";

// A source that isn't OK gets one gray line with its reason, never placeholder data.
// Its content renders only for an OK source, whose data is present.
function SourceSection<T>({ title, label, section, loading, empty, render }: {
  title: ReactNode; label: string; section?: ContextSection<T> | null; loading: boolean; empty: string; render: (data: T, section: ContextSection<T>) => ReactNode;
}) {
  return (
    <section aria-label={label} className="border-t pt-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-base font-semibold">{title}</h3>
        {section?.status === "OK" && <Provenance value={section.provenance} at={section.retrieved_at} />}
      </div>
      <div className="mt-2 text-sm">
        {loading && !section ? <p className="text-muted-foreground">Loading…</p>
          : !section ? <p className="text-muted-foreground">{empty}</p>
            : section.status !== "OK" ? <p className="text-muted-foreground">{label} {section.status === "BLOCKED_EXTERNAL" ? "not configured" : "unavailable"} · {section.error}</p>
              : render(section.data, section)}
      </div>
    </section>
  );
}

const rowClass = "border-b py-2.5 last:border-0";

// Context tab: the linked NASA EONET event on a map, then NWS alerts, NASA FIRMS detections, and OpenFEMA declarations.
export function EmergencyPanel({ mission, context, loading }: { mission: Mission; context?: MissionContext; loading: boolean }) {
  const event = context?.event?.data ?? mission.emergency_event;
  const eventSection = context?.event;
  const nws = context?.nws;
  const firms = context?.firms;
  const fema = context?.fema;
  const point = event?.point ?? context?.point ?? null;
  const markers: MapMarker[] = [
    ...(firms?.status === "OK" ? firms.data.map((row) => ({ lat: row.latitude, lon: row.longitude, kind: "detection" as const })) : []),
    ...(point ? [{ lat: point.lat, lon: point.lon, kind: "event" as const, label: event?.title }] : []),
  ];
  return (
    <div className="grid gap-12 lg:grid-cols-[minmax(0,7fr)_minmax(0,3fr)]">
      <div className="min-w-0">
        <section aria-label="Emergency context">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-xs font-medium text-muted-foreground">Linked NASA EONET event</p>
            {eventSection?.status === "OK" ? <Provenance value={eventSection.provenance} at={eventSection.retrieved_at} /> : event && <Provenance value={event.provenance} at={event.retrieved_at} />}
          </div>
          {event ? (
            <>
              <h2 className="mt-1 text-xl font-semibold">{event.title}</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {event.categories.map((category) => category.title).join(", ")}
                {event.latest_geometry?.magnitude_value ? ` · ${event.latest_geometry.magnitude_value.toLocaleString()} ${event.latest_geometry.magnitude_unit ?? ""}` : ""}
                {point ? ` · ${point.lat.toFixed(3)}, ${point.lon.toFixed(3)}` : ""}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">Observed {when(event.first_observed)} → {when(event.last_observed)} · <span className="font-mono text-xs">{event.id}</span></p>
              <p className="mt-2 flex flex-wrap gap-x-5 text-sm">
                {event.link && <a className="font-medium hover:underline" href={event.link} target="_blank" rel="noreferrer">EONET record →</a>}
                {event.sources.map((source) => <a key={source.url} className="font-medium hover:underline" href={source.url} target="_blank" rel="noreferrer">{source.id} →</a>)}
              </p>
              {eventSection?.note && <p className="mt-2 text-sm text-muted-foreground">{eventSection.note}</p>}
            </>
          ) : <p className="mt-1 text-sm text-muted-foreground">{mission.emergency_event_error ? `The linked event could not be resolved: ${mission.emergency_event_error}` : "No real-world event is linked to this mission."}</p>}
        </section>

        {point && (
          <div className="mt-6">
            <TileMap center={point} markers={markers} label={`Map of ${event?.title ?? "the linked event"} with satellite fire detections`} />
            <p className="mt-1 text-xs text-muted-foreground">Triangle: linked event{firms?.status === "OK" && firms.data.length > 0 ? " · dots: NASA FIRMS detections" : ""}. The delivery location ({mission.delivery_location}) isn&apos;t geocoded by the API, so it isn&apos;t plotted.</p>
          </div>
        )}
      </div>

      <aside className="min-w-0 space-y-8">
        <SourceSection title={<>NWS alerts{nws?.scope && <span className="font-normal text-muted-foreground"> · {nws.scope}</span>}</>} label="NWS alerts" section={nws} loading={loading} empty="No US location to query."
          render={(alerts) => alerts.length === 0 ? <p className="text-muted-foreground">No active NWS alerts for this area.</p> : (
            <ul>
              {alerts.slice(0, 5).map((alert) => (
                <li key={alert.id} className="border-b py-2.5 last:border-0">
                  <a href={alert.source_url} target="_blank" rel="noreferrer" className="font-medium hover:underline">{alert.event}</a>
                  <p className="text-xs text-muted-foreground">{alert.severity} · {alert.urgency} · until {when(alert.expires)}</p>
                </li>
              ))}
              {alerts.length > 5 && <li className="pt-2 text-xs text-muted-foreground">{alerts.length - 5} more active alerts</li>}
            </ul>
          )} />

        <SourceSection title="NASA FIRMS · 48 h" label="NASA FIRMS" section={firms} loading={loading} empty="Needs a linked event location."
          render={(rows) => <p><span className="text-2xl font-semibold tabular">{rows.length}</span> <span className="text-muted-foreground">satellite fire detections within about 50 km{rows.length ? `; latest ${when(rows.map((row) => row.acquired_at).sort().at(-1))}` : ""}</span></p>} />

        <SourceSection title={<>OpenFEMA declarations{context?.delivery_state && <span className="font-normal text-muted-foreground"> · {context.delivery_state}</span>}</>} label="OpenFEMA" section={fema} loading={loading} empty="No state on record for the delivery location."
          render={(rows, section) => (
            <>
              {rows.length === 0 ? <p className="text-muted-foreground">No recent declarations.</p> : (
                <ul>
                  {rows.slice(0, 4).map((row) => (
                    <li key={`${row.declaration_number}-${row.designated_area}`} className={rowClass}>
                      <span><a href={row.source_url} className="font-medium hover:underline" target="_blank" rel="noreferrer">{row.declaration_number}</a> · {row.incident_type}: {row.title}</span>
                      <span className="block text-xs text-muted-foreground">{day(row.declaration_date)} · {row.designated_area}</span>
                    </li>
                  ))}
                </ul>
              )}
              {section.note && <p className="mt-2 text-xs text-muted-foreground">{section.note}</p>}
            </>
          )} />
      </aside>
    </div>
  );
}
