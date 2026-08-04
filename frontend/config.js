// config.js (Landing Page publik, root "/") — SAMA PERSIS nilainya dengan
// app/config.js (duplikasi SENGAJA, bukan bug: proyek ini TIDAK memakai
// proses build/bundler sama sekali, lihat README, jadi tidak ada mekanisme
// "satu sumber kebenaran" lintas frontend/ dan frontend/app/ selain disiplin
// manual menjaga keduanya sama). Ganti KEDUA file ini bersamaan kalau URL
// backend berubah.

window.MUGEN_API_BASE = "https://api.rivoirsett.com";
