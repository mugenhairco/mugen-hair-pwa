// state.js — sesi login (token + data user) disimpan di localStorage supaya
// tidak perlu login ulang tiap buka app (termasuk saat dibuka sebagai PWA
// yang di-install). Juga menyimpan cache GET terakhir per endpoint untuk
// mode offline (poin #22) — hanya data yang PERNAH berhasil diambil saat
// online yang bisa ditampilkan lagi saat offline, tidak pernah mengarang data.

const MugenState = (() => {
  const TOKEN_KEY = "mugen_token";
  const USER_KEY = "mugen_user";
  const TENANT_KEY = "mugen_tenant";
  const CACHE_PREFIX = "mugen_cache:";

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function getUser() {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  }

  function setSession(token, user, tenant) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    // FONDASI Multi-Tenant Phase 2.0: simpan slug toko yang BERHASIL login
    // (kalau ada) -- lihat getTenantSlug()/rememberTenantSlug() di bawah,
    // dipakai halaman Login untuk pre-fill slug di percobaan login
    // BERIKUTNYA di perangkat yang sama (satu perangkat/PWA install
    // biasanya memang dipakai satu toko terus-menerus), supaya alur
    // "ambigu, pilih toko" (lihat login.js) SANGAT JARANG muncul lagi
    // setelah login pertama kali berhasil. SENGAJA TIDAK dihapus saat
    // clearSession() (logout) -- slug toko tetap relevan dipakai lagi
    // walau sesi login sudah berakhir.
    if (tenant && tenant.slug) rememberTenantSlug(tenant.slug);
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    // BUGFIX (audit, kebocoran data lintas tenant): dulu cache offline
    // (mugen_cache:*, lihat cacheSet/cacheGet di bawah) TIDAK PERNAH
    // dibersihkan di sini. Kunci cache-nya cuma method+path (BUKAN per
    // tenant/user) -- di perangkat bersama/kiosk, Tenant A login lalu
    // logout, lalu Tenant B login di perangkat yang sama: kalau koneksi
    // Tenant B sempat terputus sebelum fetch pertama berhasil, api.js
    // diam-diam jatuh ke cache lama dan menampilkan data finansial milik
    // Tenant A di dalam sesi Tenant B. Satu-satunya perbaikan aman adalah
    // menghapus SEMUA entri cache saat logout (localStorage tidak punya
    // API hapus-berdasarkan-prefix, jadi kumpulkan dulu kuncinya baru
    // hapus satu per satu -- menghapus sambil iterasi indeks localStorage
    // akan melompati entri karena indeksnya bergeser).
    const kunciCache = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith(CACHE_PREFIX)) kunciCache.push(k);
    }
    kunciCache.forEach((k) => localStorage.removeItem(k));
  }

  function isLoggedIn() {
    return !!getToken();
  }

  function getTenantSlug() {
    return localStorage.getItem(TENANT_KEY) || "";
  }

  function rememberTenantSlug(slug) {
    if (slug) localStorage.setItem(TENANT_KEY, slug);
  }

  // REVISI UI/UX: penanda in-memory (SENGAJA bukan localStorage -- cukup
  // hidup selama satu kali muat halaman) untuk mengontrol kapan animasi
  // Slide+Fade di halaman Login boleh diputar: hanya saat aplikasi
  // pertama kali dibuka (ditandai router.js di panggilan handle() pertama)
  // atau tepat setelah Logout (ditandai nav.js) -- BUKAN setiap kali
  // halaman Login tampil (mis. gara-gara sesi kedaluwarsa di api.js).
  let _animateLoginEntrance = false;

  function markLoginEntrance() {
    _animateLoginEntrance = true;
  }

  function consumeLoginEntrance() {
    const v = _animateLoginEntrance;
    _animateLoginEntrance = false;
    return v;
  }

  // PERMINTAAN OWNER: Dashboard (Owner/Admin maupun Barber) jangan fetch
  // ulang ke server setiap kali halaman itu dibuka lagi (mis. pindah ke
  // menu lain lalu balik) kalau TIDAK ADA data baru yang masuk sejak
  // terakhir kali Dashboard berhasil dimuat -- supaya tidak ada
  // skeleton/loading berulang-ulang tanpa alasan. "Ada data baru" diartikan
  // SEDERHANA & AMAN: user INI SENDIRI baru menyimpan/mengoreksi/menghapus
  // sesuatu (lewat method HTTP selain GET, lihat api.js::request()) sejak
  // Dashboard terakhir ditandai bersih -- BUKAN memantau perubahan dari
  // user lain (kasir/barber lain), itu di luar cakupan permintaan ini.
  // SENGAJA in-memory (bukan localStorage/sessionStorage): otomatis reset
  // ke "kotor" (perlu fetch) setiap kali aplikasi dimuat ulang dari awal
  // (cold start PWA/refresh browser) -- hanya berlaku SELAMA satu kali
  // muat app (SPA, navigasi antar menu tidak reload index.html).
  let _dashboardKotor = true;

  function tandaiDashboardKotor() {
    _dashboardKotor = true;
  }

  function dashboardPerluRefresh() {
    return _dashboardKotor;
  }

  function tandaiDashboardBersih() {
    _dashboardKotor = false;
  }

  // PERMINTAAN OWNER: pola SAMA seperti _dashboardKotor di atas, tapi
  // generik (bisa dipakai halaman lain selain Dashboard -- Rekap, Produk,
  // dst) supaya tidak perlu pasangan tiga fungsi baru per halaman. Key
  // yang belum pernah didaftarkan dianggap "kotor" (perlu fetch) secara
  // default -- SENGAJA in-memory (bukan localStorage), reset ke "kotor"
  // tiap aplikasi dimuat ulang dari awal, sama seperti _dashboardKotor.
  const _halamanKotor = {};

  function tandaiHalamanKotor(nama) {
    _halamanKotor[nama] = true;
  }

  function halamanPerluRefresh(nama) {
    return _halamanKotor[nama] !== false;
  }

  function tandaiHalamanBersih(nama) {
    _halamanKotor[nama] = false;
  }

  function cacheSet(key, data) {
    try {
      localStorage.setItem(CACHE_PREFIX + key, JSON.stringify({ data, savedAt: Date.now() }));
    } catch (e) {
      // localStorage penuh atau tidak tersedia — abaikan, offline cache memang best-effort
    }
  }

  function cacheGet(key) {
    const raw = localStorage.getItem(CACHE_PREFIX + key);
    return raw ? JSON.parse(raw) : null;
  }

  return {
    getToken, getUser, setSession, clearSession, isLoggedIn, cacheSet, cacheGet,
    markLoginEntrance, consumeLoginEntrance, getTenantSlug, rememberTenantSlug,
    tandaiDashboardKotor, dashboardPerluRefresh, tandaiDashboardBersih,
    tandaiHalamanKotor, halamanPerluRefresh, tandaiHalamanBersih,
  };
})();
