// icons.js — PERMINTAAN Owner ("desain kurang ikon/ilustrasi"): kumpulan
// SVG ikon outline terpusat, dipakai sidebar navigasi (nav.js), kartu
// statistik Dashboard (dashboard_owner.js), empty state (ui.js), dan kolom
// Metode Pembayaran (booking.js/pos.js). SENGAJA inline SVG string (BUKAN
// font ikon/library eksternal dari CDN) -- konsisten dengan filosofi
// aplikasi ini menghindari aset eksternal (lihat booking_notif.js::
// playChime(), chime disintesis sendiri lewat Web Audio API dengan alasan
// yang sama persis: tanpa request jaringan tambahan, tetap berfungsi
// offline, ter-cache Service Worker seperti file JS lain). Gaya: outline
// 2px, stroke="currentColor" (otomatis ikut warna teks di sekitarnya,
// termasuk saat hover/active/dark mode -- tidak perlu varian warna
// terpisah), viewBox 24x24, ukuran tampil diatur lewat CSS (.icon-inline/
// .nav-icon/dst), BUKAN atribut width/height tetap di SVG-nya sendiri.

const MugenIcons = (() => {
  const S = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';

  return {
    // ---- Sidebar navigasi ----
    dashboard: `<svg ${S}><rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="5" rx="1.5"/><rect x="13" y="12" width="8" height="9" rx="1.5"/><rect x="3" y="15" width="8" height="6" rx="1.5"/></svg>`,
    inputData: `<svg ${S}><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/><path d="M9 13h6"/><path d="M9 17h6"/></svg>`,
    rekap: `<svg ${S}><path d="M3 21h18"/><rect x="5" y="11" width="3.5" height="8" rx="0.5"/><rect x="10.3" y="6" width="3.5" height="13" rx="0.5"/><rect x="15.5" y="14" width="3.5" height="5" rx="0.5"/></svg>`,
    karyawan: `<svg ${S}><circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><path d="M16.5 6.2a3.2 3.2 0 0 1 0 6.1"/><path d="M15.5 14.3c2.8.5 5 2.8 5 5.7"/></svg>`,
    absensi: `<svg ${S}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/></svg>`,
    booking: `<svg ${S}><rect x="3" y="5" width="18" height="16" rx="2.5"/><path d="M3 10h18"/><path d="M8 3v4"/><path d="M16 3v4"/></svg>`,
    keuangan: `<svg ${S}><path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h13A2.5 2.5 0 0 1 21 7.5V9H3z"/><path d="M3 9v8a2.5 2.5 0 0 0 2.5 2.5h13A2.5 2.5 0 0 0 21 17V9"/><path d="M16 14h2"/></svg>`,
    pos: `<svg ${S}><circle cx="9" cy="20" r="1.4"/><circle cx="18" cy="20" r="1.4"/><path d="M2.5 4h2.3l2.1 11.2a2 2 0 0 0 2 1.6h8.6a2 2 0 0 0 2-1.6L21 7.5H6"/></svg>`,
    produk: `<svg ${S}><path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="M3 8l9 5 9-5"/><path d="M12 13v8"/></svg>`,
    whatsapp: `<svg ${S}><path d="M21 11.5a8.5 8.5 0 0 1-12.4 7.5L3 20l1.1-5.4A8.5 8.5 0 1 1 21 11.5Z"/><path d="M8.5 9.8c.2 2.9 2.7 5.4 5.6 5.6" stroke-dasharray="0.1 3"/></svg>`,
    billing: `<svg ${S}><rect x="2.5" y="5" width="19" height="14" rx="2.2"/><path d="M2.5 10h19"/><path d="M6 15h4"/></svg>`,
    setting: `<svg ${S}><circle cx="12" cy="12" r="3"/><path d="M19.4 13.5a7.6 7.6 0 0 0 0-3l2-1.4-2-3.4-2.3.8a7.6 7.6 0 0 0-2.6-1.5L14 2.5h-4l-.5 2.5a7.6 7.6 0 0 0-2.6 1.5l-2.3-.8-2 3.4 2 1.4a7.6 7.6 0 0 0 0 3l-2 1.4 2 3.4 2.3-.8a7.6 7.6 0 0 0 2.6 1.5l.5 2.5h4l.5-2.5a7.6 7.6 0 0 0 2.6-1.5l2.3.8 2-3.4z"/></svg>`,

    // ---- Kartu statistik Dashboard ----
    service: `<svg ${S}><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M8.3 7.8 19 19"/><path d="M19 5 8.3 16.2"/></svg>`,
    komisi: `<svg ${S}><rect x="2.5" y="6" width="19" height="12" rx="2"/><circle cx="12" cy="12" r="2.6"/><path d="M6 6v12M18 6v12"/></svg>`,
    tips: `<svg ${S}><path d="M12 3v3"/><path d="M12 21c3.5 0 6-2.5 6-6V9H6v6c0 3.5 2.5 6 6 6Z"/><path d="M6 11H4.5A2.5 2.5 0 0 0 4 15.9"/><path d="M18 11h1.5A2.5 2.5 0 0 1 20 15.9"/></svg>`,
    uangHarian: `<svg ${S}><circle cx="12" cy="12" r="9"/><path d="M12 7.5v9"/><path d="M15 9.8c0-1.3-1.3-2.3-3-2.3s-3 1-3 2.3c0 3 6 1.4 6 4.4 0 1.3-1.3 2.3-3 2.3s-3-1-3-2.3"/></svg>`,
    bonusCustomer: `<svg ${S}><rect x="3" y="9" width="18" height="11" rx="1.5"/><path d="M3 13h18"/><path d="M12 9v11"/><path d="M12 9c-1.8 0-3.3-1.3-3.3-3S10.2 3 12 4.6C13.8 3 15.3 4.2 15.3 6S13.8 9 12 9Z"/></svg>`,
    pengeluaran: `<svg ${S}><path d="M12 4v13"/><path d="M7 12l5 5 5-5"/><path d="M5 20h14"/></svg>`,
    penjualanProduk: `<svg ${S}><path d="M12.4 3h6.1A1.5 1.5 0 0 1 20 4.5v6.1a1.5 1.5 0 0 1-.44 1.06l-8 8a1.5 1.5 0 0 1-2.12 0l-6-6a1.5 1.5 0 0 1 0-2.12l8-8A1.5 1.5 0 0 1 12.4 3Z"/><circle cx="16" cy="7" r="1.3"/></svg>`,
    labaKotor: `<svg ${S}><path d="M3 7 10 14l4-4 7 7"/><path d="M14 7h7v7"/></svg>`,

    // ---- Lain-lain ----
    emptyBox: `<svg ${S}><path d="M3 9.5 12 5l9 4.5V18L12 22l-9-4.5Z"/><path d="M3 9.5 12 14l9-4.5"/><path d="M12 14v8"/></svg>`,
    qris: `<svg ${S}><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM19 14h2M14 19h2M19 19h2"/></svg>`,
    cash: `<svg ${S}><rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="3"/><path d="M6 10v4M18 10v4"/></svg>`,
    gateway: `<svg ${S}><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 9.5h20"/><path d="M6 14h4"/></svg>`,
    bayarNanti: `<svg ${S}><circle cx="12" cy="12" r="9"/><path d="M12 7.5v5l3.3 1.8"/></svg>`,

    // ---- PERMINTAAN Owner ("ikon di tiap dropdown sesuai artinya"):
    // dipakai MugenUI.selectIcon() (ui.js) untuk ikon prefix di dalam
    // <select> (Bulan/Tahun/filter status/jenis/metode dkk) di seluruh app.
    calendar: `<svg ${S}><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>`,
    filter: `<svg ${S}><path d="M4 5h16"/><path d="M7 12h10"/><path d="M10.5 19h3"/></svg>`,
    tag: `<svg ${S}><path d="M12.4 3h6.1A1.5 1.5 0 0 1 20 4.5v6.1a1.5 1.5 0 0 1-.44 1.06l-8 8a1.5 1.5 0 0 1-2.12 0l-6-6a1.5 1.5 0 0 1 0-2.12l8-8A1.5 1.5 0 0 1 12.4 3Z"/><circle cx="16" cy="7" r="1.3"/></svg>`,
    statusCheck: `<svg ${S}><circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/></svg>`,

    // PERMINTAAN Owner (tombol "Keluar" sidebar jadi ikon polos, bukan
    // tombol lebar): pintu + panah keluar -- dipakai nav.js::btnLogout
    // untuk SEMUA role (satu implementasi dipakai bersama).
    logout: `<svg ${S}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>`,

    // PERMINTAAN Owner (aksi per-baris tabel Daftar Produk jadi satu
    // tombol menu, bukan banyak tombol sejajar): titik tiga vertikal,
    // isi solid (BUKAN outline seperti ikon lain -- fill/stroke di-override
    // langsung di tiap <circle> supaya tetap pakai currentColor).
    moreVertical: `<svg ${S}><circle cx="12" cy="5" r="1.6" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none"/><circle cx="12" cy="19" r="1.6" fill="currentColor" stroke="none"/></svg>`,

    // PERMINTAAN Owner (tombol "Tambah Produk" di header "Daftar Produk"
    // -- form pindah jadi modal): plus polos, dipakai jadi ikon prefix
    // tombol tambah/buat baru.
    plus: `<svg ${S}><path d="M12 5v14M5 12h14"/></svg>`,

    // PERMINTAAN Owner (pencarian produk di Daftar Produk, pakai ikon):
    // kaca pembesar -- dipakai MugenUI.selectIcon() sebagai prefix input
    // teks pencarian (fungsinya generik, bukan cuma untuk <select>).
    search: `<svg ${S}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>`,
  };
})();

// PERBAIKAN PERFORMA: modul dimuat dinamis page_loader.js, lihat catatan
// window.PageXxx di bagian bawah file js/pages/*.js -- tapi file INI dimuat
// via <script> biasa (bukan lazy), langsung dipakai nav.js yang juga
// non-lazy, jadi top-level const sudah cukup, tidak perlu window.MugenIcons.
