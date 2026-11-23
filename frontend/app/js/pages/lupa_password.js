// pages/lupa_password.js — FITUR Lupa Kata Sandi: halaman PENUH (pola sama
// seperti PageRegister/PageLogin), tombol "Lupa Kata Sandi?" di Login
// mengarah ke sini (#/lupa-password). Murni PLATFORM (BUKAN halaman
// tenant mana pun, lihat MugenBrand.refreshPlatformOnly()).
//
// SATU form (username + nomor HP) untuk Owner MAUPUN Karyawan (PERMINTAAN
// Owner: "saya tidak mau ada dua pilihan seperti itu" -- menggantikan
// rancangan toggle 2 pilihan yang sempat dibuat sebelumnya, TIDAK pernah
// dirilis). Channel pengiriman (WhatsApp/Email) ditentukan OTOMATIS oleh
// backend berdasarkan role akun yang ditemukan lewat username -- lihat
// routers/auth_router.py::lupa_password_telepon(). Respons membawa
// `channel`, dipakai di sini untuk menentukan langkah berikutnya:
// - "whatsapp" (akun barber): tampilkan form kode OTP + password baru.
// - "email" (akun Owner): cukup tampilkan "cek email Anda" -- Owner
//   melanjutkan dari LINK di emailnya (#/reset-password?token=...,
//   halaman TERPISAH yang SUDAH ADA, tidak diubah sama sekali).

const PageLupaPassword = (() => {
  function render(root) {
    root.innerHTML = "";
    const wrap = MugenUI.el("div", { class: "login-wrap" });
    const card = MugenUI.el("div", { class: "login-card" });
    card.appendChild(MugenUI.el("img", { class: "brand-logo login-logo", style: "display:none;", alt: "Logo" }));
    card.appendChild(MugenUI.el("h1", { class: "brand-name" }, "Rivoir"));
    card.appendChild(MugenUI.el("div", { class: "subtitle" }, "Lupa Kata Sandi"));
    card.appendChild(MugenUI.el("div", { style: "font-size:13px;color:var(--text-dim);margin:4px 0 12px;" },
      "Masukkan username & nomor HP yang terdaftar di akun Anda. Kode OTP (karyawan) atau link reset "
      + "(Owner) akan dikirim secara otomatis ke tempat yang sesuai."));

    // ---- Langkah 1: username + nomor HP -> minta reset ----
    const inputUsername = MugenUI.el("input", {
      type: "text", placeholder: "Username", autocomplete: "username",
      autocapitalize: "off", autocorrect: "off", spellcheck: "false",
    });
    const inputNomor = MugenUI.el("input", { type: "tel", placeholder: "Nomor HP (contoh: 081234567890)", autocomplete: "tel" });
    const errorBox1 = MugenUI.el("div", { class: "login-error" });
    const hasilBox1 = MugenUI.el("div", { style: "margin-top:12px;font-size:14px;" });
    const btnLangkah1 = MugenUI.el("button", { class: "btn-primary", style: "width:100%;margin-top:16px;" }, "Lanjutkan");

    const form1 = MugenUI.el("form", {}, [
      MugenUI.el("label", {}, "Username"), inputUsername,
      MugenUI.el("label", {}, "Nomor HP"), inputNomor,
      errorBox1, hasilBox1,
      btnLangkah1,
    ]);

    // ---- Langkah 2 (HANYA untuk channel="whatsapp"): kode OTP + password
    // baru + konfirmasi -- SEMBUNYI sampai langkah 1 sukses dengan channel
    // itu. ----
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

    const form2 = MugenUI.el("form", {}, [
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
      hasilBox1.innerHTML = "";
      const username = inputUsername.value.trim();
      const nomor = inputNomor.value.trim();
      if (!username || !nomor) {
        errorBox1.textContent = "Username dan nomor HP wajib diisi.";
        return;
      }
      btnLangkah1.disabled = true;
      btnLangkah1.textContent = "Memproses...";
      try {
        const res = await MugenApi.post("/api/auth/lupa-password-telepon", { username, nomor_hp: nomor });
        inputUsername.disabled = true;
        inputNomor.disabled = true;
        btnLangkah1.style.display = "none";
        if (res.channel === "whatsapp") {
          hasilBox1.textContent = res.message || "Kode OTP telah dikirim ke WhatsApp Anda.";
          langkah2.style.display = "";
        } else {
          // channel === "email" (akun Owner) -- tidak ada form lanjutan
          // di halaman ini, Owner melanjutkan dari link di emailnya.
          hasilBox1.innerHTML = "";
          hasilBox1.appendChild(MugenUI.el("div", { style: "color:#16a34a;font-weight:600;" },
            res.message || "Link reset password telah dikirim ke email Anda."));
        }
      } catch (e) {
        const detail = e.detail && e.detail.detail;
        errorBox1.textContent = (typeof detail === "string" && detail) || e.message;
      } finally {
        btnLangkah1.disabled = false;
        btnLangkah1.textContent = "Lanjutkan";
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

    card.appendChild(form1);
    card.appendChild(langkah2);
    const linkLogin = MugenUI.el("a", { href: "#/login", style: "display:block;text-align:center;margin-top:16px;" }, "Kembali ke Login");
    card.appendChild(linkLogin);
    wrap.appendChild(card);
    root.appendChild(wrap);
    MugenBrand.refreshPlatformOnly();
  }

  return { render };
})();
