// service-worker.js (Landing Page publik, root "/") — FONDASI Multi-Tenant
// Phase 5: precache RINGAN untuk shell Landing Page saja (bukan aplikasi
// internal, itu SW terpisah di /app/service-worker.js dengan scope /app/,
// TIDAK disatukan/diubah di sini sama sekali). Scope file ini default "/"
// (folder tempat file ini didaftarkan) -- TAPI /app/ punya SW sendiri
// dengan scope "/app/" yang lebih spesifik, jadi SW ini TIDAK PERNAH
// benar-benar menangani request di bawah /app/ begitu SW itu aktif
// (spesifikasi Service Worker: scope paling spesifik yang menang).

const ASSET_VERSION = "1";
const CACHE_NAME = "rivoir-landing-shell-v" + ASSET_VERSION;

const APP_SHELL = [
  "/", "/index.html", "/manifest.json",
  "/config.js",
  `/css/landing.css?v=${ASSET_VERSION}`,
  `/js/landing.js?v=${ASSET_VERSION}`,
  "/icons/favicon.ico",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/apple-touch-icon.png",
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
