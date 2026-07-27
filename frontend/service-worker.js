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
// v15 -> v16: REVISI UI/UX -- Dark Mode & Light Mode per akun (theme.js
// baru, style.css token gelap + switch, endpoint /api/auth/tema,
// Setting > Tampilan di pengaturan.js, switch di sidebar untuk Barber di
// nav.js, router.js memaksa tema TERANG khusus di halaman Web Booking);
// toast sukses/info dihilangkan total, hanya toast error yang tampil
// (ui.js), teks proses ditambahkan di banyak withLoading() (login.js,
// book_public.js, booking.js, produk.js, pengaturan.js, input_data.js,
// pengeluaran.js, sinkronisasi.js); transisi Fade In murni opacity di
// area konten tiap pindah menu (style.css, .content); animasi Slide+Fade
// di halaman Login HANYA saat aplikasi pertama dibuka/setelah Logout
// (state.js, router.js, nav.js, login.js); halaman awal Web Booking kini
// tombol besar "BOOKING" dengan animasi terbang lintasan Z + motion blur
// sebelum form wizard muncul (book_public.js, style.css); Dashboard Owner:
// judul/deskripsi "Service Bulan Ini" disederhanakan jadi judul tabel
// "SERVICE BULAN INI", header "Customer" di tabel Per Barber jadi
// "Service" (dashboard_owner.js).
// v16 -> v17: REVISI Struktur Setting -- tab "Komisi & Bonus" disederhanakan
// jadi "Komisi" (persentase komisi + aturan potongan Bonus Customer saja),
// Target Bonus Service (tier) pindah ke tab Bonus Service jadi satu pusat
// pengaturan bonus, Potongan Modal Chemical dihapus digantikan Harga Modal
// per-service (dipakai langsung oleh hitung_komisi_service, lihat
// database.py/revisi_setting_migrasi.py), tab Layanan dapat kolom "Nilai
// Komisi Barber" (tampilan, dihitung otomatis), tab Uang Harian dapat field
// Target Jumlah Service Harian yang bisa diatur bebas (dulu hardcode 3)
// (semua di pengaturan.js); teks progress Dashboard Barber disederhanakan
// (dashboard_barber.js); Notifikasi Booking Baru -- badge jumlah booking
// belum dikonfirmasi di menu Booking + suara pengingat sintesis Web Audio
// (khusus Admin), modul baru js/booking_notif.js ditambahkan ke APP_SHELL,
// nav.js/app.js/booking.js/style.css berubah untuk mendukungnya.
// v17 -> v18: AUDIT SINKRONISASI ANTAR DEVICE -- booking.js (Booking List,
// Calendar, Toko Libur, Barber Holiday, Closed Slot, "booking saya" untuk
// Barber) dan dashboard_owner.js (grafik harian/bulanan) sebelumnya TIDAK
// PERNAH menampilkan offlineBanner walau semua fetch-nya memakai
// useCache:true -- kalau jaringan sempat putus sesaat, halaman-halaman itu
// diam-diam menampilkan data cache lokal LAMA tanpa tanda apa pun, salah
// satu penyebab gejala "kadang sinkron kadang tidak" yang dilaporkan.
// Sekarang semuanya konsisten menampilkan offlineBanner. produk.js: dropdown
// filter Riwayat Mutasi sekarang ikut di-refresh setelah Tambah/Ubah Produk
// (sebelumnya baru muncul setelah halaman dibuka ulang). Lihat juga
// perubahan backend (database.py WAL mode, main.py logging + endpoint
// /api/health/diagnostik) di CHANGELOG README -- tidak memengaruhi
// APP_SHELL frontend tapi bagian dari perbaikan yang sama.
// v20 -> v21: REVISI Menu Booking & Aset PWA -- nomor WhatsApp customer di
// Menu Booking (booking.js) sekarang link wa.me yang bisa langsung diklik;
// perbaikan logo/banner yang kadang tidak muncul/rusak/lambat saat aplikasi
// pertama dibuka (brand.js: preload + sembunyikan sampai TERBUKTI berhasil
// dimuat alih-alih tampil sebagai ikon rusak; login.js: terapkan cache
// lebih dulu sebelum menunggu refresh dari server; book_public.js: banner
// booking pakai pola sama; index.html: preconnect ke backend Render).
// v21 -> v22: Penyempurnaan Metode Pembayaran Booking (book_public.js) --
// kalau cuma 1 metode pembayaran aktif, customer langsung diarahkan ke
// detailnya tanpa perlu memilih; selector metode tetap tampil seperti
// biasa kalau 2+ metode aktif; tombol "Download QRIS" baru (fetch->blob->
// anchor download, dengan fallback buka tab baru) supaya customer bisa
// unduh gambar QRIS kualitas asli, kompatibel browser & PWA Android/iPhone.
// v22 -> v23: REVISI Penyempurnaan Sistem Booking -- alur Metode Pembayaran
// diubah jadi Ringkasan+Metode -> tombol Konfirmasi -> loading -> Halaman
// Pembayaran (QRIS/transfer/cash) yang baru terpisah, tombol Download QRIS
// didesain ulang modern (ikon + ripple, style.css) dengan nama file rapi
// "<Nama-Barbershop>-QRIS.<ext>" (book_public.js). Slot jam booking hari
// ini kini dihitung memakai zona waktu Asia/Jakarta (WIB) di backend
// (booking_db.py, requirements.txt: tzdata) supaya konsisten dengan jam
// WIB customer, bukan jam server (Render defaultnya UTC).
// v23 -> v24: PR 1 "Revisi Konsep Website Booking" -- tab baru "Website
// Content" di Booking Panel (booking.js, KHUSUS Owner/'admin', TIDAK
// pernah untuk staff) untuk mengelola konten CMS halaman publik /book yang
// akan dibangun ulang jadi landing page penuh di PR 2 (Hero/About/Gallery/
// Visit Us/Social/Footer/Booking CTA/Contact) -- backend baru
// website_content.py + routers/website.py (/api/website/*), tabel baru
// website_gallery (postgres_schema.py sekaligus). style.css: grid
// thumbnail Gallery drag & drop.
// v24 -> v25: PR 2 "Revisi Konsep Website Booking" -- book_public.js
// dibangun ulang total: halaman awal "BOOKING" terbang diganti landing
// page penuh (Hero/About/Gallery/Visit Us/Connect With Us/Closing,
// konsumsi /api/website/* dari PR 1), wizard booking hanya muncul setelah
// tombol "Book Appointment" ditekan, urutan step diubah (Choose Barber ->
// Choose Service -> Select Date -> Select Time -> Your Details -> Payment
// -- Service sekarang SEBELUM Date/Time supaya slot langsung
// duration-aware sejak awal), SELURUH teks UI diterjemahkan ke Bahasa
// Inggris, indikator "Langkah X dari Y" diganti pagination dots di bawah
// konten. style.css: CSS landing page baru, CSS "BOOKING" terbang lama
// dihapus (sudah tidak dipakai), durasi animasi step disamakan ke 300ms.
const CACHE_NAME = "mugen-hair-shell-v25";
const APP_SHELL = [
  "/",
  "/index.html",
  "/manifest.json",
  "/config.js",
  "/css/style.css",
  "/js/state.js",
  "/js/theme.js",
  "/js/api.js",
  "/js/ui.js",
  "/js/brand.js",
  "/js/nav.js",
  "/js/booking_notif.js",
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
