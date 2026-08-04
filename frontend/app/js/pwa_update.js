// pwa_update.js — notifikasi "versi baru tersedia" yang AMAN untuk PWA ini.
// SENGAJA TIDAK PERNAH me-reload halaman secara otomatis/paksa tanpa aksi
// user -- aplikasi ini penuh form input (Input Data, Rekap, Kasbon,
// Reimburse, dst) yang belum tentu sudah tersimpan; reload paksa di tengah
// sesi bisa menghilangkan data yang sedang diketik user. Sebagai gantinya:
// banner kecil, tidak mengganggu, dengan tombol "Muat Ulang" manual.
//
// Dipanggil app.js HANYA saat Service Worker BARU sudah 'installed' DAN
// SUDAH ADA controller aktif sebelumnya (lihat app.js) -- kombinasi itu
// artinya ini benar-benar UPDATE (bukan instalasi pertama kali PWA ini di
// perangkat user, yang tidak perlu diberi tahu apa-apa).
const MugenPwaUpdate = (() => {
  let sudahTampil = false;

  function tampilkanNotifikasi() {
    if (sudahTampil) return; // idempotent -- jangan dobel kalau event pemicu fire lebih dari sekali
    sudahTampil = true;

    const banner = document.createElement("div");
    banner.className = "pwa-update-banner";
    const teks = document.createElement("span");
    teks.textContent = "Versi baru tersedia.";
    const tombol = document.createElement("button");
    tombol.type = "button";
    tombol.className = "pwa-update-btn";
    tombol.textContent = "Muat Ulang";
    tombol.addEventListener("click", () => location.reload());
    banner.appendChild(teks);
    banner.appendChild(tombol);
    document.body.appendChild(banner);
  }

  return { tampilkanNotifikasi };
})();
