// pdfjs_boot.js — TYPE MODULE (lihat index.html) supaya bisa `import` build
// PDF.js langsung dari file lokal (vendor/pdfjs/, BUKAN dari CDN -- PWA ini
// harus tetap bisa dipakai offline/di jaringan lambat, lihat prinsip yang
// sama di ui.js barChart()). File .mjs sengaja disimpan APA ADANYA dari
// paket resmi pdfjs-dist (legacy build, kompatibilitas browser lebih luas)
// -- TIDAK dimodifikasi.
//
// Skrip lain (pdf_preview.js) memakainya lewat window.pdfjsLib (bukan
// import langsung) supaya tetap berupa skrip biasa non-module seperti
// seluruh file lain di aplikasi ini -- event 'pdfjs-ready' dipakai supaya
// pdf_preview.js tidak perlu tahu/pusing soal timing eksekusi module vs
// skrip biasa (module SELALU dieksekusi setelah HTML di-parse, tapi tetap
// aman ditunggu lewat event daripada berasumsi soal urutan).
import * as pdfjsLib from "/app/vendor/pdfjs/pdf.min.js";

pdfjsLib.GlobalWorkerOptions.workerSrc = "/app/vendor/pdfjs/pdf.worker.min.js";
window.pdfjsLib = pdfjsLib;
window.dispatchEvent(new Event("pdfjs-ready"));
