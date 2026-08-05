// izin_notif.js — Modul Karyawan (Fase 5): Notifikasi Izin & Cuti (badge
// jumlah pengajuan Pending di menu Izin & Cuti), KHUSUS Owner/Admin --
// pola SAMA PERSIS booking_notif.js (polling ringan tiap POLL_MS ke SATU
// angka /api/izin-cuti/pending-count), TAPI TANPA suara pengingat --
// approval izin/cuti tidak sekritis/se-real-time booking baru, badge
// visual saja sudah cukup memenuhi "notifikasi admin/owner" di spesifikasi.
//
// REVISI Efisiensi Polling: interval HANYA jalan selagi tab ini terlihat
// (Page Visibility API) -- di-pause total begitu tab disembunyikan/
// diminimize/pindah tab lain (TIDAK ADA request sama sekali ke backend
// selama itu), lalu di-refresh SEKALI + interval dilanjutkan lagi begitu
// tab terlihat kembali. Ini mengikuti praktik umum SaaS untuk badge
// notifikasi berbasis polling -- data tetap akurat kapan pun user benar-
// benar melihat aplikasinya, tanpa membebani server saat tab idle di
// background (yang sebelumnya tetap poll terus tanpa henti).

const MugenIzinNotif = (() => {
  const POLL_MS = 15000;
  let _timer = null;

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

  function _mulaiInterval() {
    if (_timer) return; // sudah jalan
    _timer = setInterval(_poll, POLL_MS);
  }

  function _hentikanInterval() {
    if (_timer) {
      clearInterval(_timer);
      _timer = null;
    }
  }

  // Dipanggil izin_cuti.js setelah aksi Setujui/Tolak supaya badge langsung
  // ter-update saat itu juga, tidak perlu menunggu POLL_MS berikutnya.
  function refreshNow() {
    _poll();
  }

  function init() {
    _poll();
    _mulaiInterval();
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") {
        _hentikanInterval();
      } else {
        _poll(); // data mungkin sudah basi selama tab disembunyikan
        _mulaiInterval();
      }
    });
  }

  return { init, refreshNow };
})();
