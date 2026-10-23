// menu_access.js — Hak Akses (REVISI BESAR, lihat permissions.py::
// PERMISSION_TREE di backend): sistem Baca/Baca & Edit/Tidak Ada Akses
// 3-level DIHAPUS TOTAL -- diganti SATU boolean "boleh akses atau tidak"
// per unit (menu/tab/sub-item), dibaca lewat GET /api/pengaturan/
// hak-akses-admin yang SEKARANG mengembalikan flat {izin_key: bool} APA
// ADANYA (TIDAK ADA LAGI sub-objek `menu` dengan level none/read/write).
//
// `has(izinKey)` -- helper UTAMA, generik untuk SEMUA key izin_* (root
// menu, tab, maupun sub-item/aksi destruktif) -- dipakai halaman BARU/
// yang sudah direvisi untuk menyembunyikan/menonaktifkan elemen secara
// granular per unit, PERSIS sesuai checklist Owner.
//
// `get(menuKey)` -- shim KOMPATIBILITAS MUNDUR untuk halaman yang BELUM
// direvisi ke granularitas penuh: mengembalikan "none" (root menu ini
// tidak dicentang -- halaman HARUS tampilkan HANYA emptyState, jangan
// fetch/tampilkan apa pun) atau "write" (root dicentang -- tampilkan
// akses penuh, sama seperti sebelumnya; backend TETAP menegakkan setiap
// aksi destruktif/spesifik lewat require_permission() masing-masing
// endpoint, TERLEPAS dari apa yang ditampilkan di sini). TIDAK PERNAH
// lagi mengembalikan "read" -- menghapus perilaku "read-only, tombol
// disembunyikan" lama (lihat PERMINTAAN OWNER: hapus sistem 3-level).
//
// PENTING: ini MURNI kenyamanan UI (sembunyikan yang tidak relevan) --
// perlindungan SEBENARNYA tetap di backend (require_menu_read()/
// require_permission() di routers/*.py, lihat auth.py).
//
// Owner ('admin') dan role di luar 'staff' (Barber, dst -- akses mereka
// diatur mekanisme LAIN yang sudah ada, TIDAK PERNAH lewat katalog izin_*
// ini, lihat permissions.py) SELALU dapat akses penuh dari helper ini
// supaya halaman yang mereka pakai bersama staff (mis. Rekap, Absensi)
// tidak pernah ikut terbatasi oleh sistem yang bukan buat mereka.

const MugenMenuAccess = (() => {
  let _cache = null;
  let _pending = null;

  function _muatIzin() {
    if (_cache) return Promise.resolve(_cache);
    if (_pending) return _pending;
    _pending = MugenApi.get("/api/pengaturan/hak-akses-admin")
      .then((data) => {
        _cache = data || {};
        _pending = null;
        return _cache;
      })
      .catch((e) => {
        _pending = null;
        throw e;
      });
    return _pending;
  }

  // Return Promise<boolean> -- akun yang login punya izin `izinKey` ini
  // (persis nama key di permissions.py::PERMISSION_TREE, mis.
  // "izin_booking_list"/"izin_produk_mutasi"/dst).
  async function has(izinKey) {
    const user = MugenState.getUser();
    if (!user || user.role !== "staff") return true;
    try {
      const izin = await _muatIzin();
      return !!izin[izinKey];
    } catch (e) {
      // Gagal memuat (offline/error jaringan) -- fail-open supaya staff
      // yang SEBENARNYA punya akses tidak diblokir cuma gara-gara koneksi
      // bermasalah; backend TETAP jadi lapis pertahanan sebenarnya.
      return true;
    }
  }

  // Shim kompatibilitas mundur -- lihat docstring modul. `menuKey` sama
  // seperti nama lama (mis. "booking"/"input_data"/"rekap"/"kasbon"/dst),
  // diterjemahkan ke root key barunya (`izin_<menuKey>_lihat`).
  async function get(menuKey) {
    const akses = await has(`izin_${menuKey}_lihat`);
    return akses ? "write" : "none";
  }

  // Versi SINKRON dari has() -- dipakai nav.js (sidebar dibangun sinkron
  // di SETIAP pindah halaman/menu, lihat router.js::shell(), tidak bisa
  // menunggu Promise). Baca cache yang SUDAH terisi; kalau belum terisi
  // (navigasi PERTAMA setelah login, request masih di jalan), fail-open
  // ke `true` -- sama seperti has()/get() di atas, konsekuensinya PALING
  // BURUK menu tampil sesaat sebelum menghilang di render sidebar
  // berikutnya (shell() rerender di navigasi manapun), BUKAN staff
  // mendapat akses sungguhan (backend tetap menolak). `preload()` di
  // bawah dipanggil non-blocking supaya cache ini biasanya SUDAH terisi
  // sebelum navigasi kedua.
  function hasSync(izinKey) {
    const user = MugenState.getUser();
    if (!user || user.role !== "staff") return true;
    if (!_cache) return true;
    return !!_cache[izinKey];
  }

  // Memicu _muatIzin() tanpa menunggu hasilnya -- dipanggil nav.js setiap
  // render() supaya cache terisi secepat mungkin (idempotent, _muatIzin()
  // sendiri sudah mencegah fetch dobel lewat _pending).
  function preload() {
    if (MugenState.getUser() && MugenState.getUser().role === "staff") {
      _muatIzin().catch(() => {});
    }
  }

  // Dipanggil setelah PUT checklist Hak Akses berhasil disimpan (Setting >
  // Hak Akses User) supaya sesi Owner sendiri (kalau kebetulan sedang
  // menyimulasi/menguji) tidak memakai cache basi -- staff lain tetap
  // perlu reload (SPA ini tidak punya mekanisme push realtime untuk hal
  // ini, sama seperti MugenBrand/cache lain di aplikasi ini).
  function invalidate() {
    _cache = null;
    _pending = null;
  }

  return { has, hasSync, preload, get, invalidate };
})();

window.MugenMenuAccess = MugenMenuAccess;
