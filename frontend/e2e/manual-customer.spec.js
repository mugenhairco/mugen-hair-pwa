// e2e/manual-customer.spec.js — Input Data: Manual Customer (Waiting List/
// Booking) -- login sebagai e2eowner (satu-satunya akun admin di fixture
// e2e_server.py), pilih mode "Manual Customer" (tiga pilihan sejajar dengan
// Input Barber/Non-Barber), tambah satu Waiting List (hanya nama) dan satu
// Booking (nama+jam+barber+service), pastikan nama Booking mendapat highlight
// kuning (.mc-nama-booking) sedangkan Waiting List tidak, lalu Tutup & Simpan
// Hari Ini dan pastikan status berubah jadi CLOSED.
//
// CATATAN locator: halaman ini punya BEBERAPA <select>/<input type="date">
// yang identik strukturnya (form Input Barber, Tandai Libur, Non-Barber,
// Manual Customer semua render bersamaan di DOM, hanya disembunyikan lewat
// display:none) -- setiap locator di bawah SENGAJA di-scope lewat filter
// unik (isi <option> section itu) atau pseudo-class :visible supaya tidak
// pernah salah pilih elemen dari section lain yang sedang tersembunyi.
const { test, expect } = require("./fixtures");
const { login } = require("./helpers");

test.describe("Input Data — Manual Customer", () => {
  test("Waiting List + Booking tersimpan, highlight benar, Closing berhasil", async ({ page }) => {
    await login(page, "e2eowner", "e2eowner12345");
    await page.click("text=Input Data");
    await page.waitForTimeout(1000);

    const selMode = page.locator("select").filter({ has: page.locator("option", { hasText: "Manual Customer" }) });
    await selMode.selectOption({ label: "Manual Customer" });
    await page.waitForTimeout(500);

    // Tanggal HARUS unik setiap kali test ini dijalankan -- bukan cuma
    // "jauh di masa depan" tapi benar-benar baru tiap run, karena database
    // E2E dipakai bersama SATU proses selama seluruh suite (lihat komentar
    // di playwright.config.js) dan tanggal yang sudah pernah di-Closing
    // pada run sebelumnya akan (secara BENAR, sesuai desain) menolak
    // input baru -- dibuktikan sendiri saat menulis test ini: menjalankan
    // ulang dengan tanggal yang sama membuat form Manual Customer disabled
    // karena tanggal itu sudah berstatus CLOSED dari run sebelumnya.
    const dasar = new Date("2030-01-01T00:00:00Z");
    dasar.setUTCDate(dasar.getUTCDate() + (Date.now() % 3650)); // sebar ~10 tahun, praktis tidak pernah bentrok
    const tanggal = dasar.toISOString().slice(0, 10);
    await page.locator('input[type="date"]:visible').fill(tanggal);
    await page.waitForTimeout(500);

    // --- Waiting List: hanya Nama Customer, field Booking harus tersembunyi ---
    await page.fill('input[placeholder="Nama Customer"]', "Budi Waiting");
    await expect(page.locator('input[type="time"]')).toBeHidden();
    await page.locator("button", { hasText: /^Tambah$/ }).click();
    await page.waitForTimeout(1000);

    await expect(page.locator("text=Budi Waiting")).toBeVisible();
    // Nama Waiting List TIDAK memakai class highlight kuning.
    await expect(page.locator(".mc-nama-booking")).toHaveCount(0);

    // --- Booking: Nama + Jam + Barber + Service wajib ---
    const selJenis = page.locator("select").filter({ has: page.locator("option", { hasText: "Waiting List" }) });
    await selJenis.selectOption({ label: "Booking" });
    await page.waitForTimeout(300);
    await expect(page.locator('input[type="time"]')).toBeVisible();

    await page.fill('input[placeholder="Nama Customer"]', "Andi Booking");
    await page.fill('input[type="time"]', "14:30");
    const selectBarber = page.locator("select:visible").filter({ has: page.locator("option", { hasText: "-- pilih barber --" }) });
    await selectBarber.selectOption({ label: "E2E Barber" });
    await page.locator(".checklist-service label", { hasText: "E2E Haircut" }).locator('input[type="checkbox"]').check();
    await page.locator("button", { hasText: /^Tambah$/ }).click();
    await page.waitForTimeout(1000);

    // Nama Booking HARUS memakai highlight kuning (.mc-nama-booking), Waiting List tidak.
    await expect(page.locator(".mc-nama-booking")).toHaveCount(1);
    await expect(page.locator(".mc-nama-booking")).toHaveText("Andi Booking");

    // --- Tutup & Simpan Hari Ini ---
    page.once("dialog", (dialog) => dialog.accept());
    await page.locator("button", { hasText: "Tutup & Simpan Hari Ini" }).click();
    await page.waitForTimeout(1500);

    await expect(page.locator("text=sudah DITUTUP")).toBeVisible({ timeout: 10000 });
  });
});
