// e2e/billing-default-tahunan.spec.js — Setting > Billing (halaman "Pilih
// Paket" in-app, app/js/pages/billing.js): diminta Owner, halaman ini
// SEKARANG SELALU terbuka di tab Tahunan sebagai tampilan awal (BUKAN
// Bulanan seperti sebelumnya), apa pun asal Owner datang (langsung/dari
// Landing Page) -- Owner tetap bebas pindah manual ke Bulanan/6 Bulan.
const { test, expect } = require("./fixtures");
const { login } = require("./helpers");

test.describe("Setting > Billing — default tab Tahunan", () => {
  test("halaman Billing terbuka langsung di tab Tahunan", async ({ page }) => {
    await login(page, "e2eowner", "e2eowner12345");
    await page.click('a:has-text("Billing")');
    await page.waitForTimeout(1000);

    await expect(page.locator("h2", { hasText: "Pilih Paket" })).toBeVisible();
    // Bukti tab Tahunan aktif sebagai default: kartu paket menampilkan
    // "per tahun" (bukan "per 30 hari"/bulanan) TANPA harus mengklik toggle
    // apa pun terlebih dahulu.
    await expect(page.locator(".grid-cards")).toContainText("per tahun");
    await expect(page.locator(".grid-cards")).toContainText("Setara Rp");

    // Owner tetap bebas pindah manual ke "Bulanan".
    await page.locator("button", { hasText: "Bulanan" }).first().click();
    await page.waitForTimeout(500);
    await expect(page.locator(".grid-cards")).not.toContainText("per tahun");
  });
});
