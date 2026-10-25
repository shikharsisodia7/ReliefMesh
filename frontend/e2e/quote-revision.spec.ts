import { expect, test } from "@playwright/test";

// Found on production: the revise form pre-filled the quote expiry with the UTC clock time as if it were local,
// so saving a price change silently moved the expiry by the viewer's UTC offset (7 h in California).
test.use({ timezoneId: "America/Los_Angeles" });

test("revising a quote keeps its expiry in the supplier's local time", async ({ browser }) => {
  const runId = Date.now();
  const password = "correct horse battery staple";
  const coordinator = await (await browser.newContext()).newPage();
  await coordinator.goto("/sign-up");
  await coordinator.getByLabel("Email").fill(`coordinator-revise-${runId}@e2e.example.com`);
  await coordinator.getByLabel("Password").fill(password);
  await coordinator.getByRole("button", { name: "Create coordinator account" }).click();
  await expect(coordinator).toHaveURL(/\/dashboard/);
  await coordinator.getByPlaceholder("Organization name").fill("Revision Check Response");
  await coordinator.getByRole("button", { name: "Create organization" }).click();
  await coordinator.getByLabel("Mission name").fill("Revision check");
  await coordinator.getByLabel("Delivery location").fill("Ukiah, CA");
  await coordinator.getByLabel("Delivery deadline").fill("2030-01-05T10:00");
  await coordinator.getByLabel("Budget (USD)").fill("5000");
  await coordinator.getByLabel("Required item").fill("blankets");
  await coordinator.getByLabel("Quantity").fill("10");
  await coordinator.getByRole("button", { name: "Create mission" }).click();
  await expect(coordinator).toHaveURL(/\/missions\//);
  const supplierEmail = `supplier-revise-${runId}@e2e.example.com`;
  // Send RFQ opens a dialog with the supplier email.
  await coordinator.getByRole("button", { name: "Send RFQ" }).click();
  await coordinator.getByLabel("Supplier email").fill(supplierEmail);
  await coordinator.getByRole("dialog", { name: "Send RFQ" }).getByRole("button", { name: "Send RFQ" }).click();
  const inviteUrl = (await coordinator.getByText(/Development invitation:/).textContent())?.match(/https?:\/\/\S+/)?.[0];
  expect(inviteUrl).toBeTruthy();

  const supplier = await (await browser.newContext({ timezoneId: "America/Los_Angeles" })).newPage();
  await supplier.goto(`/sign-up?role=supplier&next=${encodeURIComponent(new URL(inviteUrl!).pathname)}`);
  await supplier.getByLabel("Email").fill(supplierEmail);
  await supplier.getByLabel("Password").fill(password);
  await supplier.getByRole("button", { name: "Create supplier account" }).click();
  await supplier.getByRole("button", { name: "Accept RFQ" }).click();
  await supplier.getByLabel("Legal business name").fill("Revision Check Textiles");
  await supplier.getByLabel("Item").fill("blankets");
  await supplier.getByLabel("Available quantity").fill("10");
  await supplier.getByLabel("Unit price (USD)").fill("32");
  await supplier.getByLabel("Shipping (USD)").fill("0");
  await supplier.getByLabel("Delivery estimate").fill("2030-01-03T09:00");
  await supplier.getByLabel("Quote expiration").fill("2030-01-02T23:00");
  await supplier.getByRole("button", { name: "Submit binding quote" }).click();
  await expect(supplier).toHaveURL(/\/supplier/);
  await supplier.getByText("Revise price or inventory").click();
  await expect(supplier.locator("details").getByLabel("Quote expiration")).toHaveValue("2030-01-02T23:00");
});
