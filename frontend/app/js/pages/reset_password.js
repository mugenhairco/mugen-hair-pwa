// pages/reset_password.js — FITUR Lupa Kata Sandi: halaman PENUH dituju
// link di email reset password (#/reset-password?token=...). Murni
// PLATFORM (lihat MugenBrand.refreshPlatformOnly()), TIDAK butuh sesi
// login sama sekali (endpoint publik, token yang membuktikan identitas).

const PageResetPassword = (() => {
  function render(root) {
    root.innerHTML = "";
    const wrap = MugenUI.el("div", { class: "login-wrap" });
    const card = MugenUI.el("div", { class: "login-card" });
    card.appendChild(MugenUI.el("img", { class: "brand-logo login-logo", style: "display:none;", alt: "Logo" }));
    card.appendChild(MugenUI.el("h1", { class: "brand-name" }, "Rivoir"));
    card.appendChild(MugenUI.el("div", { class: "subtitle" }, "Atur Ulang Password"));

    const token = (MugenUI.ambilQueryHash().get("token") || "").trim();
    if (!token) {
      card.appendChild(MugenUI.el("div", { class: "login-error" }, "Link reset password tidak lengkap (token tidak ditemukan)."));
      card.appendChild(MugenUI.el("a", { href: "#/lupa-password", style: "display:block;text-align:center;margin-top:16px;" }, "Minta link baru"));
      wrap.appendChild(card);
      root.appendChild(wrap);
      MugenBrand.refreshPlatformOnly();
      return;
    }

    const inputPassword = MugenUI.el("input", { type: "password", placeholder: "Password Baru", autocomplete: "new-password" });
    const inputConfirmPassword = MugenUI.el("input", { type: "password", placeholder: "Konfirmasi Password Baru", autocomplete: "new-password" });
    const errorBox = MugenUI.el("div", { class: "login-error" });
    const hasilBox = MugenUI.el("div", { style: "margin-top:12px;font-size:14px;" });
    const btnSubmit = MugenUI.el("button", { class: "btn-primary", style: "width:100%;margin-top:16px;" }, "Simpan Password Baru");

    const form = MugenUI.el("form", {}, [
      MugenUI.el("label", {}, "Password Baru"), inputPassword,
      MugenUI.el("label", {}, "Konfirmasi Password Baru"), inputConfirmPassword,
      errorBox, hasilBox,
      btnSubmit,
    ]);

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      errorBox.textContent = "";
      hasilBox.innerHTML = "";
      if (inputPassword.value !== inputConfirmPassword.value) {
        errorBox.textContent = "Konfirmasi password tidak cocok.";
        return;
      }
      btnSubmit.disabled = true;
      btnSubmit.textContent = "Memproses...";
      try {
        const res = await MugenApi.post("/api/auth/reset-password", {
          token, password: inputPassword.value, confirm_password: inputConfirmPassword.value,
        });
        form.querySelectorAll("input, button").forEach((el) => { el.disabled = true; });
        hasilBox.innerHTML = "";
        hasilBox.appendChild(MugenUI.el("div", { style: "color:#16a34a;font-weight:600;margin-bottom:12px;" },
          res.message || "Password berhasil diubah."));
        hasilBox.appendChild(MugenUI.el(
          "a", { href: "#/login", class: "btn-primary", style: "display:block;text-decoration:none;text-align:center;" },
          "Lanjut ke Login",
        ));
      } catch (e) {
        const detail = e.detail && e.detail.detail;
        errorBox.textContent = (typeof detail === "string" && detail) || e.message;
        btnSubmit.disabled = false;
        btnSubmit.textContent = "Simpan Password Baru";
      }
    });

    card.appendChild(form);
    wrap.appendChild(card);
    root.appendChild(wrap);
    MugenBrand.refreshPlatformOnly();
  }

  return { render };
})();
