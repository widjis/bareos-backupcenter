import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test("observed alerts acknowledge review and keep recovery separate", async ({
  page,
}) => {
  let ack = false;
  const alert = {
    id: "12345678-1234-1234-1234-123456789abc",
    job_name: "VMware-fixture",
    source_job_id: 42,
    severity: "Error",
    state: "Open",
    revision: 1,
    evidence: {
      id: 42,
      name: "VMware-fixture",
      type: "Backup",
      status: "Failed",
    },
    acknowledged_by: null,
    resolved_by_job_id: null,
  };
  await page.route("**/api/alerts", (route) =>
    route.fulfill({
      json: {
        alerts: [
          {
            ...alert,
            state: ack ? "Acknowledged" : "Open",
            acknowledged_by: ack ? "admin" : null,
          },
        ],
        limit: 100,
        evaluationState: "current",
        syncedAt: "2026-10-14T00:00:00Z",
        scope: "Observed terminal backup sessions only.",
      },
    }),
  );
  await page.route("**/api/alerts/*/ack", (route) => {
    ack = true;
    return route.fulfill({
      json: {
        ...alert,
        state: "Acknowledged",
        revision: 2,
        acknowledged_by: "admin",
      },
    });
  });
  await page.goto("/?view=history");
  const area = page.locator(".alert-journal");
  await expect(
    area.getByRole("button", { name: "Acknowledge", exact: true }),
  ).toBeVisible();
  await area.getByRole("button", { name: "Acknowledge", exact: true }).click();
  await expect(
    area.getByRole("cell", { name: "Acknowledged", exact: true }),
  ).toBeVisible();
  await expect(
    area.getByText("Alert acknowledged. Backup/recovery state is unchanged."),
  ).toBeVisible();
  await area.getByLabel("Alert state").selectOption("Open");
  await expect(area.getByText("No alerts in this state")).toBeVisible();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
});
