"use client";

import { useEffect, useRef, useState } from "react";

// "ReliefMesh" as a dot matrix: the word is drawn once on a hidden canvas and sampled on a grid, so every dot is a
// whole circle. The bottom of the letters is cropped by the viewBox.
const WIDTH = 1000;
const HEIGHT = 190;
const REVEAL_SECONDS = 0.9;

// "fine" is the footer mark, shown near full page width, so a tight grid still reads as crisp type.
// "compact" is the header mark, shown ~24-28px tall, so dots are coarser (fewer, bigger) or the
// wordmark would blur into a grey smudge at that scale.
const DENSITY = {
  fine: { spacing: 9, radius: 9 * 0.36 },
  compact: { spacing: 26, radius: 26 * 0.42 },
} as const;
type Density = keyof typeof DENSITY;

function sampleDots(spacing: number): [number, number][] {
  const canvas = document.createElement("canvas");
  canvas.width = WIDTH;
  canvas.height = HEIGHT;
  const context = canvas.getContext("2d");
  if (!context) return [];
  // The page's Inter, at the weight and size that spans the full width. Falls back to a generic
  // sans-serif if the page font isn't resolvable yet, so the mark never silently renders empty.
  const pageFont = getComputedStyle(document.body).fontFamily || "sans-serif";
  context.font = `800 290px ${pageFont}, sans-serif`;
  context.textBaseline = "alphabetic";
  const measured = context.measureText("ReliefMesh").width;
  if (!measured) return [];
  const scale = WIDTH / measured;
  context.setTransform(scale, 0, 0, 1, 0, 0);
  context.fillText("ReliefMesh", 0, 228);
  const pixels = context.getImageData(0, 0, WIDTH, HEIGHT).data;
  const found: [number, number][] = [];
  for (let y = spacing / 2; y < HEIGHT; y += spacing) {
    for (let x = spacing / 2; x < WIDTH; x += spacing) {
      if (pixels[(Math.floor(y) * WIDTH + Math.floor(x)) * 4 + 3] > 128) found.push([x, y]);
    }
  }
  return found;
}

// One cache per density: the layout never changes, so repeated mounts (header persists across
// every page) sample once rather than on every navigation.
const cache: Record<Density, [number, number][] | null> = { fine: null, compact: null };

/**
 * The dot-matrix "ReliefMesh" wordmark, used anywhere the brand mark appears (header, footer).
 * Dots stay invisible until the mark scrolls into view, then sweep in left-to-right so the mark
 * never just pops in — and never sits there blank if sampling is slow on first paint.
 */
export function DotWordmark({ className, density = "fine" }: { className?: string; density?: Density }) {
  const { spacing, radius } = DENSITY[density];
  const [dots, setDots] = useState<[number, number][] | null>(cache[density]);
  const [revealed, setRevealed] = useState(false);
  const containerRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (cache[density]) return;
    let cancelled = false;
    const compute = () => {
      const found = sampleDots(spacing);
      if (cancelled) return;
      if (found.length === 0) {
        // Fonts can report "ready" a tick before metrics actually settle; one retry covers it.
        window.setTimeout(() => {
          if (cancelled) return;
          cache[density] = sampleDots(spacing);
          setDots(cache[density]);
        }, 150);
        return;
      }
      cache[density] = found;
      setDots(found);
    };
    void document.fonts.ready.then(compute);
    return () => { cancelled = true; };
  }, [density, spacing]);

  useEffect(() => {
    const node = containerRef.current;
    if (!node || revealed) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setRevealed(true);
        observer.disconnect();
      }
    }, { threshold: 0.2 });
    observer.observe(node);
    return () => observer.disconnect();
  }, [revealed]);

  return (
    <svg ref={containerRef} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className={className ?? "block h-auto w-full"} role="img" aria-label="ReliefMesh">
      <g fill="currentColor">
        {(dots ?? []).map(([x, y]) => (
          <circle
            key={`${x}:${y}`}
            cx={x}
            cy={y}
            r={radius}
            className="motion-safe:transition-[opacity,transform] motion-safe:ease-out"
            style={{
              transformOrigin: `${x}px ${y}px`,
              transitionDuration: `${REVEAL_SECONDS}s`,
              transitionDelay: revealed ? `${(x / WIDTH) * REVEAL_SECONDS * 0.6}s` : "0s",
              opacity: revealed ? 1 : 0,
              transform: revealed ? "scale(1)" : "scale(0.2)",
            }}
          />
        ))}
      </g>
    </svg>
  );
}
