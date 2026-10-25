import { expect, test } from "@playwright/test";

// The landing page's failure demo runs on static data in the browser and never calls the API.
test("landing: marketing nav and the client-side supplier failure demo", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Emergency procurement/ })).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Main" });
  for (const label of ["How it works", "Judge guide", "System Status"]) await expect(nav.getByRole("link", { name: label })).toBeVisible();

  const scene = page.locator("section", { has: page.getByRole("heading", { name: "When a supplier fails, the plan rebuilds itself." }) });
  await scene.scrollIntoViewIfNeeded();
  await page.waitForLoadState("networkidle");
  const apiCalls: string[] = [];
  // The hero's live strip and map may still be loading (or retrying); only the demo's own traffic counts.
  const heroFacts = ["/v1/fire-detections/california", "/v1/emergency-events", "/v1/integrations/status"];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.port === "8000" && !heroFacts.includes(url.pathname)) apiCalls.push(request.url());
  });

  // Starts before the failure: Plan v1, no withdrawal notice, no audit entry.
  await expect(scene.getByRole("heading", { name: "Shelter blankets · Plan v1" })).toBeVisible();
  await expect(scene.getByText("Quote withdrawn · 14:32:08")).toBeHidden();
  const timeline = scene.getByRole("slider", { name: "Failure timeline" });
  await timeline.focus();
  await page.keyboard.press("ArrowRight");
  await expect(scene.getByText("Quote withdrawn · 14:32:08")).toBeVisible();
  await page.keyboard.press("ArrowRight");
  await expect(scene.getByText("Approval revoked · new approval required.")).toBeVisible();
  await page.keyboard.press("ArrowRight");
  await expect(scene.getByTestId("demo-total")).toHaveText("$3,466");
  // The approval hasn't happened yet at 14:32:10, so there is no audit entry.
  await expect(scene.getByText("#14 plan.approved")).toBeHidden();
  await scene.getByRole("button", { name: "Approve" }).click();
  await expect(scene.getByRole("button", { name: "Approved" })).toBeDisabled();
  await expect(scene.getByText("#14 plan.approved")).toBeVisible();

  await scene.getByRole("button", { name: "Replay failure" }).click();
  await expect(scene.getByRole("button", { name: "Replay failure" })).toBeVisible({ timeout: 8_000 });
  await expect(scene.getByText("#14 plan.approved")).toBeVisible();
  expect(apiCalls).toEqual([]);
});
