// state.js — sesi login (token + data user) disimpan di localStorage supaya
// tidak perlu login ulang tiap buka app (termasuk saat dibuka sebagai PWA
// yang di-install). Juga menyimpan cache GET terakhir per endpoint untuk
// mode offline (poin #22) — hanya data yang PERNAH berhasil diambil saat
// online yang bisa ditampilkan lagi saat offline, tidak pernah mengarang data.

const MugenState = (() => {
  const TOKEN_KEY = "mugen_token";
  const USER_KEY = "mugen_user";
  const CACHE_PREFIX = "mugen_cache:";

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function getUser() {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  }

  function setSession(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  function isLoggedIn() {
    return !!getToken();
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

  return { getToken, getUser, setSession, clearSession, isLoggedIn, cacheSet, cacheGet };
})();
