import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test("explicit VMware selection produces a disabled, secret-free configuration preview", async ({
  page,
}) => {
  await page.goto("/?view=infrastructure");
  const area = page.locator(".inventory-section");
  await expect(
    area.getByText("Inventory connected", { exact: false }),
  ).toBeVisible({ timeout: 45000 });
  await area.getByRole("checkbox").first().check();
  const trigger = area.getByRole("button", {
    name: "Preview onboarding",
    exact: true,
  });
  await trigger.click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("heading", { name: "Onboarding preview" }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "Generate preview" }).click();
  await expect(
    dialog.getByRole("heading", { name: "Configuration review" }),
  ).toBeVisible({ timeout: 45000 });
  await expect(dialog.locator("pre")).toContainText("Enabled = no");
  await expect(dialog.locator("pre")).not.toContainText("vcpass=");
  await expect(
    dialog.getByRole("button", { name: "Apply configuration" }),
  ).toBeDisabled();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.screenshot({
    path: ".local/onboarding-preview.png",
    fullPage: true,
  });
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
});
