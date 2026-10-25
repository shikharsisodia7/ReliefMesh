// A simplified California outline (lon, lat), clockwise from the Oregon border on the coast.
const OUTLINE: [number, number][] = [
  [-124.21, 42.0], [-120.0, 42.0], [-120.0, 39.0], [-114.63, 35.0], [-114.57, 34.8], [-114.43, 34.3], [-114.13, 34.27],
  [-114.53, 33.93], [-114.5, 33.67], [-114.72, 33.41], [-114.7, 33.09], [-114.47, 32.84], [-114.72, 32.72], [-117.12, 32.53],
  [-117.25, 32.7], [-117.28, 33.0], [-117.6, 33.39], [-118.0, 33.65], [-118.29, 33.71], [-118.52, 34.03], [-118.8, 34.0],
  [-119.22, 34.15], [-119.6, 34.4], [-120.47, 34.45], [-120.64, 34.57], [-120.62, 35.1], [-120.88, 35.43], [-121.3, 35.66],
  [-121.9, 36.3], [-121.95, 36.6], [-121.8, 36.8], [-122.0, 36.96], [-122.4, 37.2], [-122.51, 37.78], [-122.98, 38.0],
  [-123.7, 38.92], [-123.83, 39.8], [-124.36, 40.44], [-124.1, 40.9], [-124.2, 41.75],
];

const WEST = -124.6;
const NORTH = 42.2;
const LON_SCALE = Math.cos((37.5 * Math.PI) / 180);

// Grid spacing in map units; one degree of latitude is 10 units.
export const GAP = 1.25;
export const MAP_WIDTH = (-113.9 - WEST) * LON_SCALE * 10;
export const MAP_HEIGHT = (NORTH - 32.3) * 10;

export function project(lat: number, lon: number) {
  return { x: (lon - WEST) * LON_SCALE * 10, y: (NORTH - lat) * 10 };
}

const polygon = OUTLINE.map(([lon, lat]) => project(lat, lon));

function inside(x: number, y: number) {
  let hit = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const a = polygon[i];
    const b = polygon[j];
    if (a.y > y !== b.y > y && x < ((b.x - a.x) * (y - a.y)) / (b.y - a.y) + a.x) hit = !hit;
  }
  return hit;
}

export type Dot = { col: number; row: number; x: number; y: number };

// Every grid dot that falls inside the state, computed once.
export const DOTS: Dot[] = [];
for (let row = 0; row * GAP <= MAP_HEIGHT; row += 1) {
  for (let col = 0; col * GAP <= MAP_WIDTH; col += 1) {
    const x = col * GAP + GAP / 2;
    const y = row * GAP + GAP / 2;
    if (inside(x, y)) DOTS.push({ col, row, x, y });
  }
}
const byCell = new Set(DOTS.map((dot) => `${dot.col}:${dot.row}`));

// Snaps real coordinates to the nearest dot inside the state; points outside it are dropped.
export function nearestDots(points: { latitude: number; longitude: number }[]) {
  const keys = new Set<string>();
  for (const point of points) {
    const { x, y } = project(point.latitude, point.longitude);
    const key = `${Math.floor(x / GAP)}:${Math.floor(y / GAP)}`;
    if (byCell.has(key)) keys.add(key);
  }
  return keys;
}
