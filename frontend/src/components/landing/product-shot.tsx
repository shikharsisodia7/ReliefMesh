"use client";

import { Ellipsis } from "lucide-react";
import { useLayoutEffect, useMemo, useRef, useState } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { demoPlanData } from "@/components/landing/demo-plan";
import { PlanTab } from "@/components/mission/plan-tab";
import { TabPanel, UnderlineTabs } from "@/components/patterns/underline-tabs";
import { Button } from "@/components/ui/button";
import { useHydrated } from "@/hooks/use-session";

// The real Plan tab, rendered at app width and scaled into a browser frame. Inert: nothing in it can be clicked.
const APP_WIDTH = 1132;
const VISIBLE_HEIGHT = 1010;
const noop = () => {};

export function ProductShot() {
  const hydrated = useHydrated();
  const viewport = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.76);
  // Times are local to the viewer, so the data is built in the browser only.
  const data = useMemo(() => (hydrated ? demoPlanData() : null), [hydrated]);
  useLayoutEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const measure = () => setScale(element.clientWidth / APP_WIDTH);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return (
    <figure
      role="img"
      aria-label="ReliefMesh Plan tab: Plan v2, rebuilt after Bayside Relief Supply Co withdrew, waiting for a new approval"
      className="overflow-hidden rounded-[14px] border bg-background text-left shadow-[0_24px_60px_-20px_rgb(21_22_26/0.25),0_2px_8px_rgb(21_22_26/0.06)]"
    >
      <div className="border-b bg-muted px-4 py-2 text-[11px] text-muted-foreground"><span className="font-semibold text-foreground">ReliefMesh</span> / Mission workspace</div>
      <div ref={viewport} className="relative overflow-hidden" style={{ height: VISIBLE_HEIGHT * scale }}>
        <div inert aria-hidden className="absolute top-0 left-0 origin-top-left" style={{ width: APP_WIDTH, transform: `scale(${scale})` }}>
          <div className="px-4 pt-4">
            <div className="grid h-14 grid-cols-[1fr_auto_1fr] items-center rounded-xl border px-6">
              <span className="text-lg font-semibold tracking-tight">ReliefMesh</span>
              <span className="flex h-full items-center gap-8 text-sm font-medium text-muted-foreground">
                <span className="flex h-full items-center border-b-2 border-foreground text-foreground">Missions</span><span>Suppliers</span><span>Analytics</span><span>System Status</span>
              </span>
              <span className="grid size-9 place-items-center justify-self-end rounded-full border text-xs font-semibold">JP</span>
            </div>
          </div>
          {data && (
            <div className="px-4 pt-8">
              <PageHeader
                breadcrumb={[{ label: "Missions" }, { label: "Shelter blankets" }]}
                title="Shelter blankets"
                meta="Bay Area Emergency Logistics · DEMO ORG"
                actions={<><Button variant="text">Explain changes</Button><Button variant="text" size="icon"><Ellipsis /></Button></>}
              />
              <div className="mt-6">
                <UnderlineTabs label="Mission stages" value="plan" onValueChange={noop} items={[
                  { value: "context", label: "Context" },
                  { value: "evidence", label: "Suppliers & Evidence" },
                  { value: "plan", label: <>Plan<span className="font-normal text-muted-foreground"> · needs approval</span></> },
                  { value: "approval", label: "Approval" },
                  { value: "orders", label: "Orders" },
                  { value: "audit", label: "Audit" },
                ]}>
                  <TabPanel value="plan">
                    <PlanTab
                      {...data} suppliers={[]} disruptions={[]} token="" run={async () => {}} setNotice={noop} onTab={noop} onOptimize={noop}
                      canApprove approvalBlocked={null} requester="Maya Chen" showDemo={false} approvalTtlMinutes={1440}
                      busy={false} continuityRunning={false} eligibleCount={2} quoteCount={3}
                    />
                  </TabPanel>
                </UnderlineTabs>
              </div>
            </div>
          )}
        </div>
      </div>
    </figure>
  );
}
