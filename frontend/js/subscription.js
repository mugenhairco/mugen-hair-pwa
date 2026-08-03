// subscription.js — FONDASI Multi-Tenant Phase 3: Subscription & Tenant
// Lifecycle. Cache app-wide status "akses_diblokir" tenant yang sedang
// login (GET /api/subscription/status -- terbuka untuk SEMUA role tenant,
// lihat routers/subscription.py), dipakai router.js untuk mengalihkan
// SELURUH akun toko yang subscription-nya Expired/Suspended/Cancelled ke
// halaman status (pages/subscription_blocked.js) alih-alih dashboard biasa.
//
// Pola caching SAMA PERSIS dengan brand.js (localStorage + refresh() async
// terpisah dari get() sinkron) -- get() dipakai router.js::handle() yang
// SINKRON, jadi tidak bisa menunggu fetch API di tengah render. refresh()
// dipanggil app.js (boot) + login.js (setelah login berhasil, DI-AWAIT --
// beda dari MugenBrand.refresh() yang sengaja tidak di-await, supaya akun
// yang diblokir TIDAK PERNAH sempat melihat dashboard normal walau
// sekejap sebelum dialihkan).
const MugenSubscription = (() => {
  const KEY = "mugen_subscription_status_cache";

  let current = null; // null = belum pernah dicek / tidak relevan (superadmin, belum login)
  try {
    const cached = JSON.parse(localStorage.getItem(KEY));
    if (cached) current = cached;
  } catch (e) { /* cache rusak/tidak ada, mulai dari null */ }

  function get() {
    return current;
  }

  function aksesDiblokir() {
    return !!(current && current.akses_diblokir);
  }

  function _simpan(data) {
    current = data;
    try { localStorage.setItem(KEY, JSON.stringify(data)); } catch (e) { /* storage penuh/nonaktif, lanjut tanpa cache */ }
  }

  async function refresh() {
    const user = typeof MugenState !== "undefined" ? MugenState.getUser() : null;
    // Superadmin (tenant_id null) & belum login: tidak relevan sama sekali
    // -- lihat auth.get_current_tenant_id() (backend) yang menolak akun ini
    // dari SELURUH endpoint ber-scope tenant, endpoint /status pun tidak
    // pernah perlu dipanggil untuk sesi ini.
    if (!user || !MugenState.isLoggedIn() || user.role === "superadmin") {
      _simpan(null);
      return current;
    }
    try {
      const data = await MugenApi.get("/api/subscription/status");
      _simpan(data);
    } catch (e) {
      // Offline/error server: PERTAHANKAN cache lama (jangan diam-diam
      // dianggap "tidak diblokir" hanya karena network gagal, TAPI juga
      // jangan diam-diam dianggap "diblokir" kalau sebelumnya belum
      // pernah tahu -- lihat null-check di aksesDiblokir()).
    }
    return current;
  }

  return { get, refresh, aksesDiblokir };
})();
