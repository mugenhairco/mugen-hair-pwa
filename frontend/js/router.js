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
    MugenBrand.refresh(); // TAHAP 10: sinkronkan nama/logo terbaru ke sidebar setiap pindah halaman
    return main;
  }

  function resolveDashboardPage(user) {
    return user.role === "admin" ? PageDashboardOwner : PageDashboardBarber;
  }

  function handle() {
    const hash = location.hash || "#/dashboard";

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
    if (hash === "#/book" || hash.startsWith("#/book/") || hash.startsWith("#/book?")) {
      // REVISI UI/UX: Web Booking SENGAJA TIDAK mengikuti Dark Mode akun,
      // dipaksa di sini (bukan hanya di dalam book_public.js) supaya
      // benar dari titik NAVIGASI manapun -- termasuk kalau sebelumnya
      // sempat di halaman internal ber-Dark Mode lalu pindah ke sini
      // tanpa reload penuh (perilaku SPA biasa).
      MugenTheme.forceLight();
      appRoot.innerHTML = "";
      PageBookPublic.render(appRoot);
      return;
    }

    // REVISI UI/UX: terapkan ulang tema tersimpan setiap kali masuk ke
    // halaman INTERNAL (Login maupun setelah login) -- perlu diulang di
    // sini (bukan cukup sekali di boot lewat theme.js) supaya kalau user
    // sebelumnya sempat membuka Web Booking (dipaksa terang di atas) lalu
    // kembali ke aplikasi utama, Dark Mode akunnya aktif lagi dengan benar.
    MugenTheme.applyStored();

    const loggedIn = MugenState.isLoggedIn();

    if (!loggedIn) {
      appRoot.innerHTML = "";
      PageLogin.render(appRoot);
      return;
    }
    if (hash.startsWith("#/login")) {
      location.hash = "#/dashboard";
      return;
    }

    const user = MugenState.getUser();
    const content = shell();

    if (hash.startsWith("#/dashboard")) {
      resolveDashboardPage(user).render(content);
    } else if (hash.startsWith("#/input-data")) {
      // REVISI: khusus admin sekarang (Barber tidak lagi mengakses Input
      // Data). Perlindungan sebenarnya tetap di backend (require_admin di
      // setiap endpoint /api/input-data/*).
      if (user.role !== "admin") {
        location.hash = "#/dashboard";
        return;
      }
      PageInputData.render(content);
    } else if (hash.startsWith("#/rekap")) {
      PageRekap.render(content);
    } else if (hash.startsWith("#/pengeluaran")) {
      // Tahap 9: halaman khusus admin. Barber tidak diberi link ini di nav.js,
      // tapi kalau nekat buka lewat URL langsung, lempar ke dashboard di sini
      // juga (perlindungan sebenarnya tetap di backend: require_admin).
      if (user.role !== "admin") {
        location.hash = "#/dashboard";
        return;
      }
      PagePengeluaran.render(content);
    } else if (hash.startsWith("#/pengaturan")) {
      // Tahap 10: halaman khusus admin. Perlindungan sebenarnya tetap di
      // backend (require_admin di setiap endpoint /api/pengaturan/*).
      if (user.role !== "admin") {
        location.hash = "#/dashboard";
        return;
      }
      PagePengaturan.render(content);
    } else if (hash.startsWith("#/produk")) {
      // Tahap 11: halaman khusus admin (persediaan toko, bukan milik barber
      // manapun). Perlindungan sebenarnya tetap di backend (require_admin di
      // setiap endpoint /api/produk/*).
      if (user.role !== "admin") {
        location.hash = "#/dashboard";
        return;
      }
      PageProduk.render(content);
    } else if (hash.startsWith("#/sinkronisasi")) {
      // Tahap 12: halaman khusus admin (status sinkron & backup/restore
      // adalah operasional toko, bukan milik barber manapun). Perlindungan
      // sebenarnya tetap di backend (require_admin di setiap endpoint
      // /api/sync/* dan /api/pengaturan/backup/*).
      if (user.role !== "admin") {
        location.hash = "#/dashboard";
        return;
      }
      PageSinkronisasi.render(content);
    } else if (hash.startsWith("#/booking")) {
      // BOOKING: halaman internal (admin+barber). Admin/Owner full access
      // (Booking List, Calendar, Operating Hours, Barber Holiday, Closed
      // Slot, Payment Settings, Booking Settings); Barber hanya lihat
      // booking miliknya sendiri -- pembagian tab persis dilakukan DI
      // DALAM booking.js sendiri (mengikuti user.role), bukan di sini.
      // Perlindungan sebenarnya tetap di backend (require_admin/
      // require_barber di setiap endpoint /api/booking/*).
      PageBooking.render(content);
    } else {
      location.hash = "#/dashboard";
    }
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
