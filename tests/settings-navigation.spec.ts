import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test("Settings separates subpages, supports direct links and narrow keyboard navigation", async ({
  page,
}) => {
  await page.goto("/?view=settings");
  const nav = page.getByRole("navigation", { name: "Settings navigation" });
  await expect(
    page.getByRole("heading", { name: "Application database", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Application accounts", exact: true }),
  ).toHaveCount(0);
  for (const [name, heading] of [
    ["Users", "Application accounts"],
    ["Permissions", "Permissions and capabilities"],
    ["Notifications", "Notifications"],
    ["Audit", "Collector audit history"],
    ["Connections", "Connection"],
  ]) {
    await nav.getByRole("link", { name, exact: true }).click();
    await expect(nav.getByRole("link", { name, exact: true })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await expect(
      page.getByRole("heading", { name: heading, exact: true }),
    ).toBeVisible();
  }
  await nav.getByRole("link", { name: "Notifications", exact: true }).click();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Notifications", exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await nav.getByRole("link", { name: "Users", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Application accounts", exact: true }),
  ).toBeVisible();
  await expect(page).toHaveURL(/section=users/);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.screenshot({
    path: ".local/settings-submenu-mobile.png",
    fullPage: true,
  });
});
test("changing settings subpages protects an unsaved policy", async ({
  page,
}) => {
  await page.route("**/api/policies/active", (route) =>
    route.fulfill({
      json: {
        jobs: [
          {
            job: "VMware-PNET",
            timeWita: "21:30",
            automatic: true,
            retentionDays: 30,
            maximumVolumes: 6,
          },
        ],
        applyEnabled: true,
      },
    }),
  );
  await page.goto("/?view=settings&section=policies");
  await page.getByLabel("Backup start (WITA)").fill("22:00");
  await page
    .getByRole("navigation", { name: "Settings navigation" })
    .getByRole("link", { name: "Connections", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "Discard unsaved changes?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Go back", exact: true }).click();
  await expect(page.getByLabel("Backup start (WITA)")).toHaveValue("22:00");
  await page
    .getByRole("navigation", { name: "Settings navigation" })
    .getByRole("link", { name: "Connections", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Discard changes", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Application database", exact: true }),
  ).toBeVisible();
});
