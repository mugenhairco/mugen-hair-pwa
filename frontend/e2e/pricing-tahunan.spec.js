// e2e/pricing-tahunan.spec.js — Landing Page Pricing: opsi baru "Tahunan"
// berdampingan dengan "Bulanan"/"6 Bulan" yang sudah ada (TIDAK diubah).
// Menguji halaman Landing Page publik (frontend/index.html, BUKAN
// frontend/app/) -- toggle tiga arah, harga/badge/catatan "Setara Rp.../
// bulan" muncul benar di mode Tahunan, dan mode Bulanan tetap identik
// (tidak ada regresi) setelah berpindah-pindah mode.
const { test, expect } = require("./fixtures");

test.describe("Landing Page Pricing — mode Tahunan", () => {
  test("toggle Bulanan/6 Bulan/Tahunan menampilkan harga & badge yang benar", async ({ page }) => {
    await page.goto("/index.html", { waitUntil: "networkidle" });

    // Tunggu kartu Pricing selesai dimuat dari /api/public/landing/packages.
    await expect(page.locator(".lp-pricing-card").first()).toBeVisible({ timeout: 10000 });

    // --- Mode default "Bulanan" -- tidak ada badge penghematan sama sekali. ---
    await expect(page.locator(".lp-pricing-badge-save")).toHaveCount(0);
    await expect(page.locator("#lp-pricing-slider")).toContainText("Rp 188.000");

    // --- Mode "6 Bulan" (SUDAH ADA, tidak boleh berubah) ---
    await page.locator("#lp-cycle-toggle .lp-cycle-btn", { hasText: "6 Bulan" }).click();
    await page.waitForTimeout(600);
    await expect(page.locator("#lp-pricing-slider")).toContainText("Rp 950.000");
    await expect(page.locator(".lp-pricing-badge-save").first()).toHaveText("Paling Hemat");
    await expect(page.locator("#lp-pricing-slider")).toContainText("Hemat Rp");
    await expect(page.locator("#lp-pricing-slider")).not.toContainText("Setara Rp");

    // --- Mode "Tahunan" (BARU) ---
    await page.locator("#lp-cycle-toggle .lp-cycle-btn", { hasText: "Tahunan" }).click();
    await page.waitForTimeout(600);
    // Basic: Rp 1.560.000 / tahun, Setara Rp 130.000/bulan.
    await expect(page.locator("#lp-pricing-slider")).toContainText("Rp 1.560.000");
    await expect(page.locator("#lp-pricing-slider")).toContainText("/ tahun");
    await expect(page.locator("#lp-pricing-slider")).toContainText("Setara Rp 130.000/bulan");
    await expect(page.locator("#lp-pricing-slider")).toContainText("Hemat dengan pembayaran tahunan");
    // Badge ribbon kartu HARUS "⭐ Paling Hemat", BUKAN "Hemat Lebih Banyak".
    await expect(page.locator(".lp-pricing-badge-save").first()).toHaveText("⭐ Paling Hemat");
    await expect(page.locator("#lp-pricing-slider")).not.toContainText("Hemat Lebih Banyak");
    // Harga 6 bulan/bulanan TIDAK ikut muncul di mode ini.
    await expect(page.locator("#lp-pricing-slider")).not.toContainText("Rp 950.000");

    // --- Kembali ke "Bulanan" -- harus PERSIS seperti semula (regression check). ---
    await page.locator("#lp-cycle-toggle .lp-cycle-btn", { hasText: "Bulanan" }).click();
    await page.waitForTimeout(600);
    await expect(page.locator(".lp-pricing-badge-save")).toHaveCount(0);
    await expect(page.locator("#lp-pricing-slider")).toContainText("Rp 188.000");
    await expect(page.locator("#lp-pricing-slider")).not.toContainText("Setara Rp");
  });

  test("toggle & badge Tahunan tidak terpotong di viewport mobile", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    await page.goto("/index.html", { waitUntil: "networkidle" });
    await expect(page.locator(".lp-pricing-card").first()).toBeVisible({ timeout: 10000 });

    const btnTahunan = page.locator("#lp-cycle-toggle .lp-cycle-btn", { hasText: "Tahunan" });
    await expect(btnTahunan).toBeVisible();
    const toggleBox = await page.locator("#lp-cycle-toggle").boundingBox();
    const btnBox = await btnTahunan.boundingBox();
    // Tombol "Tahunan" (dan badge di dalamnya) harus tetap berada di dalam
    // batas kanan viewport -- lp-cycle-toggle sudah flex-wrap di breakpoint
    // mobile (lihat landing.css), jadi TIDAK boleh overflow horizontal.
    expect(btnBox.x + btnBox.width).toBeLessThanOrEqual(375 + 1);
    expect(toggleBox.x + toggleBox.width).toBeLessThanOrEqual(375 + 1);

    await btnTahunan.click();
    await page.waitForTimeout(600);
    // Slider Pricing merender SEMUA kartu sekaligus di DOM (slide non-aktif
    // sengaja diposisikan di luar viewport lewat transform, itu bukan bug)
    // -- HANYA kartu ".lp-slide-active" (yang sedang di tengah) yang relevan
    // dicek tidak terpotong. Slide pertama (index 0) = paket Free, TIDAK
    // pernah punya badge (harga 0) -- geser SATU slide ke paket Basic yang
    // pasti punya badge di mode Tahunan. Panah slider disembunyikan di
    // breakpoint mobile (swipe-only UX, lihat landing.css) -- titik/dot
    // navigasi TETAP tampil, dipakai di sini sebagai gantinya.
    await page.locator("#lp-pricing-slider .lp-slider-dots .lp-slider-dot").nth(1).click();
    await page.waitForTimeout(600);
    const badge = page.locator(".lp-slide-active .lp-pricing-badge-save").first();
    await expect(badge).toBeVisible();
    const badgeBox = await badge.boundingBox();
    expect(badgeBox.x).toBeGreaterThanOrEqual(-1);
    expect(badgeBox.x + badgeBox.width).toBeLessThanOrEqual(375 + 1);
  });
});
