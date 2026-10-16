import { test, expect } from "@playwright/test";
const row = {
  job: "VMware-PNET",
  timeWita: "21:30",
  automatic: true,
  retentionDays: 30,
  maximumVolumes: 6,
};
for (const initiallyEnabled of [false, true])
  test(`local-only review cannot Apply (initial enabled ${initiallyEnabled})`, async ({
    page,
  }) => {
    let writes = 0;
    await page.route("**/api/policies/active", (r) =>
      r.fulfill({
        json: {
          jobs: [row],
          applyEnabled: initiallyEnabled,
          liveApplyBlocker: initiallyEnabled
            ? null
            : "Helper upgrade required before live Apply.",
        },
      }),
    );
    await page.route("**/api/policies/active/preview", (r) =>
      r.fulfill({
        json: {
          definition: r.request().postDataJSON().definition,
          reviewDigest: "a".repeat(64),
          applyEnabled: false,
          targetVerified: false,
          verification: "Local preview only",
          liveApplyBlocker: "Helper upgrade required before live Apply.",
          existingVolumePolicy: "Complete chains retained.",
          doesNotRun: "No backup or cleanup runs.",
        },
      }),
    );
    await page.route("**/api/policies/active/apply", (r) => {
      writes++;
      return r.fulfill({
        status: 500,
        json: { detail: "Unexpected mutation" },
      });
    });
    await page.goto("/?view=settings&section=policies");
    const panel = page.getByRole("region", {
      name: "Active backup schedule and retention",
    });
    await panel.getByLabel("VMware-PNET", { exact: true }).check();
    await panel
      .getByRole("button", { name: "Review active policy", exact: true })
      .click();
    await expect(
      panel.getByRole("heading", { name: "Reviewed policy" }),
    ).toBeVisible();
    await expect(
      panel.getByRole("button", { name: "Apply reviewed policy", exact: true }),
    ).toBeDisabled();
    await expect(panel).toContainText(
      "Helper upgrade required before live Apply.",
    );
    expect(writes).toBe(0);
  });
