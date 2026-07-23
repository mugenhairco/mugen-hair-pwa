// router.js — router hash sederhana (tanpa library). Setiap navigasi:
// 1. Kalau belum login -> paksa ke #/login.
// 2. Kalau sudah login tapi buka #/login -> lempar ke #/dashboard.
// 3. Render ulang sidebar (nav.js) + halaman yang sesuai ke <main id="content">.

const MugenRouter = (() => {
  const appRoot = document.getElementById("app");

  function shell() {
    appRoot.innerHTML = "";
    const wrap = MugenUI.el("div", { class: "app-shell" });
    const sidebar = MugenNav.render(location.hash || "#/dashboard");
    const main = MugenUI.el("main", { class: "content", id: "content" });
    wrap.appendChild(sidebar);
    wrap.appendChild(main);
    appRoot.appendChild(wrap);
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
