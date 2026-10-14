import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("sign-in is masked, validates input, handles rejection and is accessible", async ({
  page,
  context,
}) => {
  await context.clearCookies();
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Sign in to Backup Center" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByText("Enter a valid username and password."),
  ).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Username" })).toBeFocused();
  await page.getByLabel("Password", { exact: true }).fill("synthetic-password");
  await page
    .getByRole("button", { name: "Show password", exact: true })
    .click();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute(
    "type",
    "text",
  );
  await page
    .getByRole("button", { name: "Hide password", exact: true })
    .click();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute(
    "type",
    "password",
  );
  await page.route("**/api/auth/login", (route) =>
    route.fulfill({
      status: 401,
      json: { detail: "Sign-in failed. Check your credentials." },
    }),
  );
  await page.getByRole("textbox", { name: "Username" }).fill("synthetic");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByText("Sign-in failed. Check your credentials."),
  ).toBeVisible();
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
  ).toBeTruthy();
});

test("logout revokes its own session and removes dashboard access", async ({
  page,
  context,
}) => {
  const { localLogin } = await import("./auth-helpers");
  await context.request.post("/api/auth/login", {
    headers: {
      Origin: "http://127.0.0.1:3000",
      "X-Backup-Center-Action": "confirmed",
    },
    data: localLogin(),
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in to Backup Center" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Jobs", exact: false }),
  ).toHaveCount(0);
});

test("account drafts survive canceled navigation and account creation is confirmed with synthetic writes", async ({
  page,
}) => {
  let sent = 0;
  await page.route("**/api/users", (route) => {
    if (route.request().method() === "POST") {
      sent++;
      return route.fulfill({
        status: 201,
        json: { username: "fixtureuser", role: "Viewer" },
      });
    }
    return route.fulfill({
      json: { users: [{ username: "admin", role: "Admin", enabled: true }] },
    });
  });
  await page.goto("/?view=settings");
  const area = page.locator(".identity-settings");
  await area.getByRole("button", { name: "Review account" }).click();
  await expect(area.getByLabel("New username")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  await expect(area.getByLabel("New username")).toBeFocused();
  await area.getByLabel("New username").fill("fixtureuser");
  await area
    .getByLabel("New account password", { exact: true })
    .fill("synthetic-long-password");
  await page.getByRole("link", { name: "Jobs", exact: false }).click();
  const discard = page.getByRole("dialog", {
    name: "Discard unsaved changes?",
  });
  await expect(discard.getByRole("button", { name: "Go back" })).toBeFocused();
  await discard.getByRole("button", { name: "Go back" }).click();
  await expect(area.getByLabel("New username")).toHaveValue("fixtureuser");
  await area.getByLabel("Role", { exact: true }).selectOption("Viewer");
  await area.getByRole("button", { name: "Review account" }).click();
  const confirm = page.getByRole("dialog", {
    name: "Create application account?",
  });
  await expect(confirm.getByRole("button", { name: "Go back" })).toBeFocused();
  expect(sent).toBe(0);
  await confirm
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(confirm).not.toBeVisible();
  expect(sent).toBe(1);
  await expect(area.getByLabel("New username")).toHaveValue("");
});

test("permission revocation closes an unsubmitted operation confirmation", async ({
  page,
}) => {
  let viewer = false;
  await page.clock.install();
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      json: { username: "fixture", role: viewer ? "Viewer" : "Admin" },
    }),
  );
  await page.route("**/api/snapshot*", (route) =>
    route.fulfill({
      json: {
        director: { name: "fixture", version: "fixture" },
        connection: "connected",
        syncedAt: "2026-10-14T00:00:00Z",
        sourceErrors: {},
        persistence: { state: "connected" },
        capabilities: { controls: true },
        jobs: [
          {
            name: "VMware-fixture",
            type: "Backup",
            client: "fixture",
            fileset: "fixture",
            schedule: "Manual",
            storage: [],
            pool: "fixture",
            enabled: true,
            level: "Full",
            latest: null,
          },
        ],
        workloads: [],
        sessions: [],
        storages: [],
        pools: [],
        volumes: [],
        schedules: [],
        sessionTotal: 0,
        sessionLimit: 200,
      },
    }),
  );
  await page.route("**/api/operations*", (route) =>
    route.fulfill({ json: { operations: [], limit: 100 } }),
  );
  await page.goto("/?view=jobs");
  await page.getByRole("button", { name: "Run VMware-fixture now" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  viewer = true;
  await page.clock.fastForward(30001);
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(
    page.getByText("fixture · Viewer", { exact: false }),
  ).toBeVisible();
});
