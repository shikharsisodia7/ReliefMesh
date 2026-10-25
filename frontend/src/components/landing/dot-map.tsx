import { DOTS, GAP, MAP_HEIGHT, MAP_WIDTH } from "@/components/landing/california";
import { cn } from "@/lib/utils";

// California as a grid of dots. `lit` holds "col:row" keys of dots drawn in signal orange.
export function DotMap({ lit, dotClass, litClass, glow = false, className, label }: {
  lit?: Set<string>; dotClass: string; litClass?: string; glow?: boolean; className?: string; label?: string;
}) {
  const radius = GAP * 0.24;
  const on = DOTS.filter((dot) => lit?.has(`${dot.col}:${dot.row}`));
  return (
    <svg viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`} className={className} style={{ aspectRatio: `${MAP_WIDTH} / ${MAP_HEIGHT}` }} role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      {glow && (
        <defs>
          <filter id="dot-glow" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation={GAP * 0.6} /></filter>
        </defs>
      )}
      <g className={dotClass}>
        {DOTS.map((dot) => <circle key={`${dot.col}:${dot.row}`} cx={dot.x} cy={dot.y} r={radius} />)}
      </g>
      {on.length > 0 && (
        <g className={cn("fill-signal", litClass)}>
          {glow && <g filter="url(#dot-glow)" opacity={0.7}>{on.map((dot) => <circle key={`${dot.col}:${dot.row}`} cx={dot.x} cy={dot.y} r={radius * 2.2} />)}</g>}
          {on.map((dot) => <circle key={`${dot.col}:${dot.row}`} cx={dot.x} cy={dot.y} r={radius * 1.5} />)}
        </g>
      )}
    </svg>
  );
}
