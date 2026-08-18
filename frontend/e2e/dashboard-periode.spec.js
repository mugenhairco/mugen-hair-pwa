// e2e/dashboard-periode.spec.js — Dashboard Owner mode "Periode" (rentang
// tanggal bebas, diminta Owner sebagai alternatif mode "Bulanan" yang sudah
// ada) -- login sebagai e2eowner, pindah tab "Periode", pastikan dua date
// picker muncul (menggantikan dropdown Bulan/Tahun), grid kartu tetap
// merender tanpa error (termasuk kartu "Laba Kotor Toko"), dan kartu "Bonus
// Customer" TIDAK PERNAH muncul di mode ini (backend selalu null, lihat
// routers/dashboard.py::dashboard_owner_periode()) sedangkan MUNCUL di mode
// Bulanan (default) -- bukti nyata field itu benar-benar disembunyikan,
// bukan cuma ditampilkan "Rp 0" yang menyesatkan.
const { test, expect } = require("./fixtures");
const { login } = require("./helpers");

test.describe("Dashboard Owner — mode Periode", () => {
  test("toggle Bulanan/Periode menukar picker, kartu Bonus Customer hanya muncul di mode Bulanan", async ({ page }) => {
    await login(page, "e2eowner", "e2eowner12345");
    await page.waitForTimeout(1000);

    // Mode default "Bulanan" -- kartu Bonus Customer HARUS ada, date picker
    // periode ada di DOM tapi disembunyikan (display:none), belum pernah dipilih.
    await expect(page.locator(".card-collapse-title", { hasText: "Bonus Customer" })).toBeVisible();
    await expect(page.locator('input[type="date"]:visible')).toHaveCount(0);

    await page.locator(".mugen-tabs button", { hasText: "Periode" }).click();
    await page.waitForTimeout(1000);

    // Mode "Periode" -- dua date picker (dari/sampai) menggantikan dropdown Bulan/Tahun.
    await expect(page.locator('input[type="date"]:visible')).toHaveCount(2);
    // Kartu Bonus Customer TIDAK PERNAH muncul di mode Periode.
    await expect(page.locator(".card-collapse-title", { hasText: "Bonus Customer" })).toHaveCount(0);
    // Kartu lain tetap merender (bukti request ke endpoint baru berhasil, tidak error).
    await expect(page.locator(".card-collapse-title", { hasText: "Nilai Service" })).toBeVisible();
    await expect(page.locator(".card-collapse-title", { hasText: "Laba Kotor Toko" })).toBeVisible();
    await expect(page.locator("h2", { hasText: "SERVICE PERIODE INI" })).toBeVisible();
    // Grafik Pendapatan (terikat kalender bulan/tahun) sengaja disembunyikan di mode Periode.
    await expect(page.locator("h2", { hasText: "Grafik Pendapatan" })).toHaveCount(0);

    // Kembali ke "Bulanan" -- Bonus Customer & Grafik Pendapatan muncul lagi.
    await page.locator(".mugen-tabs button", { hasText: "Bulanan" }).click();
    await page.waitForTimeout(1000);
    await expect(page.locator(".card-collapse-title", { hasText: "Bonus Customer" })).toBeVisible();
    await expect(page.locator("h2", { hasText: "Grafik Pendapatan" })).toBeVisible();
  });
});
