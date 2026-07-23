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
- [ ] Tahap 3 — Login & Hak Akses
- [ ] Tahap 4 — API
- [ ] Tahap 5 — Dashboard
- [ ] Tahap 6 — Input Data
- [ ] Tahap 7 — Rekap
- [ ] Tahap 8 — Produk
- [ ] Tahap 9 — Pengeluaran
- [ ] Tahap 10 — Setting
- [ ] Tahap 11 — Dashboard Barber
- [ ] Tahap 12 — Testing
- [ ] Tahap 13 — Deployment

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
