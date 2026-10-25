"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Fragment, useMemo } from "react";

import { nearestDots } from "@/components/landing/california";
import { DotMap } from "@/components/landing/dot-map";
import { ProductShot } from "@/components/landing/product-shot";
import { buttonVariants } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { EmergencyEvent, FirmsDetection, IntegrationCheck } from "@/lib/types";
import { cn } from "@/lib/utils";

type FireDetections = { status: string; data: Pick<FirmsDetection, "latitude" | "longitude" | "acquired_at">[] };

// Each live number comes from the API; a part that fails to load is left out, never estimated.
function useLiveFacts() {
  const fires = useQuery({ queryKey: ["fire-detections", "CA"], queryFn: () => api<FireDetections>("/v1/fire-detections/california"), staleTime: 600_000 });
  const events = useQuery({ queryKey: ["emergency-events"], queryFn: () => api<EmergencyEvent[]>("/v1/emergency-events"), staleTime: 120_000 });
  const status = useQuery({ queryKey: ["integration-status", false], queryFn: () => api<{ integrations: IntegrationCheck[] }>("/v1/integrations/status") });
  const detections = fires.data?.status === "OK" ? fires.data.data : null;
  const california = events.data?.filter((event) => event.state === "CA").length;
  const checks = status.data?.integrations;
  const parts: string[] = [];
  if (detections) parts.push(`${detections.length.toLocaleString("en-US")} NASA FIRMS fire detections, last 48 h`);
  if (california !== undefined) parts.push(`${california} open NASA EONET event${california === 1 ? "" : "s"} in California`);
  if (checks?.length) parts.push(`${checks.filter((check) => check.status === "ok").length} of ${checks.length} integrations operational`);
  return { detections, parts };
}

export function Hero() {
  const { detections, parts } = useLiveFacts();
  const lit = useMemo(() => (detections ? nearestDots(detections) : undefined), [detections]);
  return (
    <section className="relative overflow-hidden bg-background pb-20">
      <DotMap
        lit={lit}
        dotClass="fill-[#C9CCD1]"
        className="pointer-events-none absolute top-14 left-[max(-60px,calc(50%-700px))] hidden h-[880px] w-auto md:block"
        label={detections ? "Map of California with NASA FIRMS fire detections from the last 48 hours in orange" : undefined}
      />
      <div className="relative mx-auto max-w-[1132px] px-4 pt-10 text-center md:pt-12">
        <h1 className="text-[44px] leading-[1.02] font-bold tracking-[-0.04em] text-ink md:text-[78px]">
          Emergency procurement<br /><span className="text-signal">that rebuilds itself.</span>
        </h1>
        <p className="mx-auto mt-5 max-w-[680px] text-lg leading-snug text-muted-foreground md:text-xl">
          When a supplier fails mid-disaster, ReliefMesh rebuilds the purchasing plan in seconds and asks a human to approve it again.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-x-8 gap-y-3">
          <Link href="/sign-up" className={cn(buttonVariants(), "h-12 rounded-md px-10 text-base")}>Start a mission</Link>
          <Link href="/sign-up?role=supplier" className="text-base font-medium text-foreground hover:underline">Supplier portal →</Link>
        </div>
      </div>
      <div className="relative mx-auto mt-6 max-w-[892px] px-4 xl:translate-x-[120px]">
        <ProductShot />
      </div>
      {parts.length > 0 && (
        <p className="relative mx-auto mt-6 max-w-[1132px] px-4 text-center text-sm text-muted-foreground tabular md:text-base">
          Live: {parts.map((part, index) => <Fragment key={part}>{index > 0 && <span className="mx-2">·</span>}{part}</Fragment>)}
          <span className="mx-2">·</span><Link href="/status" className="font-medium text-foreground underline underline-offset-4">View status →</Link>
        </p>
      )}
    </section>
  );
}
