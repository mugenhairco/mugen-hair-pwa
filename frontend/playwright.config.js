// playwright.config.js — Suite E2E untuk frontend/app (PWA MUGEN Hair Co.)
// =============================================================================
// Menjalankan DUA server sekaligus (backend E2E di :8031, frontend statis di
// :8130) lewat opsi `webServer` (array, didukung Playwright sejak lama) --
// backend/e2e_server.py mengisi database SQLite throwaway dengan fixture
// awal (Owner, Barber, Booking, Pengaturan Absensi) SEBELUM test mulai.
//
// workers: 1 (BUKAN paralel) -- seluruh spec berbagi SATU database E2E yang
// sama (bukan database terisolasi per test seperti backend/tests/conftest.py
// -- itu FastAPI TestClient yang me-reset DB tiap function, di sini kita
// menguji browser sungguhan lewat HTTP jadi butuh server yang benar-benar
// jalan). Paralel berisiko race condition menulis ke baris yang sama.
// @ts-check
const { defineConfig, devices } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: "http://127.0.0.1:8130",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: "python3 e2e_server.py",
      cwd: "../backend",
      url: "http://127.0.0.1:8031/api/health",
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      // cwd frontend/ (BUKAN frontend/app/) -- index.html asli ada di
      // frontend/app/index.html, jadi root server HARUS frontend/ supaya
      // path "/app/..." yang dipanggil frontend/e2e/helpers.js resolve
      // dengan benar (lihat catatan yang sama di README > Deployment).
      command: "python3 -m http.server 8130",
      cwd: ".",
      url: "http://127.0.0.1:8130/app/index.html",
      timeout: 15_000,
      reuseExistingServer: !process.env.CI,
    },
  ],
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
