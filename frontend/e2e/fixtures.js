// e2e/fixtures.js — Fixture bersama SEMUA spec E2E: intercept panggilan API
// ke domain production (frontend/config.js commit hardcode
// "https://api.rivoirsett.com") supaya diarahkan ke backend E2E lokal
// (127.0.0.1:8031, lihat backend/e2e_server.py) -- MURNI redirect
// network-level di dalam browser test, TIDAK mengubah file tracked apa
// pun (config.js produksi tetap apa adanya).
const base = require("@playwright/test");

const API_LOCAL = "http://127.0.0.1:8031";

const test = base.test.extend({
  page: async ({ page }, use) => {
    await page.route("https://api.rivoirsett.com/**", async (route) => {
      const newUrl = route.request().url().replace("https://api.rivoirsett.com", API_LOCAL);
      const response = await route.fetch({ url: newUrl });
      await route.fulfill({ response });
    });
    await use(page);
  },
});

module.exports = { test, expect: base.expect };
