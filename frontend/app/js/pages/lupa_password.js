// pages/lupa_password.js — FITUR Lupa Kata Sandi: halaman PENUH (pola sama
// seperti PageRegister/PageLogin), tombol "Lupa Kata Sandi?" di Login
// mengarah ke sini (#/lupa-password). Murni PLATFORM (BUKAN halaman
// tenant mana pun, lihat MugenBrand.refreshPlatformOnly()) -- endpoint
// backend (/api/auth/lupa-password) SELALU membalas pesan yang SAMA
// apa pun hasilnya (email Owner ditemukan ATAU tidak ditemukan sama
// sekali), KECUALI kalau email itu ternyata milik akun karyawan (pesan
// eksplisit mengarahkan ke Owner) -- lihat routers/auth_router.py.

const PageLupaPassword = (() => {
  function render(root) {
    root.innerHTML = "";
    const wrap = MugenUI.el("div", { class: "login-wrap" });
    const card = MugenUI.el("div", { class: "login-card" });
    card.appendChild(MugenUI.el("img", { class: "brand-logo login-logo", style: "display:none;", alt: "Logo" }));
    card.appendChild(MugenUI.el("h1", { class: "brand-name" }, "Rivoir"));
    card.appendChild(MugenUI.el("div", { class: "subtitle" }, "Lupa Kata Sandi"));
    card.appendChild(MugenUI.el("div", { style: "font-size:13px;color:var(--text-dim);margin:4px 0 12px;" },
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

    const linkLogin = MugenUI.el("a", { href: "#/login", style: "display:block;text-align:center;margin-top:16px;" }, "Kembali ke Login");

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

    card.appendChild(form);
    card.appendChild(linkLogin);
    wrap.appendChild(card);
    root.appendChild(wrap);
    MugenBrand.refreshPlatformOnly();
  }

  return { render };
})();
