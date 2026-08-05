// app.js — entry point JS frontend.
// TAHAP 3-9: mendaftarkan service worker lalu menjalankan router (login,
// dashboard, input data, rekap, pengeluaran).
// TAHAP 10: refresh identitas barbershop (nama/logo) sekali di awal supaya
// tab/judul browser & sidebar terisi data terbaru dari Setting.
// REVISI: setelah registrasi, panggil registration.update() supaya app aktif
// meminta browser mengecek versi service-worker.js terbaru di setiap kali
// aplikasi dibuka -- sebelumnya hanya mengandalkan jadwal pengecekan bawaan
// browser (yang bisa jarang/lambat), jadi kalau CACHE_NAME dinaikkan di
// deploy baru (lihat service-worker.js), user yang PWA-nya sudah ter-install
// lebih cepat mendapat versi baru pada kunjungan berikutnya.
// PERBAIKAN MEKANISME CACHE & UPDATE PWA (v57): keluhan "harus Hard
// Refresh/hapus cache manual" -- registrasi sekarang pakai
// updateViaCache:"none" (paksa browser SELALU mengambil byte
// service-worker.js dari network, tidak pernah dari HTTP cache, saat
// mengecek update -- tanpa ini, host yang meng-cache file statis secara
// agresif bisa membuat browser mengira service-worker.js "tidak berubah"
// walau sebenarnya sudah di-deploy ulang). Update dicek lebih sering
// (tiap 1 jam + tiap tab kembali terlihat), bukan cuma sekali saat app
// dibuka -- banyak user PWA membiarkan tab/app terbuka berhari-hari.
// Begitu Service Worker baru TERDETEKSI (bukan instalasi pertama kali,
// lihat pwa_update.js), tampilkan banner "Muat Ulang" -- TIDAK PERNAH
// reload otomatis tanpa aksi user (aplikasi ini penuh form input yang
// belum tentu sudah tersimpan).
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js", { updateViaCache: "none" })
      .then((reg) => {
        reg.update().catch(() => {});

        reg.addEventListener("updatefound", () => {
          const workerBaru = reg.installing;
          if (!workerBaru) return;
          workerBaru.addEventListener("statechange", () => {
            // 'installed' + SUDAH ADA controller aktif = ini benar-benar
            // UPDATE (ganti versi) -- BUKAN instalasi pertama kali PWA ini
            // di perangkat user (saat itu navigator.serviceWorker.controller
            // masih null), yang tidak perlu diberi tahu apa-apa.
            if (workerBaru.state === "installed" && navigator.serviceWorker.controller) {
              MugenPwaUpdate.tampilkanNotifikasi();
            }
          });
        });

        setInterval(() => reg.update().catch(() => {}), 60 * 60 * 1000);
        document.addEventListener("visibilitychange", () => {
          if (document.visibilityState === "visible") reg.update().catch(() => {});
        });
      })
      .catch((err) => {
        console.error("Gagal mendaftarkan service worker:", err);
      });
  });
}

window.addEventListener("DOMContentLoaded", () => {
  // BUGFIX Register (Landing Page SaaS): halaman Register SELALU platform
  // Rivoir, TIDAK PERNAH branding tenant (lihat brand.js::
  // refreshPlatformOnly(), dipanggil sendiri oleh PageRegister.render()
  // di bawah lewat MugenRouter.init()/handle()) -- refresh() tenant-aware
  // di sini (dari slug "diingat") kalau TETAP dipanggil untuk hash ini
  // akan BALAPAN dengan refreshPlatformOnly() (keduanya sama-sama fetch
  // async independen) dan bisa "menang" belakangan, menimpa balik DOM ke
  // branding tenant yang kebetulan pernah dibuka di perangkat itu --
  // dilewati KHUSUS di sini, halaman lain semuanya TIDAK berubah.
  if (!location.hash.startsWith("#/register")) {
    MugenBrand.refresh();
  }
  MugenRouter.init();
  // FONDASI Multi-Tenant Phase 3: cache akses_diblokir (dari localStorage,
  // lihat subscription.js) sudah dipakai router.js SAAT init() di atas --
  // refresh() di sini menyegarkannya dari server di background, lalu
  // memanggil handle() lagi supaya kalau statusnya BERBEDA dari cache
  // (mis. baru diblokir Super Admin sejak kunjungan terakhir), halaman
  // langsung dialihkan ke status subscription tanpa perlu navigasi manual.
  MugenSubscription.refresh().then(() => MugenRouter.handle());
  // REVISI: Notifikasi Booking Baru -- dimulai SEKALI di sini (bukan di
  // dalam halaman Booking) supaya badge + suara tetap aktif app-wide,
  // TIDAK terikat ke halaman mana pun yang sedang dibuka Admin. Modul ini
  // sendiri yang memeriksa (tiap poll) apakah user sedang login sebagai
  // admin -- aman dipanggil walau saat ini masih di halaman Login.
  MugenBookingNotif.init();
  // Modul Karyawan Fase 5: Notifikasi Izin & Cuti -- pola sama seperti
  // MugenBookingNotif di atas (badge jumlah pengajuan Pending, app-wide).
  MugenIzinNotif.init();
});
