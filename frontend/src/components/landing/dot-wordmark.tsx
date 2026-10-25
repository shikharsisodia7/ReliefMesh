"use client";

import { useEffect, useState } from "react";

// "ReliefMesh" as a dot matrix: the word is drawn once on a hidden canvas and sampled on a grid, so every dot is a
// whole circle. Dots fill about 40% of each cell. The bottom of the letters is cropped by the viewBox.
const WIDTH = 1000;
const HEIGHT = 190;
const SPACING = 9;
const RADIUS = SPACING * 0.36;

export function DotWordmark() {
  const [dots, setDots] = useState<[number, number][]>([]);
  useEffect(() => {
    let cancelled = false;
    void document.fonts.ready.then(() => {
      const canvas = document.createElement("canvas");
      canvas.width = WIDTH;
      canvas.height = HEIGHT;
      const context = canvas.getContext("2d");
      if (!context || cancelled) return;
      // The page's Inter, at the weight and size that spans the full width.
      context.font = `800 290px ${getComputedStyle(document.body).fontFamily}`;
      context.textBaseline = "alphabetic";
      const scale = WIDTH / context.measureText("ReliefMesh").width;
      context.setTransform(scale, 0, 0, 1, 0, 0);
      context.fillText("ReliefMesh", 0, 228);
      const pixels = context.getImageData(0, 0, WIDTH, HEIGHT).data;
      const found: [number, number][] = [];
      for (let y = SPACING / 2; y < HEIGHT; y += SPACING) {
        for (let x = SPACING / 2; x < WIDTH; x += SPACING) {
          if (pixels[(Math.floor(y) * WIDTH + Math.floor(x)) * 4 + 3] > 128) found.push([x, y]);
        }
      }
      setDots(found);
    });
    return () => { cancelled = true; };
  }, []);
  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="block h-auto w-full" role="img" aria-label="ReliefMesh">
      <g fill="#15161A">{dots.map(([x, y]) => <circle key={`${x}:${y}`} cx={x} cy={y} r={RADIUS} />)}</g>
    </svg>
  );
}
