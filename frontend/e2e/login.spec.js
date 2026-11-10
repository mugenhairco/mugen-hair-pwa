const { test, expect } = require("./fixtures");
const { login } = require("./helpers");

test.describe("Login", () => {
  // BUGFIX (audit): tombol Keluar sekarang ikon polos TANPA teks (lihat
  // nav.js::btnLogout -- aria-label="Keluar", tidak ada lagi teks visual),
  // jadi locator `button:has-text("Keluar")` tidak pernah ketemu lagi.
  // Pakai class `.btn-logout` (unik, tidak berubah) sebagai ganti.
  test("Owner login berhasil, tombol Keluar muncul di sidebar", async ({ page }) => {
    await login(page, "e2eowner", "e2eowner12345");
    await expect(page.locator("button.btn-logout")).toBeVisible({ timeout: 10000 });
  });

  test("Barber login berhasil, tombol Keluar muncul di sidebar", async ({ page }) => {
    await login(page, "e2ebarber", "e2epassword123");
    await expect(page.locator("button.btn-logout")).toBeVisible({ timeout: 10000 });
  });

  test("Password salah menampilkan pesan error, TIDAK masuk", async ({ page }) => {
    await login(page, "e2eowner", "password-yang-salah");
    await expect(page.locator(".login-error")).toContainText("Username atau password salah", { timeout: 10000 });
    await expect(page.locator("button.btn-logout")).toHaveCount(0);
  });
});
