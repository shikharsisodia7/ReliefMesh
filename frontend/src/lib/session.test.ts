import { describe, expect, it } from "vitest";

import { safeNext } from "./session";

describe("safeNext", () => {
  it("keeps same-site paths so invitation links survive sign-up", () => {
    expect(safeNext("/invitations/abc")).toBe("/invitations/abc");
    expect(safeNext("/join/xyz?x=1")).toBe("/join/xyz?x=1");
  });

  it("rejects anything that could leave the site", () => {
    for (const value of ["https://evil.test", "//evil.test", "/\\evil.test", "javascript:alert(1)", "", null, undefined]) {
      expect(safeNext(value)).toBeNull();
    }
  });
});
