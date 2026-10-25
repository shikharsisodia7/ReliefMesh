import { expect, test, type BrowserContext, type Page } from "@playwright/test";

async function registerSupplier(context: BrowserContext, email: string, inviteUrl: string, unitPrice: string, legalName: string): Promise<Page> {
  const page = await context.newPage();
  await page.goto("/sign-up?role=supplier");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct horse battery staple");
  await page.getByRole("button", { name: "Create supplier account" }).click();
  await expect(page).toHaveURL(/\/supplier/);
  await page.goto(inviteUrl);
  await page.getByRole("button", { name: "Accept RFQ" }).click();
  await page.getByLabel("Legal business name").fill(legalName);
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

test("coordinator and two suppliers complete quote, screening, disruption recovery, approval, PO acceptance, and fulfillment", async ({ browser }) => {
  test.setTimeout(120_000);
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

  // Coordinator B joins through a single-use invite link and becomes the independent approver.
  // Members live in Settings, reached from the avatar menu.
  const approverEmail = `approver-${runId}@e2e.example.com`;
  await coordinator.getByRole("button", { name: "Account menu" }).click();
  await coordinator.getByRole("menuitem", { name: "Settings" }).click();
  await coordinator.getByRole("tab", { name: "Members" }).click();
  await coordinator.getByLabel("Member email").fill(approverEmail);
  await coordinator.getByRole("button", { name: "Add member" }).click();
  const inviteText = await coordinator.getByText(/Invite link/).textContent();
  const joinUrl = inviteText?.match(/https?:\/\/\S+/)?.[0];
  expect(joinUrl).toBeTruthy();
  const approverContext = await browser.newContext();
  const approver = await approverContext.newPage();
  await approver.goto("/sign-up");
  await approver.getByLabel("Email").fill(approverEmail);
  await approver.getByLabel("Password").fill("correct horse battery staple");
  await approver.getByRole("button", { name: "Create coordinator account" }).click();
  await expect(approver).toHaveURL(/\/dashboard/);
  await approver.goto(joinUrl!);
  await approver.getByRole("button", { name: "Accept invitation" }).click();
  await expect(approver).toHaveURL(/\/dashboard/);
  await coordinator.getByRole("link", { name: "Missions" }).click();
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
  const supplierOne = await registerSupplier(await browser.newContext(), supplierOneEmail, firstInvite, "7", "Northwind Blanket Company");
  const supplierTwo = await registerSupplier(await browser.newContext(), supplierTwoEmail, secondInvite, "9", "Harbor Textile Supply");

  // Live OFAC screening must finish before either quote is eligible.
  await expect(coordinator.getByText(/OFAC NO_MATCH/)).toHaveCount(2, { timeout: 45_000 });
  await coordinator.getByRole("tab", { name: "Plan" }).click();
  await coordinator.getByRole("button", { name: "Run optimization" }).click();
  await expect(coordinator.getByRole("heading", { name: "Plan v1" })).toBeVisible();
  await expect(coordinator.getByTestId("plan-total")).toHaveText("$80");
  // Segregation of duties: the requester has no approve control; Coordinator B approves.
  await expect(coordinator.getByText(/another approver in your organization must approve/).first()).toBeVisible();
  await expect(coordinator.getByRole("button", { name: "Approve plan" })).toHaveCount(0);
  await approver.goto(coordinator.url());
  await expect(approver.getByRole("heading", { name: "Plan v1" })).toBeVisible();
  await approver.getByRole("button", { name: "Approve plan" }).click();
  await expect(approver.getByText("Approved", { exact: true }).first()).toBeVisible();

  await supplierOne.getByRole("button", { name: "Withdraw quote" }).click();
  await expect(supplierOne.getByText("withdrawn", { exact: true })).toBeVisible();
  await expect(coordinator.getByRole("heading", { name: "Plan v2" })).toBeVisible({ timeout: 20_000 });
  await expect(coordinator.getByTestId("plan-total")).toHaveText("$90");
  await expect(coordinator.getByText(/Approval revoked/).first()).toBeVisible();
  await expect(approver.getByRole("heading", { name: "Plan v2" })).toBeVisible({ timeout: 20_000 });
  await approver.getByRole("button", { name: "Approve plan" }).click();
  await expect(approver.getByText("Approved", { exact: true }).first()).toBeVisible();
  await coordinator.getByRole("button", { name: "Generate POs" }).click();
  await coordinator.getByRole("tab", { name: "Orders" }).click();
  await expect(coordinator.getByRole("button", { name: "Confirm & send" })).toBeVisible();
  await coordinator.getByRole("button", { name: "Confirm & send" }).click();
  await expect(coordinator.getByText("sent", { exact: true })).toBeVisible();

  await supplierTwo.reload();
  await expect(supplierTwo.getByRole("button", { name: "Accept" })).toBeVisible();
  await supplierTwo.getByRole("button", { name: "Accept" }).click();
  await expect(supplierTwo.getByText("supplier_accepted", { exact: true })).toBeVisible();
  await supplierTwo.getByRole("button", { name: "Mark delivered" }).click();
  await expect(supplierTwo.getByText("completed", { exact: true })).toBeVisible();
  await coordinator.getByRole("tab", { name: "Audit" }).click();
  await expect(coordinator.getByText(/hash chain verified/)).toBeVisible({ timeout: 15_000 });
});
