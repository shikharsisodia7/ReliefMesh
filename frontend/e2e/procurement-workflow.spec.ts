import { expect, test, type BrowserContext, type Page } from "@playwright/test";

async function registerSupplier(context: BrowserContext, email: string, inviteUrl: string, unitPrice: string): Promise<Page> {
  const page = await context.newPage();
  await page.goto("/sign-up?role=supplier");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct horse battery staple");
  await page.getByRole("button", { name: "Create supplier account" }).click();
  await expect(page).toHaveURL(/\/supplier/);
  await page.goto(inviteUrl);
  await page.getByRole("button", { name: "Accept RFQ" }).click();
  await page.getByLabel("Item").fill("blankets");
  await page.getByLabel("Available quantity").fill("10");
  await page.getByLabel("Unit price (USD)").fill(unitPrice);
  await page.getByLabel("Shipping (USD)").fill(unitPrice === "7" ? "10" : "0");
  await page.getByLabel("Delivery estimate").fill("2030-01-03T09:00");
  await page.getByLabel("Quote expiration").fill("2030-01-02T09:00");
  await page.getByRole("button", { name: "Submit binding quote" }).click();
  await expect(page).toHaveURL(/\/supplier/);
  return page;
}

test("coordinator and two suppliers complete quote, disruption recovery, approval, and PO acceptance", async ({ browser }) => {
  const runId = Date.now();
  const coordinatorEmail = `coordinator-${runId}@e2e.example.com`;
  const supplierOneEmail = `first-supplier-${runId}@e2e.example.com`;
  const supplierTwoEmail = `second-supplier-${runId}@e2e.example.com`;
  const coordinatorContext = await browser.newContext();
  const coordinator = await coordinatorContext.newPage();
  await coordinator.goto("/sign-up");
  await coordinator.getByLabel("Email").fill(coordinatorEmail);
  await coordinator.getByLabel("Password").fill("correct horse battery staple");
  await coordinator.getByRole("button", { name: "Create coordinator account" }).click();
  await expect(coordinator).toHaveURL(/\/dashboard/);

  await coordinator.getByPlaceholder("Organization name").fill("Harbor Response");
  await coordinator.getByRole("button", { name: "Create organization" }).click();
  await coordinator.getByLabel("Mission name").fill("Winter response");
  await coordinator.getByLabel("Delivery location").fill("Oakland, CA");
  await coordinator.getByLabel("Delivery deadline").fill("2030-01-05T10:00");
  await coordinator.getByLabel("Budget (USD)").fill("100");
  await coordinator.getByLabel("Required item").fill("blankets");
  await coordinator.getByLabel("Quantity").fill("10");
  await coordinator.getByRole("button", { name: "Create mission" }).click();
  await expect(coordinator).toHaveURL(/\/missions\//);

  const invite = async (email: string) => {
    await coordinator.getByLabel("Supplier email").fill(email);
    await coordinator.getByRole("button", { name: "Send RFQ" }).click();
    const text = await coordinator.getByText(/Development invitation:/).textContent();
    const url = text?.match(/https?:\/\/\S+/)?.[0];
    expect(url).toBeTruthy();
    return url!;
  };
  const firstInvite = await invite(supplierOneEmail);
  const secondInvite = await invite(supplierTwoEmail);
  const supplierOne = await registerSupplier(await browser.newContext(), supplierOneEmail, firstInvite, "7");
  const supplierTwo = await registerSupplier(await browser.newContext(), supplierTwoEmail, secondInvite, "9");

  await coordinator.getByRole("button", { name: "Run optimization" }).click();
  await expect(coordinator.getByText("Plan v1")).toBeVisible();
  await expect(coordinator.getByText(/Total \$80\.00/)).toBeVisible();
  await coordinator.getByRole("button", { name: "Approve plan" }).click();
  await expect(coordinator.getByText("approved").first()).toBeVisible();

  await supplierOne.getByRole("button", { name: "Withdraw quote" }).click();
  await expect(supplierOne.getByText("withdrawn")).toBeVisible();
  await expect(coordinator.getByText("Plan v2")).toBeVisible({ timeout: 15_000 });
  await expect(coordinator.getByText(/Total \$90\.00/)).toBeVisible();
  await coordinator.getByRole("button", { name: "Approve plan" }).click();
  await coordinator.getByRole("button", { name: "Generate POs" }).click();
  await expect(coordinator.getByRole("button", { name: "Confirm & send" })).toBeVisible();
  await coordinator.getByRole("button", { name: "Confirm & send" }).click();
  await expect(coordinator.getByText("sent").last()).toBeVisible();

  await supplierTwo.reload();
  await expect(supplierTwo.getByRole("button", { name: "Accept" })).toBeVisible();
  await supplierTwo.getByRole("button", { name: "Accept" }).click();
  await expect(supplierTwo.getByText("supplier_accepted")).toBeVisible();
});
