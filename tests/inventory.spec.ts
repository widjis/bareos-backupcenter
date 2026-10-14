import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("live VMware inventory shows stable identities, paging and accessible selection", async ({
  page,
}) => {
  await page.goto("/?view=infrastructure");
  await expect(
    page.getByText("Inventory connected", { exact: false }),
  ).toBeVisible({ timeout: 45000 });
  await expect(
    page.getByRole("heading", { name: "VMware inventory" }),
  ).toBeVisible();
  const area = page.locator(".inventory-section");
  await expect(
    area.getByRole("button", { name: "Next page", exact: true }),
  ).toBeEnabled();
  const first = area.getByRole("checkbox").first();
  await first.check();
  await expect(area.getByText("1 VM selected", { exact: true })).toBeVisible();
  await area.getByRole("button", { name: "Next page", exact: true }).click();
  await expect(area.getByText("Page 2 of 2")).toBeVisible();
  await expect(area.getByText("1 VM selected", { exact: true })).toBeVisible();
  await area
    .getByRole("textbox", { name: "Search VMware inventory" })
    .fill("NO-SUCH-VM");
  await expect(area.getByText("No matching virtual machines")).toBeVisible();
  await expect(page).toHaveURL(/invq=NO-SUCH-VM/);
  await area.getByRole("button", { name: "Clear search" }).click();
  await expect(
    area.getByRole("textbox", { name: "Search VMware inventory" }),
  ).toBeFocused();
  await area.getByRole("button", { name: "Clear selection" }).click();
  await expect(area.getByText("0 VMs selected", { exact: true })).toBeVisible();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.screenshot({
    path: ".local/inventory-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("heading", { name: "VMware inventory" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: ".local/inventory-mobile.png",
    fullPage: true,
  });
});

test("inventory errors preserve cached evidence and disable selection", async ({
  page,
}) => {
  let mode = "stale";
  await page.route("**/api/inventory*", (route) =>
    route.fulfill({
      json: {
        state: mode,
        error:
          mode === "stale"
            ? "VMware authentication failed."
            : "VMware certificate fingerprint mismatch.",
        syncedAt: mode === "stale" ? "2026-10-14T00:00:00Z" : null,
        folders: [],
        vms:
          mode === "stale"
            ? [
                {
                  id: "one",
                  name: "Duplicate",
                  moref: "vm-1",
                  instanceUuid: "one",
                  folder: "/",
                  datacenter: "DC",
                  power: "unknown",
                  host: null,
                  cpu: null,
                  memoryMb: null,
                  association: "Unassigned",
                  job: null,
                },
              ]
            : [],
        total: mode === "stale" ? 1 : 0,
        totalVisible: mode === "stale" ? 1 : 0,
        page: 1,
        pages: 1,
        pageSize: 25,
      },
    }),
  );
  await page.goto("/?view=infrastructure");
  const area = page.locator(".inventory-section");
  await expect(
    area.getByText("VMware authentication failed.", { exact: false }),
  ).toBeVisible();
  await expect(area.getByRole("checkbox")).toBeDisabled();
  await expect(area.getByText("Duplicate", { exact: true })).toBeVisible();
  mode = "unavailable";
  await area.getByRole("button", { name: "Refresh inventory" }).click();
  await expect(
    area.getByText("VMware inventory unavailable", { exact: true }),
  ).toBeVisible();
  await expect(
    area.getByText("VMware certificate fingerprint mismatch.", {
      exact: false,
    }),
  ).toBeVisible();
});

test("empty inventory and service failure have distinct recovery states", async ({
  page,
}) => {
  let failed = false;
  await page.route("**/api/inventory*", (route) =>
    failed
      ? route.fulfill({ status: 503, json: { detail: "offline" } })
      : route.fulfill({
          json: {
            state: "connected",
            error: null,
            syncedAt: "2026-10-14T00:00:00Z",
            folders: [],
            vms: [],
            total: 0,
            totalVisible: 0,
            page: 1,
            pages: 1,
            pageSize: 25,
          },
        }),
  );
  await page.goto("/?view=infrastructure");
  const area = page.locator(".inventory-section");
  await expect(area.getByText("No visible virtual machines")).toBeVisible();
  failed = true;
  await area.getByRole("button", { name: "Refresh inventory" }).click();
  await expect(
    area.getByText("Inventory service is unavailable. Retry the connection.", {
      exact: false,
    }),
  ).toBeVisible();
});
