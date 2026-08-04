// pages/subscription_blocked.js — FONDASI Multi-Tenant Phase 3: Subscription
// & Tenant Lifecycle. Halaman PENUH (dirender LANGSUNG ke #app, BUKAN lewat
// router.js::shell() -- pola sama seperti PageLogin/PageBookPublic) yang
// ditampilkan router.js untuk SEMUA hash begitu tenant yang sedang login
// subscription-nya Expired/Suspended/Cancelled (lihat subscription.js,
// MugenSubscription.aksesDiblokir()).
//
// Owner (role 'admin') melihat detail package/status/trial/grace (GET
// /api/subscription/me, read-only -- SAMA PERSIS data yang ditampilkan di
// Setting > Subscription, lihat pages/pengaturan.js) sesuai cakupan Phase 3
// "Owner hanya dapat melihat informasi subscription (read-only)". Akun
// 'staff'/'barber' HANYA melihat pesan generik TANPA detail finansial (izin
// GET /api/subscription/me murni Owner, lihat routers/subscription.py) --
// diarahkan menghubungi Owner tokonya sendiri.

const PageSubscriptionBlocked = (() => {
  const LABEL_STATUS = {
    trial: "Trial", active: "Active", grace_period: "Grace Period",
    expired: "Expired", suspended: "Suspended", cancelled: "Cancelled",
  };
  const LABEL_PACKAGE = { free: "Free", basic: "Basic", pro: "Pro", enterprise: "Enterprise" };

  function formatWaktu(iso) {
    if (!iso) return "-";
    const [tanggal, jam] = iso.split("T");
    return `${MugenUI.formatTanggal(tanggal)} ${jam || ""}`.trim();
  }

  function btnLogout() {
    const btn = MugenUI.el("button", { type: "button" }, "Keluar");
    btn.addEventListener("click", () => {
      MugenState.clearSession();
      MugenState.markLoginEntrance();
      location.hash = "#/login";
    });
    return btn;
  }

  // FONDASI Multi-Tenant Phase 5 (Landing Page SaaS): sebelumnya halaman ini
  // jalan buntu (HANYA tombol Keluar) -- sekarang Owner bisa langsung
  // memilih paket & bayar sendiri lewat #/billing, yang router.js SENGAJA
  // dikecualikan dari blokir ini (lihat router.js). Berlaku untuk SEMUA
  // tenant yang diblokir (bukan cuma tenant baru Register) -- perbaikan UX
  // sekaligus untuk tenant lama yang subscription-nya expired.
  function btnBayar() {
    const btn = MugenUI.el("button", { type: "button", class: "btn-primary" }, "Pilih Paket / Bayar Sekarang");
    btn.addEventListener("click", () => {
      location.hash = "#/billing";
      MugenRouter.handle();
    });
    return btn;
  }

  async function render(root) {
    root.innerHTML = "";
    const wrap = MugenUI.el("div", { class: "login-wrap" });
    const card = MugenUI.el("div", { class: "login-card" });
    card.appendChild(MugenUI.el("img", { class: "brand-logo login-logo", style: "display:none;", alt: "Logo" }));
    card.appendChild(MugenUI.el("h1", { class: "brand-name" }, MugenBrand.get().nama_barbershop));
    MugenBrand.applyToDom();

    card.appendChild(MugenUI.el("div", { class: "login-error", style: "margin-top:8px;" }, "Akses Dibatasi"));

    const user = MugenState.getUser();
    if (user.role === "admin") {
      let sub = null;
      try {
        sub = await MugenApi.get("/api/subscription/me");
      } catch (e) { /* ditangani di bawah lewat sub === null */ }

      if (sub) {
        card.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:8px;" },
          `Status subscription toko ini: ${LABEL_STATUS[sub.status] || sub.status}. Hubungi penyedia layanan untuk mengaktifkan kembali.`));
        const info = MugenUI.el("div", { style: "text-align:left;margin-top:16px;" }, [
          MugenUI.el("div", { style: "display:flex;justify-content:space-between;padding:6px 0;border-top:1px solid var(--border);" }, [
            MugenUI.el("span", { class: "subtitle" }, "Package"),
            MugenUI.el("span", {}, LABEL_PACKAGE[sub.package] || sub.package),
          ]),
          MugenUI.el("div", { style: "display:flex;justify-content:space-between;padding:6px 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border);" }, [
            MugenUI.el("span", { class: "subtitle" }, "Terakhir Diperbarui"),
            MugenUI.el("span", {}, formatWaktu(sub.updated_at)),
          ]),
        ]);
        card.appendChild(info);
        card.appendChild(MugenUI.el("div", { style: "margin-top:20px;" }, btnBayar()));
      } else {
        card.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:8px;" },
          "Toko ini sedang tidak aktif. Hubungi penyedia layanan untuk informasi lebih lanjut."));
      }
    } else {
      card.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:8px;" },
        "Toko ini sedang tidak aktif. Hubungi Owner/pemilik toko untuk informasi lebih lanjut."));
    }

    card.appendChild(MugenUI.el("div", { style: "margin-top:20px;" }, btnLogout()));
    wrap.appendChild(card);
    root.appendChild(wrap);
  }

  return { render };
})();
