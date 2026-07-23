// nav.js — sidebar. Menu Produk/Pengeluaran/Setting sengaja ditandai
// "(segera)" dan tidak diberi link aktif dulu karena router/API-nya belum
// dibuat di tahap ini (baru Dashboard, Input Data, Rekap).

const MugenNav = (() => {
  const MENU = [
    { hash: "#/dashboard", label: "Dashboard", roles: ["admin", "barber"] },
    { hash: "#/input-data", label: "Input Data", roles: ["admin", "barber"] },
    { hash: "#/rekap", label: "Rekap", roles: ["admin", "barber"] },
  ];
  const MENU_SEGERA = ["Produk", "Pengeluaran", "Setting"];

  function render(activeHash) {
    const user = MugenState.getUser();
    const sidebar = MugenUI.el("aside", { class: "sidebar" });

    sidebar.appendChild(MugenUI.el("div", { class: "brand" }, "MUGEN HAIR CO."));

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
      MugenState.clearSession();
      location.hash = "#/login";
    });
    userBox.appendChild(btnLogout);
    sidebar.appendChild(userBox);

    return sidebar;
  }

  return { render };
})();
