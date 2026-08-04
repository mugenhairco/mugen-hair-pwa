// theme.js — REVISI UI/UX: Dark Mode & Light Mode PER AKUN.
// Preferensi "sebenarnya" disimpan server-side (kolom users.tema, lihat
// auth_router.py) supaya akun yang sama tetap dapat tema yang sama di
// perangkat lain -- localStorage di sini HANYA cache lokal supaya tema
// yang benar bisa langsung diterapkan SEBELUM halaman sempat digambar
// (menghindari "flash" tema salah sesaat sebelum data user termuat), dan
// supaya halaman Login (yang belum tahu akun mana yang akan login) tetap
// menampilkan tema yang terakhir dipakai di perangkat itu.
//
// Web Booking (/book) SENGAJA TIDAK mengikuti Dark Mode (instruksi
// eksplisit) -- lihat forceLight(), dipanggil dari book_public.js
// sebelum merender apa pun, dan router.js memanggil applyStored() lagi
// begitu kembali ke halaman internal supaya atribut ini selalu benar
// tidak peduli urutan navigasi SPA (tanpa reload penuh).

const MugenTheme = (() => {
  const CACHE_KEY = "mugen_theme";

  function applyAttribute(tema) {
    if (tema === "gelap") {
      document.documentElement.setAttribute("data-theme", "dark");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
  }

  function getCached() {
    return localStorage.getItem(CACHE_KEY) || "terang";
  }

  function setCached(tema) {
    localStorage.setItem(CACHE_KEY, tema);
  }

  // Dipanggil di halaman internal (login & sesudah login) -- terapkan tema
  // dari data user yang sedang login (kalau ada, lebih akurat/terbaru
  // daripada cache), atau dari cache lokal (mis. saat halaman Login belum
  // ada sesi sama sekali).
  function applyStored() {
    const user = typeof MugenState !== "undefined" ? MugenState.getUser() : null;
    const tema = (user && user.tema) || getCached();
    applyAttribute(tema);
  }

  // Dipanggil HANYA oleh book_public.js -- Web Booking selalu terang,
  // apapun preferensi akun (kalau kebetulan sedang login di tab yang sama).
  function forceLight() {
    document.documentElement.removeAttribute("data-theme");
  }

  // Ganti tema akun yang SEDANG login: simpan ke server (per akun),
  // perbarui cache lokal + object user yang tersimpan di sesi, lalu
  // terapkan langsung tanpa perlu reload halaman.
  async function setTema(tema) {
    setCached(tema);
    applyAttribute(tema);
    const user = MugenState.getUser();
    if (user) {
      user.tema = tema;
      MugenState.setSession(MugenState.getToken(), user);
    }
    try {
      await MugenApi.put("/api/auth/tema", { tema });
    } catch (e) {
      // Gagal simpan ke server (mis. offline) -- tema tetap berlaku di
      // perangkat ini lewat cache lokal, tidak perlu menggagalkan UI.
    }
  }

  function current() {
    const user = typeof MugenState !== "undefined" ? MugenState.getUser() : null;
    return (user && user.tema) || getCached();
  }

  // Terapkan sesegera mungkin (script ini dimuat lebih awal di index.html,
  // sebelum halaman digambar) supaya tidak ada flash tema salah.
  applyStored();

  return { applyStored, forceLight, setTema, current };
})();
