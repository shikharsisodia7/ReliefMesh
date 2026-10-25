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
  // Coordinators reach the judge guide from the avatar menu, not the tabs.
  await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Judge guide" })).toHaveCount(0);
  await page.getByRole("button", { name: "Account menu" }).click();
  await expect(page.getByRole("menuitem", { name: "Judge guide" })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByPlaceholder("Organization name").fill("Bay Area Emergency Logistics");
  await page.getByLabel("Demo organization (labeled self-approval)").check();
  await page.getByRole("button", { name: "Create organization" }).click();

  // The mission form lives in the New mission slide-over.
  await page.getByRole("button", { name: "New mission" }).click();
  const eventSelect = page.getByLabel("Real emergency (NASA EONET, open events)");
  await expect(eventSelect.locator("option")).not.toHaveCount(1, { timeout: 30_000 });
  // Link an open California event when EONET has one (the demo is set in Oakland); otherwise the first event.
  const california = eventSelect.locator("option", { hasText: /, California$/ });
  const eventOption = (await california.count()) > 0 ? california.first() : eventSelect.locator("option").nth(1);
  const eventId = await eventOption.getAttribute("value");
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
  // The linked event lives on the Context tab; suppliers are seeded from Suppliers & Evidence.
  await page.getByRole("tab", { name: "Context" }).click();
  await expect(page.getByText(eventId!)).toBeVisible();
  await page.getByRole("tab", { name: "Suppliers & Evidence" }).click();

  await page.getByRole("button", { name: "Seed TEST suppliers" }).click();
  const pioneer = page.getByTestId("supplier-Pioneer Logistics Supply");
  // Check lines read "OFAC · Potential match"; the raw result code stays in data-result.
  await expect(pioneer.getByRole("button", { name: /^OFAC · Potential match/ })).toBeVisible({ timeout: 60_000 });
  await expect(pioneer.getByText(/needs review/i).first()).toBeVisible();
  await expect(page.locator('[data-check="OFAC_SCREENING"][data-result="NO_MATCH"]')).toHaveCount(3, { timeout: 30_000 });

  await page.getByRole("tab", { name: "Plan" }).click();
  await page.getByRole("button", { name: "Run optimization" }).click();
  await expect(page.getByRole("heading", { name: "Plan v1" })).toBeVisible();
  await expect(page.getByTestId("plan-total")).toHaveText("$3,271");
  await expect(page.getByTestId("allocation-table").getByText("Pioneer Logistics Supply")).toHaveCount(0);
  // The counterfactual analysis runs off the request path and must remain visibly
  // labeled as hypothetical before the judge performs a real supplier change.
  await expect(page.getByLabel("Continuity Engine")).toBeVisible();
  // The section is collapsed to one summary line by default.
  await page.getByLabel("Continuity Engine").getByRole("button", { name: "Show details" }).click();
  await expect(page.getByLabel("N-1 survivability")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByLabel("Failure frontier")).toBeVisible();
  await expect(page.getByText("HYPOTHETICAL STRESS TEST").first()).toBeVisible();

  await page.getByRole("tab", { name: "Suppliers & Evidence" }).click();
  await pioneer.getByRole("button", { name: /^OFAC · Potential match/ }).click();
  await expect(page.getByRole("dialog", { name: "Evidence detail" }).getByText(/PIONEER LOGISTICS/).first()).toBeVisible();
  await page.getByRole("button", { name: "Close evidence" }).click();

  await page.getByRole("tab", { name: "Plan" }).click();
  await page.getByRole("button", { name: "Approve plan" }).click();
  await expect(page.getByText("Approved", { exact: true }).first()).toBeVisible();

  await page.getByRole("button", { name: "Disrupt supply chain" }).click();
  await page.getByLabel("Disruption", { exact: true }).selectOption("withdraw");
  await page.getByLabel("Supplier", { exact: true }).selectOption({ label: "Bayside Relief Supply Co (TEST) · allocated" });
  await page.getByRole("button", { name: "Apply disruption" }).click();
  await expect(page.getByRole("heading", { name: "Plan v2" })).toBeVisible({ timeout: 30_000 });
  // The rail shows the stale previous plan and its revoked approval; the compare view keeps cents.
  await expect(page.getByRole("heading", { name: "Previous plan" })).toBeVisible();
  await expect(page.getByText(/Approval revoked/).first()).toBeVisible();
  await expect(page.getByText("+$195 vs v1")).toBeVisible();
  await expect(page.getByText(/Bayside Relief Supply Co withdrew its quote/).first()).toBeVisible();
  await page.getByRole("button", { name: "Compare v1 and v2" }).click();
  const compare = page.getByTestId("compare-view");
  await expect(compare.getByText("Previous plan")).toBeVisible();
  await expect(compare.getByText("Approval revoked", { exact: true })).toBeVisible();
  await expect(compare.getByText("+$195.00", { exact: true })).toBeVisible();
  await compare.getByRole("button", { name: "Back to plan" }).click();

  await page.getByRole("button", { name: "Approve plan" }).click();
  await page.getByRole("button", { name: "Generate POs" }).click();
  await page.getByRole("tab", { name: "Orders" }).click();
  // Each draft opens a confirmation dialog; sending is a separate, explicit step.
  const sends = page.getByRole("button", { name: "Confirm & send" });
  const confirm = page.getByRole("dialog", { name: "Confirm & send" });
  await expect(sends).toHaveCount(2);
  for (const remaining of [1, 0]) {
    await sends.first().click();
    await confirm.getByRole("button", { name: "Confirm & send" }).click();
    await expect(confirm).toHaveCount(0);
    await expect(sends).toHaveCount(remaining);
  }

  // OFAC false positive, and (when the CRS sandbox is configured) the failed signer identity check.
  for (let index = 0; index < 3; index += 1) {
    await page.getByRole("tab", { name: "Suppliers & Evidence" }).click();
    await expect(pioneer).toBeVisible();
    if ((await pioneer.getByRole("button", { name: "Clear finding" }).count()) === 0) break;
    // Clear finding opens a dialog that requires a reason.
    await pioneer.getByRole("button", { name: "Clear finding" }).first().click();
    const clearDialog = page.getByRole("dialog", { name: "Clear finding" });
    await clearDialog.getByLabel("Clear finding reason").fill("Distinct US entity; signer and EIN verified by phone");
    await clearDialog.getByRole("button", { name: "Clear finding" }).click();
    await expect(clearDialog).toHaveCount(0);
    await page.waitForTimeout(1500);
  }
  await page.getByRole("tab", { name: "Plan" }).click();
  await expect(page.getByRole("heading", { name: "Plan v3" })).toBeVisible({ timeout: 30_000 });
  // Units already on sent purchase orders stay committed: the policy change must not re-buy them.
  await expect(page.getByText(/Committed on POs \$3,466\.00 · New spend \$0\.00/)).toBeVisible();
  await page.getByRole("tab", { name: "Audit" }).click();
  await expect(page.getByText(/Hash chain verified/)).toBeVisible({ timeout: 15_000 });
});
