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
    const btnLogout = MugenUI.el("button", { class: "btn-logout" }, "Keluar");
    btnLogout.addEventListener("click", () => {
      if (!confirm("Yakin ingin keluar?")) return;
      MugenState.clearSession();
      location.hash = "#/login";
    });
    userBox.appendChild(btnLogout);
    sidebar.appendChild(userBox);

    return sidebar;
  }

  return { render };
})();
