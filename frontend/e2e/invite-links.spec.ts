import { expect, test } from "@playwright/test";

// An emailed RFQ link must survive sign-up and must not dead-end when the browser holds another role's session
// (found on production: a coordinator session opening an RFQ link had no way forward).
test("RFQ link opened under a coordinator session switches to a new supplier account and returns to the RFQ", async ({ page }) => {
  const runId = Date.now();
  const password = "correct horse battery staple";
  await page.goto("/sign-up");
  await page.getByLabel("Email").fill(`coordinator-links-${runId}@e2e.example.com`);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create coordinator account" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.getByPlaceholder("Organization name").fill("Link Check Response");
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.getByLabel("Mission name").fill("Link check");
  await page.getByLabel("Delivery location").fill("Oakland, CA");
  await page.getByLabel("Delivery deadline").fill("2030-01-05T10:00");
  await page.getByLabel("Budget (USD)").fill("100");
  await page.getByLabel("Required item").fill("blankets");
  await page.getByLabel("Quantity").fill("10");
  await page.getByRole("button", { name: "Create mission" }).click();
  await expect(page).toHaveURL(/\/missions\//);

  const supplierEmail = `supplier-links-${runId}@e2e.example.com`;
  await page.getByLabel("Supplier email").fill(supplierEmail);
  await page.getByRole("button", { name: "Send RFQ" }).click();
  const inviteUrl = (await page.getByText(/Development invitation:/).textContent())?.match(/https?:\/\/\S+/)?.[0];
  expect(inviteUrl).toBeTruthy();

  await page.goto(inviteUrl!);
  await page.getByRole("button", { name: `Sign out and continue as ${supplierEmail}` }).click();
  await expect(page).toHaveURL(/\/sign-up\?role=supplier&next=/);
  await page.getByLabel("Email").fill(supplierEmail);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create supplier account" }).click();
  await expect(page).toHaveURL(new URL(inviteUrl!).pathname);
  await expect(page.getByRole("button", { name: "Accept RFQ" })).toBeVisible();
});
