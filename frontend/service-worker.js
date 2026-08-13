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
const ASSET_VERSION = "16";
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
