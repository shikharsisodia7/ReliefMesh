"use client";

import "leaflet/dist/leaflet.css";
import "./leaflet-map.css";

import L from "leaflet";
import Link from "next/link";
import { CircleMarker, MapContainer, Marker, Popup, TileLayer, useMapEvents } from "react-leaflet";

import type { MapMarker } from "@/components/patterns/tile-map";

const escape = (text: string) => text.replace(/[&<>"']/g, (char) => `&#${char.charCodeAt(0)};`);

// The same marker look as before: a white triangle for an event, a cross for a delivery, and a label beside it.
function icon(marker: MapMarker) {
  const shape = marker.kind === "event"
    ? '<path d="M8 2 14.5 13.5h-13z" fill="white" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" />'
    : '<path d="M8 2v12M2 8h12" stroke="currentColor" stroke-width="2.5" />';
  const label = marker.label ? `<span class="map-label ${marker.labelLeft ? "map-label-left" : ""}">${escape(marker.label)}</span>` : "";
  return L.divIcon({ className: "map-marker", html: `<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">${shape}</svg>${label}`, iconSize: [16, 16], iconAnchor: [8, 8], popupAnchor: [0, -8] });
}

// Scroll-wheel zoom turns on only after a click into the map, so scrolling the page never gets stuck on it.
function WheelAfterClick() {
  const map = useMapEvents({
    click: () => map.scrollWheelZoom.enable(),
    mouseout: () => map.scrollWheelZoom.disable(),
  });
  return null;
}

export default function LeafletMap({ markers, center, zoom, height, label }: { markers: MapMarker[]; center?: { lat: number; lon: number }; zoom: number; height: number; label: string }) {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  // Starts on the caller's center when given, otherwise fitted to every marker.
  const view = center || markers.length < 2
    ? { center: [center?.lat ?? markers[0]?.lat ?? 0, center?.lon ?? markers[0]?.lon ?? 0] as [number, number], zoom }
    : { bounds: L.latLngBounds(markers.map((marker) => [marker.lat, marker.lon] as [number, number])), boundsOptions: { paddingTopLeft: [markers.some((marker) => marker.labelLeft) ? 170 : 40, 48] as [number, number], paddingBottomRight: [150, 40] as [number, number], maxZoom: 10 } };
  return (
    // `isolate` keeps Leaflet's internal z-indexes (400–1000) inside the map, below drawers and dialogs.
    <div role="region" aria-label={label} className="relative isolate overflow-hidden rounded-md border bg-muted" style={{ height }}>
      <MapContainer
        {...view}
        className="map-gray h-full w-full"
        scrollWheelZoom={false}
        attributionControl={false}
        zoomAnimation={!reduced}
        fadeAnimation={!reduced}
        markerZoomAnimation={!reduced}
        inertia={!reduced}
      >
        <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={18} />
        <WheelAfterClick />
        {markers.filter((marker) => marker.kind === "detection").map((marker, index) => (
          <CircleMarker key={`d${index}`} center={[marker.lat, marker.lon]} radius={3} interactive={false} pathOptions={{ stroke: false, fillColor: "#202124", fillOpacity: 0.7 }} />
        ))}
        {markers.filter((marker) => marker.kind !== "detection").map((marker, index) => (
          <Marker key={`m${index}`} position={[marker.lat, marker.lon]} icon={icon(marker)} title={marker.label} keyboard={Boolean(marker.popup)} interactive={Boolean(marker.popup)}>
            {marker.popup && (
              <Popup autoPanPaddingTopLeft={[48, 16]}>
                <div className="text-sm font-semibold">{marker.popup.title}</div>
                {(marker.popup.category || marker.popup.date) && <div className="mt-0.5 text-xs text-muted-foreground">{[marker.popup.category, marker.popup.date].filter(Boolean).join(" · ")}</div>}
                {marker.popup.links.length > 0 && (
                  <div className="mt-2 flex flex-col gap-1 text-sm">
                    {marker.popup.links.map((link) => link.external
                      ? <a key={link.href} href={link.href} className="font-medium hover:underline" target="_blank" rel="noreferrer">{link.label} →</a>
                      : <Link key={link.href} href={link.href} className="font-medium hover:underline">{link.label} →</Link>)}
                  </div>
                )}
              </Popup>
            )}
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
