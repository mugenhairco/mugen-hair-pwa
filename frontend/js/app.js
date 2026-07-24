// app.js — entry point JS frontend.
// TAHAP 3-9: mendaftarkan service worker lalu menjalankan router (login,
// dashboard, input data, rekap, pengeluaran).
// TAHAP 10: refresh identitas barbershop (nama/logo) sekali di awal supaya
// tab/judul browser & sidebar terisi data terbaru dari Setting.

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js").catch((err) => {
      console.error("Gagal mendaftarkan service worker:", err);
    });
  });
}

window.addEventListener("DOMContentLoaded", () => {
  MugenBrand.refresh();
  MugenRouter.init();
});
