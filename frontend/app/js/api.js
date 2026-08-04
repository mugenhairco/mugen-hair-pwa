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
      const detail = payload && payload.detail ? payload.detail : "Terjadi kesalahan pada server.";
      throw new ApiError(detail, response.status, payload);
    }

    if (method === "GET" && useCache) {
      MugenState.cacheSet(cacheKey, payload);
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
      const detail = payload && payload.detail ? payload.detail : "Terjadi kesalahan pada server.";
      throw new ApiError(detail, response.status, payload);
    }
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
      let detail = "Terjadi kesalahan pada server.";
      try { detail = (await response.json()).detail || detail; } catch (e) { /* body bukan JSON */ }
      throw new ApiError(detail, response.status, null);
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
