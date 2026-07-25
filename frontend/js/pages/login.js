// pages/login.js
// TAHAP 10: nama & logo barbershop dibaca dari brand.js (MugenBrand), bukan
// hardcode lagi, supaya kalau diganti lewat Setting, halaman Login ikut berubah
// tanpa perlu ubah source code.

const PageLogin = (() => {
  function render(root) {
    root.innerHTML = "";
    const wrap = MugenUI.el("div", { class: "login-wrap" });
    // REVISI UI/UX: animasi Slide+Fade (logo, judul, form, tombol Login)
    // HANYA diputar saat aplikasi pertama dibuka atau tepat setelah Logout
    // (lihat state.js/router.js/nav.js) -- consumeLoginEntrance() sekaligus
    // me-reset penandanya supaya render() berikutnya (mis. sesi kedaluwarsa)
    // TIDAK ikut animasi lagi.
    const animateEntrance = MugenState.consumeLoginEntrance();
    const card = MugenUI.el("div", { class: "login-card" + (animateEntrance ? " login-entrance" : "") });
    card.appendChild(MugenUI.el("img", { class: "brand-logo login-logo", style: "display:none;", alt: "Logo" }));
    card.appendChild(MugenUI.el("h1", { class: "brand-name" }, MugenBrand.get().nama_barbershop));
    card.appendChild(MugenUI.el("div", { class: "subtitle" }, "Masuk ke akun Anda"));
    MugenBrand.refresh();

    // BUGFIX: tanpa atribut ini, keyboard HP (iOS/Android) otomatis
    // meng-kapital-kan huruf pertama username yang diketik user (perilaku
    // bawaan autocapitalize pada <input type="text">). Karena pencocokan
    // username di backend case-sensitive, ini menyebabkan login GAGAL
    // dengan pesan "username/password salah" padahal yang diketik user
    // sudah benar -- gejalanya terlihat "kadang" karena tergantung
    // keyboard/perangkat yang dipakai. Lihat juga auth_db.py
    // (get_user_by_username) untuk perbaikan sisi backend-nya.
    const inputUsername = MugenUI.el("input", {
      type: "text", placeholder: "Username", autocomplete: "username",
      autocapitalize: "off", autocorrect: "off", spellcheck: "false",
    });
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
        const res = await MugenUI.withLoading(() => MugenApi.post("/api/auth/login", {
          username: inputUsername.value.trim(),
          password: inputPassword.value,
        }), { message: "Memproses login…" });
        MugenState.setSession(res.token, res.user);
        // TAHAP 13 (bugfix): kalau hash URL kebetulan SUDAH persis
        // "#/dashboard" (mis. reload/bookmark #/dashboard saat sesi sudah
        // kedaluwarsa), set location.hash ke nilai yang sama TIDAK memicu
        // event "hashchange" (perilaku standar browser) -- akibatnya
        // MugenRouter.handle() tidak pernah dipanggil ulang dan halaman
        // Login tetap tampil walau login sebenarnya berhasil. Panggil
        // handle() langsung supaya kasus ini tetap pindah ke dashboard.
        location.hash = "#/dashboard";
        MugenRouter.handle();
        // REVISI: badge notifikasi booking langsung terisi begitu login
        // berhasil (bukan menunggu poll berkala berikutnya yang jaraknya
        // bisa sampai 15 detik, lihat booking_notif.js) -- dipanggil
        // SETELAH handle() supaya sidebar (elemen #booking-badge) sudah
        // pasti ada di DOM saat badge-nya di-update.
        if (typeof MugenBookingNotif !== "undefined") MugenBookingNotif.refreshNow();
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
