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
    // REVISI: terapkan dulu dari cache localStorage (lewat applyToDom(), bukan
    // langsung tunggu refresh() yang butuh roundtrip ke server) supaya logo
    // yang sudah pernah tersimpan langsung tampil tanpa delay/flash kosong
    // saat halaman Login pertama kali dibuka -- refresh() tetap dipanggil
    // sesudahnya untuk menyegarkan data di background.
    MugenBrand.applyToDom();
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
    // FONDASI Multi-Tenant Phase 2.0: pemilih toko -- SEMBUNYI secara default
    // (mayoritas mutlak: satu perangkat = satu toko, TIDAK PERNAH ambigu),
    // hanya dimunculkan kalau backend membalas 409 "username+password ini
    // terdaftar di lebih dari satu toko" (lihat blok catch di form.submit
    // di bawah). Alur ini SENGAJA tidak menambah field apa pun ke form
    // untuk kasus normal, sesuai instruksi asli Phase 1 "jangan mengubah
    // workflow pengguna" -- pemilih toko murni fallback untuk kasus langka.
    const tenantPickerBox = MugenUI.el("div", { class: "login-tenant-picker", style: "display:none;" });
    // FITUR Verifikasi Email: kotak KHUSUS kasus 403 "email_belum_
    // terverifikasi" (routers/auth_router.py::login()) -- SEMBUNYI secara
    // default (kasus langka, hanya akun hasil Registrasi mandiri yang
    // belum sempat verifikasi), diisi & ditampilkan lewat
    // tampilkanBelumVerifikasi() di blok catch bawah.
    const belumVerifikasiBox = MugenUI.el("div", { style: "display:none;margin-top:8px;" });
    const btnSubmit = MugenUI.el("button", { class: "btn-primary", style: "width:100%;margin-top:16px;" }, "Masuk");

    const linkLupaPassword = MugenUI.el("a", { href: "#/lupa-password", style: "display:block;text-align:right;font-size:13px;margin-top:6px;" }, "Lupa Kata Sandi?");

    const form = MugenUI.el("form", {}, [
      MugenUI.el("label", {}, "Username"), inputUsername,
      MugenUI.el("label", {}, "Password"), inputPassword,
      linkLupaPassword,
      errorBox,
      tenantPickerBox,
      belumVerifikasiBox,
      btnSubmit,
    ]);

    function tampilkanBelumVerifikasi(email) {
      belumVerifikasiBox.innerHTML = "";
      belumVerifikasiBox.style.display = "";
      belumVerifikasiBox.appendChild(MugenUI.el("div", { class: "login-error" },
        "Email Anda belum diverifikasi. Silakan cek email Anda, atau kirim ulang link verifikasi."));
      const btnKirimUlang = MugenUI.el("button", { type: "button" }, "Kirim Ulang Email Verifikasi");
      btnKirimUlang.addEventListener("click", async () => {
        try {
          const res = await MugenUI.withButtonLoading(btnKirimUlang,
            () => MugenApi.post("/api/public/registration/resend-verification", { email }));
          MugenUI.toast(res.message || "Email verifikasi telah dikirim ulang.", "success", { force: true });
        } catch (e) {
          MugenUI.toast(e.message, "error");
        }
      });
      belumVerifikasiBox.appendChild(btnKirimUlang);
    }

    // PENTING (correctness): TIDAK mengirim slug toko yang "diingat" dari
    // login sebelumnya (state.js::getTenantSlug()) secara otomatis di
    // percobaan PERTAMA -- kalau perangkat ini sebelumnya dipakai untuk
    // toko lain (device bersama/berganti tempat kerja) dan username+
    // password yang diketik sekarang sebenarnya valid untuk toko BERBEDA,
    // mengirim slug lama akan salah scoping login jadi 401 "salah" walau
    // kredensialnya benar. tenantSlugTerpilih HANYA diisi lewat dua jalur
    // eksplisit di bawah: (1) pengguna menekan tombol toko di pemilih yang
    // muncul saat 409, atau (2) slug yang diingat KEBETULAN cocok dengan
    // salah satu kandidat 409 itu sendiri (auto-retry transparan, lihat
    // blok catch di bawah) -- jadi tidak pernah dikirim "buta".
    let tenantSlugTerpilih = null;

    function tampilkanPemilihToko(daftarToko, pesan) {
      tenantPickerBox.innerHTML = "";
      tenantPickerBox.style.display = "";
      tenantPickerBox.appendChild(
        MugenUI.el("div", { class: "login-tenant-picker-label" }, pesan)
      );
      daftarToko.forEach((t) => {
        const btn = MugenUI.el("button", { type: "button", class: "login-tenant-option" }, t.nama_barbershop);
        btn.addEventListener("click", () => {
          tenantSlugTerpilih = t.slug;
          form.requestSubmit();
        });
        tenantPickerBox.appendChild(btn);
      });
    }

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      errorBox.textContent = "";
      btnSubmit.disabled = true;
      btnSubmit.textContent = "Memproses...";
      try {
        const res = await MugenUI.withLoading(() => MugenApi.post("/api/auth/login", {
          username: inputUsername.value.trim(),
          password: inputPassword.value,
          tenant: tenantSlugTerpilih || undefined,
        }), { message: "Memproses login…" });
        MugenState.setSession(res.token, res.user, res.tenant);
        // FONDASI Multi-Tenant Phase 2.2: tenant baru saja "diketahui" lewat
        // login berhasil ini -- SATU refresh() tambahan (di luar yang
        // sudah dipanggil sekali saat app.js boot) supaya sidebar/Dashboard
        // langsung menampilkan branding TOKO YANG BENAR, bukan cache
        // sebelum login (mis. branding platform pada percobaan login
        // pertama di perangkat baru). Tidak di-await (sama seperti pola
        // MugenBookingNotif.refreshNow() di bawah) supaya tidak menunda
        // perpindahan ke Dashboard.
        MugenBrand.refresh();
        // FONDASI Multi-Tenant Phase 3: BEDA dari MugenBrand.refresh() di
        // atas (sengaja tidak di-await) -- akses_diblokir HARUS sudah
        // diketahui SEBELUM baris handle() di bawah supaya akun yang
        // subscription-nya diblokir TIDAK PERNAH sempat melihat dashboard
        // normal walau sekejap sebelum dialihkan ke halaman status (lihat
        // subscription.js, router.js).
        await MugenSubscription.refresh();
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
        // FONDASI Multi-Tenant Phase 2.0: 409 = ambigu, backend mengembalikan
        // {message, tenants: [...]} di e.detail.detail (BUKAN string biasa)
        // -- lihat routers/auth_router.py::login().
        const detail = e.detail && e.detail.detail;
        if (e.status === 409 && detail && Array.isArray(detail.tenants)) {
          // Auto-retry TRANSPARAN (tanpa menampilkan pemilih toko sama
          // sekali) kalau slug yang diingat dari login SEBELUMNYA di
          // perangkat ini kebetulan cocok dengan salah satu kandidat --
          // aman (BUKAN kirim "buta") karena backend sudah membuktikan
          // username+password ini valid untuk toko itu (salah satu dari
          // daftar `tenants` di respons 409 ini).
          const slugDiingat = MugenState.getTenantSlug();
          const cocok = slugDiingat && detail.tenants.some((t) => t.slug === slugDiingat);
          if (cocok && tenantSlugTerpilih !== slugDiingat) {
            tenantSlugTerpilih = slugDiingat;
            form.requestSubmit();
            return;
          }
          errorBox.textContent = "";
          belumVerifikasiBox.style.display = "none";
          tampilkanPemilihToko(detail.tenants, detail.message || "Pilih toko Anda:");
        } else if (e.status === 403 && detail && detail.code === "email_belum_terverifikasi") {
          // FITUR Verifikasi Email -- lihat routers/auth_router.py::login().
          tenantPickerBox.style.display = "none";
          errorBox.textContent = "";
          tampilkanBelumVerifikasi(detail.email || inputUsername.value.trim());
        } else {
          tenantPickerBox.style.display = "none";
          belumVerifikasiBox.style.display = "none";
          errorBox.textContent = (typeof detail === "string" && detail) || e.message;
        }
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
