const { test, expect } = require("./fixtures");
const { login } = require("./helpers");

test.describe("Login", () => {
  test("Owner login berhasil, tombol Keluar muncul di sidebar", async ({ page }) => {
    await login(page, "e2eowner", "e2eowner12345");
    await expect(page.locator('button:has-text("Keluar")')).toBeVisible({ timeout: 10000 });
  });

  test("Barber login berhasil, tombol Keluar muncul di sidebar", async ({ page }) => {
    await login(page, "e2ebarber", "e2epassword123");
    await expect(page.locator('button:has-text("Keluar")')).toBeVisible({ timeout: 10000 });
  });

  test("Password salah menampilkan pesan error, TIDAK masuk", async ({ page }) => {
    await login(page, "e2eowner", "password-yang-salah");
    await expect(page.locator(".login-error")).toContainText("Username atau password salah", { timeout: 10000 });
    await expect(page.locator('button:has-text("Keluar")')).toHaveCount(0);
  });
});
