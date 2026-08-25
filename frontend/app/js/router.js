// router.js — router hash sederhana (tanpa library). Setiap navigasi:
// 1. Kalau belum login -> paksa ke #/login.
// 2. Kalau sudah login tapi buka #/login -> lempar ke #/dashboard.
// 3. Render ulang sidebar (nav.js) + halaman yang sesuai ke <main id="content">.
// TAHAP 13: tombol hamburger (buka/tutup sidebar di layar sempit) + backdrop
// dipasang di sini -- CSS-nya (.hamburger/.sidebar.open/.sidebar-backdrop)
// sudah ada sejak awal tapi belum pernah dihubungkan ke elemen/JS apa pun,
// jadi di layar tablet/HP sidebar sebelumnya tidak bisa dibuka sama sekali.

const MugenRouter = (() => {
  const appRoot = document.getElementById("app");

  // REVISI UI/UX: true HANYA untuk panggilan handle() PERTAMA sejak
  // halaman dimuat -- dipakai untuk membedakan "aplikasi baru dibuka"
  // dari navigasi/redirect internal berikutnya (termasuk lempar ke Login
  // gara-gara sesi kedaluwarsa, lihat api.js).
  let _firstHandle = true;

  // REVISI UI/UX Premium: posisi scroll SETIAP hash yang pernah dikunjungi
  // sesi ini (in-memory, BUKAN sessionStorage -- cukup bertahan selama SPA
  // ini hidup, "kembali ke halaman sebelumnya" tidak berarti lintas reload
  // penuh). shell() menghapus <main id="content"> lama total tiap navigasi
  // (lihat catatan shell() di bawah, TIDAK diubah), jadi posisi scroll-nya
  // HARUS disimpan di sini SEBELUM itu terjadi, lalu dipulihkan setelah
  // halaman baru selesai dirender.
  const _scrollPos = new Map();
  let _lastHash = null;

  // FITUR Kompatibilitas URL Booking (Instagram Bio dkk): "/book" atau
  // "/app/book" (PATH ASLI, BUKAN hash "#/book") -- render.yaml me-rewrite
  // KEDUA path ini ke app/index.html yang sama (lihat komentar routes di
  // sana), jadi begitu index.html ini dimuat lewat salah satu path itu,
  // location.hash-nya KOSONG (URL asli di address bar tidak pernah punya
  // "#" sama sekali). Dicek lewat location.pathname, TERPISAH dari
  // pengecekan hash "#/book" yang sudah ada di bawah -- keduanya harus
  // tetap didukung bersamaan (hash lama untuk link yang sudah kadung
  // disebar, path baru untuk link baru yang aman ditempel di Instagram
  // Bio). Pola startsWith("/book/")/("/app/book/") menjaga cakupannya
  // SAMA PERSIS dengan pola hash "#/book/..." di bawah. Duplikasi kecil
  // yang SAMA persis ada di tenant_guard.js (dipanggil lebih dulu saat
  // boot) -- pola konsisten dengan gaya codebase ini: helper kecil per-
  // modul, bukan cross-import lintas closure.
  function pathAdalahHalamanBook() {
    const p = location.pathname;
    return p === "/book" || p.startsWith("/book/") || p === "/app/book" || p.startsWith("/app/book/");
  }

  function _simpanScrollLama() {
    const contentLama = document.getElementById("content");
    if (contentLama && _lastHash) _scrollPos.set(_lastHash, contentLama.scrollTop);
  }

  function _pulihkanScroll(hash, content) {
    const posisi = _scrollPos.get(hash);
    if (!posisi) return;
    // requestAnimationFrame: beri browser satu frame untuk selesai layout
    // konten baru (tinggi tabel/daftar dst) SEBELUM scrollTop diterapkan --
    // menerapkannya sinkron langsung setelah render() bisa gagal kalau
    // tinggi konten belum final.
    requestAnimationFrame(() => { content.scrollTop = posisi; });
  }

  // PERBAIKAN PERFORMA (loading awal lambat): render halaman yang modul
  // js/pages/-nya dimuat DINAMIS lewat page_loader.js (lihat catatan
  // lengkap di sana), BUKAN lewat <script> biasa di index.html lagi --
  // dipakai di SETIAP cabang di bawah yang merender salah satu dari 20
  // modul besar itu, supaya polanya konsisten satu tempat (skeleton
  // sementara sambil menunggu, lalu render() sungguhan, atau pesan error
  // jelas kalau gagal dimuat -- BUKAN halaman kosong diam-diam). Selalu
  // mengembalikan Promise, jadi tetap kompatibel dengan pola
  // `Promise.resolve(renderResult).then(...)` yang sudah ada di akhir
  // handle() (pola itu SUDAH menerima renderResult sinkron ATAU async
  // sebelum revisi ini, tidak perlu diubah).
  function _renderLazy(content, globalName, src) {
    content.appendChild(MugenUI.skeleton("card", { lines: 4 }));
    return MugenPageLoader.ensure(globalName, src)
      .then(() => window[globalName].render(content))
      .catch((err) => {
        content.innerHTML = "";
        content.appendChild(MugenUI.errorState("Gagal memuat halaman ini. Cek koneksi internet Anda, lalu coba lagi."));
        console.error(err);
      });
  }

  function shell() {
    appRoot.innerHTML = "";
    const wrap = MugenUI.el("div", { class: "app-shell" });
    const sidebar = MugenNav.render(location.hash || "#/dashboard");
    const backdrop = MugenUI.el("div", { class: "sidebar-backdrop" });
    const hamburger = MugenUI.el("button", { class: "hamburger", "aria-label": "Buka menu", type: "button" }, "☰");
    const main = MugenUI.el("main", { class: "content", id: "content" });

    function closeSidebar() {
      sidebar.classList.remove("open");
      backdrop.classList.remove("open");
    }
    hamburger.addEventListener("click", () => {
      sidebar.classList.toggle("open");
      backdrop.classList.toggle("open");
    });
    backdrop.addEventListener("click", closeSidebar);
    // Tutup otomatis begitu satu menu dipilih (layar sempit) supaya user
    // tidak perlu tap backdrop lagi tiap pindah halaman.
    sidebar.addEventListener("click", (e) => {
      if (e.target.tagName === "A") closeSidebar();
    });

    wrap.appendChild(sidebar);
    wrap.appendChild(backdrop);
    wrap.appendChild(hamburger);
    wrap.appendChild(main);
    appRoot.appendChild(wrap);
    // FONDASI Multi-Tenant Phase 2.2: applyToDom() SAJA (dari cache), BUKAN
    // refresh() -- shell() dipanggil di SETIAP pindah halaman/menu, dan
    // spesifikasi Phase 2.2 eksplisit melarang request branding berulang
    // tiap navigasi ("Branding cukup diambil sekali saat aplikasi dimuat").
    // Data terbaru sudah cukup di-refresh() SEKALI saat app.js boot + SEKALI
    // lagi tepat setelah login berhasil (lihat login.js).
    MugenBrand.applyToDom();
    return main;
  }

  function resolveDashboardPage(user) {
    // REVISI Hak Akses Admin: 'staff' (Admin) melihat versi Dashboard Owner
    // yang sudah difilter kartunya oleh backend sesuai hak akses yang
    // diatur Owner (lihat routers/dashboard.py::_filter_dashboard_untuk_staff)
    // -- BUKAN Dashboard Barber (itu khusus akun ber-role 'barber').
    // PERBAIKAN PERFORMA: mengembalikan {globalName, src} (bukan langsung
    // objek Page-nya lagi) -- dashboard_owner.js/dashboard_barber.js
    // sekarang dimuat DINAMIS lewat _renderLazy(), lihat pemanggilnya di
    // handle().
    return (user.role === "admin" || user.role === "staff")
      ? { globalName: "PageDashboardOwner", src: "js/pages/dashboard_owner.js" }
      : { globalName: "PageDashboardBarber", src: "js/pages/dashboard_barber.js" };
  }

  function handle() {
    const hash = location.hash || "#/dashboard";
    // BUGFIX Landing Page /book dirender dobel: hashSebelumnya diambil
    // SEBELUM _lastHash ditimpa di bawah -- dipakai HANYA oleh guard #/book
    // (lihat komentar di sana), tidak mengubah perilaku _lastHash yang sudah
    // ada untuk fitur scroll.
    const hashSebelumnya = _lastHash;
    // REVISI UI/UX Premium: simpan scroll halaman SEBELUM ditinggalkan,
    // key-nya hash SEBELUMNYA (_lastHash) -- lalu _lastHash langsung
    // diperbarui ke hash SEKARANG supaya siap dipakai panggilan handle()
    // berikutnya, SEBELUM shell() (kalau dipanggil di bawah) sempat
    // menghapus DOM lama. Aman dipanggil untuk hash APA PUN (termasuk
    // /book yang tidak memakai shell() sama sekali) -- getElementById
    // sekadar mengembalikan null kalau elemennya tidak ada.
    _simpanScrollLama();
    _lastHash = hash;

    // REVISI UI/UX: dicek SEKALI SAJA (panggilan handle() pertama). Kalau
    // saat itu belum ada sesi tersimpan sama sekali, ini benar-benar
    // "aplikasi baru dibuka" -- tandai supaya halaman Login memutar
    // animasi Slide+Fade. Kalau ADA sesi tersimpan (walau nanti ternyata
    // kedaluwarsa di server), JANGAN ditandai -- biar kalau ujung-ujungnya
    // dilempar ke Login karena 401, itu tidak dianggap "pertama dibuka".
    if (_firstHandle) {
      _firstHandle = false;
      if (!MugenState.isLoggedIn()) MugenState.markLoginEntrance();
    }

    // BOOKING: halaman publik /book, TANPA login sama sekali -- dicek PALING
    // AWAL, sebelum pengecekan isLoggedIn() di bawah (yang sebelumnya selalu
    // memaksa ke halaman Login untuk hash APAPUN kalau belum login). Render
    // langsung ke appRoot (bukan lewat shell()/sidebar), sama seperti
    // PageLogin -- customer yang booking bukan bagian dari aplikasi internal.
    // BUGFIX: match harus PRESIS "#/book" (atau "#/book/..."), BUKAN
    // startsWith("#/book") saja -- kalau tidak, "#/booking" (menu internal
    // admin+barber, lihat bagian bawah handle()) ikut ketangkap di sini juga
    // karena "booking" kebetulan diawali huruf "book", sehingga halaman
    // Booking internal itu jadi ikut ditampilkan tanpa login sama sekali.
    if (pathAdalahHalamanBook() || hash === "#/book" || hash.startsWith("#/book/") || hash.startsWith("#/book?")) {
      // REVISI UI/UX: Web Booking SENGAJA TIDAK mengikuti Dark Mode akun,
      // dipaksa di sini (bukan hanya di dalam book_public.js) supaya
      // benar dari titik NAVIGASI manapun -- termasuk kalau sebelumnya
      // sempat di halaman internal ber-Dark Mode lalu pindah ke sini
      // tanpa reload penuh (perilaku SPA biasa).
      MugenTheme.forceLight();
      // BUGFIX "Landing Page dobel": app.js SENGAJA memanggil handle() DUA
      // KALI setiap boot -- sekali langsung lewat MugenRouter.init(), lalu
      // sekali lagi lewat MugenSubscription.refresh().then(() =>
      // MugenRouter.handle()) supaya halaman INTERNAL yang bergantung ke
      // status blokir subscription (cache akses_diblokir) ikut ter-refresh
      // (lihat komentar app.js). /book tidak pernah butuh panggilan kedua
      // itu -- subscription-nya dicek sendiri lewat endpoint terpisah
      // (/api/public/booking/subscription-status di dalam
      // PageBookPublic.render()). Tanpa guard ini, panggilan kedua memanggil
      // PageBookPublic.render(appRoot) LAGI sebelum render pertama selesai
      // (keduanya penuh operasi async), dan karena render() TIDAK menghapus
      // isi appRoot milik pemanggil lain, appRoot berakhir berisi DUA salinan
      // penuh halaman (Hero/About/Opening Hours/Book Appointment dst
      // masing-masing tampil dua kali, seperti "halaman kembar"). Guard:
      // hash yang PERSIS SAMA dengan panggilan handle() sebelumnya (tanpa
      // ada navigasi lain di antaranya) tidak perlu dirender ulang dari nol
      // -- navigasi baru yang sungguhan (termasuk kembali ke /book setelah
      // sempat pindah ke hash lain) selalu punya hashSebelumnya yang beda,
      // jadi tetap dirender seperti biasa.
      if (hash === hashSebelumnya) return;
      appRoot.innerHTML = "";
      // PERBAIKAN PERFORMA: book_public.js (halaman booking publik customer,
      // puluhan KB) dimuat DINAMIS di sini -- Owner/Admin/Barber yang login
      // ke aplikasi internal TIDAK PERNAH butuh file ini sama sekali, jadi
      // sebelumnya selalu ikut terunduh sia-sia di awal untuk mereka juga.
      appRoot.appendChild(MugenUI.el("div", { class: "mugen-state" }, "Memuat..."));
      MugenPageLoader.ensure("PageBookPublic", "js/pages/book_public.js")
        .then(() => { appRoot.innerHTML = ""; PageBookPublic.render(appRoot); })
        .catch((err) => {
          appRoot.innerHTML = "";
          appRoot.appendChild(MugenUI.errorState("Gagal memuat halaman. Cek koneksi internet Anda, lalu muat ulang halaman."));
          console.error(err);
        });
      return;
    }

    // FITUR Email, Verifikasi Email, Lupa Kata Sandi: tiga halaman PUBLIK
    // murni berbasis token dari link email (?token=... di DALAM hash,
    // lihat MugenUI.ambilQueryHash()) -- dicek PALING AWAL sama seperti
    // #/book di atas (SEBELUM pengecekan isLoggedIn()) supaya link email
    // tetap berfungsi APA PUN status sesi saat ini (termasuk kalau
    // kebetulan device itu SEDANG login sebagai akun lain).
    if (hash.startsWith("#/verify-email")) {
      appRoot.innerHTML = "";
      PageVerifyEmail.render(appRoot);
      return;
    }
    if (hash.startsWith("#/reset-password")) {
      appRoot.innerHTML = "";
      PageResetPassword.render(appRoot);
      return;
    }
    if (hash.startsWith("#/lupa-password")) {
      appRoot.innerHTML = "";
      PageLupaPassword.render(appRoot);
      return;
    }

    // REVISI STRUKTUR WEBSITE CONTENT: watermark developer BESAR (dev-
    // watermark-bg, di luar #app) disembunyikan KHUSUS selama di /book --
    // "Website hanya menggunakan background yang dipilih oleh Owner" tapi
    // kredit developer tetap wajib ada lewat watermark KECIL footer
    // (dev-watermark-footer), yang TIDAK disentuh sama sekali di sini.
    // Dipulihkan di sini juga (lapis pertahanan pertama, sebelum
    // MugenTheme.applyStored() di bawah) supaya benar dari titik navigasi
    // manapun -- book_public.js sendiri sudah menambah class ini lagi
    // sebagai lapis pertahanan KEDUA (sama seperti pola forceLight()).
    document.body.classList.remove("book-public-active");

    // REVISI UI/UX: terapkan ulang tema tersimpan setiap kali masuk ke
    // halaman INTERNAL (Login maupun setelah login) -- perlu diulang di
    // sini (bukan cukup sekali di boot lewat theme.js) supaya kalau user
    // sebelumnya sempat membuka Web Booking (dipaksa terang di atas) lalu
    // kembali ke aplikasi utama, Dark Mode akunnya aktif lagi dengan benar.
    MugenTheme.applyStored();

    const loggedIn = MugenState.isLoggedIn();

    if (!loggedIn) {
      appRoot.innerHTML = "";
      // FONDASI Multi-Tenant Phase 5 (Landing Page SaaS): Register
      // self-service dari Landing Page publik (tombol "Get Started" ->
      // /app/#/register) -- halaman PENUH sama seperti Login, TANPA sesi.
      if (hash.startsWith("#/register")) {
        PageRegister.render(appRoot);
      } else {
        PageLogin.render(appRoot);
      }
      return;
    }
    if (hash.startsWith("#/login") || hash.startsWith("#/register")) {
      location.hash = "#/dashboard";
      return;
    }

    const user = MugenState.getUser();

    // FONDASI Multi-Tenant Phase 2.1: akun 'superadmin' (tenant_id=NULL)
    // TIDAK punya akses ke wilayah tenant mana pun (backend menolak lewat
    // get_current_tenant_id(), lihat auth.py) -- satu-satunya halaman yang
    // relevan untuknya adalah Kelola Tenant, dirender untuk hash APA PUN
    // yang diminta (superadmin tidak punya menu lain untuk dituju).
    if (user.role === "superadmin") {
      const content = shell();
      // REVISI UI/UX Premium (bugfix): render() halaman ASYNC (fetch data
      // dulu sebelum konten asli terpasang) -- _pulihkanScroll() TIDAK bisa
      // dipanggil langsung sinkron di sini, satu requestAnimationFrame akan
      // keburu jalan SEBELUM konten asli (dan tinggi sebenarnya) terpasang,
      // sehingga scrollTop yang diterapkan hilang lagi begitu render selesai
      // dan mengganti isi konten. Dirantai lewat Promise.resolve(...).then()
      // supaya jalan SETELAH render() (async ATAU sync, keduanya aman)
      // benar-benar selesai.
      Promise.resolve(_renderLazy(content, "PageSuperadmin", "js/pages/superadmin.js")).then(() => _pulihkanScroll(hash, content));
      return;
    }

    // FONDASI Multi-Tenant Phase 3: tenant yang subscription-nya Expired/
    // Suspended/Cancelled dialihkan ke halaman status untuk HASH APA PUN
    // (pola sama seperti superadmin di atas) -- Owner/Admin/Barber toko itu
    // TIDAK bisa mengakses menu lain mana pun selama diblokir, HANYA
    // halaman ini (lihat pages/subscription_blocked.js). Dirender LANGSUNG
    // ke appRoot (BUKAN lewat shell()) supaya sidebar sama sekali tidak
    // ikut tampil -- data akses_diblokir dari cache MugenSubscription
    // (lihat subscription.js, di-refresh() app.js/login.js), BUKAN dicek
    // ulang lewat API di sini (handle() SINKRON, tidak bisa menunggu fetch).
    // FONDASI Multi-Tenant Phase 5: pengecualian SEMPIT -- #/billing TETAP
    // bisa diakses walau diblokir, supaya tenant yang BARU Register (status
    // 'expired' by design, lihat routers/tenant_registration.py) bisa
    // langsung memilih paket & bayar sendiri TANPA perlu Super Admin
    // mengaktifkan manual dulu. HASH lain APA PUN selain ini tetap
    // dipaksa ke halaman blocked persis seperti sebelumnya (self-correcting:
    // begitu user pindah ke menu lain, blokir langsung berlaku lagi).
    if (MugenSubscription.aksesDiblokir() && !hash.startsWith("#/billing")) {
      appRoot.innerHTML = "";
      PageSubscriptionBlocked.render(appRoot);
      return;
    }

    const content = shell();
    // REVISI UI/UX Premium (bugfix): lihat catatan Promise.resolve(...).then()
    // di cabang superadmin di atas -- alasan sama persis berlaku di sini,
    // `renderResult` ditangkap per-cabang lalu di-rantai SEKALI di bawah
    // (baris _pulihkanScroll di akhir fungsi ini).
    let renderResult;

    if (hash.startsWith("#/dashboard")) {
      { const dp = resolveDashboardPage(user); renderResult = _renderLazy(content, dp.globalName, dp.src); }
    } else if (hash.startsWith("#/input-data")) {
      // REVISI: khusus Owner/Admin (Barber tidak lagi mengakses Input Data).
      // REVISI Hak Akses Admin (kedua): 'staff' (Admin) sekarang akses PENUH
      // sama persis seperti Owner, tanpa sistem izin. Perlindungan
      // sebenarnya tetap di backend (require_owner_or_staff di setiap
      // endpoint /api/input-data/*).
      if (user.role !== "admin" && user.role !== "staff") {
        location.hash = "#/dashboard";
        return;
      }
      renderResult = _renderLazy(content, "PageInputData", "js/pages/input_data.js");
    } else if (hash.startsWith("#/rekap")) {
      // REVISI Hak Akses Admin (kedua): Rekap sekarang akses PENUH untuk
      // 'staff' (Admin) sama persis seperti Owner, tanpa sistem izin --
      // Barber tetap dibatasi ke data miliknya sendiri (lihat routers/rekap.py).
      renderResult = _renderLazy(content, "PageRekap", "js/pages/rekap.js");
    } else if (hash.startsWith("#/karyawan/slip-gaji")) {
      // Modul Karyawan (Fase 1): Owner/'staff' (kalau diberi izin
      // izin_slip_gaji) mengelola SEMUA barber; Barber hanya lihat riwayat
      // miliknya sendiri, read-only -- dibedakan DI DALAM slip_gaji.js
      // lewat user.role, sama seperti pola Rekap/Booking. Perlindungan
      // sebenarnya tetap di backend (routers/slip_gaji.py).
      renderResult = _renderLazy(content, "PageSlipGaji", "js/pages/slip_gaji.js");
    } else if (hash.startsWith("#/karyawan/kasbon")) {
      // Modul Karyawan (Fase 2): Owner/'staff' (kalau diberi izin
      // izin_kasbon) mengelola kasbon SEMUA barber; Barber hanya lihat
      // kasbon & riwayat pembayaran miliknya sendiri, read-only --
      // dibedakan DI DALAM kasbon.js lewat user.role, sama seperti
      // slip_gaji.js. Perlindungan sebenarnya tetap di backend
      // (routers/kasbon.py).
      renderResult = _renderLazy(content, "PageKasbon", "js/pages/kasbon.js");
    } else if (hash.startsWith("#/karyawan/komisi")) {
      // Modul Karyawan (Fase 3): Owner/'staff' (kalau diberi izin
      // izin_komisi) mengelola penyesuaian komisi SEMUA barber; Barber
      // hanya lihat riwayat & penyesuaian miliknya sendiri, read-only --
      // dibedakan DI DALAM komisi.js lewat user.role, sama seperti
      // kasbon.js. Perlindungan sebenarnya tetap di backend
      // (routers/komisi.py).
      renderResult = _renderLazy(content, "PageKomisi", "js/pages/komisi.js");
    } else if (hash.startsWith("#/karyawan/reimburse")) {
      // Modul Karyawan (Fase 4): self-service -- Barber boleh mengajukan/
      // mengedit/menghapus klaim MILIKNYA SENDIRI (selama Pending) TANPA
      // perlu izin apa pun; Owner/'staff' (izin_reimburse) melihat &
      // menyetujui/menolak klaim SEMUA barber. Dibedakan DI DALAM
      // reimburse.js lewat user.role. Perlindungan sebenarnya tetap di
      // backend (routers/reimburse.py).
      renderResult = _renderLazy(content, "PageReimburse", "js/pages/reimburse.js");
    } else if (hash.startsWith("#/karyawan/izin-cuti")) {
      // Modul Karyawan (Fase 5): pola akses SAMA PERSIS reimburse.js
      // (self-service). Perlindungan sebenarnya tetap di backend
      // (routers/izin_cuti.py).
      renderResult = _renderLazy(content, "PageIzinCuti", "js/pages/izin_cuti.js");
    } else if (hash.startsWith("#/absensi")) {
      // Modul BARU Absensi (GPS Check In/Out Geofencing): berdiri sendiri,
      // TIDAK terhubung ke Izin & Cuti/Barber Holiday. Pola akses sama
      // seperti izin-cuti.js (self-service Barber vs Owner/Admin -- semua
      // role boleh lihat halamannya sendiri-sendiri, dibedakan DI DALAM
      // absensi.js lewat user.role). Perlindungan sebenarnya tetap di
      // backend (routers/attendance.py).
      // AUDIT (enforcement paket/subscription -- REVISI feedback Owner):
      // gerbang fitur "absensi" DIPINDAH ke DALAM absensi.js::render()
      // (judul "Absensi" tetap tampil dulu, baru kartu upgrade -- BUKAN
      // lagi mengganti seluruh `content` di sini, supaya terasa seperti
      // halaman sungguhan yang terkunci, bukan layar kosong). Menu di
      // sidebar TETAP tampil, diredupkan + ikon gembok (bukan disembunyikan
      // -- lihat nav.js::_terkunciFitur()).
      renderResult = _renderLazy(content, "PageAbsensi", "js/pages/absensi.js");
    } else if (hash.startsWith("#/keuangan/pemasukan")) {
      // Modul Keuangan (Fase 1): data operasional TOKO, Owner/'staff' akses
      // PENUH tanpa sistem izin, Barber tidak ada akses -- pola sama
      // persis Pengeluaran di bawah. Perlindungan sebenarnya tetap di
      // backend (require_owner_or_staff di setiap endpoint /api/pemasukan/*).
      if (user.role !== "admin" && user.role !== "staff") {
        location.hash = "#/dashboard";
        return;
      }
      renderResult = _renderLazy(content, "PagePemasukan", "js/pages/pemasukan.js");
    } else if (hash.startsWith("#/keuangan/uang-kas")) {
      // Modul Keuangan (Fase 2, semula Transfer Kas/Bank -- dihapus &
      // diganti Uang Kas): pola akses SAMA PERSIS Pemasukan di atas.
      // Perlindungan sebenarnya tetap di backend (require_owner_or_staff
      // di setiap endpoint /api/uang-kas/*).
      if (user.role !== "admin" && user.role !== "staff") {
        location.hash = "#/dashboard";
        return;
      }
      renderResult = _renderLazy(content, "PageUangKas", "js/pages/uang_kas.js");
    } else if (hash.startsWith("#/keuangan/riwayat-transaksi")) {
      // Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant:
      // riwayat transaksi Payment Gateway booking TOKO INI SENDIRI (lihat
      // pages/riwayat_transaksi.js) -- pola akses SAMA PERSIS Pemasukan/
      // Uang Kas di atas. Perlindungan sebenarnya tetap di backend
      // (require_owner_or_staff di /api/booking/transactions, SELALU
      // di-scope tenant_id dari akun login).
      if (user.role !== "admin" && user.role !== "staff") {
        location.hash = "#/dashboard";
        return;
      }
      renderResult = _renderLazy(content, "PageRiwayatTransaksi", "js/pages/riwayat_transaksi.js");
    } else if (hash.startsWith("#/settlement-faspay")) {
      // Settlement Faspay per Terminal (Tenant): closing harian transaksi
      // Faspay SNAP Advance toko INI SENDIRI (lihat pages/settlement_faspay.js)
      // -- pola akses SAMA PERSIS Riwayat Transaksi di atas. Perlindungan
      // sebenarnya tetap di backend (require_menu_read("settlement_faspay")/
      // require_permission("izin_settlement_faspay") di routers/
      // faspay_settlement.py, SELALU di-scope tenant_id dari akun login).
      if (user.role !== "admin" && user.role !== "staff") {
        location.hash = "#/dashboard";
        return;
      }
      renderResult = _renderLazy(content, "PageSettlementFaspay", "js/pages/settlement_faspay.js");
    } else if (hash.startsWith("#/pengeluaran")) {
      // Tahap 9 + REVISI Hak Akses Admin (kedua): Owner dan 'staff' (Admin)
      // sekarang akses PENUH sama persis (tanpa sistem izin), Barber tidak.
      // Perlindungan sebenarnya tetap di backend (require_owner_or_staff di
      // setiap endpoint /api/pengeluaran/*).
      if (user.role !== "admin" && user.role !== "staff") {
        location.hash = "#/dashboard";
        return;
      }
      renderResult = _renderLazy(content, "PagePengeluaran", "js/pages/pengeluaran.js");
    } else if (hash.startsWith("#/whatsapp")) {
      // REVISI (feedback Owner): dulu tab di dalam Setting, dipindah jadi
      // menu utama sendiri (lihat pages/whatsapp.js) -- KHUSUS Owner, pola
      // role-check SAMA seperti #/billing di bawah. Gerbang fitur
      // "whatsapp_reminder" ada DI DALAM whatsapp.js::render() sendiri
      // (pola sama seperti #/absensi di atas), bukan di sini.
      if (user.role !== "admin") {
        location.hash = "#/dashboard";
        return;
      }
      renderResult = _renderLazy(content, "PageWhatsapp", "js/pages/whatsapp.js");
    } else if (hash.startsWith("#/billing")) {
      // FONDASI Multi-Tenant Phase 4: KHUSUS Owner (require_admin di
      // BACKEND juga -- routers/billing.py -- 'staff' TIDAK ikut, sama
      // seperti tab Subscription Phase 3 di pengaturan.js).
      if (user.role !== "admin") {
        location.hash = "#/dashboard";
        return;
      }
      renderResult = _renderLazy(content, "PageBilling", "js/pages/billing.js");
    } else if (hash.startsWith("#/pengaturan")) {
      // Tahap 10 + REVISI Hak Akses Admin: Owner selalu boleh; 'staff' (Admin)
      // boleh MASUK menu Setting (tab yang tampil difilter di dalam
      // pengaturan.js sesuai hak akses yang diatur Owner), Barber tidak.
      // Perlindungan sebenarnya tetap di backend (require_admin/
      // require_permission di setiap endpoint /api/pengaturan/*).
      if (user.role !== "admin" && user.role !== "staff") {
        location.hash = "#/dashboard";
        return;
      }
      renderResult = _renderLazy(content, "PagePengaturan", "js/pages/pengaturan.js");
    } else if (hash.startsWith("#/produk")) {
      // Tahap 11: halaman khusus Owner/Admin (persediaan toko, bukan milik
      // barber manapun). REVISI Hak Akses Admin (kedua): 'staff' (Admin)
      // sekarang akses PENUH sama persis seperti Owner, tanpa sistem izin.
      // Perlindungan sebenarnya tetap di backend (require_owner_or_staff di
      // setiap endpoint /api/produk/*).
      if (user.role !== "admin" && user.role !== "staff") {
        location.hash = "#/dashboard";
        return;
      }
      renderResult = _renderLazy(content, "PageProduk", "js/pages/produk.js");
    } else if (hash.startsWith("#/booking")) {
      // BOOKING: halaman internal (Owner/Admin/Barber). Owner dan 'staff'
      // (Admin) full access SAMA PERSIS (Booking List, Calendar, Operating
      // Hours, Barber Holiday, Closed Slot, Payment Settings, Booking
      // Settings -- REVISI Hak Akses Admin kedua: tanpa sistem izin sama
      // sekali); Barber hanya lihat booking miliknya sendiri -- pembagian
      // tab persis dilakukan DI DALAM booking.js sendiri (mengikuti
      // user.role), bukan di sini. Perlindungan sebenarnya tetap di backend
      // (require_owner_or_staff/require_barber di setiap endpoint /api/booking/*).
      renderResult = _renderLazy(content, "PageBooking", "js/pages/booking.js");
    } else {
      location.hash = "#/dashboard";
      return;
    }
    Promise.resolve(renderResult).then(() => _pulihkanScroll(hash, content));
    // REVISI Efisiensi Polling: badge Izin & Cuti (izin_notif.js) TIDAK
    // lagi polling periodik -- di-refresh SEKALI di sini tiap kali user
    // benar-benar berpindah menu (handle() dipanggil SETIAP klik link
    // sidebar/navigasi SPA), "ada aksi klik" sesuai permintaan Owner.
    // Aman dipanggil untuk role apa pun -- modul ini sendiri yang
    // memeriksa (lewat _bolehPoll()) apakah user admin/staff.
    if (typeof MugenIzinNotif !== "undefined") MugenIzinNotif.refreshNow();
  }

  function init() {
    window.addEventListener("hashchange", handle);
    handle();
  }

  // BUGFIX: `handle` sebelumnya TIDAK diekspos di sini (hanya `init`),
  // padahal login.js SUDAH lama memanggil MugenRouter.handle() secara
  // eksplisit untuk kasus edge-case yang dijelaskan di komentarnya (hash
  // sudah persis "#/dashboard" sehingga event "hashchange" tidak akan
  // terpicu) -- akibatnya panggilan itu selalu throw TypeError diam-diam
  // (langsung tertangkap try/catch login.js, tidak pernah terlihat sebagai
  // error nyata) dan kode SETELAH panggilan itu di login.js tidak pernah
  // sempat jalan. Selama ini "diselamatkan" oleh fallback: hash yang
  // BERUBAH (kasus normal, dari "#/login" ke "#/dashboard") tetap memicu
  // listener hashchange di atas secara terpisah, jadi navigasinya terlihat
  // berhasil -- tapi kasus edge-case yang komentar itu maksudkan (dan kode
  // apa pun yang taruh SETELAH baris itu) diam-diam tidak pernah berjalan.
  return { init, handle };
})();
