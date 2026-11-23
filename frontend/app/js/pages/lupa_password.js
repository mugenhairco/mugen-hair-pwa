// pages/lupa_password.js — FITUR Lupa Kata Sandi: halaman PENUH (pola sama
// seperti PageRegister/PageLogin), tombol "Lupa Kata Sandi?" di Login
// mengarah ke sini (#/lupa-password). Murni PLATFORM (BUKAN halaman
// tenant mana pun, lihat MugenBrand.refreshPlatformOnly()).
//
// DUA JALUR TERPISAH, dipilih lewat toggle di atas (default "Owner"):
// 1. Owner (Email) -- SUDAH ADA sebelumnya, TIDAK diubah sama sekali.
//    Endpoint backend (/api/auth/lupa-password) SELALU membalas pesan
//    yang SAMA apa pun hasilnya, KECUALI kalau email itu ternyata milik
//    akun karyawan (pesan eksplisit mengarahkan ke jalur WhatsApp di
//    bawah) -- lihat routers/auth_router.py.
// 2. Karyawan (WhatsApp) -- BARU (PERMINTAAN Owner): isi username + nomor
//    WhatsApp yang terdaftar di data karyawan, kode OTP 6 digit dikirim
//    ke WhatsApp itu dari WA toko. BEDA dari jalur Email (pesan SELALU
//    generik demi anti-enumerasi): di sini pesan EKSPLISIT "Akun tidak
//    ditemukan" kalau username+nomor TIDAK COCOK BERSAMA -- permintaan
//    eksplisit Owner, risiko enumerasinya kecil karena butuh DUA data
//    yang benar sekaligus (lihat routers/auth_router.py::lupa_password_wa()
//    untuk alasan lengkap).

const PageLupaPassword = (() => {
  function renderToggle(container, modeAktif, onPilih) {
    container.innerHTML = "";
    const buatTombol = (mode, label) => {
      const aktif = mode === modeAktif;
      const btn = MugenUI.el("button", {
        type: "button",
        class: "btn-toggle-lupa-password" + (aktif ? " aktif" : ""),
        style: "flex:1;padding:8px;border-radius:8px;border:1px solid var(--border-color,#ccc);"
          + (aktif ? "background:var(--accent,#16a34a);color:#fff;font-weight:600;" : "background:transparent;"),
      }, label);
      btn.addEventListener("click", () => onPilih(mode));
      return btn;
    };
    container.appendChild(buatTombol("owner", "Saya Owner"));
    container.appendChild(buatTombol("karyawan", "Saya Karyawan"));
  }

  function renderOwner(bodyBox) {
    bodyBox.innerHTML = "";
    bodyBox.appendChild(MugenUI.el("div", { style: "font-size:13px;color:var(--text-dim);margin:4px 0 12px;" },
      "Masukkan email akun Owner Anda -- kami akan mengirimkan link untuk mengatur ulang password."));

    const inputEmail = MugenUI.el("input", { type: "email", placeholder: "Email", autocomplete: "email" });
    const hasilBox = MugenUI.el("div", { style: "margin-top:12px;font-size:14px;" });
    const errorBox = MugenUI.el("div", { class: "login-error" });
    const btnSubmit = MugenUI.el("button", { class: "btn-primary", style: "width:100%;margin-top:16px;" }, "Kirim Link Reset");

    const form = MugenUI.el("form", {}, [
      MugenUI.el("label", {}, "Email"), inputEmail,
      errorBox, hasilBox,
      btnSubmit,
    ]);

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      errorBox.textContent = "";
      hasilBox.innerHTML = "";
      const email = inputEmail.value.trim();
      if (!email) {
        errorBox.textContent = "Email tidak boleh kosong.";
        return;
      }
      btnSubmit.disabled = true;
      btnSubmit.textContent = "Memproses...";
      try {
        const res = await MugenApi.post("/api/auth/lupa-password", { email });
        form.querySelectorAll("input, button").forEach((el) => { el.disabled = true; });
        hasilBox.textContent = res.message || "Kalau email tersebut terdaftar, kami telah mengirimkan instruksi lebih lanjut.";
      } catch (e) {
        const detail = e.detail && e.detail.detail;
        errorBox.textContent = (typeof detail === "string" && detail) || e.message;
      } finally {
        btnSubmit.disabled = false;
        btnSubmit.textContent = "Kirim Link Reset";
      }
    });

    bodyBox.appendChild(form);
  }

  function renderKaryawan(bodyBox) {
    bodyBox.innerHTML = "";
    bodyBox.appendChild(MugenUI.el("div", { style: "font-size:13px;color:var(--text-dim);margin:4px 0 12px;" },
      "Masukkan username & nomor WhatsApp yang terdaftar di data karyawan Anda -- kode OTP akan dikirim ke WhatsApp itu."));

    // ---- Langkah 1: username + nomor WhatsApp -> minta OTP ----
    const inputUsername = MugenUI.el("input", {
      type: "text", placeholder: "Username", autocomplete: "username",
      autocapitalize: "off", autocorrect: "off", spellcheck: "false",
    });
    const inputNomor = MugenUI.el("input", { type: "tel", placeholder: "Nomor WhatsApp (contoh: 081234567890)", autocomplete: "tel" });
    const errorBox1 = MugenUI.el("div", { class: "login-error" });
    const btnKirimOtp = MugenUI.el("button", { class: "btn-primary", style: "width:100%;margin-top:16px;" }, "Kirim Kode OTP");

    const form1 = MugenUI.el("form", {}, [
      MugenUI.el("label", {}, "Username"), inputUsername,
      MugenUI.el("label", {}, "Nomor WhatsApp"), inputNomor,
      errorBox1,
      btnKirimOtp,
    ]);

    // ---- Langkah 2: kode OTP + password baru + konfirmasi (SEMBUNYI
    // sampai langkah 1 sukses) ----
    const langkah2 = MugenUI.el("div", { style: "display:none;margin-top:20px;padding-top:16px;border-top:1px solid var(--border-color,#ccc);" });
    const inputKode = MugenUI.el("input", {
      type: "text", placeholder: "Kode OTP (6 digit)", autocomplete: "one-time-code",
      inputmode: "numeric", maxlength: "6",
    });
    const inputPassword = MugenUI.el("input", { type: "password", placeholder: "Password Baru", autocomplete: "new-password" });
    const inputConfirmPassword = MugenUI.el("input", { type: "password", placeholder: "Konfirmasi Password Baru", autocomplete: "new-password" });
    const errorBox2 = MugenUI.el("div", { class: "login-error" });
    const hasilBox2 = MugenUI.el("div", { style: "margin-top:12px;font-size:14px;" });
    const btnUbahPassword = MugenUI.el("button", { class: "btn-primary", style: "width:100%;margin-top:16px;" }, "Ubah Password");

    const infoOtpTerkirim = MugenUI.el("div", { style: "color:#16a34a;font-weight:600;margin-bottom:8px;" });
    const form2 = MugenUI.el("form", {}, [
      infoOtpTerkirim,
      MugenUI.el("label", {}, "Kode OTP"), inputKode,
      MugenUI.el("label", {}, "Password Baru"), inputPassword,
      MugenUI.el("label", {}, "Konfirmasi Password Baru"), inputConfirmPassword,
      errorBox2, hasilBox2,
      btnUbahPassword,
    ]);
    langkah2.appendChild(form2);

    form1.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      errorBox1.textContent = "";
      const username = inputUsername.value.trim();
      const nomor = inputNomor.value.trim();
      if (!username || !nomor) {
        errorBox1.textContent = "Username dan nomor WhatsApp wajib diisi.";
        return;
      }
      btnKirimOtp.disabled = true;
      btnKirimOtp.textContent = "Memproses...";
      try {
        const res = await MugenApi.post("/api/auth/lupa-password-wa", { username, nomor_whatsapp: nomor });
        inputUsername.disabled = true;
        inputNomor.disabled = true;
        btnKirimOtp.style.display = "none";
        infoOtpTerkirim.textContent = res.message || "Kode OTP telah dikirim ke WhatsApp Anda.";
        langkah2.style.display = "";
      } catch (e) {
        const detail = e.detail && e.detail.detail;
        errorBox1.textContent = (typeof detail === "string" && detail) || e.message;
      } finally {
        btnKirimOtp.disabled = false;
        btnKirimOtp.textContent = "Kirim Kode OTP";
      }
    });

    form2.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      errorBox2.textContent = "";
      hasilBox2.innerHTML = "";
      if (inputPassword.value !== inputConfirmPassword.value) {
        errorBox2.textContent = "Konfirmasi password tidak cocok.";
        return;
      }
      btnUbahPassword.disabled = true;
      btnUbahPassword.textContent = "Memproses...";
      try {
        const res = await MugenApi.post("/api/auth/reset-password-wa", {
          username: inputUsername.value.trim(),
          kode: inputKode.value.trim(),
          password: inputPassword.value,
          confirm_password: inputConfirmPassword.value,
        });
        form2.querySelectorAll("input, button").forEach((el) => { el.disabled = true; });
        hasilBox2.innerHTML = "";
        hasilBox2.appendChild(MugenUI.el("div", { style: "color:#16a34a;font-weight:600;margin-bottom:12px;" },
          res.message || "Password berhasil diubah."));
        hasilBox2.appendChild(MugenUI.el(
          "a", { href: "#/login", class: "btn-primary", style: "display:block;text-decoration:none;text-align:center;" },
          "Lanjut ke Login",
        ));
      } catch (e) {
        const detail = e.detail && e.detail.detail;
        errorBox2.textContent = (typeof detail === "string" && detail) || e.message;
      } finally {
        btnUbahPassword.disabled = false;
        btnUbahPassword.textContent = "Ubah Password";
      }
    });

    bodyBox.appendChild(form1);
    bodyBox.appendChild(langkah2);
  }

  function render(root) {
    root.innerHTML = "";
    const wrap = MugenUI.el("div", { class: "login-wrap" });
    const card = MugenUI.el("div", { class: "login-card" });
    card.appendChild(MugenUI.el("img", { class: "brand-logo login-logo", style: "display:none;", alt: "Logo" }));
    card.appendChild(MugenUI.el("h1", { class: "brand-name" }, "Rivoir"));
    card.appendChild(MugenUI.el("div", { class: "subtitle" }, "Lupa Kata Sandi"));

    const toggleBox = MugenUI.el("div", { style: "display:flex;gap:8px;margin-bottom:12px;" });
    const bodyBox = MugenUI.el("div");

    function pilihMode(mode) {
      renderToggle(toggleBox, mode, pilihMode);
      if (mode === "karyawan") renderKaryawan(bodyBox);
      else renderOwner(bodyBox);
    }
    pilihMode("owner");

    card.appendChild(toggleBox);
    card.appendChild(bodyBox);

    const linkLogin = MugenUI.el("a", { href: "#/login", style: "display:block;text-align:center;margin-top:16px;" }, "Kembali ke Login");
    card.appendChild(linkLogin);
    wrap.appendChild(card);
    root.appendChild(wrap);
    MugenBrand.refreshPlatformOnly();
  }

  return { render };
})();
