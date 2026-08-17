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
// v44 -> v45: FONDASI Multi-Tenant Phase 2.2 -- Tenant Branding & Platform
// Branding (White Label). brand.js dirombak: sumber data pindah dari
// /api/pengaturan/identitas ke /api/tenant/branding (fallback platform
// "Developer" saat tenant belum dikenali), favicon & warna Primary/
// Secondary sekarang ikut diterapkan secara dinamis (bukan cuma nama/logo).
// refresh() (fetch ke server) sekarang HANYA dipanggil sekali saat app.js
// boot + sekali lagi tepat setelah login berhasil -- router.js (dipanggil
// tiap pindah menu) sekarang pakai applyToDom() dari cache saja, TIDAK
// fetch ulang tiap navigasi. Tab baru Setting > Branding (pengaturan.js).
// index.html/manifest.json: fallback statis sebelum JS jalan diganti dari
// "MUGEN Hair Co." jadi "Developer" (branding platform generik, BUKAN
// nama satu tenant tertentu). style.css: token --accent-secondary baru.
// v45 -> v46: Setting > Branding tab baru (pengaturan.js) -- Nama
// Barbershop, Logo, Favicon (upload/hapus), Primary/Secondary Color,
// Tagline, Alamat, WhatsApp, Email, Website dalam satu form, plus entri
// baru di grup Setting pada Hak Akses Admin ("izin_setting_branding").
// v46 -> v47: brand.js -- query string `?tenant=<slug>` di URL saat ini
// (mekanisme tenant discovery yang sudah ada sejak Phase 1) sekarang juga
// dipakai untuk menampilkan branding tenant SEBELUM login, ditemukan lewat
// verifikasi E2E langsung (link khusus per-toko sebelumnya cuma didukung
// endpoint publik lain seperti /book, belum di brand.js).
// v55 -> v56: FONDASI Multi-Tenant Phase 3 (Subscription & Tenant
// Lifecycle) -- subscription.js baru (cache akses_diblokir app-wide),
// pages/subscription_blocked.js baru (halaman status saat Expired/
// Suspended/Cancelled), router.js/app.js/login.js mengalihkan tenant yang
// diblokir, pengaturan.js tab baru "Subscription" (Owner read-only),
// superadmin.js kelola package/status/trial/grace/pembayaran VA per toko,
// book_public.js menampilkan "Booking Tidak Tersedia" saat diblokir,
// style.css badge-warning baru.
// v56 -> v57: PERBAIKAN MEKANISME CACHE & UPDATE PWA -- keluhan "harus
// Hard Refresh/hapus cache manual tiap deploy baru" diperbaiki di EMPAT
// lapisan sekaligus:
// 1. install: precache SEKARANG fetch(url, {cache:"reload"}) satu per
//    satu (bukan cache.addAll() polos) -- addAll() tidak menjamin bypass
//    HTTP cache browser/CDN, jadi precache BISA SAJA diam-diam mengambil
//    byte LAMA walau CACHE_NAME sudah berubah, kalau host menyajikan
//    Cache-Control yang agresif untuk file statis.
// 2. fetch: navigasi (buka halaman/reload, event.request.mode ===
//    "navigate") sekarang NETWORK-FIRST (fallback ke cache index.html
//    HANYA saat offline) -- sebelumnya cache-first PENUH, jadi index.html
//    (dan referensi <script>/<link> ?v=... di dalamnya) bisa tersaji dari
//    cache lama sampai proses update Service Worker BENAR-BENAR kelar,
//    walau user sudah menekan reload biasa.
// 3. APP_SHELL sekarang membawa query "?v=<versi>" (index.html memakai
//    query yang SAMA persis untuk tiap <script src>/<link href>) --
//    cache-busting di lapisan URL, independen total dari Service Worker
//    (tetap benar walau SW gagal register/browser tidak mendukungnya).
// 4. app.js: registrasi sekarang pakai updateViaCache:"none" (paksa
//    browser SELALU network-check byte service-worker.js INI SENDIRI,
//    tidak pernah dari HTTP cache -- ini file paling kritis untuk selalu
//    fresh, karena SELURUH mekanisme deteksi update bergantung padanya),
//    mengecek update tiap 1 jam + tiap tab kembali terlihat, dan
//    menampilkan banner "Muat Ulang" (pwa_update.js, TIDAK PERNAH reload
//    otomatis tanpa aksi user -- aplikasi ini penuh form, reload paksa
//    berisiko menghilangkan data yang belum tersimpan).
// v57 -> v58: FONDASI Multi-Tenant Phase 4 (Billing & Payment Midtrans) --
// pages/billing.js baru (halaman Owner: paket & status langganan, katalog
// paket upgrade/downgrade/perpanjang, checkout Snap Midtrans dimuat
// dinamis, riwayat invoice), nav.js/router.js menu & rute baru "#/billing"
// (khusus role admin, TERPISAH dari tab Subscription read-only Phase 3
// yang tidak diubah).
// v58 -> v59: FONDASI Multi-Tenant Phase 4 lanjutan -- superadmin.js
// tiga kartu baru (Paket Billing: harga/durasi/urutan/status/deskripsi/
// limit + checkbox fitur per paket, Katalog Fitur: tambah/nonaktifkan/
// hapus, Monitoring Pembayaran: invoice seluruh toko), kartu Phase 3 yang
// sudah ada TIDAK diubah.
// v69 -> v70: Efisiensi polling badge notifikasi -- booking_notif.js/
// izin_notif.js sekarang pause otomatis (Page Visibility API) saat tab
// disembunyikan/pindah tab lain (SEBELUMNYA: setInterval POLL_MS=15000
// terus jalan app-wide tanpa henti walau tab di background), lalu refresh
// SEKALI + lanjut polling lagi begitu tab terlihat kembali -- mengurangi
// request idle ke backend TANPA mengubah frekuensi (tetap 15 detik) atau
// logika/akurasi badge sama sekali saat tab aktif dilihat.
// v70 -> v71: badge Izin & Cuti (izin_notif.js) TIDAK lagi polling
// periodik sama sekali (SEBELUMNYA: setInterval 15 detik + pause saat tab
// hidden dari revisi v70 di atas) -- sekarang MURNI event-driven: refresh
// hanya saat aplikasi pertama dibuka, tiap kali user berpindah menu
// (router.js::handle()), dan tepat setelah aksi Setujui/Tolak
// (izin_cuti.js) -- permintaan eksplisit Owner supaya backend TIDAK
// dihubungi sama sekali selagi tidak ada aksi apa pun. booking_notif.js
// (badge + suara pengingat Booking baru) TIDAK ikut diubah -- tetap
// polling periodik (dengan pause saat tab hidden dari v70), karena
// notifikasi booking baru butuh lebih real-time (ada suara pengingat).
// v71 -> v72: BUGFIX KRITIS -- Super Admin sempat menampilkan branding
// tenant TERAKHIR yang login di perangkat itu (nama/logo/favicon/warna),
// bukan branding platform, karena cache localStorage branding & slug
// tenant "diingat" TIDAK dihapus saat logout (by design, untuk UX tenant
// yang login lagi) sehingga sempat terbaca/terkirim sebelum refresh()
// selesai. brand.js sekarang mengecek role sesi SEKARANG secara SINKRON
// di dua titik (module load + awal refresh(), SEBELUM `await` apa pun)
// -- Super Admin SELALU dipaksa branding platform + cache tenant
// dibersihkan seketika, TANPA menunggu jaringan, TIDAK ADA jeda/flash
// branding tenant sama sekali lagi (hard refresh, login baru, maupun
// mode Incognito).
// v72 -> v73: 4 micro-interaction terakhir dari checklist Premium UX
// (fondasi + rollout ke seluruh halaman sudah selesai sebelumnya) --
// shake singkat pada .login-error begitu pesan validasi muncul, transisi
// hover/press + fade-in pada Kalender Booking publik (book_public.js),
// tooltip CSS murni ([data-tooltip]) menggantikan title native HANYA di
// sidebar collapsed (nav.js), dan override prefers-reduced-motion untuk
// accordion sidebar (.nav-group-toggle dkk, transisi aslinya tidak
// berubah). Semua CSS murni, tanpa JS baru kecuali penggantian atribut
// title -> data-tooltip/aria-label di nav.js.
// v73 -> v74: BUGFIX Rekap Transaksi (KHUSUS akun Barber, TIDAK mengubah
// tampilan Owner/Admin/Super Admin sama sekali): kolom Komisi yang
// sebelumnya tidak pernah ditampilkan sekarang muncul, Reimburse/Kasbon
// Dibayar jadi kolom sendiri (bukan tersembunyi di dalam Pendapatan), dan
// Pendapatan sekarang benar-benar total baris itu (Komisi+Uang Harian+
// Tips, sebelumnya Uang Harian tidak ikut terhitung) -- lihat rekap.js
// (kolomBarber, isAdmin branch TIDAK disentuh) & laporan_pdf.py
// (buat_pdf_rekap_transaksi(is_barber=...), PDF Barber sekarang landscape
// supaya header tidak terpotong seperti sebelumnya).
// v74 -> v75: BUGFIX Register (Landing Page SaaS): halaman registrasi
// tenant baru sebelumnya bisa menampilkan nama/logo tenant LAIN yang
// pernah login/dibuka di perangkat itu (cache branding tenant-aware,
// pola sama seperti Login) -- SEKARANG SELALU platform "Rivoir" lewat
// MugenBrand.refreshPlatformOnly() (brand.js) + app.js melewati
// MugenBrand.refresh() tenant-aware khusus untuk hash #/register supaya
// tidak balapan/menimpa balik. Halaman lain (Login, dst) TIDAK berubah.
// v75 -> v76: FITUR Alamat Website Tenant (Dashboard Super Admin > Daftar
// Toko): kolom baru "Alamat Website" -- URL subdomain tenant (dari slug)
// atau custom domain (kalau sudah diisi, otomatis ikut begitu berubah di
// masa depan), link bisa diklik langsung + tombol Salin/Buka, "Belum
// dibuat" untuk tenant tanpa slug/domain -- lihat superadmin.js,
// tenant_db.get_website_url(). Murni tampilan/derivasi, tidak ada kolom
// database baru, tidak menyentuh registrasi/autentikasi/multi-tenant.
// v76 -> v77: FITUR Email, Verifikasi Email, Lupa Kata Sandi (Resend) --
// tiga halaman publik baru (lupa_password.js, reset_password.js,
// verify_email.js, semua branding platform Rivoir), tombol "Lupa Kata
// Sandi?" + gerbang "email belum diverifikasi" di login.js, layar "cek
// email Anda" menggantikan auto-login di register.js (tenant baru wajib
// verifikasi dulu sebelum bisa login -- alur #/billing/checkout/webhook
// itu sendiri TIDAK berubah, hanya bergeser ke SETELAH verifikasi), dan
// tab Pengaturan > Profil (Owner menambah/verifikasi email sendiri,
// khusus tenant lama yang belum punya). Tidak mengubah database/JWT/API
// yang sudah ada -- lihat ui.js (ambilQueryHash), router.js (3 route
// baru).
// v77 -> v78: FITUR Subdomain Otomatis per Tenant -- slug hasil registrasi
// mandiri sekarang tanpa pemisah ("mugenhairco", bukan "mugen-hair-co"),
// resolusi tenant dari subdomain (<slug>.rivoirsett.com) AKTIF SECARA
// DEFAULT (sebelumnya opt-in lewat env var kosong), halaman baru "Tenant
// Tidak Ditemukan" (pages/tenant_not_found.js) ditampilkan lewat
// tenant_guard.js di app.js kalau subdomain yang dibuka tidak dikenal
// backend. Root Landing Page (frontend/index.html) redirect bare
// subdomain tenant ke /app/. Tidak mengubah database/JWT/API/isolasi
// data multi-tenant yang sudah ada.
//
// v78 -> v79: FITUR Undangan User Tenant -- field Email opsional di form
// "Tambah User" (Pengaturan > User, pengaturan.js), kirim email undangan
// verifikasi otomatis kalau diisi (backend: routers/pengaturan.py,
// email_templates.py::template_undangan_user()). Tidak mengubah alur
// login/pembuatan user yang sudah ada (password Owner tetap langsung
// berlaku, TIDAK menunggu verifikasi apa pun).
//
// CATATAN PENTING soal ASSET_VERSION di bawah -- WAJIB angka literal DI
// FILE INI (BUKAN diimpor dari file lain mana pun): satu-satunya sinyal
// yang membuat browser mendeteksi "ada Service Worker baru" adalah
// PERBEDAAN BYTE pada file service-worker.js YANG TERDAFTAR itu sendiri
// (algoritma update Service Worker: fetch ulang, bandingkan byte, kalau
// beda baru dianggap "installing"). Kalau angka versi diimpor dari file
// lain, mengubah file LAIN itu TIDAK mengubah SATU BYTE PUN di
// service-worker.js -- browser tidak akan pernah menganggap ada update,
// MEKANISME INI JADI TIDAK BERFUNGSI SAMA SEKALI. Karena itu: SETIAP
// deploy yang mengubah APP_SHELL atau css/style.css WAJIB menaikkan angka
// DI SINI (ASSET_VERSION) DAN query "?v=..." di index.html ke angka yang
// SAMA -- dua tempat, disiplin manual, TIDAK BISA disatukan lewat import
// selama proyek ini tidak memakai proses build (lihat README "tidak ada
// proses build").
// v81 -> v82: HOTFIX Migrasi Subdomain -- redirect URL lama root domain
// (rivoirsett.com/app/*) -> mugen.rivoirsett.com (index.html), tombol Ubah
// Slug tenant di Super Admin (superadmin.js). CATATAN: v80 -> v81
// (PR "Fitur Hapus Tenant") sebelumnya HANYA menaikkan angka ini tanpa ikut
// menaikkan query "?v=..." di index.html (kelalaian, diperbaiki sekarang --
// kedua tempat WAJIB sama, lihat komentar panjang di bawah) -- v82 dipakai
// SEKALIGUS untuk menutup celah itu.
// v82 -> v83: Payment Gateway booking customer (Checkout/Choose Payment
// Channel/Menunggu Pembayaran/Payment Failed/Expired, book_public.js) +
// penghapusan metode Cash (book_public.js, booking.js) + kartu "Payment
// Gateway" booking di Super Admin (superadmin.js, payment_gateway_db.py) --
// DAN Payment Gateway Billing SaaS (Midtrans) dipindah dari environment
// variable ke kartu "Billing SaaS -- Payment Gateway (Midtrans)" di Super
// Admin, DB-backed (superadmin.js, billing_gateway_db.py, midtrans_client.py).
// css/style.css juga berubah (kelas baru book-countdown/book-va-*/
// book-qris-placeholder untuk flow Payment Gateway booking).
// v83 -> v84: REVISI kartu "Billing SaaS -- Payment Gateway" di Super Admin
// (superadmin.js) supaya provider-agnostic -- judul dilepas dari
// "(Midtrans)", TIDAK ADA dropdown Provider, form diperluas jadi tujuh
// field generik (environment/api_key/server_key/client_key/merchant_id/
// secret_key/webhook_url, tidak semua wajib diisi). Alur checkout/webhook/
// aktivasi (midtrans_client.py/billing_webhook.py) TIDAK diubah.
// v84 -> v85: BUGFIX Rekap -- tombol Hapus untuk baris "Keterangan Libur"
// di kolom Aksi (rekap.js), sebelumnya selalu dash karena baris ini tidak
// punya "id" (dihapus lewat barber_id+tanggal, bukan id). Notifikasi sukses
// Setting > Bonus Service/Target Bonus Service/Uang Harian/Hak Akses Admin
// (pengaturan.js) sekarang selalu tampil (force:true, sebelumnya bisa
// senyap kalau toast lain baru saja tampil).
// v85 -> v86: FITUR Logo Resmi Rivoir -- seluruh file ikon platform di
// icons/ (favicon.ico, icon-72..512.png, icon-maskable-192/512.png,
// apple-touch-icon.png) diganti dari logo pita infinity lama ke logo "R"
// resmi Rivoir (nama file TIDAK berubah, jadi ASSET_VERSION WAJIB naik
// supaya pengguna yang sudah install PWA ini tidak terus melihat ikon
// lama dari cache). Ini favicon PLATFORM/default (fallback saat tenant
// belum punya favicon_url sendiri, lihat app/js/brand.js) -- BUKAN
// perubahan pada mekanisme favicon per-tenant itu sendiri, yang tetap
// utuh apa adanya.
// v86 -> v87: REVISI UI/UX Premium Web Booking Tenant -- redesign visual
// menyeluruh halaman /book (style.css blok .book-*, book_public.js) supaya
// identitas visualnya selaras dengan aplikasi kasir: hero premium (scrim
// gradient + glass tagline), step tracker bergaya, kartu/tombol premium
// (gradient, hover lift, ripple diperluas ke lebih banyak tombol), empty
// state & error state (tombol Try Again) baru, reveal-on-scroll section
// landing, kalender .ics client-side di layar Appointment Confirmed. TIDAK
// ADA perubahan API/endpoint/logika booking/validasi -- murni tampilan.
// v87 -> v88: BUGFIX Landing Page /book dirender dobel -- app.js SENGAJA
// memanggil MugenRouter.handle() dua kali saat boot (sekali langsung via
// init(), sekali lagi setelah MugenSubscription.refresh() resolve, untuk
// keperluan halaman internal), dan untuk hash #/book (yang punya operasi
// async sendiri) ini membuat PageBookPublic.render() terpanggil dua kali
// tumpang tindih -- seluruh section landing (Hero/About/Opening Hours/Book
// Appointment CTA/dst) tampil dobel, terlihat seperti halaman kembar.
// Ditambahkan guard di router.js (handle()): panggilan handle() kedua
// dengan hash PERSIS SAMA seperti panggilan sebelumnya (tanpa navigasi
// nyata di antaranya) tidak lagi memicu render ulang. TIDAK ADA perubahan
// API/endpoint/logika booking -- murni perbaikan struktur render.
// v88 -> v89: FITUR Kompatibilitas URL Booking (Instagram Bio dkk) -- link
// booking publik SEBELUMNYA hash route "/app/#/book" (Instagram Bio dkk
// otomatis meng-encode "#" jadi "%23" begitu ditempel, link jadi gagal
// terbuka). router.js/tenant_guard.js sekarang JUGA mendeteksi PATH ASLI
// "/book" & "/app/book" (bukan cuma hash "#/book") lewat location.pathname,
// dipasangkan dengan rewrite rule server baru (lihat render.yaml) supaya
// refresh halaman juga tetap berfungsi di path itu. Backend: tenant_db.py::
// get_booking_url() sekarang menghasilkan "https://<booking_slug>.
// rivoirsett.com/book" (bukan lagi "/app/#/book") untuk link BARU yang
// ditampilkan Setting > Booking/Super Admin -- hash "/app/#/book" LAMA
// tetap didukung penuh (kompatibilitas mundur), TIDAK ADA perubahan API/
// endpoint/logika booking, murni cara URL-nya diakses.
// v89 -> v90: PERBAIKAN PERFORMA (halaman /book lambat saat pertama kali
// dibuka) -- diprofilkan (Playwright + CDP network throttling ~4Mbps/50ms
// RTT, meniru kondisi mobile): waktu sampai Hero booking terlihat 2942ms,
// bottleneck TERBESAR adalah pdfjs_boot.js yang men-`import` STATIS
// vendor/pdfjs/pdf.min.js (512KB) di SETIAP halaman termasuk /book -- file
// besar ini sendirian memonopoli bandwidth ~2000ms dan menunda SEMUA
// request lain (termasuk panggilan API booking). pdfjs_boot.js sekarang
// HANYA mengunduhnya lewat `import()` DINAMIS begitu fitur Preview PDF
// sungguhan dipakai (pdf_preview.js::ensurePdfJs() memicunya) -- fitur
// Preview PDF sendiri TIDAK berubah perilakunya sama sekali (diverifikasi
// end-to-end: klik Cetak PDF, canvas preview tetap render dengan benar).
// Hasil setelah perbaikan: waktu sampai Hero terlihat turun ke ~1930ms
// (turun ~35%, ~1000ms lebih cepat), diukur konsisten di 3x pengulangan.
// Sempat dicoba juga menambah "defer" ke ~35 <script> lain di index.html,
// TAPI diukur TIDAK memberi perbaikan tambahan (browser modern sudah
// mengunduh script paralel walau tanpa "defer") -- TIDAK jadi dipakai,
// lihat komentar di index.html. TIDAK ADA perubahan UI/alur booking/
// database/fitur lain -- murni KAPAN pdf.min.js diunduh.
// v90 -> v91: FITUR Landing Page & Pricing -- Setting > Billing (billing.js)
// dapat toggle siklus Bulanan/6 Bulan (badge "Paling Hemat", hitung hemat
// dibanding bulanan) + benefit "Custom Feature Request" khusus paket
// Enterprise, siklus terpilih dikirim ke POST /api/billing/checkout.
// TIDAK ADA perubahan pada Dashboard/Booking/POS/modul internal lain --
// HANYA billing.js yang berubah.
// v91 -> v92: Revisi Landing Page & Restrukturisasi Super Admin --
// pages/superadmin.js dipecah jadi 5 tab (Dashboard/Tenant/Paket/Landing
// Page/Payment Gateway, lihat MugenUI.tabs()), fitur Testimonial dihapus
// total dari kartu Landing Page, kartu Kontak disederhanakan (Email &
// WhatsApp saja) + kartu Footer (tagline) baru. TIDAK ADA perubahan pada
// Dashboard/Booking/POS/modul internal lain -- HANYA superadmin.js yang
// berubah.
// v92 -> v93: Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant
// -- proyek berhenti mengasumsikan Midtrans sebagai provider tetap (satu
// provider generik, dua modul TERPISAH: billing_gateway_client.py untuk
// langganan SaaS, payment_gateway_client.py BARU untuk booking customer).
// Payment Gateway booking SEKARANG SUNGGUHAN (bukan simulasi) -- book_public.js
// dirombak total: fase channel/VA palsu/tombol "Cek Status Pembayaran" yang
// menandai lunas sendiri DIHAPUS, diganti checkout hosted provider sungguhan
// + polling read-only status pembayaran (booking_gateway_webhook.py, HANYA
// webhook resmi provider yang boleh mengubah status). booking.js (badge
// status 7-state + tombol Detail untuk booking gateway), riwayat_transaksi.js
// BARU (menu Keuangan > Riwayat Transaksi tenant), superadmin.js dapat tab
// baru "Riwayat Transaksi" (monitoring lintas-tenant + filter/cari/ringkasan/
// detail/export CSV) + hint URL webhook aktif, label "Midtrans" di
// billing.js/superadmin.js/landing.js/index.html/manifest.json digenerikkan.
// v93 -> v94: Perbaikan pasca-audit kesiapan Payment Gateway (booking &
// langganan SaaS) -- webhook TIDAK LAGI bisa "diturunkan" statusnya oleh
// notifikasi basi/keluar urutan (guard STATUS_FINAL di booking_gateway_db.py/
// billing_webhook.py, celah yang sebelumnya bisa membatalkan booking yang
// SUDAH DIBAYAR). Endpoint baru "Cek Ulang ke Provider" (jalur rekonsiliasi
// manual untuk transaksi/invoice yang macet karena webhook tidak pernah
// sampai) -- tombolnya ditambahkan di riwayat_transaksi.js, booking.js
// (Detail modal), dan billing.js (Riwayat Pembayaran). book_public.js:
// popup checkout yang diblokir browser sekarang terdeteksi & diberi tahu
// (toast), bukan diam-diam gagal tanpa keterangan.
// v96 -> v97: toast SUKSES/INFO diaktifkan kembali untuk SEMUA tombol
// Simpan/Edit/Hapus/Input (sebelumnya cuma aksi besar seperti pembayaran/
// booking) -- ui.js::toast() tidak lagi menyaring type non-error secara
// default, ditambah penataan tumpukan (stacking) supaya beberapa toast
// yang tampil hampir bersamaan tidak saling menimpa.
// v97 -> v98: Modul BARU Absensi (GPS Check In/Out Geofencing) -- halaman
// baru js/pages/absensi.js (menu sidebar "Absensi", nav.js/router.js),
// tab baru "Absensi" di Setting (pengaturan.js) untuk Pengaturan Absensi
// (Jam Masuk/Pulang, Toleransi, Radius, Lokasi Toko). Modul berdiri
// sendiri, TIDAK mengubah halaman lain yang sudah ada.
// v98 -> v99: FITUR Notifikasi WhatsApp Otomatis Booking -- tab baru
// "WhatsApp" di Setting (pengaturan.js, KHUSUS Owner) untuk menghubungkan
// token Fonnte milik toko sendiri. Pesan otomatis dikirim dari backend
// (booking_db.py) saat customer pilih QRIS, saat pembayaran diverifikasi
// (manual/gateway), dan saat booking dibatalkan -- TIDAK ada halaman/route
// frontend baru selain tab Setting ini.
// v99 -> v100: FITUR Batas Absensi (feedback Owner) -- Check In sekarang
// ditolak KERAS kalau sebelum jam_masuk (celah lama: bisa Check In
// sebelum toko buka). Check Out sebelum jam_pulang SEKARANG DIIZINKAN
// (sebelumnya ditolak keras) tapi memotong limit "Pulang Lebih Awal"
// bulanan -- SAMA seperti limit "Keterlambatan" bulanan untuk Check In
// terlambat (120 menit/bulan masing-masing, reset otomatis tiap tanggal
// 1, TIDAK PERNAH memblokir absensi walau limit habis -- cuma dicatat di
// Keterangan). Panel baru "Sisa Limit Bulan Ini" (ikon peringatan + teks
// merah kalau sisa <=40 menit) & kolom "Keterangan" ditambahkan ke
// absensi.js (Barber & Owner/Admin). FITUR BARU: Koreksi Absensi -- Barber
// lupa Check In/Check Out bisa mengajukan koreksi (jam yang seharusnya +
// alasan), diproses (Setujui/Tolak) Owner/Admin di menu Absensi (izin
// baru izin_absensi_koreksi untuk staff, ditambahkan ke tab Hak Akses
// Admin di pengaturan.js).
// v100 -> v101: REVISI Batas Absensi (feedback Owner lanjutan) -- besar
// limit Keterlambatan & Pulang Lebih Awal (sebelumnya konstanta tetap 120
// menit/bulan) SEKARANG BISA DIATUR Owner/Admin lewat Setting > Absensi
// (attendance_settings.batas_menit_terlambat/batas_menit_pulang_awal,
// dua field baru terpisah). Kolom Keterangan di Daftar Absensi Owner &
// Riwayat Absensi Saya Barber sekarang benar-benar menandai ikon
// peringatan + teks merah begitu SATU kejadian (terlambat/pulang lebih
// awal) terjadi SAAT limit bulan itu sudah habis (sebelumnya baris
// "keterangan_per_tanggal" versi kaya ini cuma dihitung di endpoint
// ringkasan-bulan, TIDAK PERNAH sampai ke kolom Keterangan tabel utama --
// celah yang diperbaiki di attendance_db.py::get_log_list()/_lengkapi()).
// v101 -> v102: REVISI UI Absensi (feedback Owner) -- form "Pengaturan
// Absensi" (Jam Masuk/Pulang, Toleransi, Radius, Limit Keterlambatan/
// Pulang Lebih Awal, Lokasi Toko) DIPINDAHKAN dari tab Setting > Absensi
// ke menu utama Absensi sendiri (kartu baru di atas Dashboard, lihat
// pages/absensi.js::renderPengaturanAbsensi()) -- satu tempat, tidak lagi
// terpisah dari panel Sisa Limit/Koreksi/Daftar Absensi. Tab "Absensi" di
// Setting (pages/pengaturan.js) DIHAPUS total. Gate izin_absensi_pengaturan
// TIDAK berubah (staff tetap perlu izin ini, sekarang melindungi kartu di
// halaman Absensi, bukan tab Setting). TIDAK ADA perubahan endpoint/logika
// backend.
// v102 -> v103: FITUR Hapus Log Audit (feedback Owner) -- tombol "Hapus
// Semua Log Audit" baru di kartu "Log Audit Percobaan Check In/Out" (menu
// Absensi), hard delete PERMANEN sampai ke database (DELETE
// /api/attendance/audit, backend require_admin -- KHUSUS Owner, TIDAK bisa
// didelegasikan ke staff karena log ini sendiri bukti investigasi Fake
// GPS). Tombol hanya tampil untuk Owner.
// v103 -> v104: FITUR Reset Riwayat Absensi Karyawan (feedback Owner) --
// kartu baru "Reset Riwayat Absensi Karyawan" di menu Absensi (bawah kartu
// Log Audit), hard delete PERMANEN attendance_logs (DELETE
// /api/attendance/riwayat, backend require_owner_or_staff -- Owner ATAU
// Admin/staff SAMA-SAMA boleh, TANPA delegasi permission terpisah, BEDA
// dari Hapus Log Audit yang KHUSUS Owner) untuk mengantisipasi data yang
// menumpuk. Bisa pilih satu barber atau "Semua Barber".
// v104 -> v105: REVISI UI/UX Absensi Barber (feedback Owner) -- dasbord
// Absensi barber dibuat lebih menarik: "Sisa Limit Bulan Ini" jadi diagram
// lingkaran (progress ring) animasi, "Status Absensi Hari Ini" jadi ilustrasi
// SVG per status + animasi pulse khusus "Sedang Bekerja", baris "Riwayat
// Absensi Saya" fade-in bertahap saat dimuat, dan baris "Keterangan" limit
// habis animasi shake sekali saat muncul (ui.js, css/style.css). Tombol
// Check In/Check Out & Ajukan Koreksi sekarang WAJIB konfirmasi lewat modal
// (MugenUI.confirmModal) sebelum jalan, dan semua pesan error (termasuk izin
// lokasi ditolak) sekarang tampil sebagai modal (MugenUI.infoModal), BUKAN
// teks merah inline lagi (pages/absensi.js). TIDAK ada perubahan backend.
// v105 -> v106: PERBAIKAN PERFORMA (loading awal lambat) -- 20 modul
// js/pages/*.js yang besar (dashboard_owner.js, dashboard_barber.js,
// input_data.js, rekap.js, pengeluaran.js, pemasukan.js, uang_kas.js,
// riwayat_transaksi.js, slip_gaji.js, kasbon.js, komisi.js, reimburse.js,
// izin_cuti.js, absensi.js, pengaturan.js, billing.js, produk.js,
// booking.js, book_public.js, superadmin.js -- total ratusan KB) TIDAK lagi
// dimuat lewat <script> biasa di index.html di awal aplikasi dibuka,
// SEKARANG dimuat DINAMIS oleh modul baru js/page_loader.js HANYA saat
// menunya benar-benar dibuka (router.js, index.html). File-file itu TETAP
// terdaftar di APP_SHELL di bawah (precache saat instalasi TIDAK berubah,
// jadi tetap berfungsi offline persis seperti sebelumnya begitu Service
// Worker pernah selesai terpasang sekali) -- yang berubah HANYA kapan
// browser memintanya (lazy, bukan di awal), bukan APAKAH di-cache.
// v106 -> v107: FITUR Uang Harian Dinamis Berdasarkan Absensi (opt-in per
// Tenant, default MATI -- Uang Harian tetap sistem lama tanpa perubahan
// sampai Tenant sengaja mengaktifkan) -- Tenant sekarang bisa memilih
// toleransi harian dan/atau limit bulanan (keterlambatan & pulang lebih
// awal diatur TERPISAH) sebagai dasar potongan Uang Harian, digabung
// dengan Service Rule opsional. Field baru "Toleransi Pulang Lebih Awal"
// di kartu Pengaturan Absensi (pages/absensi.js, KHUSUS dipakai fitur ini,
// TIDAK mengubah logika Absensi itu sendiri) + kartu baru "Uang Harian
// Dinamis Berdasarkan Absensi" di Setting > Uang Harian
// (pages/pengaturan.js) + kartu "Rincian Uang Harian" (breakdown
// transparan per tanggal) di halaman Absensi Barber saat fitur ini aktif
// (pages/absensi.js). TIDAK ADA perubahan pada modul Absensi (attendance)
// itu sendiri.
// v107 -> v108: PERBAIKAN Uang Harian Dinamis (feedback Owner) -- tanggal
// yang TIDAK punya data Absensi sama sekali (termasuk SELURUH riwayat dari
// sebelum fitur Absensi ada) sebelumnya bisa salah dihitung (Rp0 di
// agregat bulanan, TIDAK KONSISTEN dengan breakdown per-hari yang tampak
// 100% cair) begitu Tenant mengaktifkan fitur ini -- sekarang tanggal
// tanpa data Absensi otomatis fallback ke sistem LAMA (jumlah service vs
// target) untuk tanggal itu SAJA, konsisten di breakdown maupun agregat
// (pages/absensi.js: kartu Rincian menampilkan catatan penjelasan saat ini
// terjadi).
// v108 -> v109: FITUR Toleransi Absen Lebih Awal (feedback Owner) --
// sebelumnya Check In SELALU ditolak keras sebelum Jam Masuk PERSIS (tidak
// ada cara Barber Check In lebih awal walau cuma untuk bersiap-siap
// sebelum toko buka). Kartu Pengaturan Absensi (pages/absensi.js) sekarang
// punya field baru "Toleransi Absen Lebih Awal (menit)" -- opsional per
// tenant, default 0 (perilaku lama, tanpa perubahan). TIDAK ADA perubahan
// pada definisi Jam Masuk/status tepat waktu itu sendiri.
// v109 -> v110: FITUR Notifikasi Push (Web Push/VAPID, termasuk iPhone
// lewat PWA "Add to Home Screen" sejak iOS 16.4) -- js/push_notif.js baru
// (subscribe/unsubscribe, kartu UI dipakai pages/pengaturan.js tab Profil
// utk admin/staff DAN pages/izin_cuti.js renderBarberView utk barber),
// event listener push/notificationclick baru di bawah. Opt-in penuh:
// TIDAK ditampilkan sama sekali kalau Owner belum mengisi VAPID_* di
// hosting (GET /api/push/vapid-public-key enabled=false), TIDAK PERNAH
// auto-prompt izin notifikasi. Dipicu backend saat Booking Baru (ke
// admin/staff) dan Pengajuan Izin/Cuti baru (ke admin/staff) + status
// disetujui/ditolak (ke barber ybs) -- semua "best effort", gagal kirim
// TIDAK PERNAH menggagalkan operasi bisnis yang memicunya. Notifikasi
// SELALU getar (opsi `vibrate`, terpisah dari nada dering -- tetap terasa
// walau perangkat di-silent, KHUSUS Android/Chrome, iOS Safari mengabaikan
// opsi ini dan selalu ikut pengaturan getar SISTEM).
// v110 -> v111: FITUR Kebijakan Cuti Dinamis (feedback Owner) -- kartu
// baru "Pengaturan Izin & Cuti" (pages/pengaturan.js tab Karyawan): Kuota
// Cuti per periode (boleh dipecah beberapa kali), Minimal H- pengajuan,
// Maksimal karyawan Cuti bersamaan. Opsional per tenant, default 0/off
// penuh (perilaku lama, tanpa batasan apa pun). HANYA berlaku jenis Cuti
// (Izin tidak tersentuh). Validasi dilakukan di BACKEND (izin_cuti_db.py),
// bukan hanya frontend. Owner/Admin/Staff tetap bebas membuat pengajuan
// atas nama karyawan kapan pun (melewati kebijakan ini).
// v111 -> v112: FITUR Izin Lokasi & Notifikasi Push otomatis KHUSUS APK
// Android (android-app/, Capacitor) -- js/native_app.js baru, dipanggil
// pages/login.js begitu login berhasil DAN Capacitor.isNativePlatform()
// true (di browser biasa tidak melakukan apa-apa sama sekali, tetap murni
// opt-in lewat push_notif.js seperti sebelumnya). Kolom baru
// users.lokasi_lat/lokasi_lng/lokasi_updated_at di backend (lihat
// lokasi_user_migrasi.py) + endpoint PUT /api/auth/lokasi.
// v112 -> v113: FITUR Tampilan Operasional Harian Booking khusus Barber
// (pages/booking.js) -- 3 tab baru: "Hari Ini" (kartu, HANYA hari ini,
// diurut jam, booking lewat diredupkan + badge "Selesai", booking
// berikutnya ditonjolkan badge "Berikutnya"), "Akan Datang" (kartu
// dikelompokkan per tanggal, tanpa batas atas), "Semua Booking" (TABEL
// LAMA, TIDAK diubah). Backend: GET /api/booking/mine sekarang menerima
// `tanggal`/`dari_tanggal` opsional (default None = perilaku lama sama
// sekali tidak berubah).
// v113 -> v114: FITUR Reset Riwayat Booking (mengantisipasi data menumpuk,
// pola SAMA seperti Reset Riwayat Absensi) -- kartu baru di Booking >
// Booking Settings, tombol "Hapus Riwayat Booking" (Owner ATAU Admin/
// staff) dengan filter tanggal opsional. Backend: DELETE
// /api/booking/riwayat (cascade booking_items + transaksi/log Payment
// Gateway terkait, aman dari FK orphan).
// v114 -> v115: BUGFIX tab "Hari Ini"/"Akan Datang" (pages/booking.js) --
// booking dari tanggal LAIN ikut tercampur kalau backend yang dipanggil
// kebetulan versi lama (mengabaikan parameter tanggal/dari_tanggal yang
// belum dikenalnya). Filter tanggal sekarang DIULANG di frontend sebagai
// pertahanan lapis kedua -- backend TETAP satu-satunya yang seharusnya
// memfilter, ini murni jaring pengaman kalau deploy backend/frontend
// sempat tidak sinkron.
// v115 -> v116: FITUR DIY error monitoring (bukan Sentry) -- modul baru
// js/error_report.js (listener global window.onerror/unhandledrejection,
// POST /api/log-error) ditambahkan ke APP_SHELL. Owner melihat hasilnya
// lewat Setting > Log Error (pages/pengaturan.js, sudah dimuat dinamis,
// tidak perlu masuk APP_SHELL_BER_VERSI terpisah).
const ASSET_VERSION = "120";
const CACHE_NAME = "mugen-hair-shell-v" + ASSET_VERSION;

// Path navigasi ("/", "/index.html") SENGAJA TIDAK diberi query ?v= --
// permintaan navigasi browser yang SEBENARNYA (buka/reload halaman) selalu
// ke URL polos tanpa query itu, jadi kunci cache-nya harus cocok persis
// supaya fallback offline (lihat event "fetch" di bawah) bisa menemukannya.
// Aset lain (JS/CSS/PDF.js) dapat query ?v= yang SAMA persis dengan yang
// dipakai index.html, supaya kunci cache Service Worker cocok dengan URL
// yang benar-benar diminta halaman.
// vendor/pdfjs/*: TIDAK diberi query ?v= -- pdfjs_boot.js meng-import
// keduanya lewat path absolut TANPA query (import statement statis + nilai
// literal workerSrc, lihat file itu, sengaja "TIDAK dimodifikasi" karena
// build resmi pdfjs-dist apa adanya) -- kalau kedua entri ini dikasih query
// di sini tapi TIDAK di pdfjs_boot.js, kuncinya tidak akan pernah cocok
// dengan permintaan sungguhan (selalu network, bukan cache -- tidak fatal,
// tapi menghilangkan manfaat offline-nya).
// FONDASI Multi-Tenant Phase 5 (Landing Page SaaS): file ini (dan seluruh
// APP_SHELL di bawah) sekarang HIDUP di /app/ (Landing Page publik BARU
// dipasang terpisah di root "/", lihat frontend/index.html + frontend/
// service-worker.js) -- Service Worker ini didaftarkan dari app.js dengan
// path relatif "service-worker.js" (TIDAK diubah), yang otomatis memberi
// scope default "/app/" (scope = folder tempat file SW berada) TANPA perlu
// opsi `scope` eksplisit. SELURUH path di bawah karena itu diberi awalan
// "/app/" -- KECUALI /icons/* (tetap satu folder bersama di root, dipakai
// Landing Page maupun App yang sama).
const _APP_SHELL_TANPA_VERSI = [
  "/app/", "/app/index.html", "/app/manifest.json",
  "/app/vendor/pdfjs/pdf.min.js", "/app/vendor/pdfjs/pdf.worker.min.js",
];
const _APP_SHELL_BER_VERSI = [
  "/app/config.js",
  "/app/css/style.css",
  "/app/js/pdfjs_boot.js",
  "/app/js/state.js",
  "/app/js/theme.js",
  "/app/js/api.js",
  "/app/js/error_report.js",
  "/app/js/ui.js",
  "/app/js/pdf_preview.js",
  "/app/js/brand.js",
  "/app/js/subscription.js",
  "/app/js/pwa_update.js",
  "/app/js/nav.js",
  "/app/js/booking_notif.js",
  "/app/js/izin_notif.js",
  "/app/js/push_notif.js",
  "/app/js/native_app.js",
  "/app/js/page_loader.js",
  "/app/js/router.js",
  "/app/js/app.js",
  "/app/js/pages/login.js",
  "/app/js/pages/register.js",
  "/app/js/pages/lupa_password.js",
  "/app/js/pages/reset_password.js",
  "/app/js/pages/verify_email.js",
  "/app/js/pages/dashboard_owner.js",
  "/app/js/pages/dashboard_barber.js",
  "/app/js/pages/input_data.js",
  "/app/js/pages/rekap.js",
  "/app/js/pages/pengeluaran.js",
  "/app/js/pages/pemasukan.js",
  "/app/js/pages/uang_kas.js",
  "/app/js/pages/slip_gaji.js",
  "/app/js/pages/kasbon.js",
  "/app/js/pages/komisi.js",
  "/app/js/pages/reimburse.js",
  "/app/js/pages/izin_cuti.js",
  "/app/js/pages/absensi.js",
  "/app/js/pages/pengaturan.js",
  "/app/js/pages/billing.js",
  "/app/js/pages/produk.js",
  "/app/js/pages/booking.js",
  "/app/js/pages/book_public.js",
  "/app/js/pages/riwayat_transaksi.js",
  "/app/js/pages/superadmin.js",
  "/app/js/pages/subscription_blocked.js",
  "/app/js/pages/tenant_not_found.js",
  "/app/js/tenant_guard.js",
];
const APP_SHELL = [
  ..._APP_SHELL_TANPA_VERSI,
  ..._APP_SHELL_BER_VERSI.map((p) => `${p}?v=${ASSET_VERSION}`),
  // TAHAP 13: ikon PWA -- TIDAK diberi query ?v= (jarang berubah, dan
  // manifest.json/index.html <link> merujuknya TANPA query juga).
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
    caches.open(CACHE_NAME).then((cache) =>
      Promise.all(
        APP_SHELL.map((url) =>
          // {cache:"reload"} MEMAKSA fetch ini bypass HTTP cache browser
          // sepenuhnya (selalu network sungguhan) -- lihat catatan #2 di
          // changelog v56->v57 atas kenapa cache.addAll() polos tidak cukup.
          fetch(url, { cache: "reload" }).then((response) => {
            if (!response.ok) throw new Error(`Precache gagal untuk ${url}: HTTP ${response.status}`);
            return cache.put(url, response);
          })
        )
      )
    )
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

  // Navigasi (buka halaman/reload) -- NETWORK-FIRST, fallback ke cache
  // index.html HANYA saat offline/network gagal. Lihat catatan #3 di
  // changelog v56->v57 atas kenapa ini WAJIB diubah dari cache-first.
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(() => caches.match("/app/index.html"))
    );
    return;
  }

  // Aset lain (JS/CSS/PDF.js/ikon, termasuk yang membawa query ?v=...) --
  // cache-first seperti sebelumnya, aman karena URL-nya sendiri sudah unik
  // per versi (lihat APP_SHELL di atas) dan CACHE_NAME baru otomatis
  // membuat bucket cache baru saat Service Worker versi baru aktif.
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});

// FITUR Notifikasi Push (Web Push/VAPID, termasuk iPhone lewat PWA "Add to
// Home Screen" sejak iOS 16.4): payload dikirim backend (push_service.py)
// sebagai JSON {title, body, url} -- lihat push_notif.js utk alur
// subscribe. Event ini HANYA menampilkan notifikasi sistem, TIDAK PERNAH
// menyentuh cache/APP_SHELL di atas.
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = {};
  }
  const title = data.title || "Rivoir";
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data.body || "",
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      // Getar tetap terasa walau nada dering notifikasi perangkat
      // dimatikan/silent (opsi `vibrate` DIPISAH total dari volume/nada
      // dering sistem) -- pola pendek-jeda-panjang supaya terasa beda
      // dari getar notifikasi app lain. HANYA berlaku Android/Chrome;
      // iOS Safari mengabaikan opsi ini sepenuhnya dan selalu ikut
      // pengaturan getar/silent SISTEM (di luar kendali Web Push API,
      // tidak ada workaround dari sisi web).
      vibrate: [200, 100, 200],
      data: { url: data.url || "/app/" },
    })
  );
});

// Klik notifikasi -- fokuskan tab PWA yang sudah terbuka kalau ada
// (hindari membuka tab baru berulang tiap kali notifikasi diklik), else
// buka tab baru ke url dari payload push di atas.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/app/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ("focus" in client) {
          client.navigate(url);
          return client.focus();
        }
      }
      return self.clients.openWindow(url);
    })
  );
});
