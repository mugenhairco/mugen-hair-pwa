// izin_notif.js — Modul Karyawan (Fase 5): Notifikasi Izin & Cuti (badge
// jumlah pengajuan Pending di menu Izin & Cuti), KHUSUS Owner/Admin --
// badge visual saja sudah cukup memenuhi "notifikasi admin/owner" di
// spesifikasi, TANPA suara pengingat (approval izin/cuti tidak sekritis/
// se-real-time booking baru, lihat booking_notif.js yang MASIH polling
// periodik karena punya suara pengingat).
//
// REVISI Efisiensi Polling: TIDAK ADA setInterval/polling periodik lagi
// sama sekali di sini (sebelumnya tiap 15 detik app-wide TANPA henti,
// dikeluhkan Owner sebagai beban backend yang tidak perlu untuk sekadar
// badge angka yang tidak sekritis notifikasi booking). Sekarang MURNI
// event-driven -- _poll() HANYA dipanggil pada: (1) aplikasi pertama kali
// dibuka (init(), lihat app.js), (2) tiap kali user berpindah menu (lihat
// router.js::handle(), dipanggil SETIAP klik link sidebar/navigasi
// SPA -- "ada aksi" menurut istilah Owner), (3) tepat setelah aksi
// Setujui/Tolak pengajuan (lihat izin_cuti.js, lewat refreshNow()).
// Konsekuensi yang disadari & diterima: kalau seorang Barber mengirim
// pengajuan baru SAAT Owner sedang diam di satu halaman tanpa klik apa
// pun, badge-nya baru ter-update begitu Owner klik menu apa saja
// berikutnya -- bukan detik itu juga. Ini trade-off yang Owner minta
// secara eksplisit (lebih hemat request, bukan real-time mutlak).

const MugenIzinNotif = (() => {
  function _updateBadge(jumlah) {
    const badge = document.getElementById("izin-badge");
    if (!badge) return;
    if (jumlah > 0) {
      badge.textContent = jumlah > 99 ? "99+" : String(jumlah);
      badge.style.display = "";
    } else {
      badge.style.display = "none";
    }
  }

  function _bolehPoll() {
    if (typeof MugenState === "undefined" || !MugenState.isLoggedIn()) return false;
    const user = MugenState.getUser();
    return !!user && (user.role === "admin" || user.role === "staff");
  }

  async function _poll() {
    if (!_bolehPoll()) {
      _updateBadge(0);
      return;
    }
    try {
      const hasil = await MugenApi.get("/api/izin-cuti/pending-count");
      _updateBadge(hasil.jumlah || 0);
    } catch (e) {
      // offline/gagal fetch -- diamkan, dicoba lagi di aksi/navigasi berikutnya
    }
  }

  // Dipanggil router.js tiap pindah menu, DAN izin_cuti.js setelah aksi
  // Setujui/Tolak -- satu-satunya dua jalur badge ini di-refresh (selain
  // init() sekali di awal), TIDAK ADA timer/interval sama sekali.
  function refreshNow() {
    _poll();
  }

  function init() {
    _poll();
  }

  return { init, refreshNow };
})();
