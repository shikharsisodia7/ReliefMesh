"use client";

import { ExternalLink, Flame, Landmark, Radio, Satellite } from "lucide-react";

import { ProvenanceBadge, ago, when } from "@/components/status-badges";
import type { ContextSection, Mission, MissionContext } from "@/lib/types";

function SectionHeader({ icon: Icon, title, section }: { icon: typeof Flame; title: string; section?: ContextSection<unknown> | null }) {
  return (
    <div className="mb-2 flex items-center justify-between gap-2">
      <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground"><Icon className="size-3.5" />{title}</h3>
      {section && <span className="flex items-center gap-2">{section.status === "OK" ? <ProvenanceBadge value={section.provenance} /> : <ProvenanceBadge value={section.status} />}{section.retrieved_at && <span className="font-mono text-[10px] text-tertiary">{ago(section.retrieved_at)}</span>}</span>}
    </div>
  );
}

function Unavailable({ section }: { section: ContextSection<unknown> }) {
  return <p className="text-xs text-muted-foreground">{section.status === "BLOCKED_EXTERNAL" ? "Not configured: " : "Unavailable: "}{section.error}</p>;
}

export function EmergencyPanel({ mission, context, loading }: { mission: Mission; context?: MissionContext; loading: boolean }) {
  const event = context?.event?.data ?? mission.emergency_event;
  const nws = context?.nws;
  const firms = context?.firms;
  const fema = context?.fema;
  return (
    <section aria-label="Emergency context" className="grid gap-4 rounded-xl border bg-card p-4 lg:grid-cols-[1.3fr_1fr]">
      <div>
        <SectionHeader icon={Satellite} title="NASA EONET event" section={context?.event ?? (event ? { status: "OK", provenance: event.provenance, retrieved_at: event.retrieved_at, source_url: null, error: null, data: event } : null)} />
        {event ? (
          <div>
            <p className="text-lg font-semibold leading-snug">{event.title}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {event.categories.map((category) => category.title).join(", ")}
              {event.latest_geometry?.magnitude_value ? ` · ${event.latest_geometry.magnitude_value.toLocaleString()} ${event.latest_geometry.magnitude_unit ?? ""}` : ""}
              {event.point ? ` · ${event.point.lat.toFixed(3)}, ${event.point.lon.toFixed(3)}` : ""}
            </p>
            <p className="mt-1 font-mono text-xs text-tertiary">observed {when(event.first_observed)} → {when(event.last_observed)} · {event.id}</p>
            <div className="mt-2 flex flex-wrap gap-3 text-xs">
              {event.sources.map((source) => <a key={source.url} className="inline-flex items-center gap-1 text-live hover:underline" href={source.url} target="_blank" rel="noreferrer">{source.id}<ExternalLink className="size-3" /></a>)}
              {event.link && <a className="inline-flex items-center gap-1 text-live hover:underline" href={event.link} target="_blank" rel="noreferrer">EONET record<ExternalLink className="size-3" /></a>}
            </div>
            {context?.event?.note && <p className="mt-2 text-xs text-telemetry">{context.event.note}</p>}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">{mission.emergency_event_error ? `Event could not be resolved: ${mission.emergency_event_error}` : "No real-world event linked to this mission."}</p>
        )}
        <div className="mt-4">
          <SectionHeader icon={Flame} title="NASA FIRMS fire detections (48h)" section={firms} />
          {loading && !firms ? <p className="text-xs text-muted-foreground">Loading…</p> : !firms ? <p className="text-xs text-muted-foreground">Needs an event location.</p> : firms.status !== "OK" ? <Unavailable section={firms} /> : (
            <p className="text-sm"><span className="font-mono text-2xl font-semibold text-telemetry tabular">{firms.data.length}</span> <span className="text-muted-foreground">satellite hotspots within ~50 km{firms.data.length ? `; latest ${when(firms.data.map((row) => row.acquired_at).sort().at(-1))} (${firms.data[0].sensor})` : ""}</span></p>
          )}
        </div>
      </div>
      <div className="space-y-4">
        <div>
          <SectionHeader icon={Radio} title={`NWS active alerts${nws?.scope ? ` · ${nws.scope}` : ""}`} section={nws} />
          {loading && !nws ? <p className="text-xs text-muted-foreground">Loading…</p> : !nws ? <p className="text-xs text-muted-foreground">No US location to query.</p> : nws.status !== "OK" ? <Unavailable section={nws} /> : nws.data.length === 0 ? <p className="text-sm text-muted-foreground">No active NWS alerts for this area.</p> : (
            <ul className="space-y-1.5">
              {nws.data.slice(0, 4).map((alert) => (
                <li key={alert.id} className="text-sm">
                  <a href={alert.source_url} target="_blank" rel="noreferrer" className="font-medium hover:underline">{alert.event}</a>
                  <span className="ml-2 font-mono text-[10px] text-telemetry">{alert.severity}/{alert.urgency}/{alert.certainty}</span>
                  <p className="text-xs text-muted-foreground">until {when(alert.expires)} · {alert.sender}</p>
                </li>
              ))}
              {nws.data.length > 4 && <li className="text-xs text-tertiary">+{nws.data.length - 4} more</li>}
            </ul>
          )}
        </div>
        <div>
          <SectionHeader icon={Landmark} title={`OpenFEMA declarations${context?.delivery_state ? ` · ${context.delivery_state}` : ""}`} section={fema} />
          {!fema ? <p className="text-xs text-muted-foreground">No state on record.</p> : fema.status !== "OK" ? <Unavailable section={fema} /> : (
            <>
              <ul className="space-y-1">
                {fema.data.slice(0, 3).map((row) => <li key={`${row.declaration_number}-${row.designated_area}`} className="text-sm"><a href={row.source_url} className="font-mono text-xs text-live hover:underline" target="_blank" rel="noreferrer">{row.declaration_number}</a> <span>{row.incident_type}: {row.title}</span> <span className="text-xs text-muted-foreground">({when(row.declaration_date)}, {row.designated_area})</span></li>)}
              </ul>
              <p className="mt-1 text-[11px] text-tertiary">{fema.note}</p>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
