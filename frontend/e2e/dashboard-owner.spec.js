// e2e/dashboard-owner.spec.js — Dashboard Owner: grid kartu (Nilai Service,
// Laba Kotor Toko, dst) merender tanpa error -- login sebagai e2eowner,
// pastikan kartu-kartu utama tampil dan tidak ada lagi tab/picker mode
// "Periode".
//
// BUGFIX (CI gagal terus-menerus, ditemukan dari laporan Owner): file ini
// menggantikan dashboard-periode.spec.js, yang mengetes tab "Periode" dan
// toggle Bulanan/Periode -- SELURUH fitur itu sudah DIHAPUS PERMANEN dari
// UI (lihat dashboard_owner.js, commit "Dashboard: hapus fitur Periode" --
// PERMINTAAN Owner: "hapus periode, hapus jgn sembunyikan fiturnya").
// Test lama jadi selalu gagal karena mengetes sesuatu yang memang sengaja
// sudah tidak ada, bukan bug aplikasi. Cakupan render kartu Dashboard
// (satu-satunya hal yang masih relevan dari test lama) dipertahankan di
// sini untuk mode "Bulanan" -- satu-satunya mode yang masih ada.
const { test, expect } = require("./fixtures");
const { login } = require("./helpers");

test.describe("Dashboard Owner", () => {
  test("grid kartu merender tanpa error, tidak ada lagi tab/picker mode Periode", async ({ page }) => {
    await login(page, "e2eowner", "e2eowner12345");
    await page.waitForTimeout(1000);

    await expect(page.locator(".card-collapse-title", { hasText: "Nilai Service" })).toBeVisible();
    await expect(page.locator(".card-collapse-title", { hasText: "Total Komisi Barber" })).toBeVisible();
    await expect(page.locator(".card-collapse-title", { hasText: "Pengeluaran Toko" })).toBeVisible();
    await expect(page.locator(".card-collapse-title", { hasText: "Penjualan Produk" })).toBeVisible();
    await expect(page.locator(".card-collapse-title", { hasText: "Laba Kotor Toko" })).toBeVisible();

    // Tab switcher Bulanan/Periode dihapus permanen -- tidak ada lagi
    // tombol "Periode" maupun date picker rentang tanggal.
    await expect(page.locator(".mugen-tabs button", { hasText: "Periode" })).toHaveCount(0);
    await expect(page.locator('input[type="date"]:visible')).toHaveCount(0);
  });
});
