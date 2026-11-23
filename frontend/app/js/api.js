// api.js — satu pintu untuk semua pemanggilan REST API backend.
// - Menyisipkan token login otomatis (Authorization: Bearer ...).
// - Kalau GET gagal karena offline (network error), pakai data cache terakhir
//   yang tersimpan (lihat state.js) supaya halaman tetap bisa dibuka, dengan
//   penanda jelas bahwa data itu bukan data terbaru (poin #22).
// - Kalau server balas 401 (token invalid/kedaluwarsa), otomatis logout dan
//   lempar ke halaman login.

// Ganti nilai ini (atau override lewat window.MUGEN_API_BASE sebelum app.js
// dimuat) sesuai URL backend setelah deploy, contoh:
// "https://api.rivoirsett.com"
const MUGEN_API_BASE =
  window.MUGEN_API_BASE ||
  (location.hostname === "localhost" || location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : "");

const MugenApi = (() => {
  class ApiError extends Error {
    constructor(message, status, detail) {
      super(message);
      this.status = status;
      this.detail = detail;
    }
  }

  // BUGFIX: `payload.detail` dari backend BIASANYA string biasa (ValueError
  // dkk), TAPI auth.require_feature() (lihat routers/attendance.py,
  // booking.py) sengaja membalas OBJEK terstruktur
  // `{message, feature, upgrade_required}` di body JSON (kontrak backend
  // TIDAK diubah, tetap diuji apa adanya lewat TestClient di
  // backend/tests/) -- TAPI belum ada satu pun halaman yang membaca
  // `.feature`/`.upgrade_required`, sedangkan HAMPIR SEMUA halaman
  // menampilkan error lewat pola `e.detail.detail ? e.detail.detail :
  // e.message` (baca .detail.detail sebagai STRING). Tanpa normalisasi
  // ini, gate fitur baru (mis. "absensi" -- lihat routers/attendance.py)
  // yang sebelumnya jarang tersentuh jadi sering muncul sebagai literal
  // "[object Object]".
  //
  // PENTING: HANYA bentuk `upgrade_required` yang diratakan jadi string --
  // bentuk objek TERSTRUKTUR LAIN (mis. 409 login ambigu-tenant
  // `{message, tenants: [...]}` dan 403 `{code: "email_belum_
  // terverifikasi", email}`, lihat pages/login.js) SENGAJA TIDAK disentuh
  // sama sekali, karena field-field itu SUNGGUHAN dibaca frontend untuk
  // alur pemilih-toko/verifikasi-email -- meratakannya jadi string akan
  // MERUSAK kedua alur itu.
  function _pesanDariDetail(detail) {
    if (typeof detail === "string" && detail) return detail;
    if (detail && detail.upgrade_required && typeof detail.message === "string") return detail.message;
    return "Terjadi kesalahan pada server.";
  }

  function _normalisasiPayload(payload) {
    if (!payload || !payload.detail || typeof payload.detail !== "object" || !payload.detail.upgrade_required) {
      return payload; // string biasa ATAU bentuk terstruktur lain -- BIARKAN apa adanya
    }
    return { ...payload, detail: _pesanDariDetail(payload.detail) };
  }

  // Daftar LENGKAP flag "halaman" generik (BUKAN termasuk "dashboard", yang
  // punya mekanisme terpisah -- lihat tandaiDashboardKotor() di state.js) --
  // INI YANG DIPAKAI SEBAGAI DEFAULT KONSERVATIF kalau endpoint yang baru
  // dipanggil TIDAK cocok pola apa pun di POLA_FLAG_PRESISI di bawah.
  const FLAG_HALAMAN_SEMUA = [
    "rekap", "rekap_transaksi", "produk", "input_data", "slip_gaji", "kasbon",
    "komisi", "reimburse", "pemasukan", "pengeluaran", "uang_kas", "whatsapp",
    "pengaturan",
  ];

  // BUGFIX "Rekap/menu lain reload penuh tanpa alasan" (PERMINTAAN Owner,
  // lanjutan PR #304/#305) -- SEBELUMNYA SETIAP mutasi (POST/PUT/DELETE) di
  // MANA PUN mengotori SEMUA 13 flag di atas + dashboard sekaligus (lihat
  // riwayat di bawah FLAG_HALAMAN_SEMUA), padahal mayoritas endpoint cuma
  // benar-benar memengaruhi SATU flag miliknya sendiri. Efeknya: menu A
  // selalu reload penuh begitu dibuka lagi gara-gara mutasi TIDAK TERKAIT
  // di menu B/C/dst.
  //
  // Daftar di bawah MENGGANTIKAN daftar penuh HANYA untuk endpoint yang
  // cocok (method + path, path TANPA query string) -- tiap baris punya
  // bukti kode backend (riset menyeluruh, bukan tebakan) soal flag mana
  // yang BENAR relevan. Endpoint yang TIDAK cocok pola apa pun di bawah
  // (termasuk SEMUA endpoint Input Data/manual-customer/data-non-barber --
  // BELUM diverifikasi tuntas relasinya dengan flag lain, lihat riset) TETAP
  // memakai FLAG_HALAMAN_SEMUA + dashboard seperti sebelumnya -- default
  // AMAN/konservatif ini SENGAJA dipertahankan: lebih baik reload
  // berlebihan daripada diam-diam menampilkan DATA UANG yang basi.
  //
  // Relasi uang nyata (BUKAN nol relasi) yang dipertahankan di bawah,
  // dengan bukti:
  // - Pengeluaran (sumber_dana="karyawan") membuat/ubah/hapus baris
  //   Reimburse OTOMATIS langsung berstatus "disetujui" (reimburse_db.py::
  //   buat_reimburse_sistem()), yang ikut tampil di tab Transaksi Rekap
  //   (reimburse_db.py::gabung_ke_rekap_transaksi()) -- endpoint Pengeluaran
  //   TETAP mengotori "reimburse"/"rekap"/"rekap_transaksi" (suntik di
  //   rekap.js::suntikBarisPengeluaran()/hapusBarisPengeluaran() yang
  //   membersihkan SEBAGIAN lagi kalau baris itu ternyata sumber_dana="kas").
  // - Slip Gaji ubah status (sudah_dibayar/batal) MEMOTONG/MEMBATALKAN
  //   Kasbon NYATA (kasbon_db.py::terapkan_potongan_slip_gaji()/
  //   batalkan_potongan_slip_gaji(), dipanggil slip_gaji_db.py) -- endpoint
  //   ini TETAP mengotori "kasbon"/"rekap"/"rekap_transaksi" (sudah
  //   di-suntik slip_gaji.js::suntikBarisKasbon()/hapusBarisKasbon()).
  //   Endpoint GENERATE slip gaji (POST) TIDAK menyentuh Kasbon sama sekali
  //   (hanya baca live saldo Kasbon/Komisi/Reimburse lewat GET terpisah
  //   sebelum submit, lihat slip_gaji.js) -- aman HANYA kotori "slip_gaji".
  // - Produk "jual" (POS maupun manual) mengubah omzet penjualan produk
  //   yang dibaca Dashboard (routers/dashboard.py::dashboard_owner() ->
  //   database.py::get_omzet_penjualan_produk()) -- TETAP kotori "dashboard".
  // - Pengaturan Komisi/Bonus Tier/Bonus Service/Uang Harian/status aktif
  //   Barber dibaca LIVE oleh Rekap Bulanan DAN Dashboard
  //   (database.py::get_ringkasan_semua_barber_bulan(), routers/
  //   dashboard.py::dashboard_owner()) -- TETAP kotori "rekap" + dashboard
  //   (TIDAK "rekap_transaksi" -- tidak pernah mengubah baris transaksi
  //   apa pun, murni angka ringkasan).
  const POLA_FLAG_PRESISI = [
    // ---- Produk (logic di database.py) -- TIDAK PERNAH dibaca Rekap
    // (Transaksi maupun Bulanan) ataupun halaman lain mana pun, KECUALI
    // "jual"/koreksi-hapus mutasi (bisa jenis "jual") yang muncul di omzet
    // Dashboard.
    { re: /^\/api\/produk\/\d+\/jual$/, methods: ["POST"], flags: ["produk"], dashboard: true },
    { re: /^\/api\/produk\/mutasi\/\d+$/, methods: ["PUT", "DELETE"], flags: ["produk"], dashboard: true },
    { re: /^\/api\/produk(\/\d+)?$/, methods: ["POST", "PUT", "DELETE"], flags: ["produk"], dashboard: false },
    { re: /^\/api\/produk\/\d+\/(restock|tester)$/, methods: ["POST"], flags: ["produk"], dashboard: false },

    // ---- Pemasukan (pemasukan_db.py) -- leaf TOTAL, tidak pernah ditulis
    // maupun dibaca modul lain mana pun (hanya laporan_pdf.py yang membaca,
    // itu generate-on-demand, bukan cache halaman apa pun).
    { re: /^\/api\/pemasukan(\/\d+)?$/, methods: ["POST", "PUT", "DELETE"], flags: ["pemasukan"], dashboard: false },

    // ---- Uang Kas -- endpoint MANUAL milik menu ini sendiri (penyesuaian
    // otomatis dari Pengeluaran sumber_dana="kas" BUKAN request terpisah,
    // lihat pola Pengeluaran di bawah).
    { re: /^\/api\/uang-kas\/saldo-awal$/, methods: ["PUT"], flags: ["uang_kas"], dashboard: false },
    { re: /^\/api\/uang-kas(\/\d+)?$/, methods: ["POST", "PUT", "DELETE"], flags: ["uang_kas"], dashboard: false },

    // ---- Kasbon (kasbon_db.py) -- endpoint MILIK SENDIRI (ajukan/bayar/
    // hapus). Leaf TOTAL untuk tulisan KELUAR (tidak pernah menulis ke
    // modul lain) DAN tidak dibaca Dashboard -- TAPI baris Kasbon
    // dibayar/diajukan MEMANG tampil di tab Transaksi Rekap (sudah
    // di-suntik kasbon.js::suntikBarisKasbon()/hapusBarisKasbon()), jadi
    // TETAP kotori "rekap"/"rekap_transaksi".
    { re: /^\/api\/kasbon(\/\d+)?$/, methods: ["POST", "PUT", "DELETE"], flags: ["kasbon", "rekap", "rekap_transaksi"], dashboard: false },
    { re: /^\/api\/kasbon\/\d+\/pembayaran$/, methods: ["POST"], flags: ["kasbon", "rekap", "rekap_transaksi"], dashboard: false },

    // ---- Reimburse (reimburse_db.py) -- endpoint MILIK SENDIRI (ajukan/
    // setujui/tolak/hapus lewat reimburse.js, BEDA dari baris sistem yang
    // dibuat Pengeluaran sumber_dana="karyawan" lewat endpoint Pengeluaran
    // sendiri). Leaf TOTAL untuk tulisan KELUAR, tidak dibaca Dashboard --
    // TAPI klaim disetujui TAMPIL di tab Transaksi Rekap (sudah di-suntik
    // reimburse.js::suntikBarisReimburse()), jadi TETAP kotori
    // "rekap"/"rekap_transaksi".
    { re: /^\/api\/reimburse(\/\d+)?$/, methods: ["POST", "PUT", "DELETE"], flags: ["reimburse", "rekap", "rekap_transaksi"], dashboard: false },
    { re: /^\/api\/reimburse\/\d+\/status$/, methods: ["PUT"], flags: ["reimburse", "rekap", "rekap_transaksi"], dashboard: false },

    // ---- Komisi Penyesuaian (komisi_penyesuaian_db.py) -- leaf TOTAL,
    // TIDAK menyentuh perhitungan komisi dasar Rekap Bulanan/Transaksi
    // ataupun halaman lain mana pun (docstring modul ini sendiri: "Jangan
    // mengubah sistem komisi yang sudah ada").
    { re: /^\/api\/komisi\/penyesuaian(\/\d+)?$/, methods: ["POST", "PUT", "DELETE"], flags: ["komisi"], dashboard: false },

    // ---- Slip Gaji -- generate (POST) HANYA baca live saldo terkait lewat
    // GET terpisah sebelum submit, TIDAK menulis ke Kasbon/Rekap sama
    // sekali saat ini. Ubah status (PUT .../status) BARU memotong/
    // membatalkan Kasbon nyata -- lihat catatan panjang di atas.
    { re: /^\/api\/slip-gaji$/, methods: ["POST"], flags: ["slip_gaji"], dashboard: false },
    { re: /^\/api\/slip-gaji\/\d+\/status$/, methods: ["PUT"], flags: ["slip_gaji", "kasbon", "rekap", "rekap_transaksi"], dashboard: false },

    // ---- WhatsApp settings (token/template notifikasi booking) + Reminder
    // Absensi -- config pengiriman WA murni, tidak pernah dibaca modul
    // uang/Rekap/Dashboard mana pun.
    { re: /^\/api\/pengaturan\/whatsapp(\/tes)?$/, methods: ["POST", "PUT"], flags: ["whatsapp"], dashboard: false },
    { re: /^\/api\/pengaturan\/absensi-reminder$/, methods: ["PUT"], flags: ["whatsapp"], dashboard: false },

    // ---- Pengaturan: sub-fitur TERBUKTI dibaca LIVE oleh Rekap Bulanan
    // DAN Dashboard -- lihat catatan panjang di atas.
    { re: /^\/api\/pengaturan\/komisi$/, methods: ["PUT"], flags: ["pengaturan", "rekap"], dashboard: true },
    { re: /^\/api\/pengaturan\/bonus-tiers(\/[^/]+)?$/, methods: ["POST", "PUT", "DELETE"], flags: ["pengaturan", "rekap"], dashboard: true },
    { re: /^\/api\/pengaturan\/bonus-service-acuan$/, methods: ["PUT"], flags: ["pengaturan", "rekap"], dashboard: true },
    { re: /^\/api\/pengaturan\/uang-harian-acuan$/, methods: ["PUT"], flags: ["pengaturan", "rekap"], dashboard: true },
    { re: /^\/api\/pengaturan\/uang-harian-syarat$/, methods: ["PUT"], flags: ["pengaturan", "rekap"], dashboard: true },
    { re: /^\/api\/pengaturan\/uang-harian-target$/, methods: ["PUT"], flags: ["pengaturan", "rekap"], dashboard: true },
    { re: /^\/api\/uang-harian-dinamis\/config$/, methods: ["PUT"], flags: ["pengaturan", "rekap"], dashboard: true },
    { re: /^\/api\/pengaturan\/barber(\/\d+)?$/, methods: ["POST", "PUT", "DELETE"], flags: ["pengaturan", "rekap"], dashboard: true },

    // ---- Pengaturan: sub-fitur LAIN yang TERBUKTI TIDAK ada hubungan sama
    // sekali (branding/favicon, akun User, Hak Akses Role, Profil/Email) --
    // murni konfigurasi platform/akses, tidak pernah dibaca modul uang/
    // Rekap/Dashboard.
    { re: /^\/api\/pengaturan\/(branding|favicon)$/, methods: ["PUT", "DELETE"], flags: ["pengaturan"], dashboard: false },
    { re: /^\/api\/pengaturan\/user(\/.*)?$/, methods: ["POST", "PUT", "DELETE"], flags: ["pengaturan"], dashboard: false },
    { re: /^\/api\/pengaturan\/user-roles(\/.*)?$/, methods: ["POST", "PUT", "DELETE"], flags: ["pengaturan"], dashboard: false },
    { re: /^\/api\/pengaturan\/profil\/(email|kirim-ulang-verifikasi)$/, methods: ["POST", "PUT"], flags: ["pengaturan"], dashboard: false },

    // ---- Pengeluaran -- lihat catatan panjang di atas (relasi uang nyata
    // dengan Uang Kas DAN Reimburse, tergantung sumber_dana baris yang
    // BARU DIUBAH -- TIDAK bisa dibedakan hanya dari method+path di sini,
    // jadi KEDUANYA tetap dikotori, suntik di rekap.js yang membersihkan
    // sebagian secara kondisional per-baris).
    { re: /^\/api\/pengeluaran(\/\d+)?$/, methods: ["POST", "PUT", "DELETE"], flags: ["pengeluaran", "uang_kas", "reimburse", "rekap", "rekap_transaksi"], dashboard: true },
  ];

  // Tentukan flag "halaman" + perlu-tidaknya kotori Dashboard untuk SATU
  // mutasi (dipanggil request() di bawah). `path` BISA membawa query string
  // (mis. POST /api/manual-customer/close?tanggal=...) -- dibuang dulu
  // sebelum dicocokkan ke pola di atas, supaya pola tetap sederhana.
  function _tentukanDampakMutasi(method, path) {
    const pathTanpaQuery = String(path || "").split("?")[0];
    for (const pola of POLA_FLAG_PRESISI) {
      if (pola.methods.includes(method) && pola.re.test(pathTanpaQuery)) {
        return { flags: pola.flags, dashboard: pola.dashboard };
      }
    }
    return { flags: FLAG_HALAMAN_SEMUA, dashboard: true }; // default konservatif, lihat catatan panjang di atas
  }

  async function request(method, path, body, { useCache = false } = {}) {
    const cacheKey = `${method}:${path}`;
    const headers = { "Content-Type": "application/json" };
    const token = MugenState.getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;

    let response;
    try {
      response = await fetch(MUGEN_API_BASE + path, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch (networkErr) {
      if (method === "GET" && useCache) {
        const cached = MugenState.cacheGet(cacheKey);
        if (cached) {
          // TAHAP 13 (bugfix): banyak endpoint GET (services, transaksi,
          // produk, pengeluaran, rekap, dst) balas ARRAY, bukan object.
          // Sebelumnya di sini dipakai spread langsung ({...cached.data,
          // __offline:true}) -- kalau cached.data adalah array, hasil
          // spread-nya jadi PLAIN OBJECT (key "0","1",...), bukan array
          // lagi, sehingga Array.isArray(data) di setiap halaman menjadi
          // false dan cache offline yang sebenarnya sudah tersimpan malah
          // ditampilkan sebagai KOSONG. Untuk array, tandai __offline
          // langsung di object array itu sendiri (array tetap array).
          if (Array.isArray(cached.data)) {
            const arr = cached.data.slice();
            arr.__offline = true;
            arr.__cachedAt = cached.savedAt;
            return arr;
          }
          return { ...cached.data, __offline: true, __cachedAt: cached.savedAt };
        }
      }
      throw new ApiError("Tidak bisa terhubung ke server. Periksa koneksi internet Anda.", 0, null);
    }

    // BUGFIX: sebelumnya SETIAP 401 (termasuk dari /api/auth/login sendiri
    // saat username/password salah) dianggap "sesi berakhir" dan pesan
    // asli dari backend ("Username atau password salah.") tertimpa jadi
    // "Sesi login berakhir, silakan login lagi." -- padahal saat itu user
    // memang belum pernah punya sesi sama sekali (baru mencoba login).
    // Endpoint login sendiri dikecualikan di sini supaya pesan error yang
    // benar (dari payload.detail, ditangani di blok !response.ok di bawah)
    // yang sampai ke halaman Login.
    if (response.status === 401 && path !== "/api/auth/login") {
      MugenState.clearSession();
      location.hash = "#/login";
      throw new ApiError("Sesi login berakhir, silakan login lagi.", 401, null);
    }

    let payload = null;
    try {
      payload = await response.json();
    } catch (e) {
      // response tanpa body (mis. 204) — biarkan payload null
    }

    if (!response.ok) {
      const pesan = _pesanDariDetail(payload && payload.detail);
      throw new ApiError(pesan, response.status, _normalisasiPayload(payload));
    }

    if (method === "GET" && useCache) {
      MugenState.cacheSet(cacheKey, payload);
    }
    // PERMINTAAN OWNER: SETIAP panggilan mutasi (bukan GET) yang sukses --
    // dari menu mana pun, sekarang ATAU di masa depan -- menandai Dashboard
    // + halaman-halaman terkait "kotor" (lihat state.js::
    // tandaiDashboardKotor()/tandaiHalamanKotor()) supaya menu itu fetch
    // ulang SEKALI begitu dibuka lagi, bukan terus-terusan menampilkan
    // angka yang sudah basi. Satu hook di sini (bukan dipanggil manual di
    // tiap halaman) supaya tidak ada jalur simpan/edit/hapus yang terlewat.
    //
    // MANA yang dikotori per mutasi ditentukan _tentukanDampakMutasi() di
    // atas (lihat riset lengkap + POLA_FLAG_PRESISI di sana) -- BUKAN lagi
    // "semua flag, selalu" seperti sebelumnya (PERLUASAN BUGFIX "Rekap/menu
    // lain reload penuh tanpa alasan", PR #304/#305). Endpoint Booking/
    // Absensi/Izin & Cuti/Riwayat Transaksi (Payment Gateway)/POS TIDAK
    // cocok pola apa pun di POLA_FLAG_PRESISI (belum/tidak perlu
    // diverifikasi di sini -- Booking/Absensi/Izin&Cuti sudah pakai pola
    // cache DOM/stale-while-revalidate sendiri yang tidak baca flag ini
    // sama sekali, Riwayat Transaksi Gateway berubah lewat webhook bukan
    // aksi akun ini, dan "pos_kasir"/"pos_transaksi" milik pos.js memang
    // SENGAJA tidak punya flag di FLAG_HALAMAN_SEMUA sama sekali) -- jadi
    // tetap jatuh ke default konservatif (kotori SEMUA flag + dashboard,
    // perilaku SAMA PERSIS sebelum refactor ini untuk endpoint-endpoint
    // itu).
    if (method !== "GET") {
      const dampak = _tentukanDampakMutasi(method, path);
      if (dampak.dashboard) MugenState.tandaiDashboardKotor();
      for (const flag of dampak.flags) MugenState.tandaiHalamanKotor(flag);
    }
    return payload;
  }

  async function uploadFile(path, file) {
    const headers = {};
    const token = MugenState.getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const form = new FormData();
    form.append("file", file);

    let response;
    try {
      response = await fetch(MUGEN_API_BASE + path, { method: "POST", headers, body: form });
    } catch (networkErr) {
      throw new ApiError("Tidak bisa terhubung ke server. Periksa koneksi internet Anda.", 0, null);
    }
    if (response.status === 401) {
      MugenState.clearSession();
      location.hash = "#/login";
      throw new ApiError("Sesi login berakhir, silakan login lagi.", 401, null);
    }
    let payload = null;
    try { payload = await response.json(); } catch (e) { /* tanpa body */ }
    if (!response.ok) {
      const pesan = _pesanDariDetail(payload && payload.detail);
      throw new ApiError(pesan, response.status, _normalisasiPayload(payload));
    }
    MugenState.tandaiDashboardKotor(); // lihat catatan di request() di atas
    MugenState.tandaiHalamanKotor("reimburse");
    MugenState.tandaiHalamanKotor("pengaturan");
    return payload;
  }

  // Ambil file biner (PDF) lewat GET terautentikasi -- dipakai bersama oleh
  // downloadFile() (unduh langsung) dan fetchBlob() (Preview PDF, TIDAK
  // langsung mengunduh, lihat pdf_preview.js). Satu tempat untuk auth
  // header/penanganan 401/error supaya perilakunya konsisten di keduanya.
  async function _ambilBlob(path) {
    const headers = {};
    const token = MugenState.getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;

    let response;
    try {
      response = await fetch(MUGEN_API_BASE + path, { headers });
    } catch (networkErr) {
      throw new ApiError("Tidak bisa terhubung ke server. Periksa koneksi internet Anda.", 0, null);
    }
    if (response.status === 401) {
      MugenState.clearSession();
      location.hash = "#/login";
      throw new ApiError("Sesi login berakhir, silakan login lagi.", 401, null);
    }
    if (!response.ok) {
      let rawDetail = null;
      try { rawDetail = (await response.json()).detail; } catch (e) { /* body bukan JSON */ }
      throw new ApiError(_pesanDariDetail(rawDetail), response.status, null);
    }
    return response.blob();
  }

  // Ambil file biner (PDF) TANPA memicu unduhan -- dipakai alur Preview PDF
  // (pdf_preview.js): PDF baru benar-benar diunduh ke perangkat setelah
  // Owner menekan tombol "Download PDF" di halaman preview, bukan otomatis
  // begitu server selesai membuatnya.
  async function fetchBlob(path) {
    return _ambilBlob(path);
  }

  // Picu unduhan sebuah Blob yang SUDAH ADA di memori (tidak fetch apa pun)
  // lewat elemen <a download> sementara -- bekerja sama baiknya di desktop
  // maupun mobile PWA (tidak mengandalkan API khusus platform apa pun).
  // Dipakai downloadFile() di bawah, dan tombol "Download PDF" di halaman
  // Preview PDF (pdf_preview.js, blob-nya sudah didapat dari fetchBlob()
  // saat preview dibuka, jadi TIDAK fetch ulang ke server).
  function saveBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  // Unduh file biner (PDF) lewat GET terautentikasi. Sekarang HANYA dipanggil
  // dari tombol "Download PDF" di halaman Preview PDF (lihat pdf_preview.js)
  // -- bukan lagi dipicu langsung dari tombol "Cetak PDF" tiap halaman
  // (Perbaikan Alur Cetak PDF).
  async function downloadFile(path, filename) {
    saveBlob(await _ambilBlob(path), filename);
  }

  return {
    ApiError,
    get: (path, opts) => request("GET", path, undefined, opts),
    post: (path, body, opts) => request("POST", path, body, opts),
    put: (path, body, opts) => request("PUT", path, body, opts),
    del: (path, body, opts) => request("DELETE", path, body, opts),
    uploadFile,
    fetchBlob,
    saveBlob,
    downloadFile,
  };
})();
