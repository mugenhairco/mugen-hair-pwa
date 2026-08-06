// pages/verify_email.js — FITUR Verifikasi Email: halaman PENUH (pola sama
// seperti PageRegister/PageLogin) yang dituju link di email verifikasi
// (#/verify-email?token=...). Murni PLATFORM (BUKAN halaman tenant mana
// pun, sama seperti Register -- lihat MugenBrand.refreshPlatformOnly()),
// TIDAK butuh sesi login sama sekali (endpoint publik).

const PageVerifyEmail = (() => {
  async function render(root) {
    root.innerHTML = "";
    const wrap = MugenUI.el("div", { class: "login-wrap" });
    const card = MugenUI.el("div", { class: "login-card" });
    card.appendChild(MugenUI.el("img", { class: "brand-logo login-logo", style: "display:none;", alt: "Logo" }));
    card.appendChild(MugenUI.el("h1", { class: "brand-name" }, "Rivoir"));
    card.appendChild(MugenUI.el("div", { class: "subtitle" }, "Verifikasi Email"));

    const statusBox = MugenUI.el("div", { style: "margin-top:16px;text-align:center;" });
    card.appendChild(statusBox);
    wrap.appendChild(card);
    root.appendChild(wrap);
    MugenBrand.refreshPlatformOnly();

    const token = (MugenUI.ambilQueryHash().get("token") || "").trim();
    if (!token) {
      statusBox.appendChild(MugenUI.el("div", { class: "login-error" }, "Link verifikasi tidak lengkap (token tidak ditemukan)."));
      return;
    }

    statusBox.appendChild(MugenUI.el("div", { class: "subtitle" }, "Memverifikasi email Anda..."));

    try {
      await MugenApi.post("/api/auth/verifikasi-email", { token });
      statusBox.innerHTML = "";
      statusBox.appendChild(MugenUI.el("div", {
        style: "color:#16a34a;font-weight:600;margin-bottom:16px;",
      }, "Email berhasil diverifikasi!"));
      statusBox.appendChild(MugenUI.el(
        "a", { href: "#/login", class: "btn-primary", style: "display:block;text-decoration:none;text-align:center;" },
        "Lanjut ke Login",
      ));
    } catch (e) {
      statusBox.innerHTML = "";
      const detail = e.detail && e.detail.detail;
      const pesan = (typeof detail === "string" && detail) || e.message || "Link verifikasi tidak valid atau sudah kedaluwarsa.";
      statusBox.appendChild(MugenUI.el("div", { class: "login-error" }, pesan));
      statusBox.appendChild(MugenUI.el("a", { href: "#/login", style: "display:block;text-align:center;margin-top:16px;" }, "Kembali ke Login"));
    }
  }

  return { render };
})();
