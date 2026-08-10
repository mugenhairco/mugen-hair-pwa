// pdfjs_boot.js — TYPE MODULE (lihat index.html) supaya bisa `import` build
// PDF.js langsung dari file lokal (vendor/pdfjs/, BUKAN dari CDN -- PWA ini
// harus tetap bisa dipakai offline/di jaringan lambat, lihat prinsip yang
// sama di ui.js barChart()). File .mjs sengaja disimpan APA ADANYA dari
// paket resmi pdfjs-dist (legacy build, kompatibilitas browser lebih luas)
// -- TIDAK dimodifikasi.
//
// PERBAIKAN PERFORMA (halaman /book lambat saat pertama kali dibuka):
// SEBELUMNYA baris ini melakukan `import` STATIS ke pdf.min.js (512KB) di
// SETIAP halaman -- termasuk /book yang TIDAK PERNAH memakai fitur PDF sama
// sekali. Diprofilkan (Playwright + CDP network throttling ~4Mbps/50ms RTT,
// meniru kondisi mobile): pdf.min.js SENDIRIAN memonopoli bandwidth selama
// ~2000ms dan menunda SEMUA request lain (termasuk panggilan API booking)
// sampai selesai -- inilah bottleneck TERBESAR di halaman /book. pdf.min.js
// (dan pdf.worker.min.js, 1.3MB, sudah lazy dari awal lewat workerSrc di
// bawah) sekarang HANYA diunduh lewat `import()` DINAMIS begitu fitur
// Preview PDF sungguhan dipakai (dipanggil dari pdf_preview.js::
// ensurePdfJs(), HANYA dipanggil dari tombol "Cetak PDF"/"Download PDF" di
// halaman INTERNAL admin) -- TIDAK ADA perubahan pada kapan/bagaimana fitur
// Preview PDF itu sendiri bekerja, murni KAPAN byte-nya diunduh.
let _pdfjsLoading = null;
function muatPdfJs() {
  if (window.pdfjsLib) return Promise.resolve();
  if (_pdfjsLoading) return _pdfjsLoading;
  _pdfjsLoading = import("/app/vendor/pdfjs/pdf.min.js").then((pdfjsLib) => {
    pdfjsLib.GlobalWorkerOptions.workerSrc = "/app/vendor/pdfjs/pdf.worker.min.js";
    window.pdfjsLib = pdfjsLib;
    window.dispatchEvent(new Event("pdfjs-ready"));
  });
  return _pdfjsLoading;
}
// Dipanggil dari pdf_preview.js (skrip biasa non-module, tidak bisa
// `import` file ini langsung) -- lihat ensurePdfJs() di sana.
window.MugenMuatPdfJs = muatPdfJs;
