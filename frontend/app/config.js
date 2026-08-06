// config.js — SATU-SATUNYA tempat yang perlu diedit setelah backend
// di-deploy. Isi dengan URL backend Anda, contoh:
//   window.MUGEN_API_BASE = "https://api.rivoirsett.com";
// Dibiarkan kosong (null) untuk development lokal — api.js otomatis akan
// memakai http://localhost:8000 kalau nilai ini kosong dan diakses dari
// localhost/127.0.0.1.

window.MUGEN_API_BASE = "https://api.rivoirsett.com";

// FITUR Subdomain Otomatis per Tenant: domain dasar SUBDOMAIN tenant
// (<slug>.MUGEN_TENANT_BASE_DOMAIN) -- SAMA PERSIS nilainya dengan
// TENANT_SUBDOMAIN_SUFFIX di backend (tenant_middleware.py/tenant_db.py).
// Dipakai tenant_guard.js MURNI di sisi klien untuk mendeteksi "apakah
// domain yang sedang dibuka ini bentuk subdomain tenant" (supaya bisa
// menampilkan halaman "Tenant Tidak Ditemukan" kalau slug-nya tidak
// dikenal backend) -- TIDAK PERNAH dipakai untuk otorisasi/keputusan
// keamanan apa pun (itu sepenuhnya tetap di backend).
window.MUGEN_TENANT_BASE_DOMAIN = "rivoirsett.com";
