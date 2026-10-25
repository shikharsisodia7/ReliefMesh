import { expect, test } from "@playwright/test";

// A stored token whose account no longer exists (deleted or revoked) must send the user to sign in,
// not leave the integrations settings page blank.
test("integrations settings with a revoked session redirects to sign-in and clears the token", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => localStorage.setItem("reliefmesh.session", JSON.stringify({
    token: "revoked.session.token",
    user: { id: "deleted-user", email: "deleted@example.test", role: "coordinator" },
  })));
  await page.goto("/settings/integrations");
  await expect(page).toHaveURL(/\/sign-in/);
  expect(await page.evaluate(() => localStorage.getItem("reliefmesh.session"))).toBeNull();
});
