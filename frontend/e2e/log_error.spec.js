// e2e/log_error.spec.js — Setting > Log Error (DIY error monitoring, bukan
// Sentry -- lihat backend/app/error_log_db.py). Fixture seed disiapkan di
// backend/e2e_server.py: satu baris error "backend" supaya tab ini punya
// sesuatu untuk diverifikasi tampil TANPA harus memicu error sungguhan
// lewat browser (frontend/js/error_report.js dites cakupannya lewat unit
// test JS-nya sendiri kalau ada, di sini murni memverifikasi tampilan &
// alur baca Owner).
const { test, expect } = require("./fixtures");
const { login } = require("./helpers");

test.describe("Setting > Log Error", () => {
  test("Owner melihat baris error seed + detail stack trace", async ({ page }) => {
    await login(page, "e2eowner", "e2eowner12345");
    await page.click("text=Setting");
    await page.waitForTimeout(1000);
    await page.click('.mugen-tabs button:has-text("Log Error")');
    await page.waitForTimeout(1000);

    await expect(page.locator("text=Contoh error seed E2E: ValueError contoh")).toBeVisible();
    await expect(page.locator('table.data-table td:has-text("Backend")')).toBeVisible();

    await page.click('table.data-table button:has-text("Detail")');
    await expect(page.locator(".modal-box")).toBeVisible();
    await expect(page.locator(".modal-box")).toContainText("ValueError: contoh error seed E2E");
  });

  test("Filter Sumber = Frontend menyembunyikan baris seed Backend", async ({ page }) => {
    await login(page, "e2eowner", "e2eowner12345");
    await page.click("text=Setting");
    await page.waitForTimeout(1000);
    await page.click('.mugen-tabs button:has-text("Log Error")');
    await page.waitForTimeout(1000);

    await page.selectOption("select", "frontend");
    await page.waitForTimeout(1000);
    await expect(page.locator("text=Contoh error seed E2E: ValueError contoh")).toHaveCount(0);
  });
});
