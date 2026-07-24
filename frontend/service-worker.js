// service-worker.js
// TAHAP 1 (skeleton): cache app-shell dasar saja, supaya PWA bisa di-install
// dan sudah tervalidasi sebagai service worker. Strategi caching untuk data
// (API calls) akan disempurnakan di tahap-tahap berikutnya sesuai kebutuhan
// tiap modul (Dashboard, Input Data, dst) — SENGAJA belum agresif men-cache
// data supaya tidak menampilkan data basi/salah ke user (data transaksi &
// stok harus selalu akurat, bukan dari cache lama).

const CACHE_NAME = "mugen-hair-shell-v5";
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
