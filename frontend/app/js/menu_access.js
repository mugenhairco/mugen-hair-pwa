// menu_access.js — Hak Akses Menu (permintaan Owner, lihat permissions.py::
// MENU_DEFS di backend): helper BERSAMA dipakai SEMUA halaman menu (Input
// Data, Rekap, Booking, dst) untuk tahu level akses ("none"/"read"/"write")
// akun yang sedang login terhadap satu menu, supaya halaman bisa:
// - "none" -> tampilkan HANYA MugenUI.emptyState("Anda tidak memiliki akses
//   ke menu ini."), JANGAN fetch/tampilkan data/form/tombol apa pun.
// - "read" -> tampilkan data seperti biasa, SEMBUNYIKAN/nonaktifkan tombol
//   tambah/edit/hapus/approve/aksi lain yang mengubah data.
// - "write" -> akses penuh, sama seperti sebelum fitur ini ada.
//
// PENTING: ini MURNI kenyamanan UI (sembunyikan yang tidak relevan) --
// perlindungan SEBENARNYA tetap di backend (require_menu_read()/
// require_permission() di routers/*.py, lihat auth.py), endpoint menolak
// permintaan tanpa akses TERLEPAS dari apa yang ditampilkan di sini.
//
// Owner ('admin') dan role di luar 'staff' (Barber, dst -- akses mereka
// diatur mekanisme LAIN yang sudah ada, TIDAK PERNAH lewat katalog izin_*
// ini, lihat permissions.py) SELALU dapat "write" dari helper ini supaya
// halaman yang mereka pakai bersama staff (mis. Rekap, Absensi) tidak
// pernah ikut terbatasi oleh sistem yang bukan buat mereka.

const MugenMenuAccess = (() => {
  let _cache = null;
  let _pending = null;

  function _muatLevels() {
    if (_cache) return Promise.resolve(_cache);
    if (_pending) return _pending;
    _pending = MugenApi.get("/api/pengaturan/hak-akses-admin")
      .then((data) => {
        _cache = data.menu || {};
        _pending = null;
        return _cache;
      })
      .catch((e) => {
        _pending = null;
        throw e;
      });
    return _pending;
  }

  // Return Promise<"none"|"read"|"write"> untuk `menuKey` (lihat daftar
  // lengkap key di permissions.py::MENU_DEFS, mis. "booking"/"input_data"/
  // "rekap"/"kasbon"/dst) akun yang sedang login.
  async function get(menuKey) {
    const user = MugenState.getUser();
    if (!user || user.role !== "staff") return "write";
    try {
      const levels = await _muatLevels();
      return levels[menuKey] || "none";
    } catch (e) {
      // Gagal memuat (offline/error jaringan) -- fail-open ke "write" supaya
      // staff yang SEBENARNYA punya akses tidak diblokir cuma gara-gara
      // koneksi bermasalah; backend TETAP jadi lapis pertahanan sebenarnya
      // (endpoint menolak kalau memang tidak berhak, lihat catatan di atas).
      return "write";
    }
  }

  // Dipanggil setelah PUT Hak Akses Menu berhasil disimpan (Setting > Hak
  // Akses User) supaya sesi Owner sendiri (kalau kebetulan sedang menyimulasi/
  // menguji) tidak memakai cache basi -- staff lain tetap perlu reload
  // (SPA ini tidak punya mekanisme push realtime untuk hal ini, sama seperti
  // MugenBrand/cache lain di aplikasi ini).
  function invalidate() {
    _cache = null;
    _pending = null;
  }

  return { get, invalidate };
})();

window.MugenMenuAccess = MugenMenuAccess;
