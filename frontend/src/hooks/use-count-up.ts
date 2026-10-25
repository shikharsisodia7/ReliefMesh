"use client";

import { useEffect, useRef, useState } from "react";

// Counts from the previous value to the new one (600 ms, ease-out). Jumps straight there under reduced motion.
export function useCountUp(target: number, duration = 600) {
  const [value, setValue] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    const start = from.current;
    from.current = target;
    if (start === target) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const began = performance.now();
    let frame = 0;
    const step = (now: number) => {
      const progress = reduce ? 1 : Math.min(1, (now - began) / duration);
      setValue(progress === 1 ? target : start + (target - start) * (1 - (1 - progress) ** 3));
      if (progress < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, duration]);
  return value;
}
