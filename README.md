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
      Pengeluaran (khusus admin — sejak Tahap 9 datanya diambil langsung
      dari tabel yang sama dipakai CRUD Pengeluaran, bukan lagi terpisah).
- [x] Frontend: SPA hash-router (`js/router.js`) + halaman Login, Dashboard
      Owner, Dashboard Barber, Input Data, Rekap (3 tab). Offline cache
      GET terakhir per endpoint via localStorage (`js/state.js`, `js/api.js`).
- [x] **Tahap 9 — Pengeluaran (CRUD)**: `backend/app/pengeluaran_db.py` +
      `routers/pengeluaran.py` + `frontend/js/pages/pengeluaran.js`.
      Fitur:
      - Tambah / Edit / Hapus pengeluaran, dengan field: Tanggal, Kategori,
        Keterangan, Nominal, Barber (opsional), Status Aktif.
      - Cari (teks bebas di keterangan/kategori), filter tanggal (bulan &
        tahun), dan filter kategori — semua difilter di backend.
      - Kategori berupa teks bebas (bukan daftar tertutup) dengan saran
        otomatis dari kategori yang sudah pernah dipakai + beberapa
        kategori default (Operasional, Sewa, Listrik & Air, Bahan/Chemical,
        Gaji, Lainnya).
      - **Hak akses**: KHUSUS admin (Owner). Barber tidak melihat menunya di
        sidebar, dan kalaupun mencoba membuka `#/pengeluaran` langsung lewat
        URL, router frontend melempar balik ke dashboard. Yang sebenarnya
        menegakkan aturan ini adalah **backend** — semua endpoint
        `/api/pengeluaran/*` memakai dependency `require_admin` (sudah ada
        sejak Tahap 3), jadi request barber ditolak 403 apapun yang
        dikirim dari sisi client.
      - Tabel `pengeluaran` (dibuat di Tahap 2, `database.py`) mendapat 3
        kolom baru (`kategori`, `barber_id`, `aktif`) lewat migrasi
        idempotent di `pengeluaran_migrasi.py` — **`database.py` sendiri
        TIDAK diubah**. Data pengeluaran lama (sebelum Tahap 9) otomatis
        diberi kategori "Lainnya" dan status aktif, tidak ada data yang
        hilang/rusak.
      - Rekap Pengeluaran (Tahap 7) sekarang otomatis menampilkan data yang
        sama dengan CRUD ini (termasuk kategori & nama barber), bukan lagi
        baca terpisah.
- [x] **Tahap 10 — Setting**: `routers/pengaturan.py` +
      `frontend/js/pages/pengaturan.js` (tab: Identitas Barbershop, Komisi &
      Bonus, Barber, Layanan, User, Backup). Semua endpoint KHUSUS admin
      (`require_admin`), kecuali `GET /api/pengaturan/identitas` dan
      `GET /api/pengaturan/logo` yang sengaja publik (halaman Login belum
      punya token tapi tetap perlu menampilkan nama/logo).
      - **Identitas Barbershop**: nama, alamat, WhatsApp, email, Instagram,
        jam operasional — disimpan di tabel `settings` yang SUDAH ADA sejak
        Tahap 2 (key-value generik), jadi tidak perlu tabel baru. Nama & logo
        TIDAK lagi hardcode — dibaca lewat `frontend/js/brand.js` dan otomatis
        diterapkan ke halaman Login + sidebar (elemen `.brand-name`/`.brand-logo`).
      - **Upload Logo**: JPG/PNG/WEBP, disimpan di `backend/app/static/logo/`,
        logo lama otomatis dihapus saat upload logo baru.
      - **Manajemen User**: ganti username & ganti password (password tetap
        di-hash lewat `auth_db.py` yang sudah ada sejak Tahap 3 — tidak pernah
        plain text), nonaktifkan/aktifkan user, tambah user baru.
      - **Manajemen Barber**: pakai `get_barbers`/`add_barber`/`update_barber`
        dari `database.py` (Tahap 2) APA ADANYA. Tambahan Tahap 10 hanya Hapus
        Barber PERMANEN — ditolak otomatis kalau barber itu sudah punya
        transaksi/absensi (arahkan ke Nonaktifkan), supaya histori lama tidak
        pernah rusak.
      - **Manajemen Layanan**: pakai `get_services`/`add_service`/
        `update_service`/`hapus_service` dari `database.py` (Tahap 2) APA
        ADANYA (termasuk aturan "tidak bisa dihapus kalau sudah dipakai
        transaksi" yang sudah ada). Tambahan Tahap 10: field **Modal** per
        layanan lewat kolom baru `services.modal` (migrasi idempotent di
        `pengaturan_migrasi.py`) — kolom ini TIDAK dipakai di manapun pada
        `hitung_komisi_service`, jadi tidak mengubah satu pun hasil komisi.
      - **Pengaturan Komisi & Bonus**: membuka akses edit ke SEMUA key yang
        SUDAH ADA di `database.DEFAULT_SETTINGS` sejak Tahap 2 (persentase
        komisi, potongan modal chemical, uang harian barber/Rafiq, bonus
        kehadiran, target & nominal bonus customer, dst) lewat
        `set_settings_bulk` yang sudah ada — TIDAK ADA rumus yang diubah,
        hanya nilainya jadi bisa diedit tanpa buka kode. Catatan jujur: bonus
        bulanan yang berjalan mendukung SATU target (bukan bertingkat
        85/100/130/150 seperti contoh instruksi) karena mengubahnya jadi
        bertingkat berarti mengubah rumus `hitung_bonus_customer` di Tahap 2 —
        di luar cakupan "jangan ubah logika bisnis" Tahap 10.
      - **Backup Database**: Export (unduh file `.db` yang sedang berjalan)
        dan Import (mengganti database aktif dengan file upload). Import
        SELALU membuat backup file lama dulu (folder `backend/app/backups/`,
        bertimestamp) sebelum menimpa, dan menolak file yang bukan SQLite
        valid.
      - **Validasi**: nama barber/layanan kosong atau duplikat, harga/modal
        negatif — semua ditolak di backend dengan pesan jelas.
      - Dashboard, Login-flow, Input Data, Rekap, Pengeluaran, Produk, dan
        seluruh rumus komisi/bonus di `database.py` **TIDAK disentuh** sama
        sekali oleh Tahap 10.
- [x] **Tahap 11 — Produk (Persediaan)**: `routers/produk.py` +
      `frontend/js/pages/produk.js` sudah ditulis sejak Tahap 10 tapi belum
      dihubungkan (belum ada di `main.py`, belum ada rute frontend, menu
      sidebar masih ditandai "segera") — Tahap 11 menghubungkan semuanya:
      - `backend/app/main.py`: `app.include_router(produk.router)`
        ditambahkan, sehingga seluruh endpoint `/api/produk/*` (daftar
        produk, tambah/ubah nama/nonaktifkan, restock, jual, riwayat mutasi,
        koreksi, hapus mutasi) aktif.
      - `frontend/js/router.js`: rute `#/produk` ditambahkan, dengan
        perlindungan frontend yang sama seperti Pengeluaran/Setting (barber
        yang mencoba buka `#/produk` langsung lewat URL dilempar balik ke
        dashboard) — perlindungan sebenarnya tetap di backend lewat
        `require_admin` yang sudah ada di `routers/produk.py` sejak ditulis.
      - `frontend/js/nav.js`: menu "Produk" dipindah dari daftar "segera" ke
        menu aktif (`roles: ["admin"]`), sehingga hanya tampil untuk Owner.
      - `frontend/index.html`, `frontend/service-worker.js`: `produk.js`
        didaftarkan sebagai script & masuk app-shell cache PWA (cache version
        dinaikkan ke v5 supaya file baru ter-cache di instalasi yang sudah
        ada).
      - **Tidak ada logika bisnis yang diubah** — seluruh perhitungan stok
        (`get_stok_produk`, validasi saldo tidak boleh negatif di
        `jual_produk`/`koreksi_mutasi_produk`/`hapus_mutasi_produk`) berasal
        dari `database.py` (Tahap 2, verbatim) dan dipakai apa adanya.
      - **Hak akses**: KHUSUS Owner (admin), sama seperti Pengeluaran — data
        produk adalah persediaan milik TOKO, bukan milik barber manapun.
        Barber tidak melihat menunya di sidebar, request langsung ke
        `/api/produk/*` ditolak 403 oleh backend, dan navigasi langsung ke
        `#/produk` lewat URL dilempar balik ke dashboard oleh frontend.
      - Diuji end-to-end (lihat bagian Pengujian Tahap 11 di bawah): login
        Owner & Barber, tambah/ubah/nonaktifkan produk, restock, jual
        (termasuk penolakan saat stok tidak cukup), riwayat mutasi +
        filter, koreksi & hapus mutasi (stok terhitung ulang otomatis),
        serta penolakan akses barber di level backend maupun frontend.
- [x] **Tahap 12 — Sinkronisasi Google Sheets & Backup Cloud**:
      `sync_helper.py` (sebelumnya no-op sejak Tahap 1) diisi sungguhan +
      `google_sheets_client.py`, `sync_meta_db.py`, `sync_migrasi.py`,
      `routers/sync.py`, `frontend/js/pages/sinkronisasi.js`. Lihat
      CHANGELOG — Tahap 12 di bawah untuk detail lengkap.
- [ ] Pengujian menyeluruh dengan `uvicorn` yang sebenarnya, di lingkungan
      deploy sungguhan (bukan sandbox pengembangan) — sejak Tahap 11, sandbox
      pengembangan ini TERNYATA sudah bisa menjalankan `pip install` +
      `uvicorn` sungguhan (lihat bagian Pengujian di CHANGELOG Tahap 11/12),
      jadi catatan lama di sini ("tidak ada akses internet untuk pip
      install") sudah tidak berlaku — tapi pengujian di server produksi
      sungguhan (Render/dsb) tetap belum pernah dilakukan.
- [ ] Deployment (render.yaml, vercel.json, runtime.txt, CORS env)

## CHANGELOG — Tahap 10

**Baru:**
- `backend/app/pengaturan_migrasi.py` — migrasi kolom `modal` di `services` +
  seed key identitas di tabel `settings`.
- `backend/app/pengaturan_identitas.py` — baca/tulis identitas barbershop +
  simpan/hapus file logo.
- `backend/app/pengaturan_barber.py` — hapus barber (dengan cek riwayat) +
  validasi ramah untuk fungsi Tahap 2 yang sudah ada.
- `backend/app/pengaturan_service.py` — field Modal + validasi ramah untuk
  fungsi Tahap 2 yang sudah ada.
- `backend/app/pengaturan_user.py` — ganti username + aktifkan kembali user.
- `backend/app/pengaturan_backup.py` — export/import database dengan backup
  otomatis sebelum menimpa.
- `backend/app/routers/pengaturan.py` — seluruh endpoint `/api/pengaturan/*`.
- `frontend/js/brand.js` — modul identitas barbershop dipakai lintas halaman.
- `frontend/js/pages/pengaturan.js` — halaman Setting (6 tab).

**Diedit minimal:**
- `backend/app/main.py` — daftar router baru + panggil migrasi saat startup.
- `frontend/js/nav.js` — aktifkan menu Setting (khusus admin) + brand dinamis.
- `frontend/js/router.js` — rute `#/pengaturan` (khusus admin) + refresh brand
  di setiap navigasi.
- `frontend/js/pages/login.js` — nama/logo dinamis, tidak hardcode lagi.
- `frontend/js/api.js` — tambah `uploadFile()` untuk upload logo/backup.
- `frontend/js/app.js` — panggil `MugenBrand.refresh()` sekali di awal.
- `frontend/index.html`, `frontend/service-worker.js` — daftarkan file baru.

**Tidak disentuh sama sekali:** `database.py`, `auth_db.py` (hanya dipakai,
tidak diubah), serta seluruh Tahap 1–9 (Dashboard, Login, Input Data, Rekap,
Pengeluaran).

## CHANGELOG — Tahap 11

**Diedit minimal (menghubungkan file yang sudah ditulis di Tahap 10):**
- `backend/app/main.py` — import + `app.include_router(produk.router)`,
  komentar diperbarui.
- `backend/app/routers/produk.py` — komentar header diperbarui (kode
  endpoint tidak diubah sama sekali).
- `frontend/js/pages/produk.js` — komentar header diperbarui (kode halaman
  tidak diubah sama sekali).
- `frontend/js/router.js` — rute `#/produk` (khusus admin, pola sama persis
  dengan `#/pengeluaran`/`#/pengaturan`).
- `frontend/js/nav.js` — menu "Produk" dipindah dari `MENU_SEGERA` ke `MENU`
  aktif (`roles: ["admin"]`).
- `frontend/index.html` — tambah `<script src="js/pages/produk.js">`.
- `frontend/service-worker.js` — tambah `produk.js` ke `APP_SHELL`, naikkan
  `CACHE_NAME` ke `v5`.
- `README.md` — dokumentasi ini.

**Bug yang diperbaiki (di luar kode Tahap 11, ditemukan saat audit):**
- `backend/requirements.txt` — `passlib[bcrypt]>=1.7.4` tanpa batas atas
  membuat pip menginstal `bcrypt` versi terbaru (5.x), yang **tidak
  kompatibel** dengan `passlib` 1.7.4 (proyek `passlib` sudah tidak
  dikembangkan lagi) — backend gagal start sama sekali (`ValueError:
  password cannot be longer than 72 bytes`) saat `auth_db.py` memanggil
  `CryptContext(schemes=["bcrypt"])` pertama kali. Diperbaiki dengan
  mengunci `bcrypt<4.0` di `requirements.txt`. Ini murni batasan versi
  dependency, **bukan perubahan logika bisnis** — hash password tetap bcrypt
  seperti sebelumnya, hanya sekarang instalasi `pip install -r
  requirements.txt` benar-benar bisa jalan.

**Tidak disentuh sama sekali:** `database.py`, `auth_db.py`, seluruh Tahap
1–10 (Dashboard, Login, Input Data, Rekap, Pengeluaran, Setting) — halaman
`produk.js` dan router `produk.py` itu sendiri sudah selesai ditulis sejak
Tahap 10 dan isinya tidak diubah, Tahap 11 hanya menghubungkannya.

### Pengujian Tahap 11

Diuji langsung lewat backend berjalan (`uvicorn`) + browser (Playwright),
memakai database SQLite kosong (bootstrap admin baru):

1. **Backend nyala tanpa error** setelah `produk.router` dipasang, endpoint
   `/api/health` normal.
2. **Login Owner** → `GET /api/produk` awalnya `[]`, `POST /api/produk`
   (tambah "Pomade") berhasil, muncul di daftar dengan `stok: 0`.
3. **Restock** 10 lalu **Jual** 3 → stok terhitung benar (7). **Jual**
   melebihi stok (999) ditolak `422` dengan pesan jelas dari
   `database.py` (`jual_produk`), stok tidak berubah.
4. **Koreksi mutasi** (ubah jumlah jual dari 3 → 5) → stok otomatis
   terhitung ulang (10 → 5). **Hapus mutasi** itu → stok kembali ke 10.
   Riwayat mutasi terurut tanggal terbaru dulu, filter tahun/bulan/tipe/
   produk berfungsi.
5. **Akun Barber** (dibuat lewat `/api/pengaturan/user`) mencoba semua
   endpoint `/api/produk/*` (GET, POST tambah, POST restock) → **ditolak
   403** ("Khusus Owner (admin).") di setiap kasus. Endpoint dashboard
   barber sendiri (`/api/dashboard/barber`) tetap normal (kontrol positif —
   memastikan 403 di atas memang soal role, bukan token rusak).
6. **Regresi Tahap 1–10**: `dashboard/owner`, `dashboard/barber` (403 untuk
   barber), `pengeluaran` (403 untuk barber), `pengaturan/identitas`
   (publik), `input-data/services`, `rekap/transaksi` — semua masih
   merespons `200`/`403` sesuai perannya masing-masing, tidak ada regresi.
7. **UI end-to-end** (Playwright, Chromium headless): login Owner → menu
   sidebar menampilkan "Produk" (bukan lagi "(segera)") → buka halaman →
   tambah produk baru lewat form → toast sukses → klik "Restock" pada
   baris produk → isi form → simpan → toast sukses → tabel daftar produk
   & riwayat mutasi ter-update otomatis tanpa reload manual. Login Barber
   → menu sidebar **tidak** menampilkan Produk/Pengeluaran/Setting sama
   sekali → navigasi paksa ke `#/produk` lewat address bar otomatis
   dilempar balik ke `#/dashboard`.
8. `python3 -m py_compile` untuk seluruh file backend yang disentuh, dan
   `node --check` untuk seluruh file frontend yang disentuh — tidak ada
   syntax error.

## CHANGELOG — Tahap 12

**Tujuan**: sinkronisasi cloud (Google Sheets) + status sinkron yang
terlihat, tanpa mengubah satu pun logika bisnis atau fitur Tahap 1–11.

### Cara kerja

`sync_async()` dipanggil di titik yang **sudah ada sejak Tahap 6/9/11**
(setelah simpan/koreksi/hapus di Input Data, Pengeluaran, dan Produk) —
**tidak ada satu baris pun** yang ditambah/diubah di `routers/input_data.py`,
`routers/pengeluaran.py`, atau `routers/produk.py` untuk Tahap 12 ini (lihat
`git diff --stat`, ketiga file itu tidak muncul). Sebelumnya `sync_async()`
adalah no-op; sekarang:

1. **Simpan lokal SELALU jalan lebih dulu** dan SELALU berhasil terlepas
   dari apa pun yang terjadi pada langkah sinkron — `sync_async()` dipanggil
   SETELAH baris `db.tambah_transaksi(...)` dkk selesai, dan seluruh isi
   `sync_async()` dibungkus try/except sehingga **tidak pernah** melempar
   error balik ke request API pemanggil.
2. Setiap panggilan menaikkan `write_counter` (tabel baru `sync_meta`,
   terpisah dari `database.py`) — inilah dasar hitungan **"jumlah data
   belum sinkron"** (`write_counter - synced_counter`, dari sisi status
   selalu ≥ 0).
3. Percobaan kirim ke Google Sheets berjalan di **background thread**
   (`threading.Thread(daemon=True)`) supaya request penyimpanan (`POST
   /api/input-data/transaksi` dsb) tidak ikut menunggu proses upload yang
   bisa lambat.
4. Kalau Google Sheets **belum dikonfigurasi** (`GOOGLE_SHEET_ID` /
   kredensial service account belum diisi) **atau** sedang tidak bisa
   dihubungi (offline, quota, dll) — percobaan itu gagal dengan aman: status
   dicatat `"gagal"` + pesan errornya, `synced_counter` TIDAK naik, data
   tetap 100% aman di SQLite lokal seperti sebelum Tahap 12 ada.
5. **Retry otomatis berkala**: satu thread background lain (mulai jalan
   sekali saat startup lewat `sync_helper.start_background_retry_loop()`)
   memeriksa tiap `SYNC_RETRY_INTERVAL_DETIK` (default 60 detik, bisa
   diubah lewat environment variable) — kalau ada data belum sinkron, coba
   kirim lagi. Ini yang memenuhi "saat koneksi kembali normal, data yang
   belum tersinkron dikirim otomatis" tanpa perlu user membuka halaman
   apa pun.
6. **Sinkron ulang penuh, bukan diff per baris**: setiap kali sinkron
   berhasil, SELURUH isi 5 tabel (`transaksi`, `absensi_libur`,
   `pengeluaran`, `produk`, `produk_mutasi`) dibaca ulang lewat fungsi baca
   yang **sudah ada** (`db.get_transaksi_list()`, `db.get_libur_list()`,
   `pengeluaran_db.get_pengeluaran_list()`, `db.get_produk_list()`,
   `db.get_mutasi_produk_list()` — semua read-only, tidak ada satu query
   tulis pun yang ditambah ke `database.py`) lalu MENIMPA PENUH tab Google
   Sheets yang bersangkutan. Ini sengaja dipilih dibanding sinkron per-baris
   supaya data yang **dihapus** di lokal (mis. hapus transaksi/mutasi
   produk) otomatis ikut hilang dari Sheets juga, tanpa perlu logika hapus
   terpisah yang bisa meleset.

### Konfigurasi (diisi saat deploy, TIDAK ikut git)

- `GOOGLE_SHEET_ID` — ID spreadsheet tujuan (bagian di URL spreadsheet).
- Kredensial service account, salah satu dari:
  - `GOOGLE_CREDENTIALS_JSON` (environment variable, isi mentah file JSON
    service account — cocok untuk Render/dsb tanpa upload file), atau
  - file `backend/app/credentials.json` (sudah disebut sejak README
    Tahap 1, di-gitignore, harus di-copy manual saat deploy).
- `SYNC_RETRY_INTERVAL_DETIK` (opsional, default `60`) — jeda antar
  percobaan retry otomatis.

Kalau `GOOGLE_SHEET_ID`/kredensial belum diisi, aplikasi tetap berjalan
normal 100% (semua fitur Tahap 1–11 tidak terpengaruh) — hanya halaman
Sinkronisasi yang menampilkan status "belum dikonfigurasi" dan data
menumpuk sebagai "belum sinkron" sampai dikonfigurasi.

### Baru

- `backend/app/sync_migrasi.py` — migrasi idempotent: tabel `sync_meta`
  (key-value status sinkron, TIDAK menyimpan data bisnis apa pun).
- `backend/app/sync_meta_db.py` — baca/tulis `sync_meta` (write_counter,
  synced_counter, last_sync_at, last_sync_status, last_sync_message).
- `backend/app/google_sheets_client.py` — klien tipis gspread + google-auth
  (`is_configured()`, `push_snapshot(entity, rows)`), dipakai HANYA oleh
  `sync_helper.py`.
- `backend/app/routers/sync.py` — `/api/sync/status` (GET) & `/api/sync/sekarang`
  (POST), KHUSUS admin (`require_admin`, pola sama seperti Pengeluaran/
  Produk/Setting).
- `frontend/js/pages/sinkronisasi.js` — halaman "Sinkronisasi": kartu status
  (jumlah belum sinkron, waktu sinkron terakhir, status berhasil/gagal +
  pesan error), tombol **Sinkronkan Sekarang**, dan menu **Backup
  Database**/**Restore Database** (lihat bawah — memanggil endpoint lama).

### Diedit minimal

- `backend/app/sync_helper.py` — dari no-op menjadi implementasi sungguhan
  (lihat "Cara kerja" di atas). Ini SATU-SATUNYA file "logika sinkron" yang
  diedit; tanda tangan fungsi `sync_async()` (nama, tanpa parameter) TIDAK
  berubah, jadi seluruh pemanggilnya (Tahap 6/9/11) tidak perlu disentuh.
- `backend/app/main.py` — import + `app.include_router(sync.router)`,
  panggil `migrasi_sync()` & `sync_helper.start_background_retry_loop()`
  saat startup.
- `frontend/js/nav.js` — menu "Sinkronisasi" (khusus admin).
- `frontend/js/router.js` — rute `#/sinkronisasi` (khusus admin, pola sama
  persis dengan `#/pengeluaran`/`#/produk`/`#/pengaturan`).
- `frontend/index.html`, `frontend/service-worker.js` — daftarkan
  `sinkronisasi.js`, naikkan cache PWA ke v6.
- `frontend/css/style.css` — 2 baris CSS baru (`.badge-success`,
  `.badge-danger`) untuk badge status di halaman Sinkronisasi — murni
  penambahan class baru, tidak ada satu pun rule/class yang sudah ada
  diubah.
- `README.md` — dokumentasi ini.

### Menu Backup Database & Restore Database

**Tidak dibuat ulang dari nol** — endpoint `/api/pengaturan/backup/export`
& `/api/pengaturan/backup/import` sudah ada sejak Tahap 10
(`routers/pengaturan.py`, `pengaturan_backup.py`) dan **TIDAK disentuh sama
sekali** di Tahap 12 (0 baris diubah — lihat `git diff --stat`). Yang baru
di Tahap 12 hanyalah **menu/tombol tambahan** di halaman Sinkronisasi yang
memanggil endpoint yang SAMA PERSIS itu, supaya Backup/Restore juga bisa
diakses dari halaman ini tanpa harus pindah ke Setting. Tab Backup yang
sudah ada di halaman Setting (Tahap 10) tetap ada dan tetap berfungsi
seperti sebelumnya, tidak dihapus.

### Tidak disentuh sama sekali

`database.py`, `auth.py`, `auth_db.py`, `routers/input_data.py`,
`routers/pengeluaran.py`, `routers/produk.py`, `routers/pengaturan.py`,
`pengaturan_backup.py`, dan seluruh frontend Tahap 1–11 (Dashboard, Login,
Input Data, Rekap, Pengeluaran, Produk, Setting) — **0 baris diubah** di
semua file itu (diverifikasi lewat `git diff --stat`, lihat daftar file di
laporan commit). Komisi, bonus, absensi, rekap, produk, dan pengeluaran
tetap dihitung 100% oleh fungsi yang sama di `database.py`/`pengeluaran_db.py`
seperti sebelum Tahap 12 ada.

### Bug yang diperbaiki

Tidak ada bug baru ditemukan di kode Tahap 1–11 selama audit Tahap 12 ini
(sudah diaudit tuntas di Tahap 11 sebelumnya). `bcrypt<4.0` dari Tahap 11
tetap berlaku dan tetap perlu (diverifikasi ulang: instalasi bersih dari
`requirements.txt` di sandbox pengujian Tahap 12 berhasil tanpa masalah).

### Pengujian Tahap 12

Diuji lewat backend berjalan sungguhan (`uvicorn`, instalasi bersih dari
`requirements.txt` termasuk `gspread`/`google-auth`) + browser (Playwright),
memakai database SQLite kosong (bootstrap admin baru). Google Sheets
SUNGGUHAN tidak tersedia di sandbox ini (tidak ada kredensial asli/akses
internet ke Google API) — jalur "belum dikonfigurasi" diuji langsung
terhadap server sungguhan, dan jalur "berhasil sinkron ke Sheets" diuji
lewat dependency-injection (mengganti `google_sheets_client.is_configured`/
`push_snapshot` dengan versi tiruan di proses Python terpisah yang
mengakses database yang sama) untuk memverifikasi seluruh pipeline
(snapshot 5 tabel → kirim → tandai `synced_counter`) berjalan benar tanpa
menyentuh kode aslinya sama sekali:

1. **Simpan data saat online** (baca: Google Sheets berhasil dikonfigurasi
   & dapat dihubungi, disimulasikan lewat dependency-injection di atas) —
   `sync_now()` membaca snapshot dari 5 tabel dengan benar (termasuk field
   hasil hitung seperti `total_komisi`), mengirimkannya, lalu
   `jumlah_belum_sinkron` turun ke 0 dan status jadi `"berhasil"`.
2. **Simpan data saat offline** (disimulasikan: Google Sheets belum
   dikonfigurasi, kondisi paling realistis untuk sandbox ini dan secara
   fungsional identik dari sudut pandang aplikasi — sama-sama "tidak bisa
   kirim ke cloud sekarang") — `POST /api/input-data/transaksi` tetap balas
   `200` dengan data transaksi lengkap (komisi Dry Cut `35000` → `14000`,
   sesuai rumus yang sudah ada, tidak berubah); `GET /api/sync/status`
   langsung menunjukkan `jumlah_belum_sinkron: 1`, `last_sync_status:
   "gagal"`, dengan pesan jelas — data tidak pernah hilang.
3. **Sinkron ulang setelah online**: `POST /api/sync/sekarang` (tombol
   "Sinkronkan Sekarang") dipanggil pada server yang masih belum
   dikonfigurasi → tetap balas `200` dengan status `"gagal"` (bukan error
   500) — membuktikan endpoint ini aman dipanggil kapan pun. Loop retry
   otomatis latar belakang (`SYNC_RETRY_INTERVAL_DETIK=5` saat pengujian)
   dibiarkan berjalan beberapa siklus tanpa membuat server crash atau
   macet.
4. **Backup Database**: `GET /api/pengaturan/backup/export` mengunduh file
   `.db` valid (diverifikasi lewat signature SQLite `SQLite 3.x database`).
5. **Restore Database**: file hasil export di atas di-upload ulang lewat
   `POST /api/pengaturan/backup/import` → berhasil, backup otomatis dibuat
   dulu sebelum menimpa, dan data (mis. produk yang sudah ditambah)
   terverifikasi tetap ada persis sama setelah restore.
6. **Login Owner** & **Login Barber**: keduanya berhasil, role & data
   masing-masing benar (`GET /api/dashboard/owner` vs
   `/api/dashboard/barber`).
7. **Hak akses `/api/sync/*`**: barber ditolak `403` di `GET /status` dan
   `POST /sekarang`; request tanpa token ditolak `401`.
8. **Rekap**: `/api/rekap/transaksi` dan `/api/rekap/pengeluaran` tetap
   mengembalikan data yang benar setelah Tahap 12 terpasang.
9. **Produk**: tambah produk + daftar produk tetap berfungsi normal.
10. **Pengeluaran**: tambah pengeluaran + daftar pengeluaran tetap
    berfungsi normal.
11. **Pengaturan**: `/api/pengaturan/identitas` (publik) dan
    `/api/pengaturan/komisi` (admin) tetap merespons benar — nilai komisi
    (persentase, potongan modal, dst) tidak berubah sedikit pun.
12. **UI end-to-end** (Playwright, Chromium headless): login Owner → menu
    sidebar menampilkan "Sinkronisasi" → halaman menampilkan status yang
    benar + banner "belum dikonfigurasi" → klik "Sinkronkan Sekarang" →
    toast error yang jelas + status ter-refresh. Login Barber → menu
    "Sinkronisasi" **tidak** muncul di sidebar sama sekali → navigasi paksa
    ke `#/sinkronisasi` lewat address bar otomatis dilempar balik ke
    `#/dashboard`.
13. `python3 -m py_compile` untuk seluruh file backend yang disentuh/baru,
    dan `node --check` untuk seluruh file frontend yang disentuh/baru —
    tidak ada syntax error.
14. `git diff --stat` dari base `master` (setelah Tahap 11 merge)
    dikonfirmasi **tidak menyertakan** `database.py`, `auth.py`,
    `auth_db.py`, `routers/input_data.py`, `routers/pengeluaran.py`,
    `routers/produk.py`, `routers/pengaturan.py`, `pengaturan_backup.py`,
    ataupun file frontend Tahap 1–11 manapun — bukti langsung bahwa Tahap
    12 tidak mengubah fitur-fitur itu.


## Struktur Project

```
mugen-hair-pwa/
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py                 # entry point FastAPI
│       ├── database.py             # SALINAN VERBATIM dari app Desktop — jangan diubah
│       ├── auth_db.py              # tabel & fungsi login (terpisah dari database.py)
│       ├── pengeluaran_db.py       # TAHAP 9: CRUD Pengeluaran (terpisah dari database.py)
│       ├── pengeluaran_migrasi.py  # TAHAP 9: migrasi kolom baru tabel pengeluaran (idempotent)
│       ├── pengaturan_migrasi.py   # TAHAP 10: migrasi kolom modal + seed setting identitas
│       ├── pengaturan_identitas.py # TAHAP 10: identitas barbershop + logo
│       ├── pengaturan_barber.py    # TAHAP 10: hapus barber (dgn cek riwayat) + validasi
│       ├── pengaturan_service.py   # TAHAP 10: field Modal + validasi layanan
│       ├── pengaturan_user.py      # TAHAP 10: ganti username + aktifkan user
│       ├── pengaturan_backup.py    # TAHAP 10: export/import database
│       ├── sync_migrasi.py         # TAHAP 12: migrasi tabel sync_meta (idempotent)
│       ├── sync_meta_db.py         # TAHAP 12: baca/tulis status sinkron (sync_meta)
│       ├── google_sheets_client.py # TAHAP 12: klien gspread, dipakai HANYA oleh sync_helper.py
│       ├── sync_helper.py          # TAHAP 12: isi sungguhan sync_async()/sync_now() (sebelumnya no-op)
│       ├── static/logo/            # TAHAP 10: file logo barbershop yang diupload
│       ├── backups/                # TAHAP 10: backup otomatis sebelum import database
│       ├── routers/pengeluaran.py  # TAHAP 9: /api/pengeluaran/* — khusus admin
│       ├── routers/pengaturan.py   # TAHAP 10: /api/pengaturan/* — khusus admin (kec. identitas & logo)
│       ├── routers/produk.py       # TAHAP 8/11: /api/produk/* — khusus admin
│       ├── routers/sync.py         # TAHAP 12: /api/sync/* — khusus admin
│       └── mugen_hair.db           # database (TIDAK ikut git — lihat bagian Deployment)
└── frontend/
    ├── index.html
    ├── manifest.json        # PWA manifest
    ├── service-worker.js
    ├── css/style.css        # palet warna sama dengan ui_theme.py (Dark Mode)
    └── js/
        ├── app.js
        ├── brand.js              # TAHAP 10: identitas barbershop lintas halaman
        └── pages/
            ├── pengeluaran.js    # TAHAP 9: halaman CRUD Pengeluaran (khusus admin)
            ├── pengaturan.js     # TAHAP 10: halaman Setting (khusus admin)
            ├── produk.js         # TAHAP 8/11: halaman Produk (khusus admin)
            └── sinkronisasi.js   # TAHAP 12: halaman Status Sinkronisasi + Backup/Restore (khusus admin)
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
