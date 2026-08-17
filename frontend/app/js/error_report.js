// error_report.js — DIY error monitoring (BUKAN Sentry -- dibahas dengan
// Owner: Sentry gratis untuk skala kecil tapi tetap dependency pihak
// ketiga, opsi DIY ini dipilih dulu: $0/bulan, murni "tercatat & bisa
// dilihat" lewat Setting > Log Error, tanpa grouping/alert otomatis).
//
// SEBELUM file ini ada, error JS yang terjadi di HP customer/barber HILANG
// BEGITU SAJA di console browser masing-masing perangkat -- satu-satunya
// cara tahu ada masalah adalah user melapor duluan (lihat backend/app/
// error_log_db.py untuk sisi backend: exception tak tertangani di sana
// SUDAH tercatat ke stdout/log Render, tapi juga pasif, jadi tabel
// error_logs sekarang menampung KEDUANYA).
//
// Listener dipasang di SINI (bukan menunggu DOMContentLoaded di app.js)
// dan file ini dimuat SEDINI mungkin (lihat index.html, tepat setelah
// api.js -- perlu MUGEN_API_BASE) supaya aktif SEBELUM router/halaman
// mana pun sempat jalan, jadi error saat boot aplikasi pun ikut tertangkap.

const MugenErrorReport = (() => {
  // Jaring pengaman: bug yang memicu error berulang-ulang (mis. di dalam
  // render loop) tidak boleh membanjiri server dengan ribuan POST identik
  // dalam satu kali buka app -- dihitung PER SESI (reset tiap reload/buka
  // app baru), bukan disimpan permanen di manapun.
  const MAX_LAPORAN_PER_SESI = 20;
  let jumlahTerkirim = 0;

  function kirim(pesan, detail) {
    if (jumlahTerkirim >= MAX_LAPORAN_PER_SESI) return;
    jumlahTerkirim++;
    const headers = { "Content-Type": "application/json" };
    // MugenState mungkin belum sempat dimuat kalau error terjadi SANGAT
    // awal (sebelum state.js dieksekusi) -- dicek defensif, token cuma
    // "nice to have" (tenant tetap bisa diresolve dari sesi login lewat
    // header ini di backend, TIDAK wajib untuk error tetap tercatat, lihat
    // auth.resolve_tenant_untuk_branding()).
    const token = typeof MugenState !== "undefined" ? MugenState.getToken() : null;
    if (token) headers["Authorization"] = `Bearer ${token}`;
    // fetch biasa (BUKAN MugenApi.post) -- endpoint ini sengaja publik,
    // tidak butuh logika retry/cache-offline MugenApi, dan HARUS tetap
    // best-effort murni: .catch(() => {}) di sini SENGAJA membiarkan
    // kegagalan kirim laporan diam-diam, TIDAK BOLEH memicu error/toast
    // baru yang malah mengganggu user gara-gara error monitoring-nya
    // sendiri gagal.
    fetch(MUGEN_API_BASE + "/api/log-error", {
      method: "POST",
      headers,
      body: JSON.stringify({
        pesan: String(pesan || "(tanpa pesan)").slice(0, 2000),
        detail: detail ? String(detail).slice(0, 8000) : null,
        url: location.href,
        user_agent: navigator.userAgent,
        sumber: "frontend",
      }),
    }).catch(() => {});
  }

  window.addEventListener("error", (ev) => {
    // Event "error" JUGA terpicu untuk resource gagal dimuat (<img>/<script>
    // src 404, dst) -- BUKAN error JavaScript, dan ev.message selalu string
    // kosong untuk kasus itu, jadi disaring di sini (bukan noise yang
    // berguna, beda dari error JS sungguhan).
    if (!ev.message) return;
    kirim(ev.message, ev.error && ev.error.stack ? ev.error.stack : `${ev.filename}:${ev.lineno}:${ev.colno}`);
  });

  window.addEventListener("unhandledrejection", (ev) => {
    const alasan = ev.reason;
    const pesan = alasan && alasan.message ? alasan.message : String(alasan);
    const detail = alasan && alasan.stack ? alasan.stack : null;
    kirim(pesan, detail);
  });

  return {};
})();
