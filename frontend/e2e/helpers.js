// e2e/helpers.js — Helper bersama spec E2E.

// Login lewat form SUNGGUHAN (bukan localStorage injection) -- sengaja
// begitu supaya suite ini juga jadi jaring pengaman untuk halaman Login
// itu sendiri, bukan cuma halaman-halaman setelahnya.
async function login(page, username, password) {
  await page.goto("/app/#/login", { waitUntil: "networkidle" });
  const inputs = await page.locator("input").all();
  for (const input of inputs) {
    const type = await input.getAttribute("type");
    if (type === null || type === "text") await input.fill(username);
    else if (type === "password") await input.fill(password);
  }
  await page.locator('button[type="submit"], button:has-text("Masuk")').click();
  await page.waitForTimeout(1200);
}

module.exports = { login };
