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
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js")
      .then((reg) => reg.update().catch(() => {}))
      .catch((err) => {
        console.error("Gagal mendaftarkan service worker:", err);
      });
  });
}

window.addEventListener("DOMContentLoaded", () => {
  MugenBrand.refresh();
  MugenRouter.init();
  // REVISI: Notifikasi Booking Baru -- dimulai SEKALI di sini (bukan di
  // dalam halaman Booking) supaya badge + suara tetap aktif app-wide,
  // TIDAK terikat ke halaman mana pun yang sedang dibuka Admin. Modul ini
  // sendiri yang memeriksa (tiap poll) apakah user sedang login sebagai
  // admin -- aman dipanggil walau saat ini masih di halaman Login.
  MugenBookingNotif.init();
});
