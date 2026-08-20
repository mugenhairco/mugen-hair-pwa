// service-worker.js (Landing Page publik, root "/") — FONDASI Multi-Tenant
// Phase 5: precache RINGAN untuk shell Landing Page saja (bukan aplikasi
// internal, itu SW terpisah di /app/service-worker.js dengan scope /app/,
// TIDAK disatukan/diubah di sini sama sekali). Scope file ini default "/"
// (folder tempat file ini didaftarkan) -- TAPI /app/ punya SW sendiri
// dengan scope "/app/" yang lebih spesifik, jadi SW ini TIDAK PERNAH
// benar-benar menangani request di bawah /app/ begitu SW itu aktif
// (spesifikasi Service Worker: scope paling spesifik yang menang).

// v8 -> v9: FITUR Landing Page & Pricing -- hero/copywriting baru (pembeda
// "setiap barber punya aplikasi sendiri"), section Differentiator baru
// (Owner Dashboard + Barber App, menggantikan section Statistik yang
// dihapus total), Free Trial 30 Hari sebagai CTA utama, toggle siklus
// Bulanan/6 Bulan + badge hemat di Pricing, benefit Enterprise Exclusive
// (Custom Feature Request) -- landing.css & landing.js berubah.
// v9 -> v10: BUGFIX scroll -- Landing Page kadang mendarat di tengah
// halaman (bukan di atas) saat dimasuki lewat navigasi Back/Forward
// browser (history.scrollRestoration dipaksa "manual" di landing.js).
// v10 -> v11: Revisi Landing Page -- section "Bandingkan Paket" (tabel
// perbandingan) & "Testimoni" dihapus total (info fitur paket cukup di
// kartu Pricing), section "Hubungi Kami" sekarang dinamis (link
// mailto:/wa.me dari Email & WhatsApp yang diatur Super Admin, field
// kosong disembunyikan), footer tagline dinamis, kartu Pricing dipoles
// (hover scale + glow, badge "Paling Populer").
// v11 -> v12: Section Fitur & Pricing diganti dari grid statis jadi slider
// "center focus + peek" (satu item besar di tengah, tetangga kiri/kanan
// mengintip mengecil/pudar, geser via drag/swipe/tombol panah/keyboard) --
// komponen baru js/lp-slider.js, ditambahkan ke precache di bawah.
// v12 -> v13: Kartu yang sedang di tengah slider (Fitur & Pricing) kini
// bisa diklik LAGI ("dipilih") untuk membuka modal detail -- deskripsi
// lebih lengkap + poin manfaat untuk Fitur, rincian paket + tombol Select
// Package untuk Pricing.
// v13 -> v14: BUGFIX KRITIS -- lp-slider.js::goTo() sebelumnya memakai
// scrollIntoView(), yang menelusuri SEMUA ancestor yang bisa discroll
// termasuk document/window itu sendiri -- karena slider berada di bawah
// lipatan (section Fitur/Pricing), posisi awal slider (dipanggil saat
// init(), sebelum pengunjung berinteraksi apa pun) ikut men-scroll
// SELURUH HALAMAN ke bawah, gejalanya "pengunjung mendarat di tengah
// halaman". Diganti scroll horizontal murni lewat track.scrollTo(),
// tidak pernah menyentuh scroll vertikal document/window sama sekali.
// v14 -> v15: kartu fitur baru "WhatsApp Notification" ditambahkan ke
// slider Fitur (landing.js) -- pesan WhatsApp otomatis ke pelanggan dari
// nomor toko sendiri (fitur backend sudah ada, ini murni menampilkannya
// di Landing Page).
// v15 -> v16: kartu "Notifikasi WhatsApp" BERDIRI SENDIRI ditambahkan ke
// section "Yang Membedakan Kami" (index.html), bersebelahan dengan kartu
// Aplikasi Barber -- preview bubble chat WhatsApp mini (landing.css:
// .lp-wa-preview/.lp-wa-bubble, grid-template-columns showcase jadi 4
// kolom untuk menampung kartu ketiga ini).
// v16 -> v17: REVISI tata letak v16 -- kartu Notifikasi WhatsApp DIPINDAH
// keluar dari .lp-diff-showcase (dikembalikan ke 3 kolom semula) ke grid
// baris kedua BARU (.lp-diff-extra-grid, 2 kolom) supaya tidak berdesakan
// dengan pasangan utama Dashboard Owner<->Aplikasi Barber. Kartu BARU
// "Absensi Karyawan" (Check In/Out berbasis jarak lewat Aplikasi Barber,
// preview Status Hari Ini + Jarak dari Toko: landing.css .lp-absensi-*)
// ditambahkan bersebelahan dengan Notifikasi WhatsApp di grid baru ini.
// Kartu fitur "Employee Attendance" juga ditambahkan ke slider Fitur
// (landing.js).
// v17 -> v18: kartu Notifikasi WhatsApp & Absensi Karyawan dilengkapi
// ilustrasi HP (.lp-phone-frame, konsisten dengan kartu Aplikasi Barber)
// -- WhatsApp: screenshot chat mini (header hijau WA + bubble percakapan,
// landing.css .lp-wa-phone/.lp-wa-screen/.lp-wa-chat-*), Absensi:
// ilustrasi maps murni CSS (pin + radius geofence putus-putus, landing.css
// .lp-absensi-map/-radius/-pin/-badge) menggantikan preview kartu polos
// sebelumnya.
// v18 -> v19: Smooth Scroll & Scroll-Spy custom -- scroll-behavior:smooth
// bawaan browser (kurva linear, sama rata semua jarak) diganti animasi JS
// (landing.js::smoothScrollTo(), durasi mengikuti jarak, easing SAMA
// PERSIS --ease/cubic-bezier(0.16,1,0.3,1) yang sudah dipakai transisi CSS
// lain) untuk SEMUA link "#id" di halaman (navbar/footer/tombol CTA).
// Offset navbar fixed ikut dihitung supaya section tidak ketutupan
// (sebelumnya tidak ada kompensasi sama sekali). Scroll-spy baru
// (initScrollSpy(), IntersectionObserver) menyalakan link menu navbar
// otomatis sesuai section yang sedang terlihat, dengan underline animasi
// (landing.css .lp-nav-active). Menghormati prefers-reduced-motion (loncat
// instan, tanpa animasi, kalau pengguna mengaktifkannya).
// v19 -> v20: REVISI Smooth Scroll (feedback Owner) -- kurva easing diganti
// easeOutCubic (0.33,1,0.68,1, khusus scroll, sebelumnya --ease/(0.16,1,
// 0.3,1) yang "meledak" di awal lalu nyaris diam mendekati tujuan, terasa
// tersentak berhenti) + durasi dilebarkan (600-1300ms, dari 450-900ms)
// supaya perlambatan mendekati section sungguh terasa. BUGFIX: halaman
// sekarang SELALU mulai dari atas tanpa syarat (sebelumnya dilewati kalau
// URL sudah membawa hash dari klik menu sebelumnya, sehingga refresh/buka
// ulang bisa memicu native anchor-jump instan browser dan "mendarat di
// tengah halaman") -- hash di URL tetap dihormati, tapi lewat animasi
// scroll halus milik sendiri setelah halaman siap, bukan native jump.
// FITUR BARU: animasi pulse (membesar/mengecil, landing.css .lp-pulse) di
// 3 tombol "Mulai Free Trial", badge "★ Paling Populer", dan badge "Hemat
// Lebih Banyak" -- menarik perhatian, dijeda saat hover/focus, dihormati
// prefers-reduced-motion.
// v20 -> v21: REVISI Pulse & Smooth Scroll (feedback Owner) -- animasi
// pulse dipercepat 2x (durasi dibagi dua: tombol 1.1s dari 2.2s, badge
// "Hemat Lebih Banyak" 0.8s dari 1.6s) + shadow "bernapas" ditambahkan ke
// SEMUA target pulse (membesar/mengecil bareng skalanya, varian cyan
// glow khusus tombol di dalam .lp-cta-box karena background gradiennya
// gelap). Pulse (skala jauh lebih halus + shadow) diterapkan juga ke 4
// kartu fitur unggulan di section "Kenapa Rivoir" (Dashboard Owner,
// Aplikasi Barber, Notifikasi WhatsApp, Absensi Karyawan) -- animasi
// ditunda 1 detik supaya tidak berebut transform dengan animasi reveal
// (fade+slide masuk) yang jalan lebih dulu saat kartu pertama terlihat.
// Durasi Smooth Scroll dilipatgandakan 2x lagi (1200-2600ms, dari
// 600-1300ms) karena masih terasa terlalu cepat.
// v21 -> v22: BUGFIX shadow pulse tidak terlihat -- .lp-cta-box punya
// overflow:hidden (dipakai supaya glow dekoratif ::before-nya ikut
// membulat mengikuti sudut kotak) yang TANPA SADAR ikut memotong habis
// shadow pulse tombol "Mulai Free Trial 30 Hari" di dalamnya. Diganti:
// ::before diberi border-radius sendiri (jadi tetap membulat rapi TANPA
// overflow di parent), overflow:hidden di .lp-cta-box dihapus. Bug serupa
// juga ditemukan di badge "★ Paling Populer" -- slider Pricing
// (.lp-slider-track) overflow-x:auto MEMAKSA overflow-y jadi auto juga
// (aturan CSS overflow 2 sumbu), badge yang menonjol -15px ke atas kartu
// jadi kepotong dari atas. Diberi padding-top ekstra KHUSUS di slider
// Pricing (bukan slider Fitur yang tidak punya badge menonjol ini).
// v22 -> v23: REVISI pulse kartu fitur unggulan (feedback Owner) -- pulse
// (skala+shadow) dipindah dari kartu (.lp-diff-card) ke gambar/mockup DI
// DALAMNYA (.lp-diff-mockup Dashboard Owner, .lp-phone-frame Aplikasi
// Barber/WhatsApp/Absensi). FITUR BARU: isi mockup "hidup" -- Dashboard
// Owner: "Booking Hari Ini" berputar 18->50->18, bar Dimas & Yoga tumbuh
// dari kecil ke 3/4 (nominal ikut naik) lalu reset, berulang. Aplikasi
// Barber: tangan 👋 melambai pelan berulang, "Pendapatan Bulan Ini" &
// "Komisi Saya" turun dari maksimum ke minimum lalu reset, berulang.
// Notifikasi WhatsApp: 2 bubble chat diketik satu per satu (efek
// typewriter), lalu reset & ulang. Absensi Karyawan: lingkaran radius
// mengecil terus, begitu kecil pin 📍 jatuh dari atas, "Jarak dari Toko"
// turun 70m->10m mengikuti progress radius yang sama persis, lalu reset
// & ulang. Semua murni dekoratif/data dummy, dimatikan total untuk
// prefers-reduced-motion.
// v23 -> v24: REVISI feedback Owner. Mockup Dashboard di HERO (bukan
// kartu fitur unggulan) sekarang juga "hidup" -- "Booking Hari Ini"
// berputar 18->50->18, grafik batang mingguan tumbuh dari kecil ke
// tinggi aslinya lalu reset, berulang. Kartu Dashboard Owner: bar Dimas
// dibuat KONSISTEN lebih penuh dari Yoga (proporsional dengan nominal
// pendapatan asli, sebelumnya sama-sama mentok 3/4). Kartu Aplikasi
// Barber: arah "Pendapatan Bulan Ini" & "Komisi Saya" DIBALIK -- naik
// dari kecil ke besar (sebelumnya turun besar ke kecil). FITUR BARU:
// efek shine/kilau bergerak kiri->kanan di logo Rivoir (navbar & footer,
// landing.css .lp-brand-logo-shine, di-mask ke bentuk asli logo),
// berulang, dimatikan untuk prefers-reduced-motion.
// v24 -> v25: REVISI feedback Owner. Mockup Dashboard di Hero: "Pendapatan"
// (Rp 4,85jt->20jt) & "Pelanggan Baru" (11->50) sekarang ikut berjalan
// bareng "Booking Hari Ini" -- SEMUA counter di mockup ini pakai satu
// konstanta interval yang sama (STEP_TICK_MS di landing.js) supaya
// kecepatan pergerakan angkanya konsisten. Kartu Dashboard Owner (fitur
// unggulan): "Pendapatan" (20,5jt->50jt, naik per 0,5jt: 20,5 / 21 /
// 21,5 / ...) & "Barber Aktif" (5->15) ditambahkan, jalan di kecepatan
// yang sama juga.
const ASSET_VERSION = "28";
const CACHE_NAME = "rivoir-landing-shell-v" + ASSET_VERSION;

const APP_SHELL = [
  "/", "/index.html", "/manifest.json",
  "/config.js",
  `/css/landing.css?v=${ASSET_VERSION}`,
  `/js/lp-slider.js?v=${ASSET_VERSION}`,
  `/js/landing.js?v=${ASSET_VERSION}`,
  "/icons/favicon.ico",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/apple-touch-icon.png",
  "/icons/logo-rivoir.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      Promise.all(
        APP_SHELL.map((url) =>
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
      Promise.all(keys.filter((k) => k !== CACHE_NAME && k.startsWith("rivoir-landing-shell-v")).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // /app/* dan /api/* TIDAK PERNAH ditangani SW ini -- biarkan lewat
  // langsung (SW /app/ yang menangani /app/*, backend yang menangani /api/*).
  if (url.pathname.startsWith("/app/") || url.pathname.startsWith("/api/")) {
    return;
  }

  if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request).catch(() => caches.match("/index.html")));
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
