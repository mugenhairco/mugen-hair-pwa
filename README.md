# MUGEN Hair Co. — PWA

Progressive Web App dari aplikasi Python Desktop MUGEN Hair Co. **Aplikasi
Python Desktop adalah satu-satunya acuan** — seluruh logika bisnis, alur
kerja, hasil perhitungan, dan struktur menu HARUS identik. PWA ini hanya
berbeda platform (Desktop → web/installable app), bukan produk baru.

## Status Pengerjaan (bertahap, sesuai rencana 13 tahap)

- [x] **Tahap 1 — Struktur Project**: folder `backend/` (FastAPI) & `frontend/`
      (HTML/CSS/JS + PWA shell) sudah dibuat.
- [x] **Tahap 2 — Database**: `backend/app/database.py` adalah salinan
      **VERBATIM** (byte-identik, diverifikasi lewat `diff`) dari `database.py`
      di aplikasi Desktop — TIDAK ADA satu baris pun yang diubah, supaya semua
      rumus (komisi, chemical, bonus, uang harian, dst) dijamin identik.
      Tabel `users` untuk login ditambahkan lewat file **terpisah**
      (`auth_db.py`), supaya `database.py` tetap murni tidak tersentuh.
- [x] **Tahap 3 — Login & Hak Akses**: `backend/app/auth.py` (token via
      itsdangerous, dependency `get_current_user` / `require_admin` /
      `require_barber`), `routers/auth_router.py` (`POST /api/auth/login`,
      `GET /api/auth/me`), plus bootstrap akun admin pertama otomatis saat
      startup (dari env var `ADMIN_BOOTSTRAP_USERNAME`/`_PASSWORD`).
- [x] **Tahap 4-5 — API & Dashboard**: `routers/dashboard.py` —
      `/api/dashboard/owner` (semua barber, khusus admin) dan
      `/api/dashboard/barber` (data sendiri saja, barber_id dipaksa dari akun
      login, bukan dari parameter request).
- [x] **Tahap 6 — Input Data**: `routers/input_data.py` — services, daftar
      barber, preview total, CRUD transaksi (simpan/koreksi/hapus), tandai/
      batalkan libur. Barber hanya bisa mengakses transaksi miliknya sendiri
      (divalidasi di backend, bukan cuma disembunyikan di frontend).
- [x] **Tahap 7 — Rekap**: `routers/rekap.py` — Rekap Transaksi, Rekap
      Bulanan (dibatasi ke barber sendiri untuk role barber), Rekap
      Pengeluaran (khusus admin, baca saja — CRUD pengeluaran menyusul).
- [x] Frontend: SPA hash-router (`js/router.js`) + halaman Login, Dashboard
      Owner, Dashboard Barber, Input Data, Rekap (3 tab). Offline cache
      GET terakhir per endpoint via localStorage (`js/state.js`, `js/api.js`).
- [ ] Tahap 8 — Produk (belum ada router/halaman)
- [ ] Tahap 9 — Pengeluaran: CRUD (baru Rekap/baca yang ada)
- [ ] Tahap 10 — Setting (aturan bisnis, kelola barber/service/akun user)
- [ ] Sinkronisasi Google Sheets: `sync_helper.sync_async()` masih **no-op**
      (placeholder) — `sync.py` dari aplikasi Desktop belum disalin ke repo
      ini, jadi belum ada isinya untuk dipanggil. Lihat komentar TODO di
      `backend/app/sync_helper.py`.
- [ ] Tahap 12 — Testing dengan `uvicorn` (belum bisa dijalankan di sandbox
      pengembangan ini karena tidak ada akses internet untuk `pip install`)
- [ ] Tahap 13 — Deployment (render.yaml, vercel.json, runtime.txt, CORS env)

## Struktur Project

```
mugen-hair-pwa/
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py         # entry point FastAPI
│       ├── database.py     # SALINAN VERBATIM dari app Desktop — jangan diubah
│       ├── auth_db.py       # tabel & fungsi login (terpisah dari database.py)
│       └── mugen_hair.db   # database (TIDAK ikut git — lihat bagian Deployment)
└── frontend/
    ├── index.html
    ├── manifest.json        # PWA manifest
    ├── service-worker.js
    ├── css/style.css        # palet warna sama dengan ui_theme.py (Dark Mode)
    └── js/app.js
```

## Menjalankan di Lokal (development)

```bash
cd backend
pip install -r requirements.txt
cd app
uvicorn main:app --reload --port 8000
```

Buka `http://localhost:8000/api/health` — harus muncul `{"status":"ok"}`.

Frontend (Tahap 1, masih shell kosong) bisa dibuka langsung dari
`frontend/index.html`, atau nanti di-serve oleh FastAPI di tahap lanjut.

## Database & Kredensial — TIDAK ikut ke Git

`mugen_hair.db` dan `credentials.json` **sengaja tidak di-commit** (lihat
`.gitignore`) — karena isinya data asli toko / kredensial rahasia. Saat
deploy ke server:

1. Push kode ini ke GitHub seperti biasa (`git push`).
2. Di server, **copy manual** `mugen_hair.db` (dari aplikasi Desktop Anda,
   supaya semua data lama ikut terbawa) ke `backend/app/mugen_hair.db`.
3. Kalau memakai sinkronisasi Google Sheets, copy juga `credentials.json` ke
   `backend/app/credentials.json`.

## Catatan Penting

- `database.py` di folder ini **tidak boleh diedit** kecuali memang ada
  perubahan logika bisnis yang diminta eksplisit — dan kalau itu terjadi,
  perubahan yang sama juga harus diterapkan ke aplikasi Python Desktop supaya
  keduanya tetap identik.
- Setiap tahap diuji dan dibandingkan hasilnya dengan aplikasi Desktop
  sebelum lanjut ke tahap berikutnya.
