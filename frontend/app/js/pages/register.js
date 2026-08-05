// pages/register.js — FONDASI Multi-Tenant Phase 5: Landing Page SaaS
// =============================================================================
// Halaman PENUH (dirender langsung ke #app, BUKAN lewat router.js::shell(),
// pola sama seperti PageLogin) untuk Register self-service dari Landing Page
// publik (tombol "Get Started" -> /app/#/register). Sukses register langsung
// login (token dikembalikan backend, lihat routers/tenant_registration.py)
// dan diarahkan ke #/billing untuk memilih paket + bayar -- tenant baru
// berstatus 'expired' (diblokir) sampai pembayaran berhasil, TIDAK bisa
// masuk dashboard dulu, lihat router.js untuk pengecualian akses #/billing
// saat diblokir.

const PageRegister = (() => {
  function render(root) {
    root.innerHTML = "";
    const wrap = MugenUI.el("div", { class: "login-wrap" });
    const card = MugenUI.el("div", { class: "login-card" });
    // BUGFIX Register: halaman ini pintu masuk PLATFORM (calon Owner
    // BELUM PERNAH "dikenal" tenant apa pun), BUKAN halaman tenant mana
    // pun seperti Login -- SELALU branding Rivoir, TIDAK BOLEH terpengaruh
    // cache/slug tenant yang kebetulan "diingat" di perangkat itu dari
    // toko lain yang pernah login/dilihat sebelumnya (lihat
    // MugenBrand.refreshPlatformOnly() untuk penjelasan lengkap). Nama
    // awal langsung "Rivoir" literal (BUKAN MugenBrand.get(), yang bisa
    // membaca cache toko lain) -- refreshPlatformOnly() akan
    // mengonfirmasi ulang ke server begitu render() ini selesai.
    card.appendChild(MugenUI.el("img", { class: "brand-logo login-logo", style: "display:none;", alt: "Logo" }));
    card.appendChild(MugenUI.el("h1", { class: "brand-name" }, "Rivoir"));
    card.appendChild(MugenUI.el("div", { class: "subtitle" }, "Daftarkan barbershop Anda"));

    const inputNamaBarbershop = MugenUI.el("input", { type: "text", placeholder: "Nama Barbershop", autocomplete: "organization" });
    const inputOwnerName = MugenUI.el("input", { type: "text", placeholder: "Nama Owner", autocomplete: "name" });
    const inputEmail = MugenUI.el("input", { type: "email", placeholder: "Email", autocomplete: "email" });
    const inputWhatsapp = MugenUI.el("input", { type: "tel", placeholder: "Nomor WhatsApp", autocomplete: "tel" });
    const inputPassword = MugenUI.el("input", { type: "password", placeholder: "Password", autocomplete: "new-password" });
    const inputConfirmPassword = MugenUI.el("input", { type: "password", placeholder: "Konfirmasi Password", autocomplete: "new-password" });
    const errorBox = MugenUI.el("div", { class: "login-error" });
    const btnSubmit = MugenUI.el("button", { class: "btn-primary", style: "width:100%;margin-top:16px;" }, "Daftar");

    const linkLogin = MugenUI.el("a", { href: "#/login", style: "display:block;text-align:center;margin-top:16px;" },
      "Sudah punya akun? Masuk");

    const form = MugenUI.el("form", {}, [
      MugenUI.el("label", {}, "Nama Barbershop"), inputNamaBarbershop,
      MugenUI.el("label", {}, "Nama Owner"), inputOwnerName,
      MugenUI.el("label", {}, "Email"), inputEmail,
      MugenUI.el("label", {}, "Nomor WhatsApp"), inputWhatsapp,
      MugenUI.el("label", {}, "Password"), inputPassword,
      MugenUI.el("label", {}, "Konfirmasi Password"), inputConfirmPassword,
      errorBox,
      btnSubmit,
    ]);

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      errorBox.textContent = "";
      if (inputPassword.value !== inputConfirmPassword.value) {
        errorBox.textContent = "Konfirmasi password tidak cocok.";
        return;
      }
      btnSubmit.disabled = true;
      btnSubmit.textContent = "Memproses...";
      try {
        const res = await MugenUI.withLoading(() => MugenApi.post("/api/public/registration/register", {
          nama_barbershop: inputNamaBarbershop.value.trim(),
          owner_name: inputOwnerName.value.trim(),
          email: inputEmail.value.trim(),
          whatsapp: inputWhatsapp.value.trim(),
          password: inputPassword.value,
          confirm_password: inputConfirmPassword.value,
        }), { message: "Mendaftarkan toko Anda…" });
        MugenState.setSession(res.token, res.user, res.tenant);
        MugenBrand.refresh();
        await MugenSubscription.refresh();
        // Langsung ke #/billing (BUKAN #/dashboard) -- tenant baru berstatus
        // 'expired', router.js mengizinkan #/billing tetap diakses walau
        // diblokir supaya Owner bisa langsung memilih paket & bayar.
        location.hash = "#/billing";
        MugenRouter.handle();
      } catch (e) {
        const detail = e.detail && e.detail.detail;
        errorBox.textContent = (typeof detail === "string" && detail) || e.message;
      } finally {
        btnSubmit.disabled = false;
        btnSubmit.textContent = "Daftar";
      }
    });

    card.appendChild(form);
    card.appendChild(linkLogin);
    wrap.appendChild(card);
    root.appendChild(wrap);
    MugenBrand.refreshPlatformOnly();
  }

  return { render };
})();
