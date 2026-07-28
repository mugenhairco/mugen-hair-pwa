// izin_notif.js — Modul Karyawan (Fase 5): Notifikasi Izin & Cuti (badge
// jumlah pengajuan Pending di menu Izin & Cuti), KHUSUS Owner/Admin --
// pola SAMA PERSIS booking_notif.js (polling ringan tiap POLL_MS ke SATU
// angka /api/izin-cuti/pending-count), TAPI TANPA suara pengingat --
// approval izin/cuti tidak sekritis/se-real-time booking baru, badge
// visual saja sudah cukup memenuhi "notifikasi admin/owner" di spesifikasi.

const MugenIzinNotif = (() => {
  const POLL_MS = 15000;

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
      // offline/gagal fetch -- diamkan, dicoba lagi di poll berikutnya
    }
  }

  // Dipanggil izin_cuti.js setelah aksi Setujui/Tolak supaya badge langsung
  // ter-update saat itu juga, tidak perlu menunggu POLL_MS berikutnya.
  function refreshNow() {
    _poll();
  }

  function init() {
    _poll();
    setInterval(_poll, POLL_MS);
  }

  return { init, refreshNow };
})();
