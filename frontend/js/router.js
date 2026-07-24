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
    } else {
      location.hash = "#/dashboard";
    }
  }

  function init() {
    window.addEventListener("hashchange", handle);
    handle();
  }

  return { init };
})();
