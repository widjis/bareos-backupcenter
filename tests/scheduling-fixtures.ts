import { expect, Page } from "@playwright/test";

export type ScheduleRow = {
  calendar?: {
    mode: "daily" | "weekly" | "monthly" | "monthly_ordinal";
    weekdays: number[];
    monthdays: number[];
    full_mode: "monthdays" | "weekly" | "ordinal";
    full_days: number[];
    full_weekday: number;
    ordinal_week: number;
    ordinal_weekday: number;
    interval_hours?: number | null;
  } | null;
  job: string;
  timeWita: string;
  automatic: boolean;
  retentionDays: number;
  maximumVolumes: number;
  triggerMode?: "calendar" | "after_job";
  afterJob?: {
    source_job: string;
    on_failure: "skip" | "run_anyway";
    level: "configured" | "full" | "incremental";
  } | null;
  windowEndWita?: string | null;
  retryCount?: number;
  retryIntervalMinutes?: number;
};

export const baseScheduleRow: ScheduleRow = {
  job: "VMware-PNET",
  timeWita: "21:30",
  automatic: true,
  retentionDays: 30,
  maximumVolumes: 6,
  calendar: null,
  triggerMode: "calendar",
  afterJob: null,
  windowEndWita: null,
  retryCount: 0,
  retryIntervalMinutes: 30,
};

export async function routeActivePolicy(
  page: Page,
  rows: ScheduleRow[],
  options: {
    applyEnabled?: boolean;
    liveApplyBlocker?: string;
  } = {},
) {
  await page.route("**/api/policies/active", (route) =>
    route.fulfill({
      json: {
        jobs: rows,
        applyEnabled: options.applyEnabled ?? true,
        ...(options.liveApplyBlocker
          ? { liveApplyBlocker: options.liveApplyBlocker }
          : {}),
      },
    }),
  );
}

export async function routeSchedulePreview(
  page: Page,
  handler: (body: any) => { status?: number; json: any },
) {
  await page.route("**/api/policies/active/preview", (route) => {
    const result = handler(route.request().postDataJSON());
    return route.fulfill({
      status: result.status ?? 200,
      json: result.json,
    });
  });
}

export async function routeScheduleApply(page: Page) {
  let applyRequests = 0;
  await page.route("**/api/policies/active/apply", (route) => {
    applyRequests += 1;
    return route.fulfill({
      status: 202,
      json: { state: "Accepted" },
    });
  });
  return {
    count: () => applyRequests,
    expectNone: () => expect(applyRequests).toBe(0),
  };
}
