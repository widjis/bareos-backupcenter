import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test("explicit VMware selection produces a disabled, secret-free configuration preview", async ({
  page,
}) => {
  await page.goto("/?view=infrastructure");
  const area = page.locator(".inventory-section");
  await expect(
    area.getByText("Inventory connected", { exact: false }),
  ).toBeVisible({ timeout: 45000 });
  await area.getByRole("checkbox").first().check();
  const trigger = area.getByRole("button", {
    name: "Preview onboarding",
    exact: true,
  });
  await trigger.click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("heading", { name: "Onboarding preview" }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "Generate preview" }).click();
  await expect(
    dialog.getByRole("heading", { name: "Configuration review" }),
  ).toBeVisible({ timeout: 45000 });
  await expect(dialog.locator("pre")).toContainText("Enabled = no");
  await expect(dialog.locator("pre")).not.toContainText("vcpass=");
  await expect(
    dialog.getByRole("button", { name: "Stage dry-run apply" }),
  ).toBeEnabled();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.screenshot({
    path: ".local/onboarding-preview.png",
    fullPage: true,
  });
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
});

test("approved VM review exposes live apply while submission remains explicitly confirmed", async ({
  page,
}) => {
  const uid = "5208e076-eb89-9f06-2ef2-790ac92b4d71";
  await page.route("**/api/snapshot*", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.capabilities = { ...data.capabilities, onboardingUuids: [uid] };
    await route.fulfill({ json: data });
  });
  await page.route("**/api/inventory?*", (route) =>
    route.fulfill({
      json: {
        state: "connected",
        error: null,
        syncedAt: new Date().toISOString(),
        folders: [],
        vms: [
          {
            id: "11111111-1111-1111-1111-111111111111",
            name: "PNET",
            moref: "vm-29087",
            instanceUuid: uid,
            folder: "/Discovered virtual machine",
            datacenter: "DC",
            power: "poweredOn",
            host: "test-host",
            cluster: null,
            cpu: 2,
            memoryMb: 4096,
            template: false,
            association: "Unassigned",
            job: null,
            backupEvidence: "Unknown",
          },
        ],
        total: 1,
        totalVisible: 1,
        page: 1,
        pages: 1,
        pageSize: 25,
        persistence: "connected",
        scope: "Synthetic test inventory",
      },
    }),
  );
  await page.route("**/api/provisioning/preview", (route) =>
    route.fulfill({
      json: {
        mode: "live",
        applyEnabled: true,
        changes: [
          {
            inventoryId: "11111111-1111-1111-1111-111111111111",
            name: "PNET",
            job: "VMware-PNET",
            fileset: "VMware-PNET",
            pool: "PNET",
            storage: "SMB-PNET",
            configuration: "FileSet { Name = VMware-PNET }",
          },
        ],
        blockers: ["Power state preserved. First backup is separate."],
        sharedImpact: "Dedicated PNET folder",
        scriptReview: {
          required: true,
          baselineCount: 6,
          message: "Extend reviewed mappings",
          additions: [],
        },
        policy: {
          name: "Fixed policy",
          retentionDays: 30,
          maximumVolumes: 6,
          schedule: "21:30 UTC+8",
        },
      },
    }),
  );
  let sends = 0;
  await page.route("**/api/provisioning/apply", (route) => {
    sends++;
    return route.fulfill({
      status: 202,
      json: {
        id: "00000000-0000-4000-8000-000000000999",
        idempotency_key: "00000000-0000-4000-8000-000000000998",
        kind: "provision",
        target: "fixture",
        state: "Prepared",
        job_id: null,
        parameters: { simulationOnly: false, message: "Fixture only" },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    });
  });
  await page.goto("/?view=infrastructure");
  await page
    .getByRole("checkbox", { name: "Select PNET vm-29087", exact: true })
    .check();
  await page
    .getByRole("button", { name: "Live Add to backup", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Generate preview", exact: true })
    .click();
  const apply = page.getByRole("button", {
    name: "Enable backup for PNET",
    exact: true,
  });
  await expect(apply).toBeEnabled();
  expect(sends).toBe(0);
  await expect(
    page.getByText("Dedicated PNET folder", { exact: true }),
  ).toBeVisible();
  await apply.click();
  await expect(
    page.getByRole("dialog", { name: "Onboarding preview" }),
  ).not.toBeVisible();
  expect(sends).toBe(1);
});
