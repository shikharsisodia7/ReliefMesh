import { describe, expect, it } from "vitest";

import { draftToInput, toLocalInput } from "./quote-form";

describe("draftToInput", () => {
  it("shows a naive wall-clock time exactly as the supplier wrote it", () => {
    expect(draftToInput("2026-10-26T12:00:00")).toBe("2026-10-26T12:00");
    expect(draftToInput("2026-10-27T23:00")).toBe("2026-10-27T23:00");
  });

  it("converts zoned instants to the viewer's local time", () => {
    for (const value of ["2026-10-26T19:00:00Z", "2026-10-26T19:00:00+00:00", "2026-10-26T12:00:00-07:00", "2026-10-26T12:00:00-0700"]) {
      expect(draftToInput(value)).toBe(toLocalInput(value));
    }
  });
});
