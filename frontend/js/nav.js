// nav.js — sidebar. Menu Pengeluaran (Tahap 9), Setting (Tahap 10), Produk
// (Tahap 11), dan Sinkronisasi (Tahap 12) sudah aktif, KHUSUS admin —
// backend juga menolak barber lewat require_admin, ini bukan satu-satunya
// lapis perlindungan.
// Nama & logo barbershop (TAHAP 10) TIDAK hardcode di sini — dibaca lewat
// brand.js (MugenBrand) dari /api/pengaturan/identitas.

const MugenNav = (() => {
  // REVISI Hak Akses Admin (kedua): 'staff' (label UI "Admin") sekarang
  // punya akses PENUH sama persis seperti Owner ke Input Data/Booking/
  // Pengeluaran/Produk/Rekap -- kelima menu ini TIDAK memakai sistem izin
  // sama sekali (lihat permissions.py). HANYA menu Dashboard (kartu
  // difilter) dan Setting (tab difilter) yang tetap diatur lewat Hak
  // Akses Admin.
  const MENU = [
    { hash: "#/dashboard", label: "Dashboard", roles: ["admin", "staff", "barber"] },
    // REVISI: Input Data sekarang khusus admin -- Barber hanya Dashboard + Rekap.
    { hash: "#/input-data", label: "Input Data", roles: ["admin", "staff"] },
    { hash: "#/rekap", label: "Rekap", roles: ["admin", "staff", "barber"] },
    // Modul Karyawan (Fase 1) -- baru berisi Slip Gaji. `children` dirender
    // sebagai grup expand/collapse KALAU child yang lolos filter role >= 2;
    // kalau cuma 1 (kondisi saat ini), otomatis dirender sebagai link flat
    // biasa (lihat _bangunItemNav()) -- supaya tidak ada dropdown kosong-
    // satu-item yang janggal, dan otomatis "naik kelas" jadi grup sungguhan
    // begitu modul Karyawan lain (Kasbon, Reimburse, dst) menyusul.
    { label: "Karyawan", roles: ["admin", "staff", "barber"], children: [
      { hash: "#/karyawan/slip-gaji", label: "Slip Gaji", roles: ["admin", "staff", "barber"] },
    ]},
    // BOOKING: Owner/Admin full access; Barber hanya lihat booking
    // miliknya sendiri (dibedakan DI DALAM booking.js sendiri lewat user.role).
    { hash: "#/booking", label: "Booking", roles: ["admin", "staff", "barber"] },
    { hash: "#/pengeluaran", label: "Pengeluaran", roles: ["admin", "staff"] },
    { hash: "#/produk", label: "Produk", roles: ["admin", "staff"] },
    { hash: "#/pengaturan", label: "Setting", roles: ["admin", "staff"] },
  ];
  const MENU_SEGERA = [];

  // Elemen <a> satu item flat (dipakai untuk item MENU biasa maupun child
  // di dalam grup, dan untuk grup yang cuma 1 child lolos filter role).
  function _elLink(hash, label, activeHash, extraChildren) {
    const linkChildren = [MugenUI.el("span", {}, label)];
    if (extraChildren) linkChildren.push(...extraChildren);
    return MugenUI.el("a", {
      href: hash,
      class: activeHash.startsWith(hash) ? "active" : "",
    }, linkChildren);
  }

  // Bangun satu entri MENU (item flat ATAU grup) jadi elemen nav, atau null
  // kalau tidak ada apa pun yang boleh dilihat role user ini.
  function _bangunItemNav(item, user, activeHash) {
    if (!item.children) {
      if (!item.roles.includes(user.role)) return null;
      // REVISI: badge jumlah booking belum dikonfirmasi, KHUSUS Owner/Admin --
      // hanya mereka yang bisa verifikasi/batalkan booking (lihat
      // routers/booking.py), Barber tidak punya kegunaan untuk badge ini.
      // id="booking-badge" dicari & di-update oleh booking_notif.js tiap
      // polling -- sengaja dibuat ulang di sini (bukan disimpan sekali)
      // karena seluruh sidebar di-render ulang tiap pindah menu.
      const extra = (item.hash === "#/booking" && (user.role === "admin" || user.role === "staff"))
        ? [MugenUI.el("span", { class: "nav-badge", id: "booking-badge", style: "display:none;" })]
        : null;
      return _elLink(item.hash, item.label, activeHash, extra);
    }

    const childrenLolos = item.children.filter((c) => c.roles.includes(user.role));
    if (!childrenLolos.length) return null;
    if (childrenLolos.length === 1) {
      return _elLink(childrenLolos[0].hash, childrenLolos[0].label, activeHash);
    }

    const grupAktif = childrenLolos.some((c) => activeHash.startsWith(c.hash));
    const wrap = MugenUI.el("div", { class: "nav-group" + (grupAktif ? " open" : "") });
    const toggle = MugenUI.el("button", { type: "button", class: "nav-group-toggle" }, [
      MugenUI.el("span", {}, item.label),
      MugenUI.el("span", { class: "nav-group-chevron" }, "›"),
    ]);
    const submenu = MugenUI.el("div", { class: "nav-submenu" });
    for (const child of childrenLolos) {
      submenu.appendChild(_elLink(child.hash, child.label, activeHash));
    }
    toggle.addEventListener("click", () => wrap.classList.toggle("open"));
    wrap.appendChild(toggle);
    wrap.appendChild(submenu);
    return wrap;
  }

  function render(activeHash) {
    const user = MugenState.getUser();
    const sidebar = MugenUI.el("aside", { class: "sidebar" });

    const brandBox = MugenUI.el("div", { class: "brand" }, [
      MugenUI.el("img", { class: "brand-logo", style: "display:none;", alt: "Logo" }),
      MugenUI.el("span", { class: "brand-name" }, MugenBrand.get().nama_barbershop),
    ]);
    sidebar.appendChild(brandBox);
    MugenBrand.applyToDom();

    const nav = MugenUI.el("nav");
    for (const item of MENU) {
      const el = _bangunItemNav(item, user, activeHash);
      if (el) nav.appendChild(el);
    }
    for (const label of MENU_SEGERA) {
      nav.appendChild(MugenUI.el("a", { href: "#", class: "disabled",
        style: "opacity:.4;pointer-events:none;" }, `${label} (segera)`));
    }
    sidebar.appendChild(nav);

    const LABEL_ROLE = { admin: "Owner", staff: "Admin", barber: "Barber" };
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

    const btnLogout = MugenUI.el("button", { class: "btn-logout" }, "Keluar");
    btnLogout.addEventListener("click", async () => {
      if (!confirm("Yakin ingin keluar?")) return;
      // REVISI: setelah konfirmasi, tampilkan loading animation + teks
      // "Sedang keluar dari aplikasi…" (jeda ~1 detik, dalam rentang
      // 800-1200ms yang diminta -- LEBIH PENDEK dari jeda minimal 1,5 detik
      // default withLoading(), lihat opts.minMs di ui.js) supaya proses
      // sign out terasa nyata, bukan langsung lompat ke halaman Login.
      btnLogout.disabled = true;
      try {
        await MugenUI.withLoading(() => Promise.resolve(), {
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

  return { render };
})();
