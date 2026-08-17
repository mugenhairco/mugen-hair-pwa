// e2e/absensi.spec.js — Check In/Check Out (GPS Geofencing). Geolocation
// browser di-mock PERSIS ke titik toko yang diatur backend/e2e_server.py
// (Monas, Jakarta -- titik yang SAMA dipakai backend/tests/test_attendance.py)
// supaya Check In lolos validasi radius.
const { test, expect } = require("./fixtures");
const { login } = require("./helpers");

test.describe("Absensi — Check In", () => {
  test.use({
    permissions: ["geolocation"],
    geolocation: { latitude: -6.175392, longitude: 106.827153 },
  });

  test("Barber di dalam radius toko berhasil Check In", async ({ page }) => {
    await login(page, "e2ebarber", "e2epassword123");
    await page.click("text=Absensi");
    await page.waitForTimeout(1000);

    const btnCheckIn = page.locator('button:has-text("Check In")').first();
    await expect(btnCheckIn).toBeEnabled({ timeout: 10000 });
    await btnCheckIn.click();

    // Modal konfirmasi (MugenUI.confirmModal) -- tombol konfirmasi SELALU
    // elemen TERAKHIR di .modal-actions (lihat ui.js::confirmModal()).
    await page.locator(".modal-actions button:last-child").click();
    await page.waitForTimeout(2000);

    // Toast sukses SENGAJA disembunyikan app-wide (lihat ui.js::toast()) --
    // bukti Check In berhasil yang benar: tombol Check In berubah disabled
    // (backend re-render status via load()).
    await expect(btnCheckIn).toBeDisabled({ timeout: 10000 });
  });
});
