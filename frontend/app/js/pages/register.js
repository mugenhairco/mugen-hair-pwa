// pages/register.js — FONDASI Multi-Tenant Phase 5: Landing Page SaaS
// =============================================================================
// Halaman PENUH (dirender langsung ke #app, BUKAN lewat router.js::shell(),
// pola sama seperti PageLogin) untuk Register self-service dari Landing Page
// publik (tombol "Get Started" -> /app/#/register).
//
// REVISI FITUR Verifikasi Email: sukses register SEBELUMNYA langsung
// login (token dikembalikan backend) & diarahkan ke #/billing. SEKARANG
// akun baru WAJIB verifikasi email dulu (routers/tenant_registration.py
// TIDAK LAGI mengembalikan token) -- form diganti layar "cek email Anda"
// + tombol "Kirim Ulang", Owner baru login NORMAL lewat #/login setelah
// klik link verifikasi di emailnya. Begitu login, mekanisme #/billing
// untuk tenant status 'expired' (router.js) TETAP jalan APA ADANYA
// seperti sebelumnya, TIDAK diubah sama sekali.

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

    // FITUR Verifikasi Email: layar "cek email Anda" menggantikan form
    // begitu register() berhasil -- BUKAN dialihkan ke halaman lain,
    // supaya tombol "Kirim Ulang" (kalau emailnya tidak sampai) tetap
    // langsung terlihat tanpa Owner perlu mencari-cari.
    function tampilkanCekEmail(email) {
      card.innerHTML = "";
      card.appendChild(MugenUI.el("img", { class: "brand-logo login-logo", style: "display:none;", alt: "Logo" }));
      card.appendChild(MugenUI.el("h1", { class: "brand-name" }, "Rivoir"));
      card.appendChild(MugenUI.el("div", { class: "subtitle" }, "Registrasi Berhasil!"));
      card.appendChild(MugenUI.el("p", { style: "font-size:14px;color:var(--text-dim);margin:12px 0;" },
        `Kami telah mengirimkan link verifikasi ke ${email}. Silakan cek kotak masuk (dan folder spam) Anda, lalu klik link tersebut sebelum bisa login.`));
      const btnKirimUlang = MugenUI.el("button", { class: "btn-primary", style: "width:100%;" }, "Kirim Ulang Email Verifikasi");
      btnKirimUlang.addEventListener("click", async () => {
        try {
          const res = await MugenUI.withButtonLoading(btnKirimUlang,
            () => MugenApi.post("/api/public/registration/resend-verification", { email }));
          MugenUI.toast(res.message || "Email verifikasi telah dikirim ulang.", "success", { force: true });
        } catch (e) {
          MugenUI.toast(e.message, "error");
        }
      });
      card.appendChild(btnKirimUlang);
      card.appendChild(MugenUI.el("a", { href: "#/login", style: "display:block;text-align:center;margin-top:16px;" }, "Sudah verifikasi? Masuk"));
    }

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
        const email = inputEmail.value.trim();
        await MugenUI.withLoading(() => MugenApi.post("/api/public/registration/register", {
          nama_barbershop: inputNamaBarbershop.value.trim(),
          owner_name: inputOwnerName.value.trim(),
          email,
          whatsapp: inputWhatsapp.value.trim(),
          password: inputPassword.value,
          confirm_password: inputConfirmPassword.value,
        }), { message: "Mendaftarkan toko Anda…" });
        tampilkanCekEmail(email);
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
