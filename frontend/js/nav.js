// nav.js — sidebar. Menu Pengeluaran (Tahap 9), Setting (Tahap 10), Produk
// (Tahap 11), dan Sinkronisasi (Tahap 12) sudah aktif, KHUSUS admin —
// backend juga menolak barber lewat require_admin, ini bukan satu-satunya
// lapis perlindungan.
// Nama & logo barbershop (TAHAP 10) TIDAK hardcode di sini — dibaca lewat
// brand.js (MugenBrand) dari /api/pengaturan/identitas.

const MugenNav = (() => {
  // REVISI Hak Akses Admin: 'staff' (label UI "Admin") HANYA melihat
  // Dashboard, Pengeluaran, dan Setting -- Input Data/Rekap/Booking/Produk
  // BUKAN bagian dari hak akses yang bisa diberikan Owner ke role ini
  // (lihat permissions.py). Menu Pengeluaran/Setting tetap tampil untuk
  // 'staff' apa pun hak aksesnya (supaya bisa masuk & melihat kenapa
  // aksinya dibatasi) -- pembatasan SEBENARNYA per-aksi terjadi di dalam
  // halamannya masing-masing + backend (require_permission).
  const MENU = [
    { hash: "#/dashboard", label: "Dashboard", roles: ["admin", "staff", "barber"] },
    // REVISI: Input Data sekarang khusus admin -- Barber hanya Dashboard + Rekap.
    { hash: "#/input-data", label: "Input Data", roles: ["admin"] },
    { hash: "#/rekap", label: "Rekap", roles: ["admin", "barber"] },
    // BOOKING: Owner/Admin(Owner) full access; Barber hanya lihat booking
    // miliknya sendiri (dibedakan DI DALAM booking.js sendiri lewat user.role).
    { hash: "#/booking", label: "Booking", roles: ["admin", "barber"] },
    { hash: "#/pengeluaran", label: "Pengeluaran", roles: ["admin", "staff"] },
    { hash: "#/produk", label: "Produk", roles: ["admin"] },
    { hash: "#/pengaturan", label: "Setting", roles: ["admin", "staff"] },
  ];
  const MENU_SEGERA = [];

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
      if (!item.roles.includes(user.role)) continue;
      // REVISI: badge jumlah booking belum dikonfirmasi, KHUSUS admin --
      // hanya Admin yang bisa verifikasi/batalkan booking (lihat
      // routers/booking.py), Barber tidak punya kegunaan untuk badge ini.
      // id="booking-badge" dicari & di-update oleh booking_notif.js tiap
      // polling -- sengaja dibuat ulang di sini (bukan disimpan sekali)
      // karena seluruh sidebar di-render ulang tiap pindah menu.
      const linkChildren = [MugenUI.el("span", {}, item.label)];
      if (item.hash === "#/booking" && user.role === "admin") {
        linkChildren.push(MugenUI.el("span", { class: "nav-badge", id: "booking-badge", style: "display:none;" }));
      }
      nav.appendChild(MugenUI.el("a", {
        href: item.hash,
        class: activeHash.startsWith(item.hash) ? "active" : "",
      }, linkChildren));
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
