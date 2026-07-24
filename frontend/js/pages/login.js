// pages/login.js
// TAHAP 10: nama & logo barbershop dibaca dari brand.js (MugenBrand), bukan
// hardcode lagi, supaya kalau diganti lewat Setting, halaman Login ikut berubah
// tanpa perlu ubah source code.

const PageLogin = (() => {
  function render(root) {
    root.innerHTML = "";
    const wrap = MugenUI.el("div", { class: "login-wrap" });
    const card = MugenUI.el("div", { class: "login-card" });
    card.appendChild(MugenUI.el("img", { class: "brand-logo login-logo", style: "display:none;", alt: "Logo" }));
    card.appendChild(MugenUI.el("h1", { class: "brand-name" }, MugenBrand.get().nama_barbershop));
    card.appendChild(MugenUI.el("div", { class: "subtitle" }, "Masuk ke akun Anda"));
    MugenBrand.refresh();

    const inputUsername = MugenUI.el("input", { type: "text", placeholder: "Username", autocomplete: "username" });
    const inputPassword = MugenUI.el("input", { type: "password", placeholder: "Password", autocomplete: "current-password" });
    const errorBox = MugenUI.el("div", { class: "login-error" });
    const btnSubmit = MugenUI.el("button", { class: "btn-primary", style: "width:100%;margin-top:16px;" }, "Masuk");

    const form = MugenUI.el("form", {}, [
      MugenUI.el("label", {}, "Username"), inputUsername,
      MugenUI.el("label", {}, "Password"), inputPassword,
      errorBox,
      btnSubmit,
    ]);
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      errorBox.textContent = "";
      btnSubmit.disabled = true;
      btnSubmit.textContent = "Memproses...";
      try {
        const res = await MugenApi.post("/api/auth/login", {
          username: inputUsername.value.trim(),
          password: inputPassword.value,
        });
        MugenState.setSession(res.token, res.user);
        location.hash = "#/dashboard";
      } catch (e) {
        errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      } finally {
        btnSubmit.disabled = false;
        btnSubmit.textContent = "Masuk";
      }
    });

    card.appendChild(form);
    wrap.appendChild(card);
    root.appendChild(wrap);
  }

  return { render };
})();
