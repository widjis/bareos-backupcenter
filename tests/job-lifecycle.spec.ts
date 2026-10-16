import { test, expect, type Page } from "@playwright/test";

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

async function routeJobs(page: Page) {
  await page.route("**/api/snapshot*", (route) =>
    route.fulfill({
      json: {
        director: { name: "test-director", version: "25.1.1" },
        connection: "connected",
        syncedAt: "2026-10-16T12:00:00Z",
        sourceErrors: {},
        jobs: [job],
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

test("clone review requires a name, reports unsupported fields, and resets when edited", async ({
  page,
}) => {
  await routeJobs(page);
  let calls = 0;
  await page.route("**/api/jobs/lifecycle/clone/review", async (route) => {
    calls += 1;
    const body = route.request().postDataJSON();
    expect(body.sourceJobName).toBe("VMware-PNET");
    await route.fulfill({
      json: {
        jobName: "VMware-PNET",
        action: "clone",
        readiness: "review_only",
        reviewDigest: "c".repeat(64),
        proofRevision: 31,
        executionSupported: false,
        summary:
          "Clone review is available, but backend execution remains blocked.",
        blockers: [
          {
            code: "target_repository_missing",
            summary:
              "Verified repository ownership is still missing for clone execution.",
          },
        ],
        impacts: [
          {
            code: "clone_disabled",
            severity: "warning",
            summary:
              "The clone stays disabled until a later confirmed enable action.",
          },
        ],
        unsupportedChanges: [
          "Job identity, VM assignment, and repository changes remain unavailable in this batch.",
        ],
        draftPlan: {
          sourceJobName: "VMware-PNET",
          newJobName: body.newJobName,
          automaticSchedule: false,
        },
      },
    });
  });

  await page.goto("/?view=jobs&q=VMware-PNET");
  await page
    .getByRole("button", { name: "Clone VMware-PNET", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "Review clone draft" });
  await dialog.getByRole("textbox", { name: "New clone job name" }).fill("");
  await dialog
    .getByRole("button", { name: "Review clone", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText(
    "Enter a unique clone job name before review.",
  );
  await dialog
    .getByRole("textbox", { name: "New clone job name" })
    .fill("VMware-PNET Clone A");
  await dialog
    .getByRole("button", { name: "Review clone", exact: true })
    .click();
  await expect(dialog).toContainText(
    "Verified repository ownership is still missing for clone execution.",
  );
  await expect(dialog).toContainText(
    "Job identity, VM assignment, and repository changes remain unavailable in this batch.",
  );
  await dialog
    .getByRole("button", { name: "Edit clone details", exact: true })
    .click();
  await dialog
    .getByRole("textbox", { name: "New clone job name" })
    .fill("VMware-PNET Clone B");
  await expect(
    dialog.getByText("Clone review is available", { exact: false }),
  ).toHaveCount(0);
  expect(calls).toBe(1);
});

test("remove review keeps retained backups explicit and blocks destructive execution when readiness is review-only", async ({
  page,
}) => {
  await routeJobs(page);
  await page.route("**/api/jobs/lifecycle/remove/review", async (route) => {
    expect(route.request().postDataJSON()).toEqual({ jobName: "VMware-PNET" });
    await route.fulfill({
      json: {
        jobName: "VMware-PNET",
        action: "remove",
        readiness: "review_only",
        reviewDigest: "d".repeat(64),
        proofRevision: 52,
        executionSupported: false,
        summary:
          "Configuration removal keeps retained backups discoverable, but live execution is still blocked.",
        blockers: [
          {
            code: "retirement_record_pending",
            summary:
              "The retirement record still needs authoritative verification before removal.",
          },
        ],
        impacts: [
          {
            code: "preserve_backups",
            severity: "warning",
            summary:
              "Backup data is kept and existing recovery chains stay discoverable.",
          },
        ],
        preserveBackupData: true,
        retainedObligations: [
          "Retained recovery points must stay discoverable through a managed retirement record.",
        ],
        retainedRecovery: {
          recoveryPointCount: 2,
          latestJobIds: [23, 24],
        },
      },
    });
  });

  await page.goto("/?view=jobs&q=VMware-PNET");
  await page
    .getByRole("button", { name: "Delete config VMware-PNET", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Review configuration removal",
  });
  await expect(dialog).toContainText(
    "Backup data is kept. This action does not authorize data deletion.",
  );
  await expect(dialog).toContainText(
    "Retained recovery points must stay discoverable through a managed retirement record.",
  );
  await dialog.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(dialog).toContainText(
    "Delete configuration for VMware-PNET. Backup data is kept",
  );
  await expect(
    dialog.getByRole("button", { name: "Delete configuration", exact: true }),
  ).toBeDisabled();
});
