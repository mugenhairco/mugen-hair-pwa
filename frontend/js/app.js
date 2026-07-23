// app.js — entry point JS frontend.
// TAHAP 1 (skeleton): baru mendaftarkan service worker. Logika Login, Dashboard,
// Input Data, dst akan ditambahkan bertahap di file terpisah per modul supaya
// mudah dibandingkan satu-per-satu dengan aplikasi Desktop.

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js").catch((err) => {
      console.error("Gagal mendaftarkan service worker:", err);
    });
  });
}
