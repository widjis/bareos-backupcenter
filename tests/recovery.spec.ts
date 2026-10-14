import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test("live recovery inspection shows chain and media without claiming verified recovery", async ({
  page,
}) => {
  await page.goto("/?view=backups");
  const trigger = page
    .getByRole("button", { name: "Inspect recovery", exact: true })
    .first();
  await expect(trigger).toBeEnabled({ timeout: 45000 });
  await trigger.click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("heading", { name: "Required backup chain" }),
  ).toBeVisible({ timeout: 45000 });
  await expect(
    dialog.getByText(
      "Media readability and restored contents have not been verified.",
      { exact: false },
    ),
  ).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "Start restore" }),
  ).toBeDisabled();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.screenshot({
    path: ".local/recovery-inspection.png",
    fullPage: true,
  });
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
});
test("recovery failure preserves retry and keyboard close", async ({
  page,
}) => {
  await page.route("**/api/recovery/*", (route) =>
    route.fulfill({
      status: 502,
      json: { detail: "Recovery inspection unavailable." },
    }),
  );
  await page.goto("/?view=backups");
  await page
    .getByRole("button", { name: "Inspect recovery", exact: true })
    .first()
    .click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByText("Recovery inspection unavailable."),
  ).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "Retry inspection" }),
  ).toBeEnabled();
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
});

test("isolated export confirmation dispatches only a simulated request", async ({
  page,
}) => {
  await page.route("**/api/recovery/*", (route) =>
    route.fulfill({
      json: {
        dispatchEnabled: true,
        sourceJobId: 17,
        jobIds: [17],
        chain: [
          {
            jobId: 17,
            job: "VMware-fixture",
            level: "Full",
            status: "Succeeded",
            media: [{ name: "fixture-1", status: "Append" }],
          },
        ],
        items: [
          { path: "/VMS/fixture/disk.vmdk", kind: "Virtual disk backup" },
        ],
        blockers: [],
        unsupported: ["Instant VM recovery"],
        engineResolved: true,
        itemTotal: 1,
        itemLimit: 2000,
      },
    }),
  );
  let sent = 0;
  await page.route("**/api/operations*", async (route) => {
    if (route.request().method() === "POST") {
      sent++;
      const body = route.request().postDataJSON();
      expect(body.kind).toBe("restore");
      expect(body.confirmed).toBe(true);
      await route.fulfill({
        status: 202,
        json: {
          id: "fixture-operation",
          kind: "restore",
          target: body.target,
          state: "Accepted",
          job_id: 42,
          idempotency_key: body.idempotency_key,
          parameters: { message: "Fixture only: export accepted." },
        },
      });
    } else await route.fulfill({ json: { operations: [], limit: 100 } });
  });
  await page.goto("/?view=backups");
  await page
    .getByRole("button", { name: "Inspect recovery", exact: true })
    .first()
    .click();
  await page.getByRole("button", { name: "Start restore" }).click();
  const confirm = page.locator(".restore-confirm");
  await expect(confirm.getByRole("button", { name: "Go back" })).toBeFocused();
  expect(sent).toBe(0);
  await confirm
    .getByRole("button", { name: "Export disks", exact: true })
    .click();
  await expect(page.getByText("Fixture only: export accepted.")).toBeVisible();
  expect(sent).toBe(1);
});
