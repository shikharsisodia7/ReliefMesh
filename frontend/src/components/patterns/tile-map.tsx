// A light gray basemap from OpenStreetMap's public tiles (grayscaled with CSS), laid out as plain images: no map library.
// Markers use real coordinates only; callers leave out anything the API doesn't locate.
export type MapMarker = { lat: number; lon: number; kind: "event" | "delivery" | "detection"; label?: string };

const TILE = 256;

// Web Mercator: degrees to fractional tile coordinates at a zoom level.
function toTile(lat: number, lon: number, zoom: number) {
  const n = 2 ** zoom;
  const rad = (lat * Math.PI) / 180;
  return { x: ((lon + 180) / 360) * n, y: ((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * n };
}

function Marker({ marker }: { marker: MapMarker }) {
  if (marker.kind === "detection") return <span className="block size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground/70" />;
  return (
    <span className="flex -translate-x-1/2 -translate-y-1/2 items-center gap-1.5 whitespace-nowrap text-xs font-medium">
      {marker.kind === "event"
        ? <svg viewBox="0 0 16 16" className="size-4" aria-hidden><path d="M8 2 14.5 13.5h-13z" fill="white" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /></svg>
        : <svg viewBox="0 0 16 16" className="size-4" aria-hidden><path d="M8 2v12M2 8h12" stroke="currentColor" strokeWidth="2.5" /></svg>}
      {marker.label && <span className="rounded-sm bg-background/90 px-1">{marker.label}</span>}
    </span>
  );
}

export function TileMap({ center, markers, zoom = 8, height = 300, label }: { center: { lat: number; lon: number }; markers: MapMarker[]; zoom?: number; height?: number; label: string }) {
  const middle = toTile(center.lat, center.lon, zoom);
  const n = 2 ** zoom;
  const tiles = [];
  // Enough tiles around the center to cover a wide column.
  for (let dx = -4; dx <= 4; dx += 1) {
    for (let dy = -2; dy <= 2; dy += 1) {
      const x = Math.floor(middle.x) + dx;
      const y = Math.floor(middle.y) + dy;
      if (y < 0 || y >= n) continue;
      tiles.push({ key: `${x}-${y}`, src: `https://tile.openstreetmap.org/${zoom}/${((x % n) + n) % n}/${y}.png`, left: (x - middle.x) * TILE, top: (y - middle.y) * TILE });
    }
  }
  return (
    <figure>
      <div role="img" aria-label={label} className="relative overflow-hidden rounded-md border bg-muted" style={{ height }}>
        {tiles.map((tile) => (
          // eslint-disable-next-line @next/next/no-img-element -- raw map tiles; next/image adds nothing here
          <img key={tile.key} src={tile.src} alt="" width={TILE} height={TILE} className="absolute max-w-none opacity-80 grayscale contrast-75 brightness-110" style={{ left: `calc(50% + ${tile.left}px)`, top: `calc(50% + ${tile.top}px)` }} />
        ))}
        {markers.map((marker, index) => {
          const point = toTile(marker.lat, marker.lon, zoom);
          return <span key={index} className="absolute" style={{ left: `calc(50% + ${(point.x - middle.x) * TILE}px)`, top: `calc(50% + ${(point.y - middle.y) * TILE}px)` }}><Marker marker={marker} /></span>;
        })}
      </div>
      <figcaption className="mt-1.5 text-xs text-muted-foreground">© <a className="hover:underline" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a></figcaption>
    </figure>
  );
}
