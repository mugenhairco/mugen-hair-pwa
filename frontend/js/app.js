// app.js — entry point JS frontend.
// TAHAP 3-7: mendaftarkan service worker lalu menjalankan router (login,
// dashboard, input data, rekap). Produk/Pengeluaran/Setting menyusul.

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js").catch((err) => {
      console.error("Gagal mendaftarkan service worker:", err);
    });
  });
}

window.addEventListener("DOMContentLoaded", () => {
  MugenRouter.init();
});
