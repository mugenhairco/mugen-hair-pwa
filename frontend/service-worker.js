// service-worker.js
// TAHAP 1 (skeleton): cache app-shell dasar saja, supaya PWA bisa di-install
// dan sudah tervalidasi sebagai service worker. Strategi caching untuk data
// (API calls) akan disempurnakan di tahap-tahap berikutnya sesuai kebutuhan
// tiap modul (Dashboard, Input Data, dst) — SENGAJA belum agresif men-cache
// data supaya tidak menampilkan data basi/salah ke user (data transaksi &
// stok harus selalu akurat, bukan dari cache lama).

// REVISI: dinaikkan v7 -> v8 karena revisi ini mengubah isi beberapa file
// yang ikut di-cache app-shell (nav.js, router.js, dashboard_owner.js,
// dashboard_barber.js, pengaturan.js, rekap.js). TANPA menaikkan
// CACHE_NAME, browser tidak akan menganggap service-worker.js berubah
// (byte-nya identik), jadi service worker LAMA yang sudah ter-install di
// perangkat user akan terus menyajikan versi JS LAMA dari Cache Storage
// selamanya walau server sudah di-deploy ulang dengan kode baru -- persis
// gejala "deploy sukses tapi tampilan masih perilaku lama". Setiap revisi
// berikutnya yang mengubah file di APP_SHELL WAJIB menaikkan angka ini.
// v8 -> v9: kartu "Jumlah Service" (dashboard_owner.js, dashboard_barber.js)
// dan perbaikan login.js (autocapitalize).
// v9 -> v10: konfirmasi Keluar, spinner loading global + delay 1,5 detik di
// semua tombol yang memanggil server (ui.js, api.js, nav.js, login.js, dan
// semua pages/*.js), bugfix pesan error login (api.js), grafik pendapatan
// harian/bulanan khusus Dashboard Owner (dashboard_owner.js, style.css).
// v10 -> v11: Modul BOOKING baru -- halaman publik /book (book_public.js)
// dan halaman internal Booking (booking.js) ditambahkan ke APP_SHELL,
// nav.js/router.js/style.css berubah untuk mendukungnya.
// v11 -> v12: Penyempurnaan Form Booking Customer -- book_public.js (header/
// banner/footer/pesan dari Setting, kalender ikut Hari Operasional & Hari
// Libur Toko, foto barber, label/instruksi metode pembayaran custom),
// booking.js (Hari Operasional, Hari Libur Toko, Label & Instruksi Metode
// Pembayaran, Link Booking, kontrol status/foto/urutan barber & urutan
// service), pengaturan.js (Tagline/Deskripsi/Website/Banner di Identitas,
// kontrol status/foto/urutan barber, urutan layanan), style.css berubah.
// v12 -> v13: Perbaikan UI/UX halaman booking -- book_public.js (animasi
// slide+fade antar step, kartu "Booking Berhasil" dirapikan jadi field
// berlabel), style.css berubah.
// v13 -> v14: REVISI -- Modul Produk (Harga Modal/Harga Jual, tipe transaksi
// Tester) di produk.js; kartu "Penjualan Produk" di dashboard_owner.js;
// label acuan Bonus Service dinamis (bukan hardcode Dry Cut + Cut & Wash
// lagi) di dashboard_owner.js/dashboard_barber.js; tab Setting > Bonus
// Service & Setting > Uang Harian baru di pengaturan.js; loading animation
// + teks kustom saat Sign Out (nav.js) dan withLoading() diperluas
// (ui.js); bugfix konsistensi loading di booking.js (QRIS merchant);
// style.css berubah.
// v14 -> v15: REVISI UI/UX Modern -- tema TERANG baru menggantikan tema
// gelap+emas (style.css, palet warna/radius/shadow/tipografi/animasi
// menyeluruh termasuk Web Booking), watermark developer + theme-color baru
// (index.html, manifest.json), label RAFIQ dihapus dari tampilan Barber
// (pengaturan.js, data/logika is_rafiq tidak berubah).
const CACHE_NAME = "mugen-hair-shell-v15";
const APP_SHELL = [
  "/",
  "/index.html",
  "/manifest.json",
  "/config.js",
  "/css/style.css",
  "/js/state.js",
  "/js/api.js",
  "/js/ui.js",
  "/js/brand.js",
  "/js/nav.js",
  "/js/router.js",
  "/js/app.js",
  "/js/pages/login.js",
  "/js/pages/dashboard_owner.js",
  "/js/pages/dashboard_barber.js",
  "/js/pages/input_data.js",
  "/js/pages/rekap.js",
  "/js/pages/pengeluaran.js",
  "/js/pages/pengaturan.js",
  "/js/pages/produk.js",
  "/js/pages/sinkronisasi.js",
  "/js/pages/booking.js",
  "/js/pages/book_public.js",
  // TAHAP 13: ikon PWA (sebelumnya file-file ini belum ada sama sekali)
  "/icons/favicon.ico",
  "/icons/icon-72.png",
  "/icons/icon-96.png",
  "/icons/icon-128.png",
  "/icons/icon-144.png",
  "/icons/icon-152.png",
  "/icons/icon-192.png",
  "/icons/icon-384.png",
  "/icons/icon-512.png",
  "/icons/icon-maskable-192.png",
  "/icons/icon-maskable-512.png",
  "/icons/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // JANGAN cache request ke API — data bisnis harus selalu fresh dari server,
  // tidak boleh ada risiko menampilkan angka lama/salah dari cache.
  if (url.pathname.startsWith("/api/")) {
    return; // biarkan lewat langsung ke network, tidak disentuh service worker
  }

  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
