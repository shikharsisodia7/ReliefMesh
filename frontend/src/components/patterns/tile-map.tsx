"use client";

import dynamic from "next/dynamic";

// An interactive light gray OpenStreetMap map (Leaflet). Markers use real coordinates only; callers leave out anything
// the API doesn't locate. labelLeft puts a label on the left of its symbol, for markers close to a neighbor.
export type MapPopup = { title: string; category?: string; date?: string; links: { label: string; href: string; external?: boolean }[] };
export type MapMarker = { lat: number; lon: number; kind: "event" | "delivery" | "detection"; label?: string; labelLeft?: boolean; popup?: MapPopup };

// Leaflet needs the browser, so it loads on the client only; the server renders a gray box of the same size.
const LeafletMap = dynamic(() => import("@/components/patterns/leaflet-map"), {
  ssr: false,
  loading: () => <div className="h-full w-full rounded-md border bg-muted" />,
});

export function TileMap({ center, markers, zoom = 8, height = 300, label }: { center?: { lat: number; lon: number }; markers: MapMarker[]; zoom?: number; height?: number; label: string }) {
  return (
    <figure>
      <div style={{ height }}><LeafletMap center={center} markers={markers} zoom={zoom} height={height} label={label} /></div>
      <figcaption className="mt-1.5 text-xs text-muted-foreground">© <a className="hover:underline" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a> · Click the map to zoom with the scroll wheel.</figcaption>
    </figure>
  );
}
