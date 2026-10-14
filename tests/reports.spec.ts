import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test("observed report uses WITA periods, exports safely and keeps coverage explicit", async ({
  page,
}) => {
  await page.goto("/?view=history");
  const area = page.locator(".session-report");
  await expect(
    area.getByRole("heading", { name: "Backup session report" }),
  ).toBeVisible();
  await area.getByLabel("From date (WITA)").fill("2026-10-01");
  await area.getByLabel("Through date (WITA)").fill("2026-10-14");
  await area.getByRole("button", { name: "Load report" }).click();
  await expect(area.getByRole("link", { name: "Export CSV" })).toBeVisible();
  await expect(
    area.getByText("Application-observed sessions only;", { exact: false }),
  ).toBeVisible();
  const response = await page.request.get(
    (await area
      .getByRole("link", { name: "Export CSV" })
      .getAttribute("href")) as string,
  );
  expect(response.status()).toBe(200);
  expect(await response.text()).toContain("Timezone: Asia/Makassar");
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.evaluate(() => {
    (window as unknown as { printCalls: number }).printCalls = 0;
    window.print = () => {
      (window as unknown as { printCalls: number }).printCalls++;
      window.dispatchEvent(new Event("afterprint"));
    };
  });
  await area.getByRole("button", { name: "Print report page" }).click();
  expect(
    await page.evaluate(
      () => (window as unknown as { printCalls: number }).printCalls,
    ),
  ).toBe(1);
  await area.getByLabel("From date (WITA)").fill("2026-10-15");
  await area.getByRole("button", { name: "Load report" }).click();
  await expect(
    area.getByText("Choose a valid period of at most 366 days."),
  ).toBeVisible();
  await expect(area.getByLabel("From date (WITA)")).toBeFocused();
});
