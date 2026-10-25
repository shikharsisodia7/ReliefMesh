"use client";

import { Tabs } from "@base-ui/react/tabs";
import { useEffect, useRef, type ReactNode } from "react";

// Plain text tabs across the full content width, with a 2px underline that slides to the active tab.
export function UnderlineTabs({ label, value, onValueChange, items, children }: {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  items: { value: string; label: ReactNode }[];
  children: ReactNode;
}) {
  const list = useRef<HTMLDivElement>(null);
  // On narrow screens the tabs scroll sideways; keep the active one in view.
  useEffect(() => { list.current?.querySelector("[data-active]")?.scrollIntoView({ block: "nearest", inline: "nearest" }); }, [value]);
  return (
    <Tabs.Root value={value} onValueChange={(next) => onValueChange(String(next))}>
      <Tabs.List ref={list} aria-label={label} className="relative flex gap-8 overflow-x-auto border-b">
        {items.map((item) => (
          <Tabs.Tab
            key={item.value}
            value={item.value}
            className="h-11 shrink-0 text-sm font-medium whitespace-nowrap text-muted-foreground outline-hidden hover:text-foreground focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-[-2px] focus-visible:outline-ring data-[active]:text-foreground"
          >
            {item.label}
          </Tabs.Tab>
        ))}
        <Tabs.Indicator className="absolute bottom-0 left-0 h-0.5 w-(--active-tab-width) translate-x-(--active-tab-left) bg-foreground transition-[translate,width] duration-200 ease-out motion-reduce:transition-none" />
      </Tabs.List>
      {children}
    </Tabs.Root>
  );
}

export function TabPanel({ value, children }: { value: string; children: ReactNode }) {
  return <Tabs.Panel value={value} className="pt-8 outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-4 focus-visible:outline-ring">{children}</Tabs.Panel>;
}
