import { expect, test } from "@playwright/test";

// Full judge demo on live data: real EONET event, TEST suppliers screened against the live OFAC list,
// policy-gated optimization, a persisted disruption, autonomous replan, re-approval, and human review.
test("judge scenario: real emergency, evidence, policy, disruption, recovery, approval", async ({ page }) => {
  test.setTimeout(180_000);
  const runId = Date.now();
  await page.goto("/sign-up");
  await page.getByLabel("Email").fill(`judge-${runId}@e2e.example.com`);
  await page.getByLabel("Password").fill("correct horse battery staple");
  await page.getByRole("button", { name: "Create coordinator account" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.getByPlaceholder("Organization name").fill("Bay Area Emergency Logistics");
  await page.getByLabel("Demo organization (labeled self-approval)").check();
  await page.getByRole("button", { name: "Create organization" }).click();

  const eventSelect = page.getByLabel("Real emergency (NASA EONET, open events)");
  await expect(eventSelect.locator("option")).not.toHaveCount(1, { timeout: 30_000 });
  const eventId = await eventSelect.locator("option").nth(1).getAttribute("value");
  await eventSelect.selectOption(eventId!);
  await page.getByLabel("Mission name").fill("Shelter blankets");
  await page.getByLabel("Delivery location").fill("Oakland, CA");
  const deadline = new Date(Date.now() + 4 * 86_400_000);
  await page.getByLabel("Delivery deadline").fill(new Date(deadline.getTime() - deadline.getTimezoneOffset() * 60_000).toISOString().slice(0, 16));
  await page.getByLabel("Budget (USD)").fill("5000");
  await page.getByLabel("Required item").fill("blankets");
  await page.getByLabel("Quantity").fill("100");
  await page.getByRole("button", { name: "Create mission" }).click();
  await expect(page).toHaveURL(/\/missions\//);
  await expect(page.getByText(eventId!)).toBeVisible();

  await page.getByRole("button", { name: "Seed TEST suppliers" }).click();
  const pioneer = page.getByTestId("supplier-Pioneer Logistics Supply");
  await expect(pioneer.getByText(/OFAC POTENTIAL_MATCH/)).toBeVisible({ timeout: 60_000 });
  await expect(pioneer.getByText("NEEDS REVIEW").first()).toBeVisible();
  await expect(page.getByText(/OFAC NO_MATCH/)).toHaveCount(3, { timeout: 30_000 });

  await page.getByRole("button", { name: "Run optimization" }).click();
  await expect(page.getByRole("heading", { name: "Plan v1" })).toBeVisible();
  await expect(page.getByText(/Total \$3,271\.00/)).toBeVisible();
  await expect(page.getByText(/Pioneer Logistics Supply: \d+ blankets/)).toHaveCount(0);

  await pioneer.getByText(/OFAC POTENTIAL_MATCH/).click();
  await expect(page.getByRole("dialog", { name: "Evidence detail" }).getByText(/PIONEER LOGISTICS/).first()).toBeVisible();
  await page.getByRole("button", { name: "Close evidence" }).click();

  await page.getByRole("button", { name: "Approve plan" }).click();
  await expect(page.getByText("approved", { exact: true }).first()).toBeVisible();

  await page.getByRole("button", { name: "DISRUPT SUPPLY CHAIN" }).click();
  await page.getByLabel("Disruption", { exact: true }).selectOption("withdraw");
  await page.getByLabel("Supplier", { exact: true }).selectOption({ label: "Bayside Relief Supply Co (TEST) · allocated" });
  await page.getByRole("button", { name: "Apply disruption" }).click();
  await expect(page.getByRole("heading", { name: "Plan v2" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("OLD PLAN")).toBeVisible();
  await expect(page.getByText("NEW PLAN")).toBeVisible();
  await expect(page.getByText("INVALIDATED", { exact: true })).toBeVisible();
  await expect(page.getByText("+$195.00")).toBeVisible();
  await expect(page.getByText(/Bayside Relief Supply Co withdrew its quote/).first()).toBeVisible();

  await page.getByRole("button", { name: "Approve plan" }).click();
  await page.getByRole("button", { name: "Generate POs" }).click();
  const sends = page.getByRole("button", { name: "Confirm & send" });
  await expect(sends).toHaveCount(2);
  await sends.first().click();
  await expect(sends).toHaveCount(1);
  await sends.first().click();
  await expect(sends).toHaveCount(0);

  // OFAC false positive, and (when the CRS sandbox is configured) the failed signer identity check.
  for (let index = 0; index < 3 && (await pioneer.getByRole("button", { name: "Clear finding" }).count()) > 0; index += 1) {
    await pioneer.getByLabel("Clear finding reason").first().fill("Distinct US entity; signer and EIN verified by phone");
    await pioneer.getByRole("button", { name: "Clear finding" }).first().click();
    await page.waitForTimeout(1500);
  }
  await expect(page.getByRole("heading", { name: "Plan v3" })).toBeVisible({ timeout: 30_000 });
  // Units already on sent purchase orders stay committed: the policy change must not re-buy them.
  await expect(page.getByText(/Committed on POs \$3,466\.00 · New spend \$0\.00/)).toBeVisible();
  await expect(page.getByText(/hash chain verified/)).toBeVisible({ timeout: 15_000 });
});
