import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {
  baseScheduleRow,
  routeActivePolicy,
  routeScheduleApply,
  routeSchedulePreview,
} from "./scheduling-fixtures";

test("Jobs opens an exact-job calendar, reviews interval payloads, and protects drafts without implicit apply", async ({
  page,
}) => {
  let preview: any;
  await routeActivePolicy(page, [
    baseScheduleRow,
    { ...baseScheduleRow, job: "VMware-MTIMRWKF01" },
  ]);
  await routeSchedulePreview(page, (body) => {
    preview = body;
    return {
      json: {
        ...body,
        reviewDigest: "a".repeat(64),
        existingVolumePolicy: "Preserve complete chains",
        doesNotRun: "No backup is run",
      },
    };
  });
  const apply = await routeScheduleApply(page);

  await page.goto("/?view=jobs&q=VMware-PNET");
  await page
    .getByRole("button", { name: "Edit schedule for VMware-PNET", exact: true })
    .click();
  await expect(page).toHaveURL(/view=job-schedule/);
  const panel = page.getByRole("region", { name: "Schedule · VMware-PNET" });
  await expect(panel.getByLabel("Backup start (WITA)")).toHaveValue("21:30");
  await expect(panel).not.toContainText("VMware-MTIMRWKF01");
  // A loaded, untouched editor must leave without a false dirty warning.
  await page.getByRole("button", { name: "Back to Jobs", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "Discard unsaved changes?" }),
  ).not.toBeVisible();
  await page
    .getByRole("textbox", { name: "Search this view" })
    .fill("VMware-PNET");
  await page
    .getByRole("button", { name: "Edit schedule for VMware-PNET", exact: true })
    .click();
  await panel.getByLabel("Full backup dates (comma-separated)").fill("5,20");
  await panel.getByLabel("Run frequency", { exact: true }).selectOption("1");
  await panel.getByLabel("Backup window end (WITA)").fill("23:30");
  await panel
    .getByRole("button", { name: "Review active policy", exact: true })
    .click();
  await expect(
    panel.getByRole("heading", { name: "Reviewed policy" }),
  ).toBeVisible();
  expect(preview.definition.jobs).toEqual(["VMware-PNET"]);
  expect(preview.definition.calendar.full_days).toEqual([5, 20]);
  expect(preview.definition.calendar.interval_hours).toBe(1);
  expect(preview.definition.window_end_wita).toBe("23:30");
  await panel
    .getByRole("button", { name: "Apply reviewed policy", exact: true })
    .click();
  const confirm = page.getByRole("dialog", {
    name: "Apply schedule and retention?",
  });
  await expect(
    confirm.getByRole("button", { name: "Go back", exact: true }),
  ).toBeFocused();
  await confirm.getByRole("button", { name: "Go back", exact: true }).click();
  apply.expectNone();
  await expect(
    panel.getByRole("button", { name: "Apply reviewed policy", exact: true }),
  ).toBeFocused();
  await page.getByRole("button", { name: "Back to Jobs", exact: true }).click();
  const discard = page.getByRole("dialog", {
    name: "Discard unsaved changes?",
  });
  await expect(discard).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(discard).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "Back to Jobs", exact: true }),
  ).toBeFocused();
  await expect(
    panel.getByLabel("Full backup dates (comma-separated)"),
  ).toHaveValue("5,20");
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  apply.expectNone();
});

test("custom active calendar is hydrated, ordinal resets to current, and rejected preview stays local", async ({
  page,
}) => {
  await routeActivePolicy(page, [
    {
      ...baseScheduleRow,
      calendar: {
        mode: "weekly",
        weekdays: [1, 3, 5],
        monthdays: [1, 15],
        full_mode: "weekly",
        full_weekday: 5,
        full_days: [1, 15],
        ordinal_week: 4,
        ordinal_weekday: 6,
        interval_hours: null,
      },
      maximumVolumes: 8,
      windowEndWita: "23:30",
      retryCount: 2,
      retryIntervalMinutes: 45,
    },
  ]);
  await routeSchedulePreview(page, (body) => ({
    status: 422,
    json: {
      detail: [
        {
          loc: ["body", "definition", "time_wita"],
          msg: "Time must stay after 21:00 WITA.",
        },
      ],
    },
  }));
  const apply = await routeScheduleApply(page);

  await page.goto("/?view=job-schedule&q=VMware-PNET");
  await expect(page.getByLabel("Run schedule", { exact: true })).toHaveValue(
    "weekly",
  );
  await expect(page.getByLabel("Monday", { exact: true })).toBeChecked();
  await expect(page.getByLabel("Tuesday", { exact: true })).not.toBeChecked();
  await expect(
    page.getByLabel("Full backup weekday", { exact: true }),
  ).toHaveValue("5");
  await page
    .getByLabel("Run schedule", { exact: true })
    .selectOption("monthly_ordinal");
  await page.getByLabel("Run on", { exact: true }).selectOption("4");
  await page.getByLabel("Weekday", { exact: true }).selectOption("6");
  await page
    .getByRole("button", { name: "Reset to current", exact: true })
    .click();
  await expect(page.getByLabel("Run schedule", { exact: true })).toHaveValue(
    "weekly",
  );
  await expect(page.getByLabel("Backup window end (WITA)")).toHaveValue(
    "23:30",
  );
  await page.getByLabel("Backup start (WITA)").fill("20:30");
  await page
    .getByRole("button", { name: "Review active policy", exact: true })
    .click();
  await expect(page.locator("#active-policy-error")).toContainText(
    "Check schedule fields, a time after 21:00",
  );
  await expect(page.getByLabel("Backup start (WITA)")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  await expect(
    page.getByRole("button", { name: "Apply reviewed policy", exact: true }),
  ).toHaveCount(0);
  apply.expectNone();
});

test("after-job mode exposes exact-job dependency options and reviews retry payloads", async ({
  page,
}) => {
  let preview: any;
  await routeActivePolicy(page, [
    baseScheduleRow,
    { ...baseScheduleRow, job: "VMware-MTIMRWKF01" },
  ]);
  await routeSchedulePreview(page, (body) => {
    preview = body;
    return {
      json: {
        ...body,
        reviewDigest: "b".repeat(64),
        existingVolumePolicy: "Preserve complete chains",
        doesNotRun: "No backup is run",
      },
    };
  });
  const apply = await routeScheduleApply(page);

  await page.goto("/?view=job-schedule&q=VMware-PNET");
  await page
    .getByLabel("Start method", { exact: true })
    .selectOption("after_job");
  await expect(
    page.getByLabel("After this job", { exact: true }).locator("option"),
  ).toHaveText(["VMware-MTIMRWKF01"]);
  await page
    .getByLabel("After this job", { exact: true })
    .selectOption("VMware-MTIMRWKF01");
  await page
    .getByLabel("If previous job fails", { exact: true })
    .selectOption("run_anyway");
  await page
    .getByLabel("Triggered backup level", { exact: true })
    .selectOption("incremental");
  await page.getByLabel("Backup window end (WITA)").fill("23:30");
  await page.getByLabel("Automatic retry count").fill("2");
  await page.getByLabel("Retry delay (minutes)").fill("45");
  await page
    .getByRole("button", { name: "Review active policy", exact: true })
    .click();
  expect(preview.definition.trigger_mode).toBe("after_job");
  expect(preview.definition.after_job).toEqual({
    source_job: "VMware-MTIMRWKF01",
    on_failure: "run_anyway",
    level: "incremental",
  });
  expect(preview.definition.retry_count).toBe(2);
  expect(preview.definition.retry_interval_minutes).toBe(45);
  expect(preview.definition.window_end_wita).toBe("23:30");
  apply.expectNone();
});
