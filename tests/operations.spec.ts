import { test, expect, Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const session = {
  id: 42,
  name: "VMware-safe",
  client: "proxy",
  type: "Backup",
  level: "Incremental",
  status: "Running",
  code: "R",
  started: "2026-10-14T09:00:00Z",
  ended: null,
  duration: "00:01:00",
  bytes: 42,
  files: 1,
  errors: 0,
  pool: "safe",
  metadataPruned: false,
};
const snapshot = {
  director: { name: "fixture", version: "fixture" },
  connection: "connected",
  syncedAt: "2026-10-14T09:00:00Z",
  sourceErrors: {},
  jobs: [
    {
      name: "VMware-safe",
      type: "Backup",
      client: "proxy",
      fileset: "safe",
      schedule: "Manual",
      storage: ["safe"],
      pool: "safe",
      enabled: true,
      level: "Incremental",
      latest: null,
    },
  ],
  workloads: [],
  sessions: [session],
  storages: [],
  pools: [],
  volumes: [],
  schedules: [],
  sessionTotal: 1,
  sessionLimit: 200,
  persistence: { state: "connected" },
  capabilities: { controls: true },
};
async function setup(page: Page) {
  await page.route("**/api/snapshot*", (route) =>
    route.fulfill({ json: snapshot }),
  );
  await page.route("**/api/sessions/*/logs", (route) =>
    route.fulfill({
      json: {
        lines: [{ time: session.started, text: "Synthetic session log." }],
      },
    }),
  );
}
test("Run requires confirmation, queues once, and shows durable feedback", async ({
  page,
}) => {
  await setup(page);
  const sent: Record<string, unknown>[] = [];
  let operation: Record<string, unknown> | null = null;
  await page.route("**/api/operations*", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      sent.push(body);
      expect(route.request().headers()["x-backup-center-action"]).toBe(
        "confirmed",
      );
      operation = {
        id: "00000000-0000-4000-8000-000000000042",
        idempotency_key: body.idempotency_key,
        kind: body.kind,
        target: body.target,
        state: "Accepted",
        job_id: 42,
        parameters: {
          message: "Fixture request accepted; awaiting Director status.",
        },
        created_at: session.started,
        updated_at: session.started,
      };
      await new Promise((resolve) => setTimeout(resolve, 300));
      await route.fulfill({ status: 202, json: operation });
    } else
      await route.fulfill({
        json: { operations: operation ? [operation] : [] },
      });
  });
  await page.goto("/?view=jobs");
  const run = page.getByRole("button", { name: "Run VMware-safe now" });
  await expect(run).toBeEnabled();
  await run.click();
  const dialog = page.getByRole("dialog", { name: "Run backup now?" });
  await expect(dialog).toBeVisible();
  expect(sent).toHaveLength(0);
  await expect(dialog.getByRole("button", { name: "Go back" })).toBeFocused();
  const scan = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(scan.violations).toEqual([]);
  await page.screenshot({ path: ".local/run-confirmation.png" });
  await dialog.getByRole("button", { name: "Run backup", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "Queuing…" })).toBeDisabled();
  await expect(dialog).not.toBeVisible();
  expect(sent).toHaveLength(1);
  expect(sent[0].kind).toBe("run");
  await expect(
    page.getByText("Fixture request accepted; awaiting Director status."),
  ).toBeVisible();
  await page.getByRole("link", { name: "History", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Operation journal" }),
  ).toBeVisible();
  await expect(
    page.getByText("Run · VMware-safe", { exact: true }),
  ).toBeVisible();
});
test("Cancel is confirmed in a separate dialog and never labeled completed on acknowledgement", async ({
  page,
}) => {
  await setup(page);
  const sent: Record<string, unknown>[] = [];
  let operation: Record<string, unknown> | null = null;
  await page.route("**/api/operations*", (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      sent.push(body);
      operation = {
        id: "00000000-0000-4000-8000-000000000043",
        ...body,
        state: "Accepted",
        job_id: 42,
        parameters: {
          message: "Cancellation requested; waiting for Director.",
        },
        created_at: session.started,
        updated_at: session.started,
      };
      return route.fulfill({ status: 202, json: operation });
    }
    return route.fulfill({
      json: { operations: operation ? [operation] : [] },
    });
  });
  await page.goto("/?view=history");
  await page.getByRole("button", { name: "VMware-safe", exact: true }).click();
  const detail = page.getByRole("dialog", { name: "Job #42" });
  await detail.getByRole("button", { name: "Cancel session" }).click();
  const confirmation = page.getByRole("dialog", {
    name: "Cancel backup session?",
  });
  await expect(confirmation).toBeVisible();
  await confirmation.getByRole("button", { name: "Go back" }).click();
  await expect(
    detail.getByRole("button", { name: "Cancel session" }),
  ).toBeFocused();
  expect(sent).toHaveLength(0);
  await detail.getByRole("button", { name: "Cancel session" }).click();
  await confirmation.getByRole("button", { name: "Cancel session" }).click();
  await expect(confirmation).not.toBeVisible();
  expect(sent).toHaveLength(1);
  expect(sent[0].kind).toBe("cancel");
  expect(sent[0].target).toBe("42");
  await detail.getByRole("button", { name: "Close session details" }).click();
  await expect(
    page
      .locator(".operation-feedback")
      .getByText("Cancellation requested; waiting for Director."),
  ).toBeVisible();
});
test("Explicit retry after browser transport loss reuses the same key", async ({
  page,
}) => {
  await setup(page);
  const sent: Record<string, unknown>[] = [];
  await page.route("**/api/operations*", (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      sent.push(body);
      if (sent.length === 1) return route.abort("failed");
      return route.fulfill({
        status: 202,
        json: {
          id: "00000000-0000-4000-8000-000000000044",
          ...body,
          state: "Unknown",
          job_id: null,
          parameters: { message: "Outcome unknown; not resent." },
          created_at: session.started,
          updated_at: session.started,
        },
      });
    }
    return route.fulfill({ json: { operations: [] } });
  });
  await page.goto("/?view=jobs");
  await page.getByRole("button", { name: "Run VMware-safe now" }).click();
  const confirmation = page.getByRole("dialog", { name: "Run backup now?" });
  await confirmation
    .getByRole("button", { name: "Run backup", exact: true })
    .click();
  await expect(confirmation.getByRole("alert")).toBeVisible();
  expect(sent).toHaveLength(1);
  await confirmation
    .getByRole("button", { name: "Run backup", exact: true })
    .click();
  await expect(confirmation).not.toBeVisible();
  expect(sent).toHaveLength(2);
  expect(sent[1].idempotency_key).toBe(sent[0].idempotency_key);
  await expect(page.getByText("Outcome unknown; not resent.")).toBeVisible();
});

test("Jobs outside the enabled operation scope remain disabled", async ({
  page,
}) => {
  await setup(page);
  await page.route("**/api/snapshot*", (route) =>
    route.fulfill({
      json: {
        ...snapshot,
        capabilities: { controls: true, operationJobs: [] },
      },
    }),
  );
  await page.route("**/api/operations*", (route) =>
    route.fulfill({ json: { operations: [] } }),
  );
  await page.goto("/?view=jobs");
  await expect(
    page.getByRole("button", { name: "Run VMware-safe now" }),
  ).toBeDisabled();
  await expect(page.getByText("Outside enabled operation scope")).toBeVisible();
});
