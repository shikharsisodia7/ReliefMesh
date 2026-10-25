import { describe, expect, it } from "vitest";

import { readableMessage } from "@/components/mission/audit-tab";
import { when } from "@/components/status-badges";

describe("readableMessage", () => {
  it("formats the approval amount and expiry", () => {
    expect(readableMessage("Plan v2 approved for $3466.00 (expires 2026-10-25T10:53Z)."))
      .toBe(`Plan v2 approved for $3,466.00 · expires ${when("2026-10-25T10:53Z")}`);
  });

  it("formats replan totals and the unsigned delta", () => {
    expect(readableMessage("Plan v2 was computed after a supplier disruption: total $3466.00 (195.00 vs prior plan). A new human approval is required."))
      .toBe("Plan v2 was computed after a supplier disruption: total $3,466.00 (+$195.00 vs prior plan). A new human approval is required.");
  });

  it("formats prices and times inside sentences", () => {
    expect(readableMessage("Approval for plan v1 ($3271.00) was invalidated.")).toBe("Approval for plan v1 ($3,271.00) was invalidated.");
    expect(readableMessage("Bayside raised unit price $30.00 -> $33.50")).toBe("Bayside raised unit price $30.00 -> $33.50");
    expect(readableMessage("Bayside delayed delivery to 2026-10-27T10:53Z")).toBe(`Bayside delayed delivery to ${when("2026-10-27T10:53Z")}`);
  });

  it("leaves unknown and already formatted messages alone", () => {
    expect(readableMessage("Evidence checks completed for 4 supplier(s).")).toBe("Evidence checks completed for 4 supplier(s).");
    expect(readableMessage("Budget is $3,466.00 today.")).toBe("Budget is $3,466.00 today.");
  });
});
