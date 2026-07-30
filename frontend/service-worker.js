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
// v25 -> v26: PR 3 "Revisi Konsep Website Booking" (terakhir dari 3 PR) --
// SEO (title/meta description/keywords/OG Image, di-inject ke <head> saat
// landing page dibuka), Branding (Primary/Secondary Color HANYA berlaku
// di halaman publik /book lewat CSS custom property scoped, Favicon &
// Splash Screen upload dengan catatan jujur soal PWA yang sudah
// ter-install), Footer legal (Privacy Policy & Terms and Conditions,
// tampil lewat overlay tanpa route baru). Backend: website_content.py +
// routers/website.py bertambah field/endpoint baru (reuse tabel settings
// yang sudah ada, tidak ada skema baru), booking.js (tab Website Content)
// dapat card SEO & Branding baru.
// v26 -> v27: REVISI STRUKTUR WEBSITE CONTENT -- Tagline/Deskripsi/Alamat/
// Nomor WA/Website/Jam Operasional/Header/Footer dipindah TOTAL dari Setting
// > Identitas Barbershop & Booking Settings ke Booking > Website Content
// (pengaturan_identitas.py, booking_db.py, pengaturan.js, booking.js);
// SEO/Branding warna/Favicon/Splash Screen/Footer legal DIHAPUS TOTAL, tidak
// ada penggantinya (website_content.py, routers/website.py, booking.js).
// Hero sekarang mendukung Gambar ATAU Video (hero-image endpoint baru,
// format video fleksibel MP4/MOV/WEBM/dst). Background Website baru --
// Image (upload + slider opacity) atau Light/Dark preset polos, kontras
// otomatis menyesuaikan (background-image endpoint baru, book_public.js
// terapkanBackground()). book_public.js dibangun ulang total: urutan
// section Hero/About/Gallery/Visit Us/Opening Hours/Book Appointment/
// Connect With Us/Footer, SATU tombol Book Appointment saja (link selalu ke
// wizard, tidak bisa diatur), Connect With Us jadi ikon kecil horizontal
// (Instagram/TikTok/WhatsApp saja, auto-hide kalau semua kosong), setiap
// section/elemen kosong TIDAK PERNAH dirender (bukan disembunyikan CSS) --
// tidak ada lagi kotak/jarak kosong. Watermark developer BESAR disembunyikan
// khusus di /book (router.js + book_public.js, class body.book-public-
// active), watermark KECIL footer tetap tampil di mana pun tanpa perubahan.
// style.css: preset warna Light/Dark background, layer gambar background +
// opacity, styling Connect With Us baru, CSS legal/SEO/Branding/Closing lama
// yang sudah tidak terpakai dihapus.
// v27 -> v28: Laporan PDF (Setting > Backup) -- Laporan Transaksi & Laporan
// Pengeluaran sekarang dipilih lewat rentang tanggal bebas (Dari - Sampai,
// pengaturan.js) alih-alih Bulan/Tahun, supaya teks "Periode:" di PDF
// menunjukkan rentang tanggal sebenarnya (mis. "3 - 25 Juli 2026"), bukan
// cuma nama bulan & tahun (laporan_pdf.py, database.py get_transaksi_list(),
// pengeluaran_db.py get_pengeluaran_list(), routers/pengaturan.py). Rekap
// Bulanan Barber TETAP Tahun+Bulan (perhitungan bonus/komisi/uang harian
// bertumpu pada batas bulan kalender, tidak diubah).
// v28 -> v29: Modul Karyawan (Fase 1) -- Slip Gaji Otomatis. Sidebar dapat
// mekanisme grup/submenu BARU (sebelumnya 100% flat, nav.js) supaya modul
// Karyawan berikutnya (Kasbon, Reimburse, dst) tinggal menambah entri
// tanpa mengubah mekanismenya lagi; grup dengan 1 child (kondisi saat ini)
// otomatis dirender flat, "naik kelas" jadi dropdown begitu child kedua
// ditambahkan. Slip Gaji = Gaji Pokok (field baru per-barber, opsional,
// default 0, backend slip_gaji_db.py) + Komisi/Tips/Uang Harian/Bonus
// Customer (dari database.get_ringkasan_barber_bulan() yang SUDAH ADA,
// bukan dihitung ulang) - Potongan Kasbon (selalu 0/manual, modul Kasbon
// belum ada) - Potongan Lain (manual) = Total Diterima, dengan status
// Belum/Sudah Dibayar (terkunci begitu Sudah Dibayar). Halaman baru
// pages/slip_gaji.js (satu halaman, sudut pandang beda untuk Owner/Admin
// vs Barber, sama seperti pola Rekap), unduh PDF lewat laporan_pdf.py
// (helper tata letak yang sama dipakai ulang, TIDAK ada layout PDF baru).
// v30: Modul Karyawan Fase 2 (Kasbon Karyawan) -- halaman baru
// pages/kasbon.js, grup sidebar "Karyawan" sekarang punya 2 child (Slip
// Gaji + Kasbon) jadi benar-benar dirender sebagai dropdown (lihat nav.js).
// v31: Modul Karyawan Fase 3 (Komisi -- Audit & Penyesuaian) -- halaman baru
// pages/komisi.js (penyesuaian bonus/potongan komisi manual + audit trail,
// terintegrasi ke Slip Gaji lewat kolom penyesuaian_komisi), grup sidebar
// "Karyawan" sekarang punya 3 child (Slip Gaji/Kasbon/Komisi).
// v32: Modul Karyawan Fase 4 (Reimburse) + Fase 5 (Izin & Cuti) -- dua
// halaman baru pages/reimburse.js (klaim self-service barber + upload
// bukti + approval, terintegrasi ke Slip Gaji lewat kolom reimburse) dan
// pages/izin_cuti.js (pengajuan izin/cuti self-service + approval + badge
// notifikasi lewat js/izin_notif.js baru), grup sidebar "Karyawan"
// sekarang punya 5 child. nav.js: mekanisme badge digeneralisasi (data-
// driven lewat badgeId/badgeRoles, bukan hardcode "#/booking" lagi).
// v33: Modul Keuangan Fase 1 (Pemasukan) + Fase 2 (Transfer Kas/Bank) --
// dua halaman baru pages/pemasukan.js (cermin pengeluaran.js) dan
// pages/transfer.js. Grup sidebar baru "Keuangan" berisi Pemasukan/
// Pengeluaran/Transfer Kas-Bank -- Pengeluaran DIPINDAH ke grup ini (hash
// #/pengeluaran & halamannya TIDAK berubah, murni penataan ulang sidebar).
// v34: Transfer Kas/Bank DIHAPUS TOTAL, diganti pages/uang_kas.js (Saldo
// Kas Awal + penyesuaian manual). Karyawan non-barber (Kasir/OB/Kru)
// ditambah, tab Setting > Barber jadi Setting > Karyawan.
// v35: Seluruh ikon aplikasi (favicon, ikon manifest PWA semua ukuran,
// maskable, apple-touch-icon) diganti dari placeholder logo "M" ke logo
// resmi MUGEN Hair Co. -- nama file TIDAK berubah, jadi CACHE_NAME WAJIB
// dinaikkan supaya instalasi yang sudah ada tidak terus memakai ikon lama
// dari cache (pola sama seperti setiap perubahan APP_SHELL lain).
// v36: Fitur Hapus Rekap Transaksi khusus Owner -- dialog konfirmasi
// modern baru (ui.js: confirmModal(), style.css: .modal-*) + tombol
// Hapus di tabel Rekap Transaksi (rekap.js).
// v37: Perluasan Hapus Rekap Transaksi -- kolom Aksi (Owner) sekarang juga
// menghapus klaim Reimburse yang sudah disetujui, dan membatalkan
// pembayaran Kasbon manual (bukan hasil potong otomatis Slip Gaji),
// rekap.js.
// v38: Dukungan Barber + Non-Barber -- Input Data punya dropdown Input
// Data Barber/Non-Barber baru (input_data.js), Rekap Transaksi menampilkan
// & menghapus baris Gaji Non-Barber juga (rekap.js), Setting > Karyawan
// bisa membuat role kustom Non-Barber (pengaturan.js).
// v39: Perbaikan Alur Cetak PDF -- tombol "Cetak PDF" di SELURUH halaman
// (Rekap, Slip Gaji, Kasbon, Komisi, Reimburse, Izin & Cuti, Pemasukan,
// Pengeluaran, Uang Kas) sekarang menampilkan Preview PDF dulu (Zoom/Nomor
// Halaman/Download/Print/Kembali, lihat pdf_preview.js + vendor/pdfjs/),
// TIDAK langsung mengunduh. Rekap Transaksi PDF punya pilihan Jenis
// Laporan baru "Rekap Periode (Ringkasan)" (satu baris per karyawan untuk
// seluruh periode). Kolom Service di seluruh tampilan Rekap sekarang
// multi-baris (satu jenis service per baris, bukan digabung koma).
// v40: Revisi kolom Keterangan -- Rekap Periode (Ringkasan) sekarang punya
// kolom Keterangan (Catatan/Kasbon/Reimburse/tiap hari Libur, satu baris
// per info, lihat rekap_ringkasan.py). Kolom Ket. di Rekap Transaksi
// (layar) dan Ket di Rekap Detail (PDF) sekarang juga multi-baris kalau
// berisi lebih dari satu info, bukan digabung titik-koma (ui.js
// keteranganCell(), laporan_pdf.py _sel_keterangan()).
const CACHE_NAME = "mugen-hair-shell-v41";
const APP_SHELL = [
  "/",
  "/index.html",
  "/manifest.json",
  "/config.js",
  "/css/style.css",
  "/js/pdfjs_boot.js",
  "/js/state.js",
  "/js/theme.js",
  "/js/api.js",
  "/js/ui.js",
  "/js/pdf_preview.js",
  "/js/brand.js",
  "/js/nav.js",
  "/js/booking_notif.js",
  "/js/izin_notif.js",
  "/js/router.js",
  "/js/app.js",
  "/js/pages/login.js",
  "/js/pages/dashboard_owner.js",
  "/js/pages/dashboard_barber.js",
  "/js/pages/input_data.js",
  "/js/pages/rekap.js",
  "/js/pages/pengeluaran.js",
  "/js/pages/pemasukan.js",
  "/js/pages/uang_kas.js",
  "/js/pages/slip_gaji.js",
  "/js/pages/kasbon.js",
  "/js/pages/komisi.js",
  "/js/pages/reimburse.js",
  "/js/pages/izin_cuti.js",
  "/js/pages/pengaturan.js",
  "/js/pages/produk.js",
  "/js/pages/booking.js",
  "/js/pages/book_public.js",
  // Perbaikan Alur Cetak PDF: PDF.js (build lokal, BUKAN dari CDN, supaya
  // Preview PDF tetap bisa dipakai offline -- lihat pdfjs_boot.js).
  "/vendor/pdfjs/pdf.min.js",
  "/vendor/pdfjs/pdf.worker.min.js",
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
