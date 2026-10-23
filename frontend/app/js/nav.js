// nav.js — sidebar. Menu Pengeluaran (Tahap 9), Setting (Tahap 10), Produk
// (Tahap 11), dan Sinkronisasi (Tahap 12) sudah aktif, KHUSUS admin —
// backend juga menolak barber lewat require_admin, ini bukan satu-satunya
// lapis perlindungan.
// Nama & logo barbershop (TAHAP 10) TIDAK hardcode di sini — dibaca lewat
// brand.js (MugenBrand) dari /api/pengaturan/identitas.

const MugenNav = (() => {
  // REVISI UI/UX Premium: Sidebar Collapse (desktop) -- BARU TOTAL,
  // sebelumnya sidebar hanya punya mode buka/tutup mobile (hamburger,
  // TIDAK disentuh di sini). Preferensi murni per-perangkat (localStorage,
  // BUKAN disinkronkan ke server seperti Dark Mode di theme.js -- collapse
  // sidebar cuma masuk akal untuk layar lebar tempat sidebar ada, tidak
  // ada alasan menyamakannya lintas perangkat).
  const COLLAPSE_KEY = "mugen_sidebar_collapsed";

  function _collapsedTersimpan() {
    return localStorage.getItem(COLLAPSE_KEY) === "1";
  }

  // Inisial 2 huruf dari label menu -- dipakai lingkaran kecil saat
  // sidebar collapsed (BUKAN ikon custom baru, codebase ini tidak punya
  // aset ikon per menu sama sekali; menambah SVG/gambar untuk tiap item
  // di luar cakupan revisi motion/animasi murni).
  function _inisialLabel(label) {
    const kata = String(label || "").trim().split(/\s+/).filter(Boolean);
    if (kata.length >= 2) return (kata[0][0] + kata[1][0]).toUpperCase();
    return (kata[0] || "?").slice(0, 2).toUpperCase();
  }


  // REVISI BESAR Hak Akses (hapus Role "Admin" bawaan, lihat backend
  // permissions.py::PERMISSION_TREE): SEMUA menu (KECUALI Billing & Hak
  // Akses User, lihat renderHakAksesAdmin() di pengaturan.js) SEKARANG
  // grantable Owner ke Role manapun -- `roles` di bawah TETAP dipakai
  // sebagai gerbang PERTAMA (tipe akun: admin/staff/barber, TIDAK PERNAH
  // disentuh untuk Owner/Barber), field BARU `izin` (opsional) adalah
  // gerbang KEDUA KHUSUS untuk 'staff' -- root key izin_* menu ini (dari
  // PERMISSION_TREE) yang dicek lewat MugenMenuAccess.has() di
  // _bangunItemNav()/_lolosIzin() di bawah SEBELUM menu ditampilkan. Menu
  // TANPA field `izin` (Dashboard/Karyawan/Absensi dst -- granularitasnya
  // sendiri sudah diatur DI DALAM halamannya masing-masing, lihat
  // menu_access.js) tetap tampil untuk SEMUA role di `roles`.
  const MENU = [
    { hash: "#/dashboard", label: "Dashboard", roles: ["admin", "staff", "barber"] },
    // REVISI: Input Data sekarang khusus admin -- Barber hanya Dashboard + Rekap.
    { hash: "#/input-data", label: "Input Data", roles: ["admin", "staff"], izin: "izin_input_data_lihat" },
    { hash: "#/rekap", label: "Rekap", roles: ["admin", "staff", "barber"], izin: "izin_rekap_lihat" },
    // Modul Karyawan -- Fase 1: Slip Gaji, Fase 2: Kasbon, Fase 3: Komisi,
    // Fase 4: Reimburse, Fase 5: Izin & Cuti. `children` dirender sebagai
    // grup expand/collapse KALAU child yang lolos filter role >= 2 (kondisi
    // ini sejak Kasbon); kalau cuma 1, otomatis dirender sebagai link flat
    // biasa (lihat _bangunItemNav()) -- supaya tidak ada dropdown kosong-
    // satu-item yang janggal. `badgeId`/`badgeRoles` (Izin & Cuti) dipakai
    // izin_notif.js untuk badge jumlah pengajuan pending, pola sama seperti
    // badge Booking di bawah (lihat _bangunItemNav()).
    { label: "Karyawan", roles: ["admin", "staff", "barber"], children: [
      { hash: "#/karyawan/slip-gaji", label: "Slip Gaji", roles: ["admin", "staff", "barber"] },
      { hash: "#/karyawan/kasbon", label: "Kasbon", roles: ["admin", "staff", "barber"] },
      { hash: "#/karyawan/komisi", label: "Komisi", roles: ["admin", "staff", "barber"] },
      { hash: "#/karyawan/reimburse", label: "Reimburse", roles: ["admin", "staff", "barber"] },
      { hash: "#/karyawan/izin-cuti", label: "Izin & Cuti", roles: ["admin", "staff", "barber"],
        badgeId: "izin-badge", badgeRoles: ["admin", "staff"] },
    ]},
    // Modul BARU Absensi (GPS Check In/Out Geofencing) -- berdiri sendiri,
    // TIDAK terhubung ke Izin & Cuti/Barber Holiday (keputusan eksplisit
    // Owner). Barber: self-service Check In/Out + riwayat sendiri. Owner/
    // Admin: dashboard + daftar semua barber + Pengaturan Absensi (lihat
    // routers/attendance.py untuk detail hak akses -- REVISI feedback
    // Owner: Pengaturan Absensi sebelumnya tab terpisah di menu Setting,
    // sekarang dipindahkan ke SINI, jadi satu tempat dengan menu Absensi
    // itu sendiri, lihat pages/absensi.js::renderPengaturanAbsensi()).
    // AUDIT (enforcement paket/subscription): backend menggerbang SELURUH
    // /api/attendance dengan fitur "absensi" (routers/attendance.py, lihat
    // feature_access.py) -- `feature` di sini SEKARANG ikut menyembunyikan
    // menunya kalau tenant tidak punya fitur itu (sebelumnya menu tetap
    // tampil, tenant baru tahu lewat 403 di dalam halaman). Lihat
    // _lolosFitur() di bawah untuk cara field `feature` ini dipakai.
    // REVISI Work #2 (Superadmin Package Permission Tree): kode fitur
    // "absensi" tersendiri DIHAPUS -- ikon gembok 🔒 paket (field `feature`)
    // TIDAK LAGI dipakai di sini (akan selalu "terkunci" keliru kalau
    // dipertahankan, karena kodenya sudah tidak ada di katalog manapun) --
    // gerbang package-level SEKARANG lewat izin_absensi_lihat, ditegakkan
    // backend (auth.py::require_menu_feature()), BUKAN ditampilkan sebagai
    // gembok di sini.
    // `izinPaket` (BEDA dari `izin`): root Absensi TIDAK punya field `izin`
    // biasa (Role-nya has_any beberapa key -- izin_absensi_lihat/
    // _pengaturan/_koreksi, lihat routers/attendance.py::_cek_akses_lihat()
    // -- field `izin` tunggal di sini akan KELIRU menyembunyikan menu untuk
    // staff yang HANYA punya salah satu dari ketiganya), tapi batas PAKET
    // (Package Permission Tree) tetap satu root tunggal -- `izinPaket`
    // dicek TERPISAH khusus untuk itu (lihat _terkunciPaket()/
    // cariIzinUntukHash() di bawah, fallback ke `izin` kalau tidak diisi).
    { hash: "#/absensi", label: "Absensi", roles: ["admin", "staff", "barber"], izinPaket: "izin_absensi_lihat" },
    // BOOKING: Owner/Admin full access; Barber hanya lihat booking
    // miliknya sendiri (dibedakan DI DALAM booking.js sendiri lewat user.role).
    { hash: "#/booking", label: "Booking", roles: ["admin", "staff", "barber"], izin: "izin_booking_lihat",
      badgeId: "booking-badge", badgeRoles: ["admin", "staff"] },
    // Modul Keuangan -- Fase 1: Pemasukan, Fase 2 (semula Transfer Kas/Bank,
    // dihapus & diganti Uang Kas -- lihat uang_kas_db.py): Uang Kas.
    // Pengeluaran (Tahap 9, sudah ada sejak lama) DIPINDAH ke sini sebagai
    // child -- hash/route/halaman-nya TIDAK berubah sama sekali (tetap
    // #/pengeluaran, tetap PagePengeluaran), murni penataan ulang lokasi di
    // sidebar sesuai pengelompokan modul di spesifikasi, BUKAN perubahan
    // fitur.
    { label: "Keuangan", roles: ["admin", "staff"], children: [
      { hash: "#/keuangan/pemasukan", label: "Pemasukan", roles: ["admin", "staff"], izin: "izin_pemasukan_lihat" },
      { hash: "#/pengeluaran", label: "Pengeluaran", roles: ["admin", "staff"], izin: "izin_pengeluaran_lihat" },
      { hash: "#/keuangan/uang-kas", label: "Uang Kas", roles: ["admin", "staff"], izin: "izin_uang_kas_lihat" },
      // Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant:
      // riwayat transaksi Payment Gateway booking milik toko ini sendiri
      // (lihat pages/riwayat_transaksi.js). Label diperjelas (PERMINTAAN
      // OWNER) supaya tidak tertukar dengan tab "Transaksi" di menu Rekap.
      { hash: "#/keuangan/riwayat-transaksi", label: "Riwayat Transaksi (Payment Gateway)", roles: ["admin", "staff"],
        izin: "izin_riwayat_transaksi_lihat" },
      // Settlement Faspay per Terminal (Tenant): closing harian transaksi
      // Faspay SNAP Advance toko ini sendiri (lihat pages/settlement_faspay.js).
      { hash: "#/settlement-faspay", label: "Settlement Faspay", roles: ["admin", "staff"], izin: "izin_settlement_faspay_lihat" },
    ]},
    { hash: "#/produk", label: "Produk", roles: ["admin", "staff"], izin: "izin_produk_lihat" },
    // REVISI Hak Akses (hapus menu Owner-only hardcoded -- lihat
    // permissions.py): WhatsApp SEKARANG grantable Owner ke Role manapun
    // (dulu KHUSUS Owner murni, token Fonnte kredensial pihak ketiga,
    // TIDAK didelegasikan) -- `roles` dibuka untuk 'staff' juga, gerbang
    // SEBENARNYA sekarang lewat `izin` (root izin_whatsapp_lihat). `feature`
    // -- lihat catatan _terkunciFitur() di atas -- menu tetap tampil
    // (redup+gembok) kalau paket tenant belum menyertakan "whatsapp_reminder".
    // `feature: "whatsapp_reminder"` DIHAPUS (lihat catatan Absensi di
    // atas, alasan sama persis).
    { hash: "#/whatsapp", label: "WhatsApp", roles: ["admin", "staff"], izin: "izin_whatsapp_lihat" },
    // FONDASI Multi-Tenant Phase 4: KHUSUS Owner (backend require_admin di
    // routers/billing.py) -- 'staff' TIDAK ikut, sama seperti tab
    // Subscription Phase 3 (pages/pengaturan.js), yang TIDAK diubah/
    // digabung ke sini sama sekali.
    { hash: "#/billing", label: "Billing", roles: ["admin"] },
    { hash: "#/pengaturan", label: "Setting", roles: ["admin", "staff"] },
  ];
  const MENU_SEGERA = [];

  // Elemen <a> satu item flat (dipakai untuk item MENU biasa maupun child
  // di dalam grup, dan untuk grup yang cuma 1 child lolos filter role).
  // `badge` (opsional): {id, roles} -- span kosong id="{id}" ditambahkan
  // KALAU role user ada di `roles`, dicari & di-update oleh modul notif
  // terkait (booking_notif.js/izin_notif.js) tiap polling -- sengaja
  // dibuat ulang di sini (bukan disimpan sekali) karena seluruh sidebar
  // di-render ULANG tiap pindah menu.
  function _elLink(hash, label, activeHash, user, badge, locked) {
    // .nav-initial (span lingkaran 2 huruf) HANYA terlihat saat
    // .sidebar.collapsed (lihat style.css) -- selalu dibuat supaya tidak
    // perlu render ulang saat collapse/expand, murni ditampilkan/
    // disembunyikan lewat CSS.
    const linkChildren = [
      MugenUI.el("span", { class: "nav-initial" }, _inisialLabel(label)),
      MugenUI.el("span", {}, label),
    ];
    // AUDIT (enforcement paket/subscription -- REVISI feedback Owner): menu
    // yang fiturnya TIDAK termasuk paket tenant TETAP tampil (BUKAN
    // disembunyikan seperti sebelumnya) -- ikon gembok kecil + gaya redup
    // supaya Owner tahu fiturnya ADA tapi belum termasuk paketnya, bukan
    // mengira fiturnya tidak pernah ada sama sekali. Link TETAP bisa diklik
    // (href tidak diubah) -- halaman tujuannya sendiri yang menampilkan
    // blok "Upgrade Paket" (lihat router.js), BUKAN dicegah di sini.
    if (locked) {
      linkChildren.push(MugenUI.el("span", { class: "nav-lock-icon", "aria-label": "Belum termasuk paket" }, "🔒"));
    } else if (badge && badge.roles.includes(user.role)) {
      linkChildren.push(MugenUI.el("span", { class: "nav-badge", id: badge.id, style: "display:none;" }));
    }
    return MugenUI.el("a", {
      href: hash,
      // REVISI UI/UX Premium: tooltip kustom (data-tooltip, lihat style.css
      // ".sidebar.collapsed [data-tooltip]") menggantikan title -- HANYA
      // tampak saat sidebar collapsed (satu-satunya kondisi label ini
      // benar-benar tidak terlihat di layar). aria-label dipertahankan
      // untuk screen reader terlepas dari state collapsed/expanded.
      "data-tooltip": locked ? `${label} (belum termasuk paket)` : label,
      "aria-label": label,
      class: (activeHash.startsWith(hash) ? "active" : "") + (locked ? " nav-locked" : ""),
    }, linkChildren);
  }

  // AUDIT (enforcement paket/subscription): field opsional `feature` pada
  // entri MENU_LIST -- kalau diisi DAN tenant TIDAK punya kode fitur itu
  // (sumber sama dengan backend, lihat feature_access.js::MugenFeature.has()),
  // menu tetap tampil TAPI ditandai terkunci (lihat _elLink() di atas).
  // Generik untuk kode fitur APA PUN (bukan hardcode nama paket) -- menu
  // lain tinggal tambah field ini kalau nanti perlu digerbang juga.
  function _terkunciFitur(item) {
    if (!item.feature) return false;
    return !(typeof MugenFeature !== "undefined" && MugenFeature.has(item.feature));
  }

  // REVISI Work #2 (Superadmin Package Permission Tree): versi _terkunciFitur()
  // di atas untuk 4 kode "sejajar" lama -- ini untuk root key izin_* (field
  // `izin`, SUDAH ADA di MENU untuk gerbang Role lewat _lolosIzin()) yang
  // TIDAK termasuk Package Permission Tree paket tenant. Dicek TERPISAH
  // dari _lolosIzin() (Role, MugenMenuAccess -- kalau GAGAL menu
  // disembunyikan total) -- paket yang gagal di sini menu TETAP tampil,
  // cuma dikunci (pola SAMA PERSIS _terkunciFitur(), digabung lewat || di
  // _elLink()).
  function _terkunciPaket(item) {
    const key = item.izinPaket || item.izin;
    if (!key) return false;
    return !(typeof MugenFeature !== "undefined" && MugenFeature.hasIzin(key));
  }

  // REVISI Hak Akses: gerbang KEDUA khusus 'staff' -- item TANPA field
  // `izin` (granularitasnya sendiri sudah diatur DI DALAM halamannya,
  // lihat menu_access.js) selalu lolos di sini. MugenMenuAccess.hasSync()
  // fail-open ke true kalau cache belum terisi (lihat docstringnya) --
  // backend TETAP lapis pertahanan sebenarnya.
  function _lolosIzin(item) {
    if (!item.izin) return true;
    return MugenMenuAccess.hasSync(item.izin);
  }

  // Bangun satu entri MENU (item flat ATAU grup) jadi elemen nav, atau null
  // kalau tidak ada apa pun yang boleh dilihat role user ini.
  function _bangunItemNav(item, user, activeHash) {
    if (!item.children) {
      if (!item.roles.includes(user.role) || !_lolosIzin(item)) return null;
      const badge = item.badgeId ? { id: item.badgeId, roles: item.badgeRoles || [] } : null;
      return _elLink(item.hash, item.label, activeHash, user, badge, _terkunciFitur(item) || _terkunciPaket(item));
    }

    const childrenLolos = item.children.filter((c) => c.roles.includes(user.role) && _lolosIzin(c));
    if (!childrenLolos.length) return null;
    if (childrenLolos.length === 1) {
      const only = childrenLolos[0];
      const badge = only.badgeId ? { id: only.badgeId, roles: only.badgeRoles || [] } : null;
      return _elLink(only.hash, only.label, activeHash, user, badge, _terkunciFitur(only) || _terkunciPaket(only));
    }

    const grupAktif = childrenLolos.some((c) => activeHash.startsWith(c.hash));
    const wrap = MugenUI.el("div", { class: "nav-group" + (grupAktif ? " open" : "") });
    // Sidebar collapsed: submenu grup ini ikut tersembunyi (lihat CSS
    // .sidebar.collapsed .nav-submenu) -- toggle di sini murni jadi
    // penanda visual (inisial) saat collapsed, Owner perlu expand sidebar
    // dulu untuk membuka grup Karyawan/Keuangan.
    const toggle = MugenUI.el("button", {
      type: "button", class: "nav-group-toggle", "data-tooltip": item.label, "aria-label": item.label,
    }, [
      MugenUI.el("span", { class: "nav-initial" }, _inisialLabel(item.label)),
      MugenUI.el("span", {}, item.label),
      MugenUI.el("span", { class: "nav-group-chevron" }, "›"),
    ]);
    const submenu = MugenUI.el("div", { class: "nav-submenu" });
    for (const child of childrenLolos) {
      const badge = child.badgeId ? { id: child.badgeId, roles: child.badgeRoles || [] } : null;
      submenu.appendChild(_elLink(child.hash, child.label, activeHash, user, badge, _terkunciFitur(child) || _terkunciPaket(child)));
    }
    toggle.addEventListener("click", () => wrap.classList.toggle("open"));
    wrap.appendChild(toggle);
    wrap.appendChild(submenu);
    return wrap;
  }

  // REVISI Work #2 (Superadmin Package Permission Tree): dipakai router.js
  // SEBELUM memuat halaman tujuan -- kalau hash ini (match PERSIS pola
  // `hash.startsWith(item.hash)` yang sama dipakai handle()) punya field
  // `izin` DAN package tenant tidak menyertakannya, router.js menampilkan
  // blok "Upgrade Paket" (MugenFeature.upgradeBlock()) di tempat halaman
  // sungguhan -- SATU titik keputusan ini menggantikan perlunya menyentuh
  // render() tiap halaman satu per satu (pola lama #/absensi/#/whatsapp,
  // lihat catatan router.js). Return null kalau hash ini TIDAK ada di
  // MENU sama sekali, ATAU tidak punya field `izin` (menu itu tidak
  // digerbang Package Permission Tree -- Dashboard/Karyawan/Billing/
  // Setting dst, granularitasnya sendiri sudah diatur di dalam
  // halamannya, lihat catatan atas MENU).
  function cariIzinUntukHash(hash) {
    for (const item of MENU) {
      if (item.children) {
        for (const child of item.children) {
          const key = child.izinPaket || child.izin;
          if (key && hash.startsWith(child.hash)) return { izin: key, label: child.label };
        }
        continue;
      }
      const key = item.izinPaket || item.izin;
      if (key && hash.startsWith(item.hash)) return { izin: key, label: item.label };
    }
    return null;
  }

  function render(activeHash) {
    const user = MugenState.getUser();
    // REVISI Hak Akses: picu pengisian cache izin (non-blocking, lihat
    // menu_access.js::preload()) -- render() ini dipanggil SETIAP pindah
    // halaman (shell(), lihat router.js), jadi cache biasanya sudah
    // terisi sebelum navigasi KEDUA, tanpa perlu mengubah render() ini
    // jadi async.
    if (typeof MugenMenuAccess !== "undefined") MugenMenuAccess.preload();
    const sidebar = MugenUI.el("aside", {
      class: "sidebar" + (_collapsedTersimpan() ? " collapsed" : ""),
    });

    const brandBox = MugenUI.el("div", { class: "brand" }, [
      MugenUI.el("img", { class: "brand-logo", style: "display:none;", alt: "Logo" }),
      MugenUI.el("span", { class: "brand-name" }, MugenBrand.get().nama_barbershop),
    ]);
    sidebar.appendChild(brandBox);
    MugenBrand.applyToDom();

    // REVISI UI/UX Premium: tombol collapse/expand sidebar (desktop) --
    // disembunyikan lewat CSS di layar sempit (lihat @media 860px di
    // style.css, mekanisme mobile TETAP hamburger seperti sebelumnya).
    // Superadmin TIDAK ikut (menunya cuma satu link, collapse tidak
    // berguna) -- dicek di bawah sebelum ditambahkan.
    if (user.role !== "superadmin" && user.role !== "sales") {
      const btnCollapse = MugenUI.el("button", {
        type: "button", class: "sidebar-collapse-btn", title: "Collapse/Expand Menu",
      }, "‹");
      btnCollapse.addEventListener("click", () => {
        const collapsed = sidebar.classList.toggle("collapsed");
        localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0");
      });
      sidebar.appendChild(btnCollapse);
    }

    const nav = MugenUI.el("nav");
    // FONDASI Multi-Tenant Phase 2.1: 'superadmin' TIDAK ikut menu MENU
    // biasa sama sekali (semuanya milik wilayah tenant, yang memang ditolak
    // backend untuk akun ini, lihat auth.get_current_tenant_id()) -- cukup
    // satu link ke satu-satunya halaman yang dia punya.
    if (user.role === "superadmin") {
      nav.appendChild(_elLink("#/dashboard", "Kelola Tenant", activeHash, user, null));
    } else if (user.role === "sales") {
      // FITUR Program Afiliasi Sales/Marketing: pola identik superadmin di
      // atas -- satu-satunya halaman milik akun ini (Portal Sales).
      nav.appendChild(_elLink("#/dashboard", "Portal Sales", activeHash, user, null));
    } else {
      for (const item of MENU) {
        const el = _bangunItemNav(item, user, activeHash);
        if (el) nav.appendChild(el);
      }
      for (const label of MENU_SEGERA) {
        nav.appendChild(MugenUI.el("a", { href: "#", class: "disabled",
          style: "opacity:.4;pointer-events:none;" }, `${label} (segera)`));
      }
    }
    sidebar.appendChild(nav);

    const LABEL_ROLE = { admin: "Owner", staff: "Admin", barber: "Barber", superadmin: "Super Admin", sales: "Sales" };
    const userBox = MugenUI.el("div", { class: "user-box" }, [
      MugenUI.el("div", {}, user.username),
      MugenUI.el("div", {}, LABEL_ROLE[user.role] || user.role),
    ]);

    // REVISI UI/UX: switch Dark Mode di sidebar HANYA untuk Barber -- Owner
    // mengatur tema lewat Setting > Tampilan (lihat pengaturan.js). REVISI
    // Hak Akses Admin: 'staff' (Admin) JUGA lewat Setting > Tampilan (bukan
    // sidebar) -- supaya tab ini benar-benar bisa dibatasi Owner lewat
    // izin_setting_tampilan (kalau sidebar selalu tampil, izin ini jadi
    // tidak berarti apa-apa karena staff tetap selalu bisa ganti tema).
    if (user.role === "barber") {
      userBox.appendChild(MugenUI.el("div", { class: "theme-switch-row", style: "margin-top:10px;" }, [
        MugenUI.el("span", {}, "Dark Mode"),
        MugenUI.themeSwitch(),
      ]));
    }

    // REVISI UI/UX Premium: data-tooltip (bukan title) -- teks "Keluar"
    // ikut hilang saat sidebar collapsed (lihat style.css, cuma ikon "⏻"
    // yang tersisa), sama seperti nav link di atas.
    const btnLogout = MugenUI.el("button", { class: "btn-logout", "data-tooltip": "Keluar", "aria-label": "Keluar" },
      MugenUI.el("span", {}, "Keluar"));
    btnLogout.addEventListener("click", async () => {
      if (!confirm("Yakin ingin keluar?")) return;
      // REVISI: setelah konfirmasi, tampilkan loading animation + teks
      // "Sedang keluar dari aplikasi…" (jeda ~1 detik, dalam rentang
      // 800-1200ms yang diminta -- LEBIH PENDEK dari jeda minimal 1,5 detik
      // default withLoading(), lihat opts.minMs di ui.js) supaya proses
      // sign out terasa nyata, bukan langsung lompat ke halaman Login.
      btnLogout.disabled = true;
      try {
        // Kontrol Sesi Login Satu-Device per Akun: mencabut sesi di
        // BACKEND (requirement "sesi lama harus benar-benar tidak valid
        // di backend, bukan hanya dihapus dari frontend") -- best-effort,
        // gagal jaringan TIDAK PERNAH menghalangi logout lokal di bawah.
        await MugenUI.withLoading(() => MugenApi.post("/api/auth/logout", {}).catch(() => {}), {
          message: "Sedang keluar dari aplikasi…",
          minMs: 1000,
        });
      } finally {
        MugenState.clearSession();
        // REVISI UI/UX: tandai supaya halaman Login yang muncul SETELAH
        // Logout ini memutar animasi Slide+Fade (lihat state.js/login.js) --
        // trigger yang SAH selain "aplikasi pertama dibuka".
        MugenState.markLoginEntrance();
        location.hash = "#/login";
      }
    });
    userBox.appendChild(btnLogout);
    sidebar.appendChild(userBox);

    return sidebar;
  }

  return { render, cariIzinUntukHash };
})();
