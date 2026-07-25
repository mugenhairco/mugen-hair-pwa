// nav.js — sidebar. Menu Pengeluaran (Tahap 9), Setting (Tahap 10), Produk
// (Tahap 11), dan Sinkronisasi (Tahap 12) sudah aktif, KHUSUS admin —
// backend juga menolak barber lewat require_admin, ini bukan satu-satunya
// lapis perlindungan.
// Nama & logo barbershop (TAHAP 10) TIDAK hardcode di sini — dibaca lewat
// brand.js (MugenBrand) dari /api/pengaturan/identitas.

const MugenNav = (() => {
  const MENU = [
    { hash: "#/dashboard", label: "Dashboard", roles: ["admin", "barber"] },
    // REVISI: Input Data sekarang khusus admin -- Barber hanya Dashboard + Rekap.
    { hash: "#/input-data", label: "Input Data", roles: ["admin"] },
    { hash: "#/rekap", label: "Rekap", roles: ["admin", "barber"] },
    // BOOKING: Owner/Admin full access; Barber hanya lihat booking miliknya
    // sendiri (dibedakan DI DALAM booking.js sendiri lewat user.role).
    { hash: "#/booking", label: "Booking", roles: ["admin", "barber"] },
    { hash: "#/pengeluaran", label: "Pengeluaran", roles: ["admin"] },
    { hash: "#/produk", label: "Produk", roles: ["admin"] },
    { hash: "#/sinkronisasi", label: "Sinkronisasi", roles: ["admin"] },
    { hash: "#/pengaturan", label: "Setting", roles: ["admin"] },
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
      nav.appendChild(MugenUI.el("a", {
        href: item.hash,
        class: activeHash.startsWith(item.hash) ? "active" : "",
      }, item.label));
    }
    for (const label of MENU_SEGERA) {
      nav.appendChild(MugenUI.el("a", { href: "#", class: "disabled",
        style: "opacity:.4;pointer-events:none;" }, `${label} (segera)`));
    }
    sidebar.appendChild(nav);

    const userBox = MugenUI.el("div", { class: "user-box" }, [
      MugenUI.el("div", {}, user.username),
      MugenUI.el("div", {}, user.role === "admin" ? "Owner" : "Barber"),
    ]);

    // REVISI UI/UX: switch Dark Mode di sidebar HANYA untuk user selain
    // admin (Barber) -- admin mengatur tema lewat Setting > Tampilan
    // (lihat pengaturan.js), karena Barber tidak punya akses ke menu
    // Setting sama sekali (lihat MENU di atas, roles: ["admin"]).
    if (user.role !== "admin") {
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
