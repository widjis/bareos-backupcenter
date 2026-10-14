import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test("draft policy validates, saves synthetically, and preserves edits on revision conflict", async ({
  page,
}) => {
  let policy: Record<string, unknown> | null = null,
    conflict = false;
  await page.route("**/api/policies", async (route) => {
    if (route.request().method() === "POST") {
      if (conflict)
        return route.fulfill({
          status: 409,
          json: {
            detail: "Policy revision changed. Reload the current policy.",
          },
        });
      const body = route.request().postDataJSON();
      policy = {
        id: "12345678-1234-1234-1234-123456789abc",
        name: body.name,
        owner: "admin",
        revision: 1,
        state: "Draft",
        definition: {
          storage: body.storage,
          freshness_hours: body.freshness_hours,
          retention_days: body.retention_days,
          maximum_volumes: body.maximum_volumes,
          schedule: body.schedule,
          time_wita: body.time_wita,
        },
      };
      return route.fulfill({ json: policy });
    }
    return route.fulfill({
      json: { policies: policy ? [policy] : [], limit: 100 },
    });
  });
  await page.goto("/?view=settings");
  const area = page.locator(".policy-settings");
  await area.getByRole("button", { name: "Save draft policy" }).click();
  await expect(area.getByLabel("Policy name")).toBeFocused();
  await area.getByLabel("Policy name").fill("Daily VM draft");
  await area.getByLabel("Backup freshness target (hours)").fill("24");
  await area.getByLabel("Schedule proposal").selectOption("Daily");
  await area.getByRole("button", { name: "Save draft policy" }).click();
  await expect(
    area.getByText("Draft policy saved. No Bareos configuration changed."),
  ).toBeVisible();
  await expect(
    area.getByRole("heading", { name: "Edit Daily VM draft · revision 1" }),
  ).toBeVisible();
  conflict = true;
  await area.getByLabel("Backup freshness target (hours)").fill("48");
  await area.getByRole("button", { name: "Save draft policy" }).click();
  await expect(
    area.getByText("Policy revision changed. Reload the current policy."),
  ).toBeVisible();
  await expect(area.getByLabel("Backup freshness target (hours)")).toHaveValue(
    "48",
  );
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.getByRole("link", { name: "Jobs", exact: false }).click();
  const dialog = page.getByRole("dialog", { name: "Discard unsaved changes?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Discard changes" }).click();
  await expect(
    page.getByRole("heading", { name: "Jobs", exact: true }),
  ).toBeVisible();
});
