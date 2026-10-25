"use client";

import { Tabs } from "@base-ui/react/tabs";
import type { ReactNode } from "react";

// Plain text tabs across the full content width, with a 2px underline that slides to the active tab.
export function UnderlineTabs({ label, value, onValueChange, items, children }: {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  items: { value: string; label: ReactNode }[];
  children: ReactNode;
}) {
  return (
    <Tabs.Root value={value} onValueChange={(next) => onValueChange(String(next))}>
      <Tabs.List aria-label={label} className="relative flex gap-8 overflow-x-auto border-b">
        {items.map((item) => (
          <Tabs.Tab
            key={item.value}
            value={item.value}
            className="h-11 shrink-0 text-sm font-medium whitespace-nowrap text-muted-foreground outline-none hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring data-[active]:text-foreground"
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
  return <Tabs.Panel value={value} className="pt-8 outline-none">{children}</Tabs.Panel>;
}
