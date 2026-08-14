// page_loader.js — PERBAIKAN PERFORMA (loading awal lambat): sebelum file
// ini ada, index.html memuat SEMUA modul js/pages/*.js lewat <script> biasa
// di awal (termasuk pengaturan.js/superadmin.js/booking.js yang masing-
// masing puluhan KB), padahal satu sesi user cuma pernah membuka SEBAGIAN
// kecil menu itu (Barber misalnya TIDAK PERNAH butuh superadmin.js/
// pengaturan.js/produk.js sama sekali). Modul di sini memuat file js/pages/
// tertentu secara DINAMIS, HANYA saat menu itu benar-benar dibuka pertama
// kali (lihat pemanggilnya di router.js) -- bukan di awal aplikasi dibuka.
//
// File INTI (ui.js/api.js/nav.js/router.js/app.js/dst) dan halaman kecil
// yang mungkin dibutuhkan SEBELUM login/routing sempat jalan (login.js,
// register.js, lupa_password.js, reset_password.js, verify_email.js,
// tenant_not_found.js, subscription_blocked.js) TETAP dimuat lewat <script>
// biasa di index.html seperti sebelumnya, TIDAK disentuh sama sekali di
// sini -- hanya modul HALAMAN besar yang baru relevan SETELAH login/routing
// jalan yang dipindah ke sini.
//
// PENTING soal offline/PWA: file yang dimuat dinamis lewat modul ini TETAP
// terdaftar di APP_SHELL service-worker.js (precache saat instalasi), TIDAK
// dihapus dari sana -- jadi begitu PWA pernah online sekali dan Service
// Worker selesai terpasang, <script> dinamis yang dibuat di sini akan
// selalu kena tangkap fetch handler SW dan disajikan dari Cache Storage
// secara instan, ONLINE ATAU OFFLINE, persis seperti sebelum revisi ini.
// Satu-satunya skenario BARU yang tidak didukung sebelumnya: instalasi
// pertama kali yang langsung offline SEBELUM precache SW sempat selesai,
// lalu membuka halaman yang belum pernah dibuka sama sekali di sesi itu --
// gagal dengan pesan error jelas (lihat ensure() di bawah + pemanggilnya di
// router.js), BUKAN halaman kosong diam-diam.

const MugenPageLoader = (() => {
  // nama objek global (mis. "PageRekap") -> Promise yang resolve begitu
  // script-nya selesai dimuat DAN objek globalnya benar-benar ada. Di-cache
  // supaya navigasi berulang ke menu yang sama TIDAK menyuntik ulang tag
  // <script> yang sama berkali-kali (baik sudah selesai maupun masih
  // berjalan -- kalau dua navigasi cepat beruntun ke menu yang sama terjadi
  // sebelum load pertama selesai, keduanya berbagi Promise yang sama).
  const _promises = new Map();

  // Query "?v=..." dipakai SAMA PERSIS dengan cache-busting yang sudah ada
  // di index.html (lihat ASSET_VERSION di service-worker.js) -- diambil
  // dari atribut src milik <script src="js/router.js?v=..."> yang SUDAH
  // ada di index.html, supaya angka versinya tidak perlu diduplikasi lagi
  // di tempat ketiga (index.html DAN service-worker.js sudah cukup, lihat
  // catatan ASSET_VERSION di sana untuk alasan kenapa keduanya tidak bisa
  // disatukan lewat satu file "sumber kebenaran" tanpa proses build).
  function _versiAset() {
    const tag = document.querySelector('script[src^="js/router.js"]');
    if (!tag) return "";
    const src = tag.getAttribute("src") || "";
    const idx = src.indexOf("?v=");
    return idx === -1 ? "" : src.slice(idx + 3);
  }

  function ensure(globalName, src) {
    if (window[globalName]) return Promise.resolve();
    if (_promises.has(globalName)) return _promises.get(globalName);

    const p = new Promise((resolve, reject) => {
      const versi = _versiAset();
      const el = document.createElement("script");
      el.src = versi ? `${src}?v=${versi}` : src;
      el.onload = () => {
        if (window[globalName]) {
          resolve();
        } else {
          // Script selesai dimuat (HTTP 200) tapi objek globalnya tidak
          // ada -- seharusnya tidak pernah terjadi kalau catalog di
          // router.js benar, tapi tetap ditangani rapi (bukan diam-diam
          // gagal) kalau suatu saat ada typo nama.
          reject(new Error(`Modul ${globalName} tidak ditemukan setelah ${src} dimuat.`));
        }
      };
      el.onerror = () => reject(new Error(`Gagal memuat ${src}.`));
      document.body.appendChild(el);
    });
    // Kegagalan TIDAK disimpan di cache -- percobaan navigasi berikutnya
    // (mis. setelah koneksi pulih) harus mencoba fetch lagi, bukan langsung
    // gagal lagi dari cache Promise yang sudah reject.
    p.catch(() => _promises.delete(globalName));
    _promises.set(globalName, p);
    return p;
  }

  return { ensure };
})();
