// e2e/dashboard-periode.spec.js — Dashboard Owner mode "Periode" (rentang
// tanggal bebas, diminta Owner sebagai alternatif mode "Bulanan" yang sudah
// ada) -- login sebagai e2eowner, pindah tab "Periode", pastikan dua date
// picker muncul (menggantikan dropdown Bulan/Tahun), grid kartu tetap
// merender tanpa error di kedua mode (termasuk kartu "Laba Kotor Toko").
//
// BUGFIX (audit): test ini sebelumnya memeriksa kartu "Bonus Customer" --
// kartu itu SUDAH TIDAK PERNAH dirender sama sekali di Dashboard Owner
// (lihat dashboard_owner.js::renderDenganData(), daftar `kartu` cuma berisi
// Nilai Service/Total Komisi Barber/Total Tips/Uang Harian/Jumlah Service/
// Pengeluaran Toko/Penjualan Produk/Laba Kotor Toko -- tidak ada field
// bonus_customer, meski backend routers/dashboard.py masih menghitungnya).
// Assertion lama jadi selalu gagal karena mengetes fitur yang sudah
// dihapus dari UI, bukan bug aplikasi -- diganti memeriksa kartu yang
// SUNGGUH ada di kedua mode.
const { test, expect } = require("./fixtures");
const { login } = require("./helpers");

test.describe("Dashboard Owner — mode Periode", () => {
  test("toggle Bulanan/Periode menukar picker, grid kartu tetap merender di kedua mode", async ({ page }) => {
    await login(page, "e2eowner", "e2eowner12345");
    await page.waitForTimeout(1000);

    // Mode default "Bulanan" -- date picker periode ada di DOM tapi
    // disembunyikan (display:none), belum pernah dipilih.
    await expect(page.locator(".card-collapse-title", { hasText: "Nilai Service" })).toBeVisible();
    await expect(page.locator('input[type="date"]:visible')).toHaveCount(0);

    await page.locator(".mugen-tabs button", { hasText: "Periode" }).click();
    await page.waitForTimeout(1000);

    // Mode "Periode" -- dua date picker (dari/sampai) menggantikan dropdown Bulan/Tahun.
    await expect(page.locator('input[type="date"]:visible')).toHaveCount(2);
    // Kartu lain tetap merender (bukti request ke endpoint baru berhasil, tidak error).
    await expect(page.locator(".card-collapse-title", { hasText: "Nilai Service" })).toBeVisible();
    await expect(page.locator(".card-collapse-title", { hasText: "Laba Kotor Toko" })).toBeVisible();
    await expect(page.locator("h2", { hasText: "SERVICE PERIODE INI" })).toBeVisible();

    // Kembali ke "Bulanan" -- grid kartu merender lagi dengan benar.
    await page.locator(".mugen-tabs button", { hasText: "Bulanan" }).click();
    await page.waitForTimeout(1000);
    await expect(page.locator(".card-collapse-title", { hasText: "Nilai Service" })).toBeVisible();
    await expect(page.locator('input[type="date"]:visible')).toHaveCount(0);
  });
});
