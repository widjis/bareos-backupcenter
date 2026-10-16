import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("live data, navigation, filtering, session details, accessibility and mobile", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("Connected", { exact: true })).toBeVisible({
    timeout: 45000,
  });
  await expect(
    page.getByText("MTIMRWZTNA01", { exact: true }).first(),
  ).toBeVisible();
  await page.screenshot({
    path: ".local/overview-desktop.png",
    fullPage: true,
  });
  const a11y = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(a11y.violations).toEqual([]);
  await page.getByRole("link", { name: "Jobs", exact: false }).click();
  await page
    .getByRole("textbox", { name: "Search this view" })
    .fill("NO-SUCH-JOB");
  await expect(page.getByText("No matching jobs")).toBeVisible();
  await page.getByRole("button", { name: "Clear search" }).click();
  await expect(
    page.getByRole("textbox", { name: "Search this view" }),
  ).toBeFocused();
  const jobHeader = page.getByRole("columnheader", {
    name: "Job",
    exact: true,
  });
  await jobHeader.getByRole("button").click();
  await expect(jobHeader).toHaveAttribute("aria-sort", "ascending");
  await jobHeader.getByRole("button").click();
  await expect(jobHeader).toHaveAttribute("aria-sort", "descending");
  await page.screenshot({ path: ".local/jobs-desktop.png", fullPage: true });
  await page.getByRole("link", { name: "History", exact: true }).click();
  const link = page.getByRole("button", { name: /^VMware-/ }).first();
  await link.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByText("Loading session log…")).not.toBeVisible({
    timeout: 30000,
  });
  await expect(page.locator(".log-view pre").first()).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(link).toBeFocused();
  await page.getByRole("link", { name: "Infrastructure", exact: true }).click();
  await expect(page.getByText(/\d+ configured VMware workloads/)).toBeVisible();
  await page.getByRole("link", { name: "Backups", exact: true }).click();
  await expect(
    page.getByText("VMs are derived from configured FileSets.", {
      exact: false,
    }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: ".local/overview-mobile.png", fullPage: true });
});

test("failed first load has a concrete retry path", async ({ page }) => {
  await page.route("**/api/snapshot*", (r) =>
    r.fulfill({ status: 502, json: { detail: "Unavailable" } }),
  );
  await page.goto("/");
  await expect(page.getByText("Unable to load Bareos data")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Refresh", exact: true }),
  ).toBeEnabled();
});

test("empty snapshot, URL search restoration, reduced motion, and stale refresh", async ({
  page,
}) => {
  const snapshot = {
    director: { name: "test", version: "test" },
    connection: "connected",
    syncedAt: "2026-10-14T09:00:00Z",
    sourceErrors: {},
    jobs: [],
    workloads: [],
    sessions: [],
    storages: [],
    pools: [],
    volumes: [],
    schedules: [],
    sessionTotal: 0,
    sessionLimit: 200,
  };
  let fail = false;
  await page.route("**/api/snapshot*", (r) =>
    r.fulfill(
      fail
        ? { status: 502, json: { detail: "Unavailable" } }
        : { json: snapshot },
    ),
  );
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/?view=jobs&q=missing");
  await expect(
    page.getByRole("textbox", { name: "Search this view" }),
  ).toHaveValue("missing");
  await expect(page.getByText("No matching jobs")).toBeVisible();
  fail = true;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByText("Stale", { exact: true })).toBeVisible();
  await expect(page.getByText("No matching jobs")).toBeVisible();
});

test("Settings shows live PostgreSQL persistence and collector audit", async ({
  page,
}) => {
  await page.goto("/?view=settings");
  const database = page.locator("section.panel").filter({
    has: page.getByRole("heading", {
      name: "Application database",
      exact: true,
    }),
  });
  await expect(database.getByText("Connected", { exact: true })).toBeVisible({
    timeout: 45000,
  });
  await expect(
    database.getByText("backupcenter", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("navigation", { name: "Settings navigation" })
    .getByRole("link", { name: "Audit", exact: true })
    .click();
  await expect(
    page.getByText("snapshot.persisted", { exact: true }).first(),
  ).toBeVisible({ timeout: 20000 });
  const scan = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(scan.violations).toEqual([]);
  await page.screenshot({
    path: ".local/settings-persistence.png",
    fullPage: true,
  });
});
