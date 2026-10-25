"use client";

import { useEffect, useRef, useState } from "react";

// A single-letter sibling to DotWordmark: the same "sample a canvas-drawn glyph onto a dot grid"
// technique, but for one character ("R") in a square frame instead of the full word. The full
// wordmark only reads as letters when it has real width to work with (the footer, near-full page
// width) — shrunk to nav-icon size it collapses into blobs. One glyph holds its shape far smaller.
const SIZE = 220;
const SPACING = 15;
const RADIUS = SPACING * 0.4;
const REVEAL_SECONDS = 0.5;

let cachedDots: [number, number][] | null = null;

function sampleGlyph(): [number, number][] {
  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;
  const context = canvas.getContext("2d");
  if (!context) return [];
  const pageFont = getComputedStyle(document.body).fontFamily || "sans-serif";
  context.font = `800 ${SIZE * 1.05}px ${pageFont}, sans-serif`;
  context.textBaseline = "alphabetic";
  context.textAlign = "center";
  context.fillText("R", SIZE / 2, SIZE * 0.82);
  const pixels = context.getImageData(0, 0, SIZE, SIZE).data;
  const found: [number, number][] = [];
  for (let y = SPACING / 2; y < SIZE; y += SPACING) {
    for (let x = SPACING / 2; x < SIZE; x += SPACING) {
      if (pixels[(Math.floor(y) * SIZE + Math.floor(x)) * 4 + 3] > 128) found.push([x, y]);
    }
  }
  return found;
}

/** Compact dot-matrix "R" monogram — the brand mark for places too small for the full wordmark. */
export function DotMonogram({ className }: { className?: string }) {
  const [dots, setDots] = useState<[number, number][] | null>(cachedDots);
  const [revealed, setRevealed] = useState(cachedDots !== null);
  const ref = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (cachedDots) return;
    let cancelled = false;
    void document.fonts.ready.then(() => {
      if (cancelled) return;
      cachedDots = sampleGlyph();
      setDots(cachedDots);
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!dots || revealed) return;
    const id = requestAnimationFrame(() => setRevealed(true));
    return () => cancelAnimationFrame(id);
  }, [dots, revealed]);

  return (
    <svg ref={ref} viewBox={`0 0 ${SIZE} ${SIZE}`} className={className ?? "block size-8"} role="img" aria-label="ReliefMesh">
      <g fill="currentColor">
        {(dots ?? []).map(([x, y]) => (
          <circle
            key={`${x}:${y}`}
            cx={x}
            cy={y}
            r={RADIUS}
            className="motion-safe:transition-[opacity,transform] motion-safe:ease-out"
            style={{
              transformOrigin: `${x}px ${y}px`,
              transitionDuration: `${REVEAL_SECONDS}s`,
              transitionDelay: revealed ? `${(y / SIZE) * REVEAL_SECONDS * 0.5}s` : "0s",
              opacity: revealed ? 1 : 0,
              transform: revealed ? "scale(1)" : "scale(0.3)",
            }}
          />
        ))}
      </g>
    </svg>
  );
}
