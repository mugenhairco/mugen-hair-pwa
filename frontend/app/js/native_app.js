// native_app.js — FITUR khusus APK Android (Capacitor, lihat android-app/):
// izin Lokasi & Notifikasi Push diminta OTOMATIS SEKALI, segera setelah
// login PERTAMA di dalam aplikasi native -- BERBEDA dari perilaku browser/
// PWA biasa, yang tetap murni opt-in lewat tombol eksplisit di halaman
// Pengaturan (admin/staff)/Izin & Cuti (barber), lihat push_notif.js.
// Dipanggil dari pages/login.js SETELAH login berhasil, HANYA kalau
// window.Capacitor?.isNativePlatform() true -- di browser biasa,
// window.Capacitor tidak pernah ada sama sekali, jadi kode di file ini
// TIDAK PERNAH berjalan di luar APK.
//
// Ditandai localStorage supaya dialog izin HANYA diminta SEKALI per
// perangkat (bukan tiap kali login) -- alasan sama seperti push_notif.js
// TIDAK PERNAH auto-prompt: begitu pengguna menekan "Tolak", browser/OS
// tidak akan menampilkan dialog itu lagi sama sekali (permanen "denied")
// sampai diaktifkan manual lewat Setting Android, jadi meminta ulang tiap
// login hanya percuma/mengganggu.
const MugenNativeApp = (() => {
  const FLAG_KEY = "mugen_native_izin_diminta_v1";

  function _jalanDiApk() {
    return !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());
  }

  // Kirim lokasi ke backend best-effort -- gagal (izin ditolak, GPS mati,
  // timeout, offline, dst) TIDAK PERNAH ditampilkan ke pengguna sebagai
  // error, sama seperti pola MugenBookingNotif/MugenIzinNotif di file lain.
  function _mintaLokasi() {
    if (!("geolocation" in navigator)) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        MugenApi.put("/api/auth/lokasi", {
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
        }).catch(() => {});
      },
      () => {},
      { timeout: 15000, maximumAge: 60000 }
    );
  }

  async function _mintaPush() {
    if (typeof MugenPushNotif === "undefined") return;
    try {
      const sudahAktif = await MugenPushNotif.subscriptionAktif();
      if (!sudahAktif) await MugenPushNotif.aktifkan();
    } catch (e) {
      // Gagal diam-diam (VAPID belum diisi Owner, izin ditolak pengguna,
      // browser/WebView tidak mendukung, dst) -- fitur opsional, TIDAK
      // boleh mengganggu alur login sama sekali.
    }
  }

  function izinPertamaKali() {
    if (!_jalanDiApk()) return;
    if (localStorage.getItem(FLAG_KEY)) return;
    localStorage.setItem(FLAG_KEY, "1");
    _mintaLokasi();
    _mintaPush();
  }

  return { izinPertamaKali };
})();
