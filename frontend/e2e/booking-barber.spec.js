// e2e/booking-barber.spec.js — Regression-lock BUG tanggal booking
// tercampur di tab "Hari Ini"/"Akan Datang" (dilaporkan Owner via
// screenshot APK, diperbaiki PR #142). Fixture booking disiapkan di
// backend/e2e_server.py: "E2E Customer Masa Depan" (masa depan asli,
// HARUS muncul di "Akan Datang") dan "E2E Customer Sudah Lewat" (dipatch
// ke KEMARIN, HARUS TIDAK PERNAH muncul di tab mana pun selain "Semua
// Booking").
const { test, expect } = require("./fixtures");
const { login } = require("./helpers");

test.describe("Booking — tampilan Barber (Hari Ini/Akan Datang/Semua Booking)", () => {
  test.beforeEach(async ({ page }) => {
    await login(page, "e2ebarber", "e2epassword123");
    await page.click("text=Booking");
    await page.waitForTimeout(1000);
  });

  test('Tab "Hari Ini" (default aktif) TIDAK menampilkan booking yang sudah lewat', async ({ page }) => {
    await expect(page.locator('button.active:has-text("Hari Ini")')).toBeVisible();
    await expect(page.locator("text=E2E Customer Sudah Lewat")).toHaveCount(0);
    await expect(page.locator("text=E2E Customer Masa Depan")).toHaveCount(0);
  });

  test('Tab "Akan Datang" menampilkan booking masa depan, TIDAK menampilkan yang sudah lewat', async ({ page }) => {
    await page.click("text=Akan Datang");
    await page.waitForTimeout(1000);
    await expect(page.locator("text=E2E Customer Masa Depan")).toBeVisible();
    await expect(page.locator("text=E2E Customer Sudah Lewat")).toHaveCount(0);
  });

  test('Tab "Semua Booking" tetap tabel lama, render tanpa error', async ({ page }) => {
    await page.click("text=Semua Booking");
    await page.waitForTimeout(1000);
    await expect(page.locator("table.data-table")).toBeVisible();
  });
});
