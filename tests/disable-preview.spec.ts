import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const job = {
  name: "VMware-PNET",
  type: "Backup",
  client: "bareos-fd",
  fileset: "PNET.fileset",
  schedule: "BC-Policy-PNET",
  storage: ["PNET-Repo"],
  pool: "PNET",
  enabled: true,
  level: "Incremental",
  latest: null,
};

async function routeJobs(page: Page, enabled = true) {
  await page.route("**/api/snapshot*", (route) =>
    route.fulfill({
      json: {
        director: { name: "test-director", version: "25.1.1" },
        connection: "connected",
        syncedAt: "2026-10-16T12:00:00Z",
        sourceErrors: {},
        jobs: [{ ...job, enabled }],
        workloads: [],
        sessions: [],
        storages: [],
        pools: [],
        volumes: [],
        schedules: [],
        persistence: { state: "connected" },
        capabilities: {
          controls: true,
          operationJobs: ["VMware-PNET"],
          readOnly: false,
        },
        sessionTotal: 0,
        sessionLimit: 200,
      },
    }),
  );
  await page.route("**/api/operations", (route) =>
    route.fulfill({ json: { operations: [], limit: 100 } }),
  );
}

test("disable lifecycle review shows retry, blockers, and mobile-safe preserved-backup copy", async ({
  page,
}) => {
  await routeJobs(page, true);
  let calls = 0;
  await page.route("**/api/jobs/lifecycle/disable/review", async (route) => {
    calls += 1;
    expect(route.request().postDataJSON()).toEqual({ jobName: "VMware-PNET" });
    if (calls === 1) {
      return route.fulfill({
        status: 503,
        json: {
          detail: "Review unavailable. Retry to fetch current evidence.",
        },
      });
    }
    return route.fulfill({
      json: {
        jobName: "VMware-PNET",
        action: "disable",
        readiness: "blocked",
        reviewDigest: "a".repeat(64),
        proofRevision: 17,
        executionSupported: false,
        summary:
          "Disable remains blocked until current dependency and retained recovery proof is complete.",
        blockers: [
          {
            code: "missing_retained_recovery",
            summary:
              "Retained recovery proof is incomplete for this managed job.",
          },
        ],
        impacts: [
          {
            code: "backup_data_kept",
            severity: "info",
            summary:
              "Existing backups stay available and this action does not delete backup data.",
          },
        ],
      },
    });
  });

  await page.goto("/?view=jobs&q=VMware-PNET");
  const trigger = page.getByRole("button", {
    name: "Disable VMware-PNET",
    exact: true,
  });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Review disable schedule" });
  await expect(
    dialog.getByRole("button", { name: "Close", exact: true }),
  ).toBeFocused();
  await expect(dialog.getByRole("alert")).toContainText(
    "Retry to fetch current evidence",
  );
  await dialog.getByRole("button", { name: "Refresh review" }).click();
  await expect(dialog).toContainText(
    "Retained recovery proof is incomplete for this managed job.",
  );
  await expect(dialog).toContainText(
    "Existing backups stay available and this action does not delete backup data.",
  );
  expect(
    (await new AxeBuilder({ page }).include("dialog[open]").analyze())
      .violations,
  ).toEqual([]);
  await page.setViewportSize({ width: 390, height: 740 });
  await expect(
    dialog.getByRole("button", { name: "Close", exact: true }),
  ).toBeInViewport();
  expect(
    await dialog.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
  ).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  expect(calls).toBe(2);
});

test("enable lifecycle keeps idempotency state and reconciles status without resubmitting", async ({
  page,
}) => {
  await routeJobs(page, false);
  let applyCalls = 0;
  let requestKey = "";
  await page.route("**/api/jobs/lifecycle/enable/review", async (route) => {
    expect(route.request().postDataJSON()).toEqual({ jobName: "VMware-PNET" });
    await route.fulfill({
      json: {
        jobName: "VMware-PNET",
        action: "enable",
        readiness: "candidate_ready",
        reviewDigest: "b".repeat(64),
        proofRevision: 24,
        executionSupported: true,
        summary:
          "Enable restores the reviewed automatic schedule for VMware-PNET.",
        blockers: [],
        impacts: [
          {
            code: "schedule_restored",
            severity: "warning",
            summary:
              "The previously reviewed schedule becomes active again for VMware-PNET.",
          },
        ],
      },
    });
  });
  await page.route("**/api/jobs/lifecycle/enable", async (route) => {
    applyCalls += 1;
    const body = route.request().postDataJSON();
    requestKey = body.idempotencyKey;
    expect(body).toMatchObject({
      jobName: "VMware-PNET",
      reviewDigest: "b".repeat(64),
      proofRevision: 24,
      confirmed: true,
    });
    expect(typeof body.idempotencyKey).toBe("string");
    await route.fulfill({
      status: 202,
      json: {
        id: "11111111-1111-1111-1111-111111111111",
        state: "Unknown",
        kind: "lifecycle_enable",
        target: "VMware-PNET",
        parameters: {
          message:
            "Delivery outcome is unknown. Check application status before another request.",
        },
      },
    });
  });
  await page.route("**/api/jobs/lifecycle/status/*", async (route) => {
    await route.fulfill({
      json: {
        id: "11111111-1111-1111-1111-111111111111",
        state: "Completed",
        kind: "lifecycle_enable",
        target: "VMware-PNET",
        parameters: {
          summary: "Enable completed after durable reconciliation.",
        },
      },
    });
  });

  await page.goto("/?view=jobs&q=VMware-PNET");
  await page
    .getByRole("button", { name: "Enable VMware-PNET", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "Review enable schedule" });
  await expect(dialog).toContainText("Candidate ready");
  await dialog.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(dialog).toContainText("Request key:");
  await dialog
    .getByRole("button", { name: "Enable schedule", exact: true })
    .click();
  await expect(dialog).toContainText(
    "Delivery outcome is unknown. Check application status before another request.",
  );
  await expect(dialog).toContainText(requestKey);
  await dialog.getByRole("button", { name: "Close", exact: true }).click();
  await page
    .getByRole("button", { name: "Enable VMware-PNET", exact: true })
    .click();
  await expect(dialog).toContainText(requestKey);
  await expect(dialog).toContainText("Unknown");
  await expect(
    dialog.getByRole("button", { name: "Enable schedule", exact: true }),
  ).toHaveCount(0);
  await dialog
    .getByRole("button", { name: "Check application status", exact: true })
    .click();
  await expect(dialog).toContainText(
    "Enable completed after durable reconciliation.",
  );
  expect(applyCalls).toBe(1);
});

test("closing a pending lifecycle review aborts it and restores focus", async ({
  page,
}) => {
  await routeJobs(page, true);
  await page.route("**/api/jobs/lifecycle/disable/review", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    await route
      .fulfill({
        status: 503,
        json: { detail: "Review unavailable." },
      })
      .catch(() => {});
  });

  await page.goto("/?view=jobs&q=VMware-PNET");
  const trigger = page.getByRole("button", {
    name: "Disable VMware-PNET",
    exact: true,
  });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Review disable schedule" });
  await expect(
    dialog.getByText("Checking current lifecycle evidence"),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "Close", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
});
