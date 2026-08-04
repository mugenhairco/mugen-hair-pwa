# MUGEN Hair Co. — PWA

Progressive Web App dari aplikasi Python Desktop MUGEN Hair Co. **Aplikasi
Python Desktop adalah satu-satunya acuan** — seluruh logika bisnis, alur
kerja, hasil perhitungan, dan struktur menu HARUS identik. PWA ini hanya
berbeda platform (Desktop → web/installable app), bukan produk baru.

## Status Pengerjaan (bertahap, sesuai rencana 13 tahap) — v1.0 Final Release

Seluruh 13 tahap telah selesai. Aplikasi ini sudah dalam status **v1.0,
siap dipakai sebagai versi produksi** — deployment sungguhan ke server
(bagian **Deployment (Produksi)** di bawah) adalah satu-satunya langkah
yang tersisa dan bergantung pada platform hosting yang dipilih, di luar
kendali sandbox pengembangan ini.

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
- [x] **Tahap 13 — Final Release (v1.0)**: audit menyeluruh, bersih-bersih
      kode tak terpakai, perbaikan bug (termasuk 2 bug nyata di alur
      offline-cache & mobile navigation — lihat CHANGELOG Tahap 13), ikon
      PWA lengkap (sebelumnya tidak ada sama sekali), dokumentasi instalasi/
      deployment/backup/restore/sinkronisasi yang lengkap. Lihat CHANGELOG —
      Tahap 13 di bawah untuk detail lengkap. **Tidak ada fitur baru** dan
      **tidak ada perubahan logika bisnis** — murni pemantapan untuk rilis
      v1.0.
- [ ] Deployment sungguhan ke server produksi (Render/Railway/VPS/dsb) —
      panduannya sudah ditulis lengkap (lihat bagian **Deployment (Produksi)**
      di bawah), tapi belum pernah benar-benar dieksekusi ke server
      sungguhan dari sandbox pengembangan ini (tidak ada akses ke platform
      hosting eksternal dari sini). File konfigurasi spesifik-platform
      (`render.yaml`/dsb) sengaja tidak dibuat karena platform hosting akhir
      belum ditentukan — instruksi generik di bawah berlaku untuk platform
      mana pun yang bisa menjalankan ASGI Python + hosting statis.

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

## CHANGELOG — Tahap 13 (Final Release v1.0)

Tahap terakhir: audit menyeluruh, bersih-bersih, perbaikan bug, kelengkapan
PWA, dan dokumentasi — **tanpa fitur baru dan tanpa perubahan logika
bisnis**. `database.py` dan seluruh rumus komisi/bonus/absensi TIDAK
disentuh sama sekali (0 baris) — sama seperti Tahap 12.

### Audit yang dilakukan

- Baca ulang seluruh file backend (22 file `.py`) dan frontend (19 file
  `.js`) satu per satu.
- Cek import tak terpakai secara otomatis (skrip AST Python) di seluruh
  modul backend.
- Cek setiap endpoint API (35+ endpoint di 9 router) benar-benar memakai
  dependency otorisasi (`Depends(get_current_user)` / `require_admin` /
  `require_barber`) — tidak ada satu pun endpoint bisnis yang tanpa
  proteksi (hanya `/api/health`, `/api/auth/login`, `GET
  /api/pengaturan/identitas`, dan `GET /api/pengaturan/logo` yang memang
  sengaja publik, dan itu pun tidak membocorkan data bisnis apa pun).
- Cek folder struktur — diputuskan **TIDAK** melakukan reorganisasi besar
  (mis. memecah `backend/app/*.py` yang flat jadi sub-package) karena
  risiko regresi (harus mengubah banyak baris `import` di banyak file)
  tidak sebanding manfaatnya untuk rilis final — struktur flat saat ini
  konsisten dengan pola aplikasi Desktop asal dan sudah rapi lewat
  penamaan `pengaturan_*`/`pengeluaran_*`/`sync_*` + folder `routers/`.
  Perubahan struktur yang dilakukan: tambah folder `frontend/icons/` (baru,
  lihat bagian Bug di bawah).
- Uji responsif di 3 lebar layar (1440px desktop, 820px tablet, 390px HP)
  + uji mode offline + uji instalabilitas PWA (lihat bagian Pengujian).

### Bug yang diperbaiki

1. **[Kritis] Ikon PWA tidak pernah ada sama sekali.** `manifest.json` dan
   `index.html` sejak Tahap 1 sudah menunjuk ke `icons/icon-192.png` dan
   `icons/icon-512.png`, tapi folder `frontend/icons/` tidak pernah dibuat
   — aplikasi tidak bisa di-install dengan benar sebagai PWA di banyak
   browser/OS (ikon rusak/hilang di homescreen, splash screen kosong).
   Diperbaiki: dibuat set ikon lengkap (72–512px, 2 varian maskable untuk
   Android adaptive icon, apple-touch-icon, favicon.ico multi-resolusi),
   `manifest.json` diperbarui dengan seluruh ukuran + `purpose`, dan
   `index.html` mendapat tag `apple-touch-icon`/`apple-mobile-web-app-*`
   supaya Safari iOS 15+ bisa membuat splash screen otomatis dari ikon +
   `background_color` manifest.
2. **[Signifikan] Sidebar tidak bisa dibuka sama sekali di tablet/HP.**
   CSS `.hamburger`/`.sidebar.open` sudah ada sejak awal (media query
   `max-width: 820px` menyembunyikan sidebar di luar layar), tapi tidak
   pernah ada elemen `<button class="hamburger">` ataupun JS yang
   menambahkan/menghapus class `.open` — di layar ≤820px (semua tablet
   portrait & HP), menu navigasi benar-benar tidak bisa diakses. Diperbaiki
   di `router.js` (`shell()`): tombol hamburger + backdrop ditambahkan,
   dengan auto-close saat memilih menu atau tap area gelap di luar sidebar.
3. **[Signifikan] Cache offline untuk data berbentuk ARRAY selalu tampil
   kosong.** `api.js` menyimpan fallback offline dengan
   `{...cached.data, __offline:true}` — kalau `cached.data` berupa array
   (services, daftar transaksi, daftar produk, daftar pengeluaran, riwayat
   mutasi, rekap, dst — hampir semua endpoint GET di aplikasi ini), hasil
   spread jadi PLAIN OBJECT (key `"0"`,`"1"`,...), BUKAN array lagi.
   Setiap halaman yang mengecek `Array.isArray(data)` sebelum menampilkan
   isinya (pola yang dipakai konsisten di semua halaman) jadi selalu jatuh
   ke cabang kosong `[]` saat offline — walau data SUDAH tersimpan benar
   di cache. Efeknya: mode offline PWA terlihat seolah "tidak ada data"
   padahal sebenarnya cache-nya ada. Diperbaiki: kalau `cached.data` adalah
   array, tandai `__offline`/`__cachedAt` langsung di object array itu
   sendiri (array tetap array, `Array.isArray()` tetap `true`) alih-alih
   men-spread ke object baru. Diverifikasi lewat Playwright dengan
   mensimulasikan mode offline sungguhan (`context.set_offline(True)`) —
   sebelum fix: 0 baris tampil; sesudah fix: seluruh baris yang sudah
   di-cache tampil normal lengkap dengan banner "Sedang offline".
4. **[Minor] Login bisa "diam" tanpa pindah ke Dashboard.** Di
   `login.js`, setelah login sukses kode hanya melakukan
   `location.hash = "#/dashboard"`. Kalau hash URL kebetulan SUDAH persis
   `"#/dashboard"` (skenario nyata: reload/buka bookmark `#/dashboard`
   setelah sesi login kedaluwarsa), browser TIDAK memicu event
   `hashchange` untuk perubahan ke nilai yang sama — router tidak pernah
   dipanggil ulang, halaman Login tetap tertampil walau login sebenarnya
   berhasil (token sudah tersimpan). Diperbaiki: panggil
   `MugenRouter.handle()` langsung setelah set hash, tidak bergantung pada
   event `hashchange` saja.
5. **[Minor] Import tak terpakai** di `routers/dashboard.py`
   (`get_current_user` diimpor tapi kedua endpoint memakai
   `require_admin`/`require_barber` langsung) — dihapus, murni
   pembersihan, tidak mengubah perilaku apa pun.
6. **[Kosmetik] Toast notifikasi bisa meluber di layar sangat sempit** —
   `.toast` tidak punya batas lebar; pesan panjang di layar <375px bisa
   terpotong di tepi layar. Ditambah `max-width: calc(100vw - 32px)`.

### Baru

- `frontend/icons/` — ikon PWA lengkap (lihat Bug #1).

### Diedit minimal

- `frontend/manifest.json` — daftar ikon lengkap + `purpose`, tambah
  `id`/`lang`.
- `frontend/index.html` — link ikon lengkap, meta tag Apple/PWA, tambah
  `viewport-fit=cover` + `meta description`.
- `frontend/css/style.css` — safe-area padding (notch iPhone), styling
  hamburger/backdrop untuk layar sempit, `.toast` max-width. Semua
  PENAMBAHAN aturan CSS baru atau perluasan media query yang sudah ada;
  tidak ada rule yang sudah berfungsi normal yang diubah/dihapus.
- `frontend/js/router.js` — tombol hamburger + backdrop (Bug #2).
- `frontend/js/api.js` — fix cache offline array (Bug #3).
- `frontend/js/pages/login.js` — fix navigasi setelah login (Bug #4).
- `backend/app/routers/dashboard.py` — hapus import tak terpakai (Bug #5).
- `frontend/service-worker.js` — daftarkan seluruh file ikon baru ke
  app-shell cache, naikkan `CACHE_NAME` ke v7.
- `README.md` — dokumentasi Instalasi, Deployment, Backup & Restore,
  Sinkronisasi Google Sheets yang lengkap (sebelumnya sebagian besar hanya
  ada di CHANGELOG per-tahap, tidak ada panduan operasional terpusat).

### Tidak disentuh sama sekali

`database.py`, `auth.py`, `auth_db.py`, seluruh fungsi hitung komisi/bonus/
absensi, `routers/input_data.py`, `routers/pengeluaran.py`,
`routers/produk.py`, `routers/pengaturan.py`, `routers/rekap.py`,
`pengaturan_backup.py`, `pengeluaran_db.py`, dan seluruh halaman frontend
Dashboard/Input Data/Rekap/Produk/Pengeluaran/Pengaturan/Sinkronisasi
(logika, bukan CSS pembungkusnya) — nol perubahan fungsional.

### Pengujian Tahap 13

Backend dijalankan sungguhan (instalasi bersih `requirements.txt`) +
browser (Playwright), database SQLite kosong (bootstrap admin baru):

1. **Login Owner & Login Barber** — keduanya berhasil, data & hak akses
   masing-masing benar.
2. **Dashboard Owner & Dashboard Barber** — data tampil benar, barber
   tidak bisa mengakses endpoint dashboard Owner (403).
3. **Input Data, Rekap, Produk, Pengeluaran, Pengaturan** — CRUD & filter
   di semua modul diuji ulang lewat API, nilai komisi (mis. Dry Cut
   Rp35.000 → komisi Rp14.000) tetap identik seperti sebelum Tahap 13.
4. **Sinkronisasi Google Sheets, Backup, Restore** — status sinkron,
   export `.db` (diverifikasi signature SQLite valid), import/restore
   (data terverifikasi utuh setelah restore) — semua tetap normal.
5. **Permission**: seluruh endpoint admin-only diverifikasi ulang menolak
   barber dengan `403`; tanpa token ditolak `401`.
6. **Responsif** — diuji dengan Playwright di 3 viewport:
   - **Desktop** (1440×900): sidebar tetap, semua 7 menu Owner dapat
     dibuka tanpa error console.
   - **Tablet** (820×1180, breakpoint persis di batas media query):
     hamburger muncul & berfungsi, sidebar terbuka lewat tombol, otomatis
     tertutup begitu memilih menu.
   - **Mobile** (390×844, setara iPhone 12): hamburger + backdrop
     berfungsi, tap area gelap menutup menu, login Barber di lebar ini
     juga diverifikasi (menu Owner-only tetap tersembunyi).
7. **PWA**: diverifikasi lewat browser sungguhan (bukan cuma baca kode) —
   `navigator.serviceWorker` berstatus `activated`, `manifest.json`
   valid & bisa diambil, seluruh 10 entri ikon di manifest + apple-touch-
   icon + favicon.ico dikonfirmasi termuat (`HTTP 200`), meta
   `apple-mobile-web-app-capable` ada.
8. **Offline** (Bug #3 di atas): halaman Produk dibuka saat online (data
   ter-cache), lalu koneksi dimatikan sungguhan lewat
   `browser_context.set_offline(True)` dan halaman di-reload — service
   worker menyajikan app-shell dari cache, DAN data (Daftar Produk +
   Riwayat Mutasi, dua tabel berbeda di halaman yang sama) tetap tampil
   lengkap dengan banner "Sedang offline", tidak lagi kosong.
9. `python3 -m py_compile` untuk **seluruh** file `.py` di `backend/app/`
   (bukan cuma yang disentuh Tahap 13) dan `node --check` untuk **seluruh**
   file `.js` di `frontend/` — tidak ada syntax error di manapun.
10. `git diff --stat` dari base `master` (setelah Tahap 12 merge)
    dikonfirmasi **tidak menyertakan** `database.py`, `auth.py`,
    `auth_db.py`, atau file logika bisnis Tahap 1–12 manapun kecuali daftar
    "Diedit minimal" di atas (murni bugfix/dokumentasi/ikon) — bukti
    langsung tidak ada regresi logika bisnis.

## BUGFIX (pasca-Tahap 13) — Startup Backend Lokal Gagal

### Ronde 1

Ditemukan setelah Tahap 13 merge: menjalankan backend secara lokal bisa
gagal start dengan dua error sekaligus:

```
AttributeError: module 'bcrypt' has no attribute '__about__'
ValueError: password cannot be longer than 72 bytes
```

**Akar masalah**: `auth_db.py` melakukan hashing password lewat
`passlib.context.CryptContext(schemes=["bcrypt"])`. Passlib 1.7.4 (rilis
terakhirnya, sudah tidak dikembangkan lagi) melakukan self-test internal
yang membaca atribut `bcrypt.__about__` dan memverifikasi hash memakai
string uji sepanjang 255 byte — dua-duanya TIDAK kompatibel dengan
`bcrypt` versi 4.0 ke atas (atribut `__about__` sudah dihapus, dan
`hashpw`/`checkpw` versi baru sengaja menolak input >72 byte alih-alih
memotongnya diam-diam seperti versi lama). Tahap 11 sempat menambal ini
dengan mengunci `bcrypt<4.0` di `requirements.txt`, tapi tambalan itu
rapuh: kalau environment lokal (venv lama, cache pip, instalasi global)
sudah lebih dulu punya `bcrypt` versi baru terpasang, `pip install -r
requirements.txt` berikutnya tidak selalu menggantinya, dan error yang
sama muncul lagi.

**Perbaikan** (murni dependency/startup, TIDAK menyentuh logika bisnis/
komisi/bonus/database/hak akses/fitur apa pun):

1. `backend/app/auth_db.py` — hashing password sekarang memanggil library
   `bcrypt` LANGSUNG (`bcrypt.hashpw`/`bcrypt.checkpw`), tidak lagi lewat
   passlib. Format hash yang dihasilkan identik (awalan `$2b$`), jadi
   **hash yang sudah tersimpan di database dari sebelumnya tetap valid
   diverifikasi** — tidak perlu migrasi data, tidak ada user yang perlu
   reset password. Password dipotong ke 72 byte sebelum di-hash/diverifikasi
   (batas bawaan algoritma bcrypt itu sendiri, simetris di kedua fungsi)
   supaya perilakunya konsisten di semua versi bcrypt.
2. `backend/requirements.txt` — `passlib[bcrypt]` dihapus (tidak
   dibutuhkan lagi sama sekali), pin `bcrypt<4.0` diganti `bcrypt>=4.0`
   (sekarang aman pakai versi bcrypt terbaru, karena kode tidak lagi
   bergantung pada internal passlib yang rapuh itu).
3. `backend/app/__init__.py` (baru) — memperbaiki cara lain backend bisa
   gagal start: modul-modul di `backend/app/` memakai import "flat"
   (`import database`, `from routers import ...`), yang hanya berfungsi
   kalau folder `backend/app/` ada di `sys.path`. Itu otomatis terjadi
   kalau dijalankan `cd backend/app && uvicorn main:app`, TAPI TIDAK kalau
   dijalankan `uvicorn app.main:app` dari folder `backend/` (folder yang
   otomatis masuk `sys.path` jadinya `backend/`, bukan `backend/app/`) —
   gagal dengan `ModuleNotFoundError: No module named 'database'`. File
   baru ini menambahkan folder `backend/app/` ke `sys.path` begitu paket
   `app` diimpor, TANPA mengubah satu pun baris import yang sudah ada di
   modul lain. Kedua cara menjalankan backend sekarang sama-sama berfungsi
   (lihat bagian **Menjalankan di Lokal** di atas).

**Diuji**: instalasi bersih `requirements.txt` (mendapat `bcrypt` versi
terbaru, terverifikasi tanpa error saat startup), kedua cara menjalankan
backend (`uvicorn main:app` dari `backend/app/`, dan `uvicorn app.main:app
--reload` dari `backend/`), login Owner & Barber, ganti password lalu
login ulang dengan password lama (ditolak) dan password baru (berhasil) —
membuktikan hash lama & baru dua-duanya tetap berfungsi benar, permission
Owner/Barber, nilai komisi (Dry Cut Rp35.000 → komisi Rp14.000, tidak
berubah), serta regresi Produk/Pengeluaran/Rekap/Pengaturan/Sinkronisasi.
`python3 -m py_compile` untuk seluruh file backend — tidak ada syntax
error. `git diff --stat` mengonfirmasi hanya 3 file yang tersentuh:
`auth_db.py`, `requirements.txt`, dan `app/__init__.py` (baru) — tidak ada
perubahan di `database.py` atau file logika bisnis manapun.

### Ronde 2 — masih gagal di Windows dengan `bcrypt==5.0.0` + `passlib==1.7.4`

Setelah Ronde 1 di-merge, dilaporkan backend MASIH gagal start di sebuah
mesin Windows lokal dengan pesan yang sama
(`ValueError: password cannot be longer than 72 bytes`), sementara venv
lokal tercatat punya `bcrypt==5.0.0` dan `passlib==1.7.4` terpasang
berdampingan.

**Investigasi**: kombinasi paket yang persis sama (`bcrypt==5.0.0` +
`passlib==1.7.4`, plus seluruh isi `requirements.txt` lain) direproduksi
di environment terpisah, menjalankan `uvicorn main:app` dengan kode
`master` hasil Ronde 1 apa adanya — **backend start normal, tidak ada
error**. Diperiksa juga ulang seluruh repository (`grep -r passlib`) —
tidak ada satu baris kode pun (di luar komentar/dokumentasi) yang masih
memanggil `passlib`. Kesimpulan: kode di repository ini sudah benar;
kegagalan di mesin Windows yang dilaporkan kemungkinan besar disebabkan
oleh environment lokal itu sendiri (kode versi lama yang masih
ter-cache/venv yang belum benar-benar bersih terpasang ulang, atau
instalasi `bcrypt` yang rusak sebagian — pola yang dikenal luas terjadi
di Windows karena file ekstensi native `.pyd` bisa gagal diganti bersih
oleh `pip install --upgrade` kalau sedang terkunci proses lain).

**Yang ditambahkan** (tetap murni dependency/startup, tidak menyentuh
logika bisnis apa pun):

1. `backend/app/auth_db.py` — `hash_password()`/`verify_password()`
   sekarang membungkus pemanggilan `bcrypt` dengan pesan diagnosa yang
   jelas kalau sampai gagal (`RuntimeError` dengan penjelasan penyebab +
   langkah perbaikan), menggantikan traceback kriptis dari dalam library
   pihak ketiga.
2. `README.md` — bagian baru **Troubleshooting Windows** di bawah
   **Instalasi**: langkah verifikasi cepat (`python -c "import auth_db;
   print(auth_db.hash_password('tes'))"`) untuk memastikan apakah masalah
   ada di kode atau di environment, plus langkah membuat ulang virtual
   environment dari nol.

**Diuji ulang**: reproduksi persis `bcrypt==5.0.0` + `passlib==1.7.4` +
seluruh `requirements.txt` lain → backend start normal & `/api/health`
merespons `200`. Diagnosa `RuntimeError` diverifikasi muncul dengan benar
lewat simulasi kegagalan `bcrypt` (monkeypatch). Regresi penuh login,
permission, dan seluruh modul tidak terpengaruh.

### Ronde 3 — `ModuleNotFoundError: No module named 'database'` (lagi) di `uvicorn app.main:app --reload`

Dilaporkan lagi: `uvicorn app.main:app --reload` gagal dengan
`ModuleNotFoundError: No module named 'database'` di `main.py` baris
`import database as db` — persis error yang seharusnya sudah diperbaiki
`app/__init__.py` di Ronde 1.

**Analisis**: `app/__init__.py` menambahkan folder `backend/app/` ke
`sys.path` begitu paket `app` diimpor — ini terbukti benar di semua
pengujian sebelumnya (termasuk dengan `--reload`, lihat Ronde 1 & 2). TAPI
mekanisme itu bergantung pada Python selalu menjalankan `app/__init__.py`
lebih dulu sebelum `app/main.py`, di PROSES MANAPUN yang mengimpornya —
termasuk proses worker yang di-*restart* oleh `--reload` tiap kali ada
perubahan file. Di beberapa platform (terutama **Windows**, yang memakai
metode `spawn` untuk membuat proses baru — bukan `fork` seperti
Linux/Mac), proses worker hasil restart itu dibuat dengan cara yang
berbeda dan tidak selalu menjamin urutan import package se-transparan di
Linux. Supaya TIDAK bergantung sama sekali pada jaminan urutan itu,
`sys.path` sekarang JUGA diperbaiki langsung di baris paling atas
`main.py` sendiri (sebelum `import database` dkk di file yang sama) --
dijalankan otomatis kapan pun modul `main.py` mulai dieksekusi, di proses
manapun, terlepas dari bagaimana ia diimpor (`main` flat, `app.main`,
proses awal, atau proses hasil `--reload`). `app/__init__.py` dari Ronde 1
TETAP ada (tidak dihapus, tidak saling bertentangan — pengecekan
`if ... not in sys.path` di kedua tempat membuat keduanya aman dijalankan
berulang/bersamaan).

**Diuji ulang**: instalasi bersih `requirements.txt` + `bcrypt==5.0.0` +
`passlib==1.7.4` (kombinasi yang dilaporkan) → `uvicorn app.main:app
--reload` start normal, `/api/health` → `200`, login berhasil. **Diuji
juga siklus reload sungguhan**: file `main.py` disentuh (`touch`) saat
server berjalan untuk memicu `--reload` (memaksa `WatchFiles`
me-restart proses worker, skenario paling dekat yang bisa disimulasikan
di sandbox Linux untuk meniru proses baru gaya `spawn`) — proses worker
baru berhasil start ulang tanpa error, dan `/api/health` + login tetap
berfungsi normal setelahnya.


## CHANGELOG — REVISI (pasca-Tahap 13) — Bonus Bertingkat, Uang Harian per-Barber, Hak Akses Barber

Revisi ini mengubah **logika bisnis** (`database.py`) atas permintaan
eksplisit — bukan pelanggaran aturan "jangan diedit" di kepala file
tersebut, melainkan pengecualian yang diminta langsung untuk revisi ini.
Semua perubahan lain (arsitektur, struktur folder, database schema lewat
migrasi idempotent, API existing yang tidak disebut di bawah, tampilan
yang sudah benar) SENGAJA tidak disentuh.

**Ringkasan perubahan:**

1. **Target Bonus Service jadi bertingkat (banyak tier)** — sebelumnya
   cuma satu target/nominal hardcoded-via-setting. Sekarang Owner bisa
   tambah/ubah/hapus tier sebanyak yang dibutuhkan lewat **Setting >
   Komisi & Bonus > Target Bonus Service** (mis. 100 service → Rp100rb,
   115 service → Rp150rb, dst). Barber dapat bonus dari tier TERTINGGI
   yang tercapai bulan itu. Tetap dihitung HANYA dari Dry Cut + Cut &
   Wash (tidak berubah — memang sudah begitu sejak awal).
   - Backend: `database.py` (`get_bonus_customer_tiers`,
     `set_bonus_customer_tiers`, `hitung_bonus_customer` dirombak),
     `pengaturan_bonus.py` (baru), endpoint baru
     `GET/POST /api/pengaturan/bonus-tiers`,
     `PUT/DELETE /api/pengaturan/bonus-tiers/{target}`.
   - Disimpan sebagai JSON di tabel `settings` yang sudah ada (key
     `bonus_customer_tiers`) — tidak ada tabel baru.

2. **Uang Harian jadi per-barber, bukan lagi 2 setting global** —
   sebelumnya nominal ditentukan dari flag `is_rafiq` (dua setting global
   `uang_harian_barber`/`uang_harian_rafiq`). Sekarang tiap barber punya
   kolom `uang_harian` sendiri, diisi bebas oleh Owner lewat **Setting >
   Barber** saat tambah/edit barber. Aturan pencairan (≥3 Dry Cut + Cut &
   Wash di hari itu) TIDAK berubah. Checkbox "RAFIQ" masih ada tapi
   sekarang murni label, tidak lagi memengaruhi nominal apa pun.
   - Migrasi (`revisi_bonus_migrasi.py`, idempotent): menambah kolom
     `barbers.uang_harian`, lalu backfill dari nilai efektif LAMA
     (`is_rafiq ? uang_harian_rafiq : uang_harian_barber`) supaya gaji
     barber manapun TIDAK berubah otomatis saat migrasi jalan — Owner
     baru mengubahnya kalau memang mau.

3. **Fitur Bonus Kehadiran dihapus total** — kartu di kedua Dashboard,
   field di Setting, fungsi `hitung_bonus_kehadiran()`, dan field
   `bonus_kehadiran`/`bonus_kehadiran_detail` di semua response API
   (`get_ringkasan_barber_bulan`, `get_rekap_bulanan_list`) dihapus.
   Kolom "Bonus Hadir" di Rekap Bulanan juga dihapus.

4. **Dashboard Owner**: tambah kartu "Total Customer", tambah bagian
   "Service Bulan Ini" dengan dropdown pilih barber (Semua Barber =
   gabungan, atau satu barber = data barber itu saja) — daftar dropdown
   otomatis mengikuti barber aktif, daftar service otomatis mengikuti
   service aktif di Setting, hanya menampilkan service dengan jumlah > 0.

5. **Dashboard Barber**: kartu "Bonus Kehadiran" dan "Jumlah Service"
   dihapus (Jumlah Service tetap terlihat rinciannya di tabel "Service
   Bulan Ini", cuma kartu ringkasannya yang dihapus). Progress tier bonus
   ditampilkan menuju tier berikutnya yang belum tercapai.

6. **Hak akses Barber diperketat** — sebelumnya Barber bisa akses Input
   Data (untuk input/koreksi transaksi miliknya sendiri). Sekarang Barber
   HANYA punya akses ke Dashboard dan Rekap; Input Data jadi khusus
   Owner/admin. Diberlakukan di backend (`routers/input_data.py`, semua
   endpoint diganti `Depends(require_admin)`) dan di frontend (`nav.js`
   menu, `router.js` route guard) — backend tetap lapisan penegakan yang
   sebenarnya.

**Tidak diubah** (sengaja, sesuai instruksi revisi): arsitektur, struktur
folder, skema tabel lewat `CREATE TABLE` (kolom baru lewat migrasi
idempotent seperti pola Tahap 12), endpoint/hak akses Produk, Pengeluaran,
Manajemen User, Sinkronisasi, dan seluruh tampilan yang sudah sesuai
spesifikasi. `DEFAULT_SETTINGS` di `database.py` masih menyisakan
key lama (`uang_harian_barber`, `uang_harian_rafiq`, `bonus_kehadiran`,
`maksimal_hari_libur`, `target_bonus_customer`, `nominal_bonus_customer`)
sebagai entri tak terpakai — dibiarkan sengaja untuk meminimalkan diff,
tidak lagi dibaca oleh kode manapun.

**Diuji**: regresi penuh lewat browser (Playwright) untuk Dashboard Owner
(dropdown barber, kartu Total Customer, tier progress, tabel Per Barber
tanpa kolom Bonus Kehadiran), Dashboard Barber (kartu terhapus, tier
progress), Setting > Komisi & Bonus (field lama terhapus, tambah/ubah/
hapus tier lewat UI end-to-end), Setting > Barber (tambah/edit uang
harian per-barber), Rekap (kolom Bonus Hadir terhapus, filter Bulan/
Tahun), dan penegakan hak akses (Barber dapat 403 dari backend untuk
`dashboard/owner`, `input-data/*`, `pengeluaran`, `produk`,
`pengaturan/*`, `sync/status`; dan tidak bisa memaksa lihat data barber
lain lewat parameter `barber_id` di `/api/rekap/*`). Modul yang tidak
disentuh (Produk, Pengeluaran, Manajemen User, Backup/Restore,
Sinkronisasi, Login) diverifikasi tetap berfungsi normal lewat regresi
API langsung.

### BUGFIX (pasca-REVISI) — PWA Menampilkan Tampilan Lama Setelah Deploy

Ditemukan setelah revisi di atas di-deploy ke production: backend
ter-deploy dengan benar (kode baru ada di server), tapi tampilan yang
dilihat user (Dashboard Owner/Barber, Setting) masih perilaku LAMA
(kartu Bonus Kehadiran masih ada, kartu Total Customer belum muncul, dst).

**Akar masalah**: `frontend/service-worker.js` men-cache seluruh app-shell
(termasuk semua file di `js/pages/*.js`, `js/nav.js`, `js/router.js`) di
bawah SATU nama, `CACHE_NAME`. Strategi fetch-nya cache-first (`caches.
match(request) || fetch(request)`), jadi selama `CACHE_NAME` tidak
berubah, browser yang PWA-nya sudah pernah dibuka sebelumnya TIDAK akan
pernah mengambil ulang file-file itu dari server, walau server sudah
di-deploy ulang dengan isi baru — persis gejala "deploy sukses tapi
tampilan masih lama". Revisi sebelumnya mengubah 6 file yang ikut
di-cache (`nav.js`, `router.js`, `dashboard_owner.js`,
`dashboard_barber.js`, `pengaturan.js`, `rekap.js`) TANPA menaikkan
`CACHE_NAME` — padahal ini adalah konvensi yang sudah dipakai konsisten
di riwayat project ini (`CACHE_NAME` naik dari v1 sampai v7 di
tahap-tahap sebelumnya, setiap kali ada file app-shell yang berubah).
Dibuktikan ulang dengan simulasi: deploy disimulasikan (file diganti di
disk, server & URL tetap sama), lalu tab dimuat ulang berkali-kali —
tampilan tetap menunjukkan versi lama selama `CACHE_NAME` tidak berubah.

**Perbaikan** (murni cache-busting, TIDAK mengubah logika bisnis apa pun
dari revisi sebelumnya):

1. `frontend/service-worker.js` — `CACHE_NAME` dinaikkan `v7` → `v8`,
   supaya browser mendeteksi `service-worker.js` berubah, meng-install
   cache baru dari network (isi terbaru), lalu menghapus cache lama
   (mekanisme `activate` yang sudah ada sebelumnya, tidak diubah).
2. `frontend/js/app.js` — setelah registrasi, sekarang juga memanggil
   `registration.update()` supaya aplikasi AKTIF meminta browser mengecek
   versi `service-worker.js` terbaru setiap kali dibuka (sebelumnya cuma
   mengandalkan jadwal pengecekan otomatis bawaan browser).

**Untuk user yang PWA-nya SUDAH terlanjur ter-install dan stuck di
tampilan lama** (sebelum deploy fix ini): setelah deploy fix ini,
kunjungan berikutnya akan otomatis mendapat versi baru begitu browser
selesai mengecek update (biasanya di reload berikutnya). Kalau ingin
langsung tanpa menunggu: hard refresh (Ctrl+Shift+R / Cmd+Shift+R), atau
uninstall lalu install ulang PWA-nya, atau hapus data situs
(`chrome://settings` → Privacy → Site settings → cari domain frontend →
Clear data) lalu buka lagi.

**Catatan konvensi untuk revisi berikutnya**: setiap kali mengubah isi
file yang terdaftar di `APP_SHELL` (`frontend/service-worker.js`), WAJIB
menaikkan `CACHE_NAME` di commit yang sama -- kalau tidak, deploy tidak
akan terlihat oleh user yang sudah pernah membuka PWA sebelumnya.

### CHANGELOG — Kartu "Jumlah Service" + Bugfix Login "Kadang Gagal"

**1. Dashboard (Owner & Barber): kartu "Total Customer"/"Jumlah Customer"
diganti kartu "Jumlah Service".** Sebelumnya kartu ringkasan itu hanya
angka tunggal jumlah customer; sekarang berisi rincian per jenis service
bulan berjalan (mis. "Dry Cut = 7", "Cut & Wash = 3", dst), memakai data
`rincian_service`/`rincian_service_semua_barber` yang backend memang sudah
menghitung (jumlah 0 otomatis tidak ikut, tanpa perlu perubahan backend).
Dashboard Owner: gabungan seluruh barber (konsisten dengan kartu lain di
baris yang sama, semuanya total toko). Dashboard Barber: rincian milik
barber yang login saja. `frontend/js/pages/dashboard_owner.js`,
`frontend/js/pages/dashboard_barber.js`.

**2. Bugfix: login kadang gagal ("username/password salah") padahal
kredensial benar.** Akar masalah: pencocokan username di backend
case-SENSITIVE (`WHERE username = ?` tanpa `COLLATE NOCASE`), sementara
banyak keyboard HP (iOS/Android) secara default meng-kapital-kan huruf
pertama input teks (autocapitalize) -- kalau user mengetik "budi" tapi
keyboard mengirim "Budi", lookup user gagal total dan login ditolak walau
password benar. Gejalanya terlihat "kadang" karena tergantung
keyboard/perangkat yang dipakai saat itu, bukan konsisten di semua
percobaan. Dikonfirmasi lewat pengujian: login dengan variasi huruf besar/
kecil pada username yang sama ("owner", "Owner", "OWNER") sebelumnya hanya
salah satu yang berhasil.

Perbaikan (dua lapis, saling melengkapi):
- `backend/app/auth_db.py` (`get_user_by_username`) — pencocokan username
  sekarang case-insensitive (`COLLATE NOCASE`), dengan exact match tetap
  diprioritaskan lewat `ORDER BY (username = ?) DESC` untuk kasus langka
  ada dua username yang hanya beda huruf besar/kecil. Username tetap
  disimpan case-sensitive persis seperti diketik saat akun dibuat -- ini
  HANYA mengubah cara mencari/mencocokkan saat login, bukan penyimpanan.
- `frontend/js/pages/login.js` — input username diberi
  `autocapitalize="off"` (+ `autocorrect="off"`, `spellcheck="false"`)
  supaya keyboard HP tidak lagi mengubah huruf yang diketik user sejak
  awal.

Diuji: login dengan kombinasi huruf besar/kecil berbeda pada username yang
sama (`owner`/`Owner`/`OWNER`, `budi`/`BUDI`) berhasil semua dan
menghasilkan sesi yang sama; password salah & username tidak ada tetap
ditolak seperti sebelumnya (tidak ada pelonggaran pada pengecekan
password).

`frontend/service-worker.js`: `CACHE_NAME` dinaikkan `v8` → `v9` (lihat
catatan konvensi di atas) karena revisi ini mengubah `dashboard_owner.js`,
`dashboard_barber.js`, dan `login.js`.

### CHANGELOG — Konfirmasi Keluar, Loading Global, Bugfix Pesan Login, Grafik Pendapatan (Owner)

**1. Konfirmasi sebelum Keluar** — tombol "Keluar" di sidebar sekarang
menampilkan dialog konfirmasi ("Yakin ingin keluar?") lebih dulu, memakai
`confirm()` bawaan browser -- pola yang sama seperti seluruh aksi hapus
lain di aplikasi ini (Hapus Barber, Hapus Layanan, Hapus Transaksi, dst).
Batal = tetap di halaman, tidak logout. `frontend/js/nav.js`.

**2. Loading spinner global + jeda 1,5 detik di setiap tombol yang
memanggil server, dan setiap filter Bulan/Tahun/Barber (dropdown).**
Spinner melingkar modern muncul di tengah aplikasi (overlay), dengan jeda
MINIMAL 1,5 detik sebelum hasilnya tampil (kalau server-nya lebih cepat
dari itu, tetap ditahan sampai 1,5 detik; kalau lebih lambat, spinner tetap
tampil sampai benar-benar selesai -- tidak dipotong paksa). Navigasi menu
sidebar dan pindah tab (Rekap/Setting) TIDAK memakai jeda ini (tetap
instan), sesuai konfirmasi: hanya aksi yang benar-benar memanggil server
(submit/simpan/hapus/tambah/upload, dan ganti filter bulan/tahun/barber)
yang dapat perlakuan ini.
- `frontend/js/ui.js` — utilitas baru `MugenUI.showLoading()` /
  `hideLoading()` / `withLoading(asyncFn)` (dengan hitungan referensi
  supaya tidak berkedip kalau ada beberapa proses tumpang tindih).
- `frontend/css/style.css` — style `.loading-overlay` / `.loading-spinner`
  (animasi CSS murni, tanpa GIF/library eksternal).
- Dipasang di SEMUA tombol yang memanggil `MugenApi.post/put/del/
  uploadFile` di seluruh halaman (`login.js`, `input_data.js`,
  `pengeluaran.js`, `produk.js`, `pengaturan.js`, `sinkronisasi.js`), dan
  di semua dropdown filter Bulan/Tahun/Barber yang men-trigger `MugenApi.
  get` ulang (`dashboard_owner.js`, `dashboard_barber.js`, `rekap.js`,
  `pengeluaran.js`, `produk.js`). Pengecualian yang SENGAJA tidak dipasangi
  (bukan "tombol"/filter, supaya tidak mengganggu): live-preview saat
  mengetik jumlah service di Input Data, dan pencarian teks langsung di
  Pengeluaran (keduanya trigger per keystroke, bukan per klik/pilih).

**3. Bugfix: pesan error login salah kredensial.** Sebelumnya SETIAP
respons 401 dari server (termasuk dari percobaan login yang salah) selalu
ditampilkan sebagai "Sesi login berakhir, silakan login lagi." -- padahal
untuk percobaan login yang gagal, pesan yang seharusnya tampil (dan
memang sudah dikirim backend) adalah "Username atau password salah."
Endpoint `/api/auth/login` sekarang dikecualikan dari penanganan 401
"sesi berakhir" itu, sehingga pesan asli dari backend yang tampil.
`frontend/js/api.js`.

**4. Grafik Pendapatan (diagram batang) — KHUSUS Dashboard Owner.** Dua
diagram batang baru di bagian bawah Dashboard Owner, dengan dropdown
"Semua Barber" (gabungan) / satu barber tertentu (daftar sama seperti
dropdown "Service Bulan Ini"):
- **Harian** — satu batang per tanggal pada bulan/tahun yang sedang
  dipilih (termasuk tanggal tanpa transaksi, nilainya 0, supaya sumbu
  tanggal tidak "loncat"). Nilainya Komisi + Tips + Uang Harian hari itu
  -- Bonus Customer SENGAJA tidak diikutkan karena itu perhitungan
  BULANAN, tidak ada cara membaginya secara berarti per tanggal.
- **Bulanan** — satu batang per bulan (Jan-Des) pada tahun yang sedang
  dipilih. Nilainya Total Pendapatan PENUH (Komisi + Tips + Uang Harian +
  Bonus Customer), sama seperti kartu "Total Pendapatan Barber" di atas.
- Backend: dua endpoint baru `GET /api/dashboard/owner/grafik-harian` dan
  `GET /api/dashboard/owner/grafik-bulanan` (khusus admin) di
  `routers/dashboard.py` -- KEDUANYA murni menyusun ulang data dari
  fungsi yang SUDAH ADA di `database.py` (`get_transaksi_list`,
  `hitung_uang_harian_per_hari`, `get_ringkasan_barber_bulan`), tidak ada
  satu baris pun logika bisnis baru/diubah di `database.py`.
- Frontend: chart digambar manual pakai SVG (`MugenUI.barChart()` di
  `ui.js`), SENGAJA tanpa library grafik dari CDN apa pun -- supaya PWA
  ini tetap bisa dibuka offline (kalau pakai library dari CDN, chart akan
  gagal dimuat begitu tidak ada koneksi internet).
- Dashboard Barber TIDAK mendapat grafik ini (sesuai permintaan, khusus
  Owner).

`frontend/service-worker.js`: `CACHE_NAME` dinaikkan `v9` → `v10` (lihat
catatan konvensi di atas) karena revisi ini mengubah `ui.js`, `api.js`,
`nav.js`, `login.js`, `style.css`, dan hampir semua `pages/*.js`.

### CHANGELOG — Modul BOOKING (Booking Online)

Modul baru, terpisah total dari `database.py` (yang tetap salinan verbatim
logika bisnis aplikasi Desktop) -- pola yang sama seperti `auth_db.py`:
tabel & logika sendiri di `backend/app/booking_db.py`, migrasi sendiri di
`backend/app/booking_migrasi.py`, router sendiri di
`backend/app/routers/booking.py`.

**Halaman publik `#/book`** (frontend/js/pages/book_public.js) — TANPA
LOGIN sama sekali, wizard 7 langkah sesuai spek: Pilih Barber (barber yang
sedang libur tetap tampil, abu-abu, "On Vacation", tidak bisa dipilih) →
Pilih Tanggal (kalender visual, bukan input teks, dibatasi
`maksimal_hari_kedepan`) → Pilih Jam (tombol hijau/merah/abu-abu =
tersedia/sudah dibooking/tutup, bukan input teks) → Pilih Service (boleh
lebih dari satu -- durasi dijumlahkan) → Data Diri (nama + WhatsApp) →
Ringkasan + Full Payment (tidak ada DP) → Booking Berhasil.

**Auto-block slot**: durasi total service yang dipilih dibulatkan ke atas
ke kelipatan interval slot, lalu SEMUA slot yang tercakup ditandai
terpakai (mis. interval 60 menit + service 150 menit mulai 10:00 ->
10:00/11:00/12:00 sama-sama terkunci untuk customer lain, persis contoh
di spek). Ketersediaan dicek ulang di TIGA titik (tampilan awal jam,
setelah Pilih Service, dan sekali lagi tepat sebelum booking disimpan)
supaya tidak mungkin dua customer kebetulan dapat slot yang sama.

**Prioritas ketersediaan slot** (urutan ini konsisten di semua
pengecekan): Barber Holiday → Closed Slot → Sudah dibooking → Available.

**Barber Holiday memakai tabel `absensi_libur` yang SUDAH ADA**
(database.py, dipakai juga untuk Bonus Customer di Dashboard) -- SENGAJA
TIDAK membuat tabel "holiday" baru yang terpisah, supaya "barber ini libur
tanggal ini" tetap SATU sumber kebenaran (kalau ada dua tabel terpisah,
keduanya bisa saling tidak sinkron). Menu Barber Holiday di halaman
Booking internal memakai endpoint `/api/input-data/libur` yang sudah ada
sejak Tahap 5, bukan endpoint baru.

**Durasi service**: kolom baru `services.durasi_menit` (default 60 menit,
migrasi idempotent), diedit di menu Setting > Layanan yang SUDAH ADA
(bukan menu baru) — field baru di sebelah harga/modal, mengikuti pola
persis yang sama seperti field `modal` sebelumnya.

**Metode Pembayaran**: Cash, Transfer Bank, QRIS aktif & berfungsi penuh
sekarang (booking berstatus "Menunggu Verifikasi" sampai Owner/Admin
menekan tombol Verifikasi di Booking List). QRIS statis (upload/ganti/
hapus gambar + nama merchant, pola upload SAMA PERSIS seperti logo
barbershop), desain modular untuk nanti diganti QRIS Dynamic/API. Payment
Gateway HANYA muncul sebagai toggle di Payment Settings -- kalau
diaktifkan, customer yang memilihnya mendapat pesan "segera hadir" dan
tidak bisa menyelesaikan booking lewat metode itu (belum ada integrasi
provider sungguhan).

**Menu internal `#/booking`** (frontend/js/pages/booking.js) — Owner/Admin
full access lewat 7 tab: Booking List (filter bulan/tahun/barber/status,
tombol Verifikasi & Batalkan), Calendar (kalender visual + badge jumlah
booking per tanggal, klik tanggal untuk lihat detail), Operating Hours
(jam buka/tutup), Barber Holiday, Closed Slot (tutup jam tertentu untuk
meeting/training/reservasi offline/istirahat/keperluan pribadi), Payment
Settings, Booking Settings (interval slot + maksimal hari booking ke
depan). Barber: HANYA daftar booking miliknya sendiri (barber_id dari
akun login lewat `/api/booking/mine`, sama pola seperti
`/api/dashboard/barber` -- bukan dari parameter apa pun yang bisa
dimanipulasi lewat client).

**Bugfix ditemukan saat pengujian**: pengecekan rute publik di
`router.js` awalnya `hash.startsWith("#/book")`, yang TANPA SENGAJA juga
cocok dengan `#/booking` (menu internal admin/barber) karena "booking"
kebetulan diawali "book" -- akibatnya menu Booking internal ikut
ter-render tanpa login sama sekali. Diperbaiki jadi pencocokan presis
(`hash === "#/book"` atau diawali `#/book/`/`#/book?`) sebelum PR ini
dibuka, ditemukan & diperbaiki lewat pengujian end-to-end.

**Diuji menyeluruh via Playwright**: alur booking publik penuh (barber →
tanggal → jam → 2 service sekaligus → data diri → ringkasan → QRIS →
selesai) tanpa error konsol; auto-block 2 slot dari service 150 menit
diverifikasi lewat API DAN lewat UI (slot yang sama muncul merah/terkunci
untuk customer berikutnya); double-booking & booking ke closed
slot/barber libur ditolak (422) baik lewat API maupun lewat UI (slot
tidak bisa diklik); admin: verifikasi pembayaran, Calendar menampilkan
booking yang benar, Barber Holiday & Closed Slot bisa ditambah/dihapus,
Payment Settings + upload QRIS berfungsi; barber: hanya melihat booking
miliknya, tidak ada tab admin, dan mendapat 403 kalau mencoba endpoint
admin langsung; regresi modul lama (Dashboard, Produk, Pengeluaran,
Setting, Sinkronisasi, Backup) dikonfirmasi tetap berfungsi normal.

`frontend/service-worker.js`: `CACHE_NAME` dinaikkan `v10` → `v11` untuk
`book_public.js`/`booking.js` yang baru serta perubahan `nav.js`/
`router.js`/`style.css`.


### CHANGELOG — Penyempurnaan Form Booking Customer

Penambahan murni (extend, bukan rewrite) di atas Modul BOOKING yang sudah
ada -- seluruh fitur lama (struktur booking, Login, Dashboard, Role, API,
database lama) TIDAK diubah/dihapus, hanya ditambahkan. Migrasi baru
`backend/app/booking_form_migrasi.py` (idempotent, `ALTER TABLE`), skema
lama tidak disentuh.

**Informasi Bisnis** (Setting > Identitas Barbershop): field baru Tagline,
Deskripsi, Website, dan Banner (upload, pola SAMA PERSIS seperti Logo --
`pengaturan_identitas.py` di-refactor supaya Logo & Banner berbagi helper
`_simpan_gambar`/`_get_gambar_file_path` yang sama, perilaku Logo tidak
berubah). Semua field ini otomatis tampil di header halaman `/book`.

**Link Booking**: TIDAK ada setting URL baru -- selalu diturunkan otomatis
dari `window.location.origin` (`Setting > Booking > Booking Settings`,
tombol "Salin Link"), jadi otomatis ikut kalau domain aplikasi berganti,
tanpa perlu ubah kode apa pun.

**Header halaman booking**: Judul, Subtitle, Footer, Pesan Pembuka, Pesan
Penutup semua bisa diubah Owner (`booking.js` tab Booking Settings; default
teksnya SAMA PERSIS dengan yang sebelumnya hardcode di frontend, supaya
tampilan tidak berubah sampai Owner sengaja menggantinya).

**Barber**: field baru `status_booking` (`aktif`/`cuti`) -- TERPISAH dari
`aktif` (Active/Non-Active) yang sudah ada, jadi sekarang ada 3 status
efektif: Aktif, On Vacation (cuti -- tetap tampil di `/book`, abu-abu,
tidak bisa dipilih, TAPI beda dari Barber Holiday per-tanggal yang sudah
ada -- cuti tidak terikat tanggal tertentu), Non Active (`aktif=false`,
tidak tampil sama sekali, perilaku lama tidak berubah). Ditambah upload
foto (`barber-{id}.<ext>`, pola sama seperti Logo/QRIS) dan urutan tampil
(diatur naik/turun di Setting > Barber, dipakai untuk mengurutkan kartu
barber di `/book`).

**Service**: field baru `urutan` (naik/turun di Setting > Layanan), dipakai
untuk mengurutkan daftar service di `/book`. Field lama (harga, durasi,
modal, aktif) tidak berubah.

**Jam Operasional**: field baru `hari_operasional` (checkbox 7 hari,
default semua aktif) -- tanggal di luar hari operasional otomatis
disilang di kalender `/book`. Ditambah **Hari Libur Toko** (tabel baru
`toko_libur`, terpisah dari Barber Holiday): menutup SEMUA barber
sekaligus untuk tanggal tertentu (mis. libur nasional), dicek PALING
AWAL di prioritas ketersediaan slot (lihat di bawah) karena tutup toko
mengalahkan ketersediaan barber manapun.

**Prioritas ketersediaan slot** (diperbarui dari Modul BOOKING): Toko
Libur/Hari Operasional (toko tutup) → Barber Holiday/Cuti (barber
libur) → Closed Slot → Sudah dibooking → Available.

**Form Customer**: TETAP hanya Nama + WhatsApp (wajib, tidak ada
opsi Email/Catatan, tidak ada pengaturan wajib/opsional per field --
sesuai instruksi eksplisit, di luar itu dianggap di luar cakupan).
Validasi nomor WhatsApp diperketat (regex `^\+?[0-9]{8,15}$`, sebelumnya
hanya cek panjang ≥ 8 karakter), pesan validasi (nama kosong & WhatsApp
tidak valid) sekarang bisa diubah Owner lewat Setting > Booking.

**Payment**: field baru per metode `metode_nama` (label tombol) dan
`metode_instruksi` (pesan detail yang dilihat customer) -- disimpan
sebagai merge, bukan overwrite (mengubah label Cash tidak menghapus
kustomisasi Transfer/QRIS/Gateway yang sudah ada). Default-nya SAMA
PERSIS dengan teks yang sebelumnya hardcode di frontend.

**Database**: seluruhnya tabel/kolom TAMBAHAN (`barbers.status_booking`,
`barbers.foto_filename`, `barbers.urutan`, `services.urutan`, tabel baru
`toko_libur`) lewat migrasi idempotent -- tidak ada kolom/tabel lama yang
diubah maupun dihapus, data lama tidak tersentuh.

**Diuji menyeluruh via Playwright** (53 pemeriksaan lolos di 3 skrip
end-to-end terpisah): halaman publik `/book` -- banner/judul/subtitle/
pesan pembuka/footer custom tampil benar, kartu barber menampilkan foto &
status "On Vacation" untuk barber cuti, kalender otomatis menyilang
tanggal Hari Libur Toko & hari di luar Hari Operasional, pesan validasi
custom tampil di Step Data Diri, label & instruksi metode pembayaran
custom tampil di Step Ringkasan, alur booking penuh sampai selesai
berhasil disubmit; admin -- Setting > Identitas menampilkan preview
Banner + field Tagline/Deskripsi/Website, Setting > Barber menampilkan
dropdown Status Booking yang perubahannya persist setelah reload, Setting
> Layanan menampilkan kontrol urutan, Booking > Operating Hours
menampilkan checkbox hari & daftar Hari Libur Toko, Booking > Payment
Settings menampilkan form label/instruksi custom, Booking > Booking
Settings menampilkan Link Booking yang otomatis mengikuti domain +
field header/footer/pesan tersimpan; regresi -- login, Dashboard, Input
Data, Rekap, Komisi & Bonus, CRUD Barber lama, Booking List/Calendar/
Closed Slot/Barber Holiday, dan alur booking publik end-to-end semuanya
dikonfirmasi tetap berfungsi normal tanpa error konsol.

`frontend/service-worker.js`: `CACHE_NAME` dinaikkan `v11` → `v12` untuk
`book_public.js`/`booking.js`/`pengaturan.js`/`style.css` yang berubah.


### CHANGELOG — Perbaikan UI/UX Halaman Booking (animasi step + kartu Booking Berhasil)

Dua perbaikan tampilan murni di atas halaman publik `/book`, TIDAK
mengubah logika booking, struktur database, maupun alur booking sama
sekali -- hanya `book_public.js` dan `style.css` yang berubah.

**Animasi perpindahan antar step**: setiap pindah step (baik lewat
tombol "Lanjut"/klik kartu-tanggal-jam-service, maupun tombol
"‹ Ganti .../Kembali") sekarang memakai animasi slide + fade ~300ms
(rentang 250-350ms sesuai permintaan) -- maju (step naik) slide dari
kanan, mundur (step turun) slide dari kiri. Cara kerja: `goto(n)`
membandingkan `n` dengan step saat ini untuk menentukan arah, lalu
`animasiTransisi()` men-clone konten step LAMA (`body.cloneNode`),
menaruhnya absolute di atas konten BARU yang langsung dirender ke
`body`, dan keduanya dianimasikan berlawanan arah lewat CSS
`@keyframes` (`transform: translateX` + `opacity`, GPU-accelerated,
tidak menyentuh `layout`/reflow berat) -- klon lama dibuang otomatis
saat `animationend` (dengan `setTimeout` jaga-jaga kalau event itu
tidak terpicu, mis. tab di background).

Selama animasi berlangsung: `transitioning=true` membuat `goto()`
mengabaikan panggilan lain (SATU-SATUNYA tempat penjagaan double-klik
perlu ditambahkan, karena semua navigasi step -- 7 step: Pilih Barber,
Pilih Tanggal, Pilih Jam, Pilih Service, Data Diri, Ringkasan+Pembayaran,
Booking Berhasil -- memanggil `goto()`), DAN class `book-nav-disabled`
menonaktifkan `pointer-events` semua tombol di halaman lewat CSS,
mencegah double-klik/perpindahan ganda dari dua sisi sekaligus (logika
+ CSS). `prefers-reduced-motion: reduce` dihormati (animasi otomatis
dimatikan, step tetap berpindah normal tanpa delay).

**Kartu "Booking Berhasil" dirapikan**: sebelumnya barber/tanggal/jam
ditampilkan digabung satu baris dengan rentang jam (`11:00-12:00`),
sekarang dipecah jadi field berlabel terpisah (Barber, Tanggal, Jam,
Service, Total) dengan alignment kolom yang konsisten (grid 3 kolom:
label — titik dua — nilai), DAN jam HANYA menampilkan jam mulai yang
dipilih customer (`jam_mulai`, bukan rentang `jam_mulai-jam_selesai`)
sesuai permintaan. Baris Total ditebalkan + warna aksen supaya menonjol.
Tema warna & komponen (`card`, `--text-dim`, `--accent`, dst) memakai
variabel CSS yang sudah ada, tidak ada palet baru.

**Diuji lewat Playwright** (18 pemeriksaan baru): animasi maju/mundur
menghasilkan class & arah yang benar lalu dibersihkan otomatis setelah
selesai, double-klik saat transisi tidak menyebabkan lompat step ganda,
`prefers-reduced-motion` dihormati, kartu Booking Berhasil menampilkan
5 field berlabel dengan urutan benar dan jam tanpa rentang waktu.
Regresi 52 pemeriksaan dari PR sebelumnya (alur booking publik penuh,
Setting, Booking internal, CRUD lama) dikonfirmasi ulang tetap lolos.

`frontend/service-worker.js`: `CACHE_NAME` dinaikkan `v12` → `v13` untuk
`book_public.js`/`style.css` yang berubah.


### CHANGELOG — REVISI: Modul Produk (Harga & Tester), Dashboard Penjualan Produk, Setting Bonus Service & Uang Harian, Loading Sign Out

Penambahan murni di atas fitur yang sudah berjalan (extend, bukan rewrite)
sesuai instruksi eksplisit ("tambahkan hanya fitur yang disebutkan, fitur
lain tetap seperti saat ini") -- seluruh perubahan database lewat migrasi
ADDITIVE baru (`produk_migrasi.py`, `bonus_service_migrasi.py`), tidak ada
kolom/tabel lama yang diubah/dihapus, dan diverifikasi (restart server
dengan data yang sudah ada) bahwa migrasi idempotent tidak menduplikasi
atau mereset data apa pun.

**Modul Produk**: kolom baru `produk.harga_modal` / `produk.harga_jual`
(diedit dari form Tambah/Ubah Produk yang sudah ada, tampil di kolom baru
pada Daftar Produk). Tipe transaksi baru **Tester** (tombol baru di
samping Restock/Jual) -- mengurangi stok sama seperti Jual, TIDAK
menambah nilai penjualan, tetap tercatat penuh di Riwayat Mutasi (badge
biru "Tester" membedakannya dari Restock/Jual). Harga Modal/Harga Jual
produk **disnapshot ke baris mutasi** (`harga_modal_saat_itu`/
`harga_jual_saat_itu`) setiap kali Jual/Tester dicatat -- diverifikasi
lewat pengujian: mengubah harga produk SEKARANG tidak mengubah angka
omzet bulan-bulan sebelumnya, transaksi baru otomatis pakai harga baru.

**Dashboard**: kartu baru **Penjualan Produk** (Dashboard Owner, mengikuti
filter bulan/tahun yang sudah ada) -- total omzet HANYA dari transaksi
Produk bertipe Jual (Restock bukan penjualan, Tester sengaja tidak
dihitung). Sengaja TIDAK diikutkan ke rumus Laba Kotor Toko yang sudah
ada (bukan diminta, rumus lama dipertahankan persis).

**Setting Bonus Service & Setting Uang Harian**: menghilangkan hardcode
lama (`SERVICE_UANG_HARIAN = {"Dry Cut", "Cut & Wash"}` di database.py,
dipakai untuk DUA keperluan berbeda sekaligus) -- diganti **DUA
pengaturan independen**: Setting > Bonus Service (acuan Target Bonus
Service bulanan) dan Setting > Uang Harian (acuan syarat cair Uang
Harian, >= 3 service/hari), masing-masing checklist seluruh service yang
bisa dipilih bebas oleh Owner. Mengubah salah satu TIDAK memengaruhi yang
lain (diverifikasi lewat pengujian: ubah acuan Uang Harian, konfirmasi
acuan Bonus Service tetap sama persis setelah reload). Disimpan sebagai
`service_id` (bukan nama) supaya tidak ikut berubah kalau nama service
diedit belakangan. Nilai awal KEDUA pengaturan di-seed otomatis dari
service "Dry Cut" + "Cut & Wash" yang sedang ada (migrasi idempotent) --
perilaku Uang Harian & Bonus Service yang sedang berjalan TIDAK BERUBAH
SEDIKIT PUN sampai Owner sengaja mengubahnya. Label di Dashboard Owner
("Progress Target Service") dan Dashboard Barber yang sebelumnya hardcode
teks "(Dry Cut + Cut & Wash)" sekarang mengikuti pilihan Owner secara
dinamis.

**Loading & Animasi**: proses Sign Out sekarang menampilkan loading
animation + teks "Sedang keluar dari aplikasi…" (jeda ~1 detik, tombol
Keluar dinonaktifkan selama proses) sebelum diarahkan ke halaman Login --
sebelumnya langsung pindah halaman tanpa umpan balik apa pun.
`MugenUI.withLoading()` diperluas menerima opsi `{ message, minMs }`
opsional (default tetap sama persis seperti sebelumnya -- tanpa teks,
jeda minimal 1,5 detik -- untuk SEMUA pemanggilan lama yang sudah ada).
Login, Booking, Simpan Data, Hapus Data, dan Transaksi Produk diaudit
menyeluruh dan sudah konsisten memakai `withLoading()` sejak PR
sebelumnya; satu celah ditemukan & diperbaiki (`booking.js`: menyimpan
Nama Merchant QRIS sebelumnya tidak memakai loading spinner sama sekali).

**Diuji menyeluruh** (16 pemeriksaan Playwright baru + regresi 25
pemeriksaan dari PR-PR sebelumnya, semua lolos): kartu Penjualan Produk
menampilkan angka benar, checklist Bonus Service/Uang Harian ter-seed
dari hardcode lama dan independen satu sama lain, tabel Produk
menampilkan Harga Modal/Harga Jual, tombol Tester berfungsi & badge-nya
tampil di Riwayat Mutasi, loading + teks + tombol nonaktif saat Sign Out
lalu redirect ke Login; migrasi diverifikasi idempotent lewat restart
server dengan data yang sudah ada (data byte-identik sebelum/sesudah);
regresi -- login, seluruh fitur Booking (termasuk animasi step & kartu
Booking Berhasil dari revisi sebelumnya), CRUD Barber, Setting lama, dan
alur booking publik end-to-end dikonfirmasi tetap berfungsi normal tanpa
error konsol maupun error backend.

`frontend/service-worker.js`: `CACHE_NAME` dinaikkan `v13` → `v14` untuk
`produk.js`/`dashboard_owner.js`/`dashboard_barber.js`/`pengaturan.js`/
`nav.js`/`ui.js`/`booking.js`/`style.css` yang berubah.


### CHANGELOG — REVISI UI/UX Modern: Tema Terang, Tipografi, Kartu/Tombol, Animasi, Watermark, Hapus Label RAFIQ

Penyempurnaan tampilan MENYELURUH (murni UI/UX, TIDAK ada logika bisnis
atau alur kerja yang berubah) -- satu-satunya file JS yang disentuh
adalah `pengaturan.js` (menghapus label RAFIQ, lihat di bawah); seluruh
perubahan lain murni `style.css`/`index.html`/`manifest.json`. Karena
arsitektur variabel CSS (`var(--accent)`, `var(--bg-card)`, dst) sudah
dipakai konsisten sejak Tahap 10, mengganti nilai token di satu tempat
(`:root`) otomatis menjalar ke SELURUH aplikasi TERMASUK Web Booking
(`book_public.js`) tanpa perlu menyentuh file JS halaman mana pun.

**Tema warna**: tema gelap + aksen emas sebelumnya diganti TOTAL dengan
tema terang, netral, profesional sesuai kode warna yang diminta --
Background `#F5F7FA`, Card `#FFFFFF`, Border `#E2E8F0`, Teks Utama
`#0F172A`, Teks Sekunder `#64748B`, Primary `#334155` (Hover `#1E293B`,
Pressed `#0F172A`), Success `#16A34A`, Danger `#DC2626`, Warning
`#EA580C`, Info `#2563EB` (dipakai badge "Tester" di Produk). Seluruh
warna hardcode lama yang mengasumsikan latar gelap (mis. teks `#1a1a1a`/
`#0a0a0a` di atas tombol/badge terang, tint `rgba(201,162,75,...)` gaya
emas) ikut diperbaiki supaya kontrasnya tetap benar di tema baru.

**Tipografi**: font stack diganti ke `Inter` dengan fallback sistem
modern (`-apple-system, Segoe UI, Roboto, ...` -- tanpa memuat font dari
CDN eksternal, supaya PWA tetap berfungsi penuh offline), hierarki
diperjelas (judul halaman & nominal kartu lebih besar/tebal, label lebih
kecil, letter-spacing disesuaikan).

**Kartu**: radius `16px`, border tipis, shadow lembut (`--shadow-card`),
padding lebih lega.

**Tombol**: radius `14px`, tinggi `48-52px` untuk tombol utama (Simpan,
Masuk, Konfirmasi Booking, dst). Tombol kecil di dalam tabel
(`.actions-cell`) & tab SENGAJA dipertahankan kompak (tidak ikut jadi
48px) supaya tabel data tidak jadi terlalu tinggi -- keputusan desain
yang tetap konsisten dengan pola compact-table-action yang sudah ada.
Efek tekan: scale 97%, shadow mengecil, warna sedikit lebih gelap
(`--accent-hover`/`--accent-pressed`), durasi 150ms.

**Loading**: spinner + teks proses (mis. "Sedang keluar dari
aplikasi…") dipertahankan SAMA PERSIS dari revisi sebelumnya, hanya
warna scrim & style disesuaikan ke tema baru -- sudah konsisten di
seluruh aplikasi dan Web Booking sejak revisi Sign Out sebelumnya.

**Animasi**: fade + slide ringan 12px, durasi ~220ms, dipakai lewat SATU
aturan CSS pada `.card`/`.login-card`/`.toast` (menjalar ke hampir
seluruh blok konten aplikasi tanpa perlu ubah JS satu per satu, tetap
menghormati `prefers-reduced-motion`). Animasi perpindahan step halaman
Booking (dari revisi sebelumnya, sebelumnya 36px/300ms) diselaraskan ke
parameter yang sama (12px/225ms) sesuai instruksi konsistensi.

**Watermark Developer**: watermark besar bertuliskan "Developer" di
background (opacity 0.03, sangat rendah) + watermark kecil "Powered by
Developer" di bagian bawah, KEDUANYA ditaruh di `index.html` DI LUAR
`#app` (root SPA) supaya tidak pernah ikut terhapus/tertimpa saat
halaman berpindah (setiap halaman hanya me-render ulang isi `#app`) dan
tidak ada jalan menonaktifkannya lewat menu Setting mana pun.

**Hapus Label RAFIQ**: checkbox "Barber RAFIQ" pada form Tambah/Ubah
Barber dan kolom "Rafiq" pada tabel Daftar Barber dihapus dari tampilan
(Setting > Barber). Kolom database `barbers.is_rafiq` dan nilai yang
sudah tersimpan pada barber manapun TIDAK disentuh sama sekali -- form
sekarang tidak mengirim field itu lagi (endpoint PUT memperlakukan field
yang tidak dikirim sebagai "jangan diubah", endpoint POST barber baru
tetap default `False` seperti sebelumnya), jadi data & logika lama
persis sama, hanya elemen visualnya yang hilang.

**Tanpa ikon baru**: tidak ada aset ikon baru ditambahkan (karakter
seperti "✓"/"‹"/"›"/"↑"/"↓" yang sudah dipakai sejak revisi-revisi
sebelumnya dipertahankan apa adanya, bukan ikon baru).

**Responsif**: breakpoint mobile (sidebar overlay + hamburger, sudah ada
sejak Tahap 13) dan tablet (`821px-1100px`, padding & grid kartu
disesuaikan) diuji ulang dengan tema baru, termasuk watermark besar yang
otomatis membesar di layar sempit.

**Diuji menyeluruh** (18 pemeriksaan Playwright baru -- warna/radius/
shadow/tinggi tombol/efek tekan sesuai token baru, watermark ada &
bertahan lintas-navigasi, label RAFIQ hilang tapi data barber tetap
utuh -- plus regresi 12 pemeriksaan lintas seluruh modul, semua lolos):
Dashboard, Setting (semua tab termasuk Bonus Service/Uang Harian baru
dari revisi sebelumnya), CRUD Barber, Produk (Tester), Booking internal,
alur booking publik end-to-end, dan Sign Out dikonfirmasi tampil dengan
tema baru DAN tetap berfungsi normal tanpa error konsol/backend; diuji
juga pada viewport mobile (390px) untuk memastikan sidebar/hamburger dan
tata letak tetap optimal.

`frontend/service-worker.js`: `CACHE_NAME` dinaikkan `v14` → `v15` untuk
`style.css`/`index.html`/`manifest.json`/`pengaturan.js` yang berubah.

### CHANGELOG — REVISI UI/UX: Dark Mode per Akun, Transisi Halaman, Animasi Login & Web Booking, Penyederhanaan Dashboard

Revisi UI/UX lanjutan (TANPA mengubah logika bisnis maupun menghapus data
yang sudah ada -- migrasi baru bersifat aditif, lihat `tampilan_migrasi.py`).

**Dark Mode & Light Mode per akun**: kolom baru `users.tema` (`'terang'`
default, migrasi idempotent lewat `tampilan_migrasi.py`, dipanggil dari
`main.py`) + endpoint `PUT /api/auth/tema` (`auth_router.py`/`auth_db.py`).
Preferensi tersimpan PER AKUN di server (bukan per-perangkat) supaya tetap
sama walau login dari perangkat lain, dengan cache lokal (`localStorage`)
sebagai lapis anti-flash sebelum data user selesai dimuat (`theme.js`
baru, `MugenTheme`). Palet gelap baru ditambahkan sebagai blok
`:root[data-theme="dark"] { ... }` di `style.css` (tidak mengganti token
terang yang sudah ada, hanya override tambahan), diaktifkan lewat atribut
`data-theme="dark"` di `<html>`. Switch modern (durasi 200ms, dalam
rentang 150-250ms yang diminta) ditaruh di **Setting > Tampilan** khusus
Owner/Admin (`pengaturan.js`, tab baru) dan di sidebar tepat di atas
tombol Keluar khusus Barber (`nav.js`, karena Barber tidak punya akses ke
menu Setting sama sekali). **Web Booking (`/book`) SENGAJA TIDAK mengikuti
Dark Mode** -- dipaksa tema terang lewat DUA lapis: `MugenTheme.forceLight()`
di `router.js` (titik masuk `#/book`) DAN di `book_public.js` sendiri,
plus lapis pertahanan CSS (`:root[data-theme="dark"] .book-public {...}`
meng-override ulang seluruh variabel ke nilai terang) supaya tetap benar
walau ada race condition SPA.

**Loading & Toast**: toast sukses/info DIHAPUS TOTAL (`ui.js`, `toast()`
jadi no-op kecuali `type === "error"` -- satu perubahan terpusat, bukan
menghapus tiap pemanggilan `toast(...,"success")` satu per satu di
puluhan file, supaya tidak ada yang terlewat). Spinner loading + teks
proses kontekstual (mis. "Menyimpan…", "Menghapus…", "Memproses
transaksi…", "Mengunggah…") ditambahkan ke hampir seluruh aksi yang
memanggil server yang sebelumnya belum punya teks (Login, Booking,
Simpan/Edit/Hapus di Setting/Input Data/Pengeluaran/Produk, Restock &
Transaksi Produk, Sinkronisasi) lewat parameter `opts.message` yang
sudah ada di `withLoading()` sejak revisi Sign Out sebelumnya -- tombol
tetap dinonaktifkan selama proses seperti sebelumnya, hanya kombinasi
teksnya yang diperkaya.

**Transisi antar menu**: Fade In murni opacity (300ms, dalam rentang
250-400ms) pada `<main class="content">` saja lewat satu aturan CSS
(`@keyframes mugen-content-fade-in`) -- `router.js` sudah selalu membuat
elemen `<main>` baru tiap navigasi lewat `shell()`, jadi tidak perlu
sentuhan JS tambahan. Sidebar TIDAK ikut animasi ini sama sekali.

**Animasi masuk halaman Login**: Slide+Fade pada logo, judul, dan form
(termasuk tombol Login) HANYA diputar saat aplikasi pertama dibuka atau
tepat setelah Logout -- BUKAN di trigger lain seperti sesi kedaluwarsa.
Dikendalikan lewat penanda in-memory `MugenState.markLoginEntrance()` /
`consumeLoginEntrance()`: `router.js` menandainya sekali di panggilan
`handle()` PERTAMA (hanya kalau saat itu belum ada sesi tersimpan sama
sekali), `nav.js` menandainya lagi tepat sebelum redirect setelah
Logout, dan `login.js` membaca+mereset penanda itu tiap kali dirender
(class `.login-entrance` ditambahkan secara kondisional). Sesi kedaluwarsa
(redirect otomatis dari `api.js` saat 401) TIDAK pernah menandai ini,
jadi Login yang muncul akibat sesi habis tampil tanpa animasi masuk.

**Halaman Awal Web Booking**: sebelum wizard booking (Step 1-7 yang
SUDAH ADA, TIDAK diubah logikanya, sekarang berada di `renderWizard()`),
ditambahkan layar awal baru (`render()`) berupa HANYA satu tombol besar
bertuliskan "BOOKING" (tanpa logo). Tombol "terbang" cepat (900ms) dari
sudut layar menuju tengah lewat lintasan berbentuk Z (`@keyframes
book-intro-fly` di `style.css`, kombinasi `transform: translate()` +
`filter: blur()` yang memuncak saat bergerak cepat lalu hilang begitu
berhenti di tengah, plus `text-shadow` sebagai jejak kecepatan/motion
trail) -- tombol dinonaktifkan sampai animasi selesai supaya tidak bisa
ditekan di tengah jalan. Setelah ditekan, layar awal memudar (220ms) dan
wizard booking muncul dengan Slide+Fade (`.book-wizard-enter`). Semua
animasi ini menghormati `prefers-reduced-motion` (langsung tampil diam
di tempat kalau diaktifkan). Halaman ini tetap dipaksa tema terang sama
seperti sebelumnya.

**Dashboard Owner**: judul & deskripsi/progress bonus pada bagian
"Service Bulan Ini" dihapus dari tampilan (data & logika perhitungan
bonus TIDAK dihapus dari backend -- tetap bisa dilihat di Dashboard
Barber & Setting > Bonus Service), HANYA dropdown barber dan tabel
Service/Jumlah yang dipertahankan, dengan judul baru huruf besar
"SERVICE BULAN INI" langsung di atas tabel. Header kolom "Customer" pada
tabel "Per Barber" diganti jadi "Service" (murni label tampilan -- kunci
data `jumlah_customer` dan nilainya tidak berubah sama sekali).

**Kompatibilitas & pengujian**: migrasi database aditif (tidak menghapus
kolom/tabel/data lama), tidak ada logika bisnis yang berubah. Diuji
menyeluruh lewat Playwright: Dark Mode tersimpan per akun (bertahan
lintas navigasi & reload penuh, terverifikasi lewat database), switch
tampil di tempat yang benar sesuai role (Setting > Tampilan untuk Admin,
sidebar untuk Barber; dikonfirmasi dengan login sebagai kedua role),
Web Booking dikonfirmasi TETAP terang walau akun Owner sedang Dark Mode,
toast sukses hilang total tapi toast error tetap tampil, aksi Simpan
(mis. Tambah Barber) dikonfirmasi tetap benar-benar tersimpan (data
mutasi tidak terganggu oleh penghapusan toast), animasi masuk Login
terkonfirmasi TIDAK muncul saat sesi kedaluwarsa tapi MUNCUL saat
aplikasi pertama dibuka & setelah Logout, animasi awal Web Booking
(terbang + motion blur + settle di tengah) dan transisi ke wizard
terverifikasi lewat tangkapan layar, serta regresi menyeluruh ke seluruh
menu (Dashboard, Input Data, Rekap, Booking, Pengeluaran, Produk,
Sinkronisasi, Setting) tanpa error konsol/backend.

`frontend/service-worker.js`: `CACHE_NAME` dinaikkan `v15` → `v16` untuk
seluruh file JS/CSS yang berubah (lihat komentar changelog di file
tersebut untuk daftar lengkap), termasuk file baru `js/theme.js`.

### CHANGELOG — Revisi Struktur Setting (Final): Komisi/Bonus Service/Layanan/Uang Harian, Notifikasi Booking Baru

Perapihan menu Setting supaya lebih sederhana, konsisten, dan fleksibel
(TANPA menghapus database/histori/data lama -- migrasi baru bersifat
aditif, lihat `revisi_setting_migrasi.py`), ditambah fitur baru Notifikasi
Booking Baru.

**Tab Komisi** (sebelumnya "Komisi & Bonus"): disederhanakan jadi HANYA
Persentase Komisi, Maksimal Hari Libur (utk Bonus Customer), dan Potongan
Bonus jika Libur Melebihi Batas. Target Bonus Service (tier bertingkat)
dipindah seluruhnya ke tab Bonus Service.

**Tab Bonus Service**: sekarang pusat SELURUH pengaturan bonus -- checklist
service acuan (sudah ada sebelumnya) DIGABUNG dengan Target Bonus Service
(tier bertingkat, dipindah dari tab Komisi) dalam satu tab. Teks hardcoded
"Dry Cut + Cut & Wash" pada subtitle dihapus (sudah sepenuhnya bisa
dikonfigurasi Owner sejak revisi sebelumnya, di sini murni rapikan sisa
teksnya).

**Tab Layanan & Potongan Modal Chemical**: field "Potongan Modal Chemical"
(select per-service + setting global `potongan_modal_chemical`) DIHAPUS
dari form/tabel Layanan dan dari Tab Komisi. Field "Modal" yang sudah ada
sejak Tahap 10 (sebelumnya murni tampilan, TIDAK memengaruhi komisi sama
sekali -- lihat komentar lama di `pengaturan_service.py`) sekarang benar-
benar DIPAKAI sebagai "Harga Modal" di rumus komisi: `hitung_komisi_service`
di `database.py` diubah dari skema lama (nama service tertentu dikecualikan
dari potongan chemical global) menjadi `(Harga - Harga Modal) x Persentase
Komisi`, dengan Harga Modal boleh dikosongkan (dianggap Rp0). Supaya
NOMINAL KOMISI YANG SEDANG BERJALAN TIDAK BERUBAH SEDIKIT PUN akibat
pergantian skema ini, `revisi_setting_migrasi.py` melakukan backfill
SEKALI SAJA (dijaga idempotent lewat setting penanda, bukan re-cek modal
== 0 -- supaya aman kalau Owner nanti sengaja mengembalikan modal suatu
layanan ke 0): setiap layanan yang SEBELUM revisi ini memang dikenai
potongan chemical (menurut aturan lama) DAN modal-nya masih 0 (belum
pernah diisi Owner untuk keperluan lain) di-set modal-nya sama dengan
nilai Potongan Modal Chemical lama -- diverifikasi hasil komisinya SAMA
PERSIS sebelum & sesudah migrasi lewat pengujian langsung. Tabel Layanan
mendapat kolom baru "Nilai Komisi Barber" (murni tampilan, dihitung
otomatis dari Harga/Harga Modal/Persentase Komisi saat itu) supaya Owner
bisa langsung melihat komisi tiap layanan tanpa hitung manual.

**Tab Uang Harian**: target jumlah service/hari supaya Uang Harian cair
(sebelumnya hardcode 3 di `database.py`) sekarang punya field tersendiri
("Target Jumlah Service Harian") yang bisa diatur bebas Owner lewat
endpoint baru `/api/pengaturan/uang-harian-target` -- default tetap 3
(di-seed lewat migrasi) supaya nominal yang sedang berjalan tidak berubah
sampai Owner sengaja menggantinya. Teks hardcoded "cair kalau Dry Cut +
Cut & Wash hari itu >= 3" dihapus dari UI.

**Dashboard Barber**: baris pertama Progress Target Service disederhanakan
dari `"{n} service (Nama Layanan) bulan ini."` menjadi `"{n} service
memenuhi target bonus bulan ini."` (tidak lagi menyebut nama service acuan
secara eksplisit, sejalan dengan seluruh aturan yang sudah bisa
dikonfigurasi Owner).

**Notifikasi Booking Baru** (fitur baru, khusus Admin/Owner -- hanya Admin
yang bisa verifikasi/batalkan booking):
- **Badge menu Booking**: menampilkan jumlah booking yang belum
  dikonfirmasi (`status_pembayaran='menunggu_verifikasi'` dan
  `status_booking='aktif'`), bertambah otomatis saat ada booking baru,
  berkurang setelah dikonfirmasi/dibatalkan, hilang total kalau semua
  sudah dikonfirmasi. Real-time TANPA reload dicapai lewat POLLING ringan
  (endpoint baru `GET /api/booking/belum-dikonfirmasi`, satu angka
  `COUNT(*)`) setiap 15 detik selama aplikasi terbuka (dimulai app-wide
  dari `app.js`, TIDAK terikat ke halaman Booking manapun), plus refresh
  seketika setelah Login dan setelah aksi Verifikasi/Batalkan supaya badge
  tidak perlu menunggu jadwal poll berikutnya.
- **Notifikasi suara**: diputar SATU KALI saat jumlah booking belum
  dikonfirmasi bertambah (bukan di poll pertama setelah Login/buka
  aplikasi -- supaya tunggakan booking lama tidak dikira "baru masuk").
  Selama masih ada booking belum dikonfirmasi, bunyi pengingat diputar
  ulang tiap 1 menit dan otomatis berhenti begitu semuanya sudah
  dikonfirmasi. SATU jenis bunyi dipakai baik untuk satu maupun banyak
  booking tertunggak sekaligus.
- **Karakter suara**: TIDAK ADA akses legal untuk menyertakan file suara
  asli iPhone (aset berhak cipta Apple) di dalam aplikasi ini, jadi suara
  disintesis LANGSUNG lewat Web Audio API (`js/booking_notif.js`, dua nada
  lonceng sine wave menaik dengan amplop volume landai) yang meniru
  KARAKTERNYA (lembut, jernih, elegan, durasi sedikit lebih panjang ~1
  detik) tanpa menyalin melodi/aset asli apa pun -- konsisten dengan
  filosofi PWA ini yang lain (grafik SVG, animasi CSS) yang tidak memuat
  aset eksternal, tetap berfungsi offline.

**Bugfix yang ditemukan & diperbaiki saat pengujian**: `MugenRouter` di
`router.js` sebelumnya HANYA mengekspos `init` (bukan `handle`), padahal
`login.js` sudah lama memanggil `MugenRouter.handle()` secara eksplisit
untuk edge-case saat hash URL sudah persis `#/dashboard` sehingga event
`hashchange` tidak akan terpicu (lihat komentar di `login.js`). Panggilan
itu selalu melempar `TypeError` diam-diam (langsung tertangkap try/catch
`login.js`, tidak pernah terlihat sebagai error nyata di konsol) dan kode
APA PUN yang diletakkan setelah baris itu di `login.js` tidak pernah
sempat berjalan -- selama ini "diselamatkan" secara visual oleh fallback
listener `hashchange` untuk kasus normal (hash yang benar-benar berubah),
sehingga bug ini tidak pernah terlihat sampai fitur refresh-badge-setelah-
login di atas butuh baris kode SETELAH `MugenRouter.handle()` benar-benar
tereksekusi. Diperbaiki dengan mengekspos `handle` di `return` `router.js`.

**Diuji menyeluruh**: kontinuitas komisi diverifikasi backend-level
(sebelum & sesudah migrasi menghasilkan nominal identik untuk service
contoh), seluruh tab Setting yang direstrukturisasi diuji lewat Playwright
(label field, teks hardcoded hilang, nilai tersimpan benar), Layanan diuji
kolom Nilai Komisi Barber menghitung benar, Uang Harian diuji target bisa
diubah & tersimpan, badge Booking diuji real-time (booking baru dari
endpoint publik terdeteksi tanpa reload, badge app-wide tetap tampil di
halaman lain, hilang setelah dikonfirmasi) DAN notifikasi suara diuji
terpicu tepat satu kali saat booking baru masuk (diinstrumentasi lewat
Web Audio API), serta regresi menyeluruh ke seluruh menu tanpa error
konsol/backend.

`frontend/service-worker.js`: `CACHE_NAME` dinaikkan `v16` → `v17` untuk
file baru `js/booking_notif.js` dan seluruh file JS/CSS yang berubah.

### AUDIT & PERBAIKAN: Sinkronisasi Data Antar Device

Laporan: login dengan akun yang sama di dua device, data KADANG sinkron,
KADANG tidak. Audit menyeluruh dilakukan terhadap seluruh jalur penyimpanan
& pengambilan data (SQLite, localStorage, Service Worker, header HTTP,
endpoint FastAPI). Ditemukan **dua penyebab konkret** (dibuktikan lewat
kode, bukan dugaan) yang SAMA-SAMA cocok dengan gejala "kadang, tidak
selalu" -- keduanya diperbaiki secara permanen di revisi ini, plus satu
faktor arsitektur (di luar kendali kode aplikasi) yang harus diverifikasi
langsung oleh Owner di pengaturan hosting.

#### Penyebab #1 (bug kode, DIPERBAIKI): banner "sedang offline" tidak konsisten dipasang

`js/api.js` (`MugenApi.get(..., {useCache:true})`) SUDAH punya mekanisme
fallback yang benar sejak lama: kalau `fetch()` ke server gagal karena
jaringan (`catch (networkErr)`, BUKAN respons error dari server), data
GET terakhir yang berhasil diambil disimpan di `localStorage` (per
device/browser) dipakai sebagai fallback, ditandai `__offline: true` +
`__cachedAt`. Pola yang benar (dipakai konsisten di `dashboard_owner.js`,
`dashboard_barber.js`, `rekap.js`, `input_data.js`, `pengeluaran.js`,
`produk.js`) adalah menampilkan `MugenUI.offlineBanner(data.__cachedAt)`
setiap kali flag ini `true`, supaya user TAHU sedang melihat data lama.

**Bukti**: `booking.js` (Booking List, Calendar, Toko Libur, Barber
Holiday, Closed Slot, "Booking Saya" untuk Barber -- 6 titik fetch, SEMUA
memakai `useCache:true`) dan grafik harian/bulanan di `dashboard_owner.js`
TIDAK PERNAH memeriksa flag ini sama sekali (`grep __offline` di
`booking.js` sebelum revisi ini: 0 hasil, padahal `useCache:true` muncul
7 kali). Akibatnya: begitu koneksi jaringan device tertentu putus SESAAT
sekalipun (umum terjadi di jaringan seluler/WiFi toko yang naik-turun),
device itu diam-diam menampilkan data booking/grafik LAMA dari cache
lokalnya sendiri TANPA tanda apa pun -- terlihat persis seperti "device
ini belum menerima booking baru yang sudah dibuat dari device lain",
padahal sebenarnya cuma cache lokal yang belum sempat diperbarui. **Ini
menjelaskan kenapa "kadang" (bergantung kapan tepatnya jaringan sempat
putus) dan kenapa Booking module yang paling sering dikeluhkan (data
paling sering berubah, paling sering dibuka dari lebih dari satu
device).** Diperbaiki: seluruh 6 titik fetch di `booking.js` dan 2 grafik
di `dashboard_owner.js` sekarang konsisten menampilkan `offlineBanner`
(diverifikasi lewat Playwright: mensimulasikan jaringan gagal ->
banner merah "Sedang offline — menampilkan data tersimpan terakhir
(...)" langsung muncul, sebelumnya tidak muncul sama sekali).

#### Penyebab #2 (bug kode, DIPERBAIKI): SQLite tanpa mode WAL rentan "database is locked" saat diakses bersamaan

`database.py` (`get_conn()`, dipakai SELURUH modul lewat satu titik yang
sama -- `auth_db.py`/`booking_db.py`/`pengeluaran_db.py`/`sync_meta_db.py`
semuanya membuka file `.db` YANG SAMA) sebelumnya membuka SQLite dengan
mode jurnal default (rollback journal) TANPA `busy_timeout` eksplisit.
Di bawah mode itu, SETIAP transaksi tulis (Simpan/Edit/Hapus apa pun)
mengunci SELURUH file database -- koneksi lain (baik untuk membaca
MAUPUN menulis, dari device lain yang kebetulan memanggil API di detik
yang sama, TERMASUK polling badge notifikasi booking setiap 15 detik yang
berjalan otomatis dari REVISI sebelumnya) harus menunggu, dan kalau lebih
lama dari 5 detik (default Python) akan gagal dengan error
`database is locked` -- request itu gagal dengan HTTP 500. **Ini
menjelaskan kenapa "kadang" (hanya terjadi kalau dua request kebetulan
tumpang tindih persis di waktu yang sama) dan kenapa gejalanya baru
terasa setelah dipakai dari DUA device sekaligus (jauh lebih sering ada
dua request bersamaan dibanding satu device sendirian).** Diperbaiki:
`get_conn()` di `database.py` DAN salinannya di `auth_db.py` sekarang
mengaktifkan `PRAGMA journal_mode = WAL` (penulis TIDAK memblokir
pembaca sama sekali, hanya penulis-vs-penulis yang masih bergiliran --
jauh lebih jarang) + `busy_timeout` dinaikkan ke 30 detik sebagai jaring
pengaman tambahan. Diverifikasi lewat stress test 60 request
baca+tulis bersamaan (30 PUT + 30 GET ke endpoint yang sama, dari thread
paralel) -- SEBELUMNYA berisiko `database is locked`, SESUDAHNYA seluruh
60 request selesai dalam 0,3 detik tanpa satu pun error.

#### Faktor arsitektur (PERLU DIVERIFIKASI Owner, di luar kendali kode)

SQLite adalah database **satu file**, bukan server terpusat -- konsekuensi
langsungnya (sudah diperingatkan di README bagian **Deployment** sejak
awal): kalau backend di-deploy dengan (a) **disk yang TIDAK persisten**
(isi hilang tiap container restart/redeploy) dan/atau (b) **lebih dari
satu instance sekaligus** (mis. Render "Number of Instances" > 1), maka
device yang berbeda BISA jadi sedang bicara dengan SALINAN file database
yang BERBEDA -- inilah kelas penyebab paling parah untuk "kadang sinkron
kadang tidak" (bukan cuma tampilan yang basi seperti Penyebab #1, tapi
data yang BENAR-BENAR berbeda di server). Kode aplikasi ini TIDAK bisa
memverifikasi/memperbaiki pengaturan hosting dari dalam dirinya sendiri,
tapi revisi ini menambahkan alat diagnostik supaya Owner bisa
MEMBUKTIKANNYA LANGSUNG:

- `GET /api/health` (publik, tanpa login) sekarang menyertakan
  `instance_id` (dibuat sekali per proses backend, acak) dan `boot_time`.
  **Cara pakai**: buka endpoint ini dari device A dan device B secara
  bersamaan (atau buka dua kali berturut-turut dalam beberapa detik) --
  kalau `instance_id` BERBEDA, itu bukti ada lebih dari satu instance
  backend berjalan. Kalau `boot_time` berubah setiap dicek ulang padahal
  tidak ada deploy baru yang disengaja, itu bukti disk TIDAK persisten
  (proses restart sendiri, data ikut ter-reset ke default).
- `GET /api/health/diagnostik` (khusus admin/login) menambahkan
  `db_path`, `db_size_bytes`, `db_mtime`, dan `jumlah_baris` (hitungan
  baris tabel `users`/`barbers`/`transaksi`/`bookings`). Device A dan
  device B HARUS melihat angka `jumlah_baris` yang SAMA PERSIS kalau
  memang satu database yang sama -- kalau berbeda, itu bukti langsung
  kedua device bicara dengan salinan database yang berbeda.

Kalau `instance_id` atau `jumlah_baris` ternyata berbeda antar device:
periksa pengaturan Render (dashboard) -- pastikan **Number of Instances =
1** dan **Persistent Disk terpasang, di-mount tepat ke folder
`backend/app/`** (lihat bagian **Deployment (Produksi)** di atas, sudah
diperingatkan sejak awal). Ini murni konfigurasi platform hosting, tidak
ada baris kode yang bisa memperbaikinya dari sisi aplikasi.

#### Yang sudah diperiksa dan DIPASTIKAN BUKAN penyebab

- **Service Worker**: `/api/*` sudah 100% dibiarkan lewat tanpa disentuh
  cache Service Worker sama sekali sejak awal (`service-worker.js`,
  `if (url.pathname.startsWith("/api/")) return;`) -- dikonfirmasi ulang,
  bukan sumber masalah. Ditambahkan lapis pertahanan HTTP tambahan (lihat
  di bawah) sebagai jaga-jaga, bukan karena ditemukan bug di sini.
- **Race condition simpan-lalu-baca**: diaudit satu per satu seluruh
  handler tombol Simpan/Edit/Hapus di semua halaman -- polanya SUDAH
  benar (tunggu respons sukses lewat `await`, baru panggil ulang fungsi
  refresh data) di hampir semua tempat. Ditemukan SATU celah kecil:
  `produk.js` menambah/mengubah produk sudah me-refresh tabel Daftar
  Produk, tapi dropdown filter "Riwayat Mutasi" baru ikut ter-refresh
  setelah halaman dibuka ulang -- diperbaiki (dipanggil ulang di titik
  yang sama).
- **Sesi/token ganda**: token login (itsdangerous, `auth.py`) sengaja
  STATELESS (tidak disimpan di server) -- login dari device kedua TIDAK
  membatalkan token device pertama, keduanya tetap valid independen.
  Bukan sumber masalah.
- **Commit transaksi SQLite**: `get_conn()` sudah benar (commit hanya
  kalau blok `with` selesai tanpa exception, rollback otomatis kalau
  gagal) -- tidak ditemukan write yang silently gagal tanpa exception.

#### Perubahan tambahan (pengerasan/hardening, bukan bug tapi lapis pertahanan)

- **`Cache-Control: no-store`** ditambahkan ke SETIAP respons `/api/*`
  (middleware baru `_log_dan_no_store` di `main.py`) -- sebelumnya tidak
  ada header cache sama sekali (browser modern umumnya sudah tidak agresif
  meng-cache respons tanpa header semacam ini, tapi eksplisit lebih aman
  daripada bergantung pada perilaku default).
- **Logging terstruktur** setiap request `/api/*` (method, path, status,
  durasi, `instance_id`) ke stdout lewat modul `logging` bawaan Python --
  Render (atau hosting lain) menangkap stdout sebagai log platform secara
  otomatis. Kalau ada laporan "data tidak tersimpan" berikutnya, log ini
  bisa langsung menunjukkan apakah request-nya benar-benar sampai ke
  server, berhasil, atau gagal (dan durasinya -- durasi tinggi bisa jadi
  tanda kontensi lock database).

**Catatan untuk Desktop app**: perubahan `get_conn()` (WAL mode) di
`database.py` murni konfigurasi KONEKSI (bagaimana file dibuka), BUKAN
perubahan rumus/logika bisnis apa pun -- tidak perlu disamakan ke
aplikasi Desktop (yang notabene cuma dipakai satu proses/user pada satu
waktu, jadi tidak mengalami masalah konkurensi yang sama).

`frontend/service-worker.js`: `CACHE_NAME` dinaikkan `v17` → `v18`.

### AUDIT KRITIS: Seluruh Data Kembali ke Kondisi Instalasi Baru Setelah Restart

Laporan lanjutan (lebih parah dari audit sinkronisasi di atas): setelah
login, SELURUH data (transaksi, setting, password yang sudah diubah)
kembali seperti instalasi baru sama sekali -- bukan lagi "kadang beda
antar device", tapi database di server benar-benar KOSONG.

**Batasan investigasi ini (penting, harus disampaikan jujur)**: sesi
audit ini berjalan di lingkungan sandbox yang TIDAK punya akses jaringan
ke backend production (`mugen-hair-api.onrender.com` diblokir kebijakan
egress sandbox) -- tidak bisa membaca log Render, dashboard Render, atau
database production secara langsung. Kesimpulan di bawah ini murni dari
**bukti kode** (bagaimana aplikasi ini pasti berperilaku, dibuktikan lewat
pembacaan source code dan pengujian lokal), BUKAN dari log production
sungguhan -- Owner perlu menjalankan langkah verifikasi di bagian paling
bawah section ini untuk memastikan dari sisi Render.

#### Bukti dari kode: kenapa ini PASTI terjadi kalau disk tidak persisten

`database.py`:
```python
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mugen_hair.db")
```
Path database dihitung RELATIF terhadap lokasi source code (`backend/app/`)
itu sendiri -- bukan folder terpisah yang sengaja dipisah dari kode.
`.gitignore` sudah benar mengecualikan `mugen_hair.db` dari git (memang
seharusnya begitu, isinya data asli toko) -- tapi konsekuensinya: **file
ini TIDAK PERNAH ikut ter-deploy dari git**. Setiap deploy (auto-deploy
Render saat ada push/merge ke branch yang di-deploy, restart manual,
maupun restart otomatis platform) menjalankan ulang `on_startup()` di
`main.py`:

```python
db.init_db()          # CREATE TABLE IF NOT EXISTS -- tabel baru = ISI KOSONG
...
_bootstrap_admin_pertama()   # tabel users kosong -> buat admin BARU dari
                              # ADMIN_BOOTSTRAP_USERNAME/PASSWORD (default:
                              # "owner" / "ganti-password-ini")
```

Kalau folder `backend/app/` tempat file `.db` ini seharusnya hidup TIDAK
di-mount ke **Persistent Disk** Render (sudah diperingatkan eksplisit di
README bagian **Deployment (Produksi)** sejak awal proyek ini ditulis),
maka SETIAP deploy/restart mendapat filesystem KOSONG dari awal --
`init_db()` membuat tabel-tabel baru yang isinya kosong (bukan menimpa
data lama, tapi karena file lama memang sudah tidak ada), dan
`_bootstrap_admin_pertama()` otomatis membuat akun admin BARU dengan
password DEFAULT -- **ini PERSIS cocok dengan seluruh gejala yang
dilaporkan**: transaksi hilang (tabel baru, kosong), setting kembali
default (tabel `settings` baru, diisi ulang dari `DEFAULT_SETTINGS` lewat
`INSERT OR IGNORE`), dan password kembali ke awal (akun admin baru dibuat
dari environment variable default, BUKAN password yang sudah diubah
Owner sebelumnya lewat Setting > User -- akun LAMA beserta hash password
barunya sudah tidak ada lagi sama sekali di tabel `users` yang baru).

**Timeline yang cocok**: dua PR sebelumnya (perbaikan sinkronisasi &
restrukturisasi Setting) baru saja di-merge ke `master` -- kalau Render
mengaktifkan auto-deploy dari branch itu, kedua merge tsb masing-masing
memicu deploy baru (container baru). Kalau disk tidak persisten, deploy
itulah momen datanya ter-reset.

#### Kemungkinan kedua (lebih jarang, tapi juga cocok untuk gejala password): `ADMIN_RESET_USERNAME`/`ADMIN_RESET_PASSWORD` masih terisi

`main.py` (`_reset_admin_darurat`) punya mekanisme break-glass yang
SUDAH ADA sejak awal: kalau DUA environment variable ini diisi eksplisit
di Render, SETIAP restart akan mereset password admin ke nilai yang sama
persis -- didokumentasikan sejak awal ("kalau dibiarkan, TIAP KALI server
restart akan mereset ulang ke password yang sama"). Kalau Owner (atau
siapa pun) pernah memakai mekanisme darurat ini dan LUPA menghapus kedua
env var itu dari Render setelah berhasil login, gejala "password kembali
ke password awal" bisa disebabkan MURNI oleh ini -- TANPA database
kosong sama sekali (transaksi/setting harusnya tetap utuh kalau ini
penyebabnya, HANYA password admin yang kembali).
**Cara membedakan dari Penyebab #1 di atas**: kalau transaksi & setting
JUGA hilang, itu Penyebab #1 (disk tidak persisten). Kalau HANYA
password yang kembali tapi transaksi/setting tetap ada, itu Penyebab #2
(env var darurat masih terisi) -- solusinya tinggal hapus
`ADMIN_RESET_USERNAME`/`ADMIN_RESET_PASSWORD` dari Environment Variables
di dashboard Render.

#### Yang SUDAH dipastikan BUKAN penyebab (diperiksa langsung di kode)

- **Tidak ada kode yang menghapus/mengganti file database secara
  otomatis.** Diperiksa SELURUH kode backend untuk `os.remove`/
  `os.unlink`/`shutil.rmtree`/`DROP TABLE` yang menyentuh file `.db` --
  nihil. Satu-satunya kode yang MENGGANTI isi file database adalah
  `pengaturan_backup.py` (`import_database`, endpoint
  `POST /api/pengaturan/backup/import`) -- ini BUTUH aksi eksplisit admin
  (login + upload file .db + klik "Restore Database" di menu
  Sinkronisasi/Setting), TIDAK bisa terpicu otomatis/diam-diam, dan
  bahkan endpoint ini SELALU membuat backup file yang sedang aktif dulu
  sebelum menimpanya. Kalau ini yang terjadi, cek folder
  `backend/app/backups/` di server (kalau kebetulan ikut persisten) untuk
  file `mugen_hair_sebelum_import_*.db`.
- **`init_db()` tidak menimpa data yang sudah ada** -- seluruhnya memakai
  `CREATE TABLE IF NOT EXISTS` dan `INSERT OR IGNORE`, aman dipanggil
  berkali-kali pada database yang SUDAH BERISI data (diverifikasi lewat
  pengujian lokal: restart proses pada database yang sudah ada data tidak
  mengubah satu baris pun, lihat bagian "BOOT: file database SUDAH ADA"
  di bawah). Masalahnya BUKAN "init_db() menimpa data", tapi "file
  database itu sendiri sudah tidak ada lagi sebelum init_db() sempat
  jalan".
- **Migrasi (`revisi_setting_migrasi.py` dkk) tidak menghapus apa pun** --
  seluruhnya idempotent, dijaga penanda (lihat kode masing-masing file
  `*_migrasi.py`), tidak ada satu pun yang men-drop tabel atau menghapus
  baris.

#### Perbaikan yang diterapkan: logging boot yang tidak bisa dilewatkan

Kode aplikasi TIDAK BISA memaksa Render memasang Persistent Disk -- itu
murni pengaturan platform hosting, di luar kendali source code. Yang BISA
dilakukan: memastikan kejadian ini TIDAK PERNAH lagi terjadi tanpa jejak
yang jelas. `main.py` (`on_startup()`) sekarang mencatat, SEBELUM
`init_db()` sempat dipanggil sama sekali:

- Kalau file `.db` **sudah ada**: log `INFO` singkat "melanjutkan data
  yang sudah ada" (kondisi normal, tidak mengkhawatirkan).
- Kalau file `.db` **tidak ditemukan**: log `CRITICAL` yang menjelaskan
  PERSIS apa yang akan terjadi dan kenapa (disk tidak persisten), dengan
  path lengkap yang dipakai.

`_bootstrap_admin_pertama()` (pembuatan akun admin baru) dan
`_reset_admin_darurat()` (reset password lewat env var darurat) SEKARANG
JUGA mencatat log `CRITICAL` setiap kali benar-benar jalan (sebelumnya
`_bootstrap_admin_pertama()` sama sekali tidak mencatat apa-apa, dan
`_reset_admin_darurat()` cuma `print()` biasa) -- di instalasi yang sehat,
kedua fungsi ini HARUSNYA nyaris tidak pernah terlihat di log setelah
setup awal; begitu terlihat lagi, itu sendiri sudah jadi bukti insiden.
Ditutup dengan log ringkasan jumlah baris tabel inti (`users`, `barbers`,
`transaksi`, `bookings`) di akhir tiap boot, supaya riwayat log Render
bisa dibandingkan dari waktu ke waktu.

Diverifikasi lewat dua skenario pengujian lokal (file `.db` dihapus vs
dipertahankan sebelum restart) -- log yang dihasilkan PERSIS sesuai
rancangan di atas untuk kedua kondisi.

#### LANGKAH YANG PERLU Owner lakukan (tidak bisa diselesaikan dari kode)

1. **Cek Render Dashboard > (nama service backend) > Settings > Disks.**
   Pastikan ADA persistent disk terpasang, dan **Mount Path**-nya
   menunjuk tepat ke folder tempat kode ini berjalan (biasanya sesuatu
   seperti `/opt/render/project/src/backend/app`, sesuaikan dengan Start
   Command yang dipakai) -- BUKAN folder lain atau kosong. Kalau belum
   ada, tambahkan (Render: New Disk, minimal 1GB cukup untuk SQLite skala
   satu barbershop), redeploy, lalu masukkan kembali data lewat Restore
   Database (kalau punya file backup lama) atau input manual.
2. **Cek Render Dashboard > Settings > Environment.** Cari
   `ADMIN_RESET_USERNAME`/`ADMIN_RESET_PASSWORD` -- kalau ADA isinya,
   HAPUS keduanya (ini kemungkinan #2 di atas untuk gejala password).
3. **Cek Render Dashboard > Settings.** Pastikan **Number of Instances =
   1** (relevan untuk audit sinkronisasi sebelumnya juga).
4. Setelah disk persisten terpasang dengan benar, buka
   `GET /api/health` dari browser BEBERAPA KALI dengan jeda -- `boot_time`
   HARUS tetap sama selama tidak ada deploy baru yang disengaja. Kalau
   berubah sendiri, disk masih belum persisten dengan benar.
5. **Soal data yang sudah hilang**: kode aplikasi ini tidak bisa
   mengembalikan data yang sudah benar-benar tertimpa di server. Cek dua
   kemungkinan pemulihan:
   - File `.db` di folder `backend/app/backups/` di server (dibuat
     otomatis setiap kali ada yang pakai fitur Restore Database) -- kalau
     kebetulan folder ini ikut berada di disk yang sama yang baru saja
     hilang, ini juga sudah tidak ada.
   - Google Sheets, KALAU fitur Sinkronisasi sempat aktif & berhasil
     sebelum insiden ini (cek menu Sinkronisasi > Status Sinkronisasi,
     atau langsung buka spreadsheet-nya kalau tahu link-nya) -- tab
     `transaksi`/`pengeluaran`/`produk`/`produk_mutasi` di sana berisi
     snapshot data SAAT sinkron terakhir berhasil (CATATAN: sinkronisasi
     ini TIDAK menyertakan `settings`/`barbers`/`users`/`bookings`, jadi
     paling banter cuma sebagian data yang bisa dipulihkan dari sini).


## TAHAP Migrasi PostgreSQL (Neon) — Implementasi (BELUM cutover)

Menindaklanjuti "AUDIT KRITIS" di atas (root cause: Render Free instance
tidak mendukung Persistent Disk sama sekali), Owner menyetujui migrasi ke
PostgreSQL terkelola (Neon) sebagai solusi jangka panjang, dikerjakan di
branch terpisah dengan aturan ketat: jangan deploy ke Render dulu, jangan
ubah frontend/endpoint/format JSON, SQLite tetap berfungsi penuh sampai
migrasi benar-benar selesai, backup SQLite sebelum mulai, dan **tidak ada
cutover** sampai Owner memeriksa seluruh implementasi ini dan menyetujuinya.

### Arsitektur

Dialek database aktif ditentukan SATU environment variable, `DATABASE_URL`:
- **Kosong (default)** -> SQLite, 100% seperti sebelumnya. `psycopg2` tidak
  pernah diimpor sama sekali di jalur ini.
- **Diisi** -> PostgreSQL, lewat connection pool + lapisan kompatibilitas.

File baru `backend/app/db_compat.py` adalah satu-satunya tempat yang tahu
soal psycopg2. Ia menyediakan `get_conn()` versi PostgreSQL yang:
- Menerjemahkan placeholder `?` -> `%s` (sadar string literal, bukan regex naif).
- Meng-emulasi `cursor.lastrowid` (tidak ada secara native di psycopg2) lewat
  otomatis menambahkan `RETURNING *` pada setiap `INSERT` tanpa `RETURNING`
  eksplisit, lalu mengambil kolom `id` dari hasilnya KALAU ADA (aman untuk
  tabel `settings`/`sync_meta` yang primary key-nya `key`, bukan `id`).
- Rollback otomatis kalau ada exception di dalam blok `with get_conn()`
  (penting di PostgreSQL: satu error yang tidak di-rollback akan membuat
  SELURUH transaksi berikutnya gagal dengan "current transaction is
  aborted" -- sudah diuji lewat skenario nama barber duplikat, lihat
  "Hasil Testing" di bawah).
- Mengekspos `IntegrityError` yang otomatis merujuk ke exception yang benar
  sesuai dialek aktif (`sqlite3.IntegrityError` atau `psycopg2.IntegrityError`).

`database.py`/`auth_db.py` (get_conn() masing-masing) tinggal delegasi satu
baris ke `db_compat.get_conn()` kalau `IS_POSTGRES` — SELURUH ~200 titik
pemanggilan `conn.execute(...)` di 19 file lain **tidak ada yang diubah**.

### Query yang ditulis ulang (supaya jalan di KEDUA dialek)

Sebagian kecil query memakai sintaks yang berbeda total antar dialek --
ini SATU-SATUNYA bagian yang disentuh langsung di file aslinya:

| Pola lama (SQLite-only) | Pola baru (dialek-netral, jalan di keduanya) | Lokasi |
|---|---|---|
| `strftime('%Y', tgl)=? AND strftime('%m', tgl)=?` | `tgl LIKE ?` dengan param `'YYYY-MM-%'` | database.py, booking_db.py, pengeluaran_db.py (~20 titik) |
| `strftime('%Y', tgl)=?` (filter tahun saja) | `tgl LIKE ?` dengan param `'YYYY-%'` | idem |
| `strftime('%m', tgl)=?` (filter bulan saja) | `tgl LIKE ?` dengan param `'%-MM-%'` | idem |
| `INSERT OR IGNORE ...` | `INSERT ... ON CONFLICT DO NOTHING` (didukung SQLite 3.24+ maupun PostgreSQL 9.5+) | database.py |
| `WHERE username = ? COLLATE NOCASE` | `WHERE LOWER(username) = LOWER(?)` | auth_db.py (login case-insensitive) |
| `sqlite3.IntegrityError` | `db_compat.IntegrityError` (alias per-dialek) | database.py, auth_db.py, pengaturan_barber/service/user.py |

Satu pola sengaja dibuat **dialek-AWARE** (bukan netral) karena perilaku
bawaannya sendiri berbeda: `LIKE` di SQLite tidak peka huruf besar/kecil
untuk ASCII secara default, sedangkan `LIKE` di PostgreSQL PEKA huruf
besar/kecil -- pencarian pengeluaran (`pengeluaran_db.py`) memakai `ILIKE`
kalau `db_compat.IS_POSTGRES`, supaya hasil pencarian identik di kedua
dialek.

Query yang **TIDAK disentuh** karena sudah dialek-netral sejak awal:
`INSERT ... ON CONFLICT(key) DO UPDATE SET ...` (upsert `settings`/`sync_meta`,
sudah didukung kedua dialek).

Query yang **TIDAK PERNAH jalan di PostgreSQL** (bukan berarti dihapus):
11 file `*_migrasi.py` (berisi `PRAGMA table_info` -- mekanisme cek kolom
khusus SQLite) tetap ada apa adanya untuk jalur SQLite, tapi di-gate di
`main.py::on_startup()` supaya sama sekali tidak dipanggil kalau
`DATABASE_URL` diisi -- lihat bagian Skema di bawah.

### Skema PostgreSQL (`backend/app/postgres_schema.py`, file baru)

Alih-alih mereplay 11 migrasi inkremental SQLite di atas PostgreSQL,
`postgres_schema.create_all()` langsung membuat skema AKHIR (hasil gabungan
seluruh migrasi itu) dalam satu langkah, idempotent (`CREATE TABLE IF NOT
EXISTS` + `ON CONFLICT DO NOTHING` untuk seed default) — 15 tabel total,
kolom & default disalin persis dari akumulasi seluruh migrasi SQLite. Kolom
boolean-as-integer (`aktif`, `is_rafiq`, dst) SENGAJA tetap `INTEGER`
(bukan `BOOLEAN` native Postgres) supaya nilai `1 if x else 0` yang sudah
ada di 9 titik kode tidak perlu diubah. `main.py::on_startup()` memanggil
`postgres_schema.create_all()` SEBAGAI GANTI (bukan tambahan) dari
`db.init_db()` + `auth_db.init_auth_db()` + `booking_db.init_booking_db()` +
11 migrasi SQLite, HANYA kalau `DATABASE_URL` diisi — jalur SQLite (default)
tidak diubah sama sekali.

### Script migrasi data (`backend/app/migrate_to_postgres.py`, file baru)

Script MANUAL (dijalankan lewat command line, **tidak pernah** dipanggil
otomatis dari `main.py`/proses lain mana pun):

```bash
cd backend/app
DATABASE_URL="postgresql://..." python migrate_to_postgres.py --dry-run   # lihat jumlah baris dulu, tidak menulis apa pun
DATABASE_URL="postgresql://..." python migrate_to_postgres.py             # migrasi sungguhan
```

- Backup SQLite OTOMATIS (salinan bertanda waktu ke `backend/backups/`)
  sebelum satu baris pun dibaca. SQLite sumber dibuka **read-only**
  sepanjang proses, tidak pernah ditulis.
- Menyalin 15 tabel sesuai urutan dependensi foreign key, mempertahankan
  `id` asli dari SQLite (supaya relasi antar tabel tetap valid), lalu
  menyamakan ulang sequence `SERIAL` PostgreSQL ke `MAX(id)` setelahnya.
- Memakai **UPSERT** (`ON CONFLICT (pk) DO UPDATE`, bukan sekadar
  `DO NOTHING`) — data SQLite selalu menang menimpa baris yang kebetulan
  sudah ada (mis. default `settings`/`services` yang otomatis diisi
  `postgres_schema.create_all()`) — sekaligus membuat script ini aman
  dijalankan ulang berkali-kali (idempotent per baris, sudah diuji).
- Menolak berjalan (kecuali `--force`) kalau tabel data bisnis di
  PostgreSQL (transaksi/users/bookings/dst — TIDAK termasuk
  `settings`/`services` yang memang selalu diisi default) sudah tidak
  kosong, supaya tidak dijalankan tidak sengaja dua kali ke database yang
  salah.
- **TIDAK melakukan cutover** — aplikasi baru benar-benar memakai
  PostgreSQL kalau `DATABASE_URL` diisi di environment proses backend
  (mis. Render) DAN proses backend di-restart, langkah terpisah yang
  sengaja tidak dilakukan script ini.

### File yang diubah/ditambah

**Baru:**
- `backend/app/db_compat.py` — lapisan kompatibilitas dialek.
- `backend/app/postgres_schema.py` — skema PostgreSQL lengkap + seed default.
- `backend/app/migrate_to_postgres.py` — script migrasi data manual.

**Diubah** (seluruhnya kompatibel-mundur, jalur SQLite byte-identik seperti sebelumnya):
- `backend/app/database.py` — `get_conn()` delegasi dialek; `INSERT OR IGNORE`→`ON CONFLICT DO NOTHING`; `strftime`→`LIKE` (12 titik); `sqlite3.IntegrityError`→`IntegrityError` (2 titik).
- `backend/app/auth_db.py` — `get_conn()` delegasi dialek; `COLLATE NOCASE`→`LOWER()`; `IntegrityError` alias.
- `backend/app/booking_db.py` — `strftime`→`LIKE` (3 pasang).
- `backend/app/pengeluaran_db.py` — `strftime`→`LIKE`; `LIKE`→`ILIKE` dialek-aware untuk pencarian.
- `backend/app/pengaturan_barber.py`, `pengaturan_service.py`, `pengaturan_user.py` — `IntegrityError` alias.
- `backend/app/main.py` — `on_startup()` cabang PostgreSQL (`postgres_schema.create_all()`) vs SQLite (seperti sebelumnya, tidak diubah).
- `backend/requirements.txt` — tambah `psycopg2-binary` (hanya diimpor kalau `DATABASE_URL` diisi).

**Tidak diubah sama sekali** (sesuai aturan): seluruh `frontend/`, seluruh signature/response endpoint API, 11 file `*_migrasi.py` (tetap dipakai apa adanya di jalur SQLite), `pengaturan_backup.py` (backup/restore file `.db` — TETAP hanya jalan untuk SQLite; PostgreSQL punya jalur backup sendiri lewat `pg_dump`/provider terkelola seperti Neon, di luar cakupan tahap ini).

### Hasil Testing

Diuji dengan PostgreSQL 16 lokal (bukan Neon — sandbox pengembangan tidak
punya akses jaringan keluar ke host eksternal manapun, jadi verifikasi
konektivitas ke Neon yang sesungguhnya baru bisa dilakukan Owner sendiri
setelah `DATABASE_URL` diisi) — DUA server backend dijalankan berdampingan
(satu SQLite, satu PostgreSQL) dengan skenario IDENTIK pada keduanya, hasil
byte-for-byte sama:
- Login (termasuk username case-insensitive), tambah barber, **nama
  barber duplikat (IntegrityError -> pesan error ramah) diikuti tambah
  barber lain langsung sesudahnya** (membuktikan rollback PostgreSQL tidak
  membuat koneksi pool "macet").
- Transaksi (header + detail, komisi terhitung benar: Rp50.000 untuk
  Dry Cut + 2x Cut & Wash @ komisi 40%).
- Tandai libur dua kali berturut-turut (membuktikan `ON CONFLICT DO
  NOTHING` mencegah duplikat, sama seperti `INSERT OR IGNORE` lama).
- Rekap transaksi & rekap bulanan dengan filter tahun+bulan gabungan
  maupun tahun-saja/bulan-saja terpisah (membuktikan seluruh varian
  rewrite `strftime`→`LIKE` benar, termasuk uji negatif: filter bulan=7
  TIDAK ikut mengembalikan data bertanggal Agustus).
- Pencarian pengeluaran case-insensitive ("shampoo" menemukan "Beli Shampoo").
- Restock & jual produk (stok terhitung benar: restock 10, jual 3, sisa 7).
- `migrate_to_postgres.py --dry-run` (baca SQLite, tanpa PostgreSQL) dan
  jalur sungguhan (42 baris tersalin ke PostgreSQL lokal kosong), termasuk
  uji dijalankan DUA KALI berturut-turut (`--force`) untuk membuktikan
  upsert tidak menghasilkan duplikat.
- `python -m py_compile` seluruh file backend: lulus.
- Boot backend SQLite (file lama & baru) tanpa `DATABASE_URL`: log & hasil
  byte-identik dengan sebelum tahap ini (regresi nihil).

Satu bug ditemukan & diperbaiki SELAMA testing (bukan lolos ke commit
akhir): `db_compat.py` awalnya selalu menambahkan `RETURNING id` ke setiap
`INSERT`, gagal untuk tabel `settings`/`sync_meta` yang primary key-nya
`key` bukan `id` (`UndefinedColumn`) — diperbaiki jadi `RETURNING *` lalu
mengambil `id` HANYA kalau kolom itu ada di hasil.

### Status & Langkah Berikutnya

- **Seluruh fitur yang diuji LULUS** di kedua dialek dengan hasil identik.
- **Migrasi data SIAP dijalankan** (`migrate_to_postgres.py`) begitu Owner
  menyiapkan `DATABASE_URL` Neon dan ingin mencobanya — script sudah diuji
  penuh terhadap PostgreSQL sungguhan (lokal), termasuk idempotensi.
- **BELUM cutover** — `DATABASE_URL` belum diminta/diisi di Render, sesuai
  instruksi. Backend produksi di Render TIDAK terpengaruh sama sekali oleh
  perubahan tahap ini sampai Owner secara eksplisit mengisi `DATABASE_URL`
  di environment Render dan me-restart service-nya.
- ~~Belum dikerjakan: redesain fitur Backup & Restore Database untuk
  PostgreSQL~~ — **sudah dikerjakan**, lihat bagian "Backup & Restore" di
  changelog REVISI Hak Akses Admin di bawah. Verifikasi konektivitas nyata
  ke Neon tetap belum dilakukan dari sandbox pengembangan (lihat catatan di
  bagian yang sama).


## REVISI: Dashboard Collapse/Expand, Hak Akses Admin, Hapus Google Sheets, Laporan PDF

Tahap besar menindaklanjuti migrasi PostgreSQL di atas (yang saat itu sudah
di-cutover sendiri oleh Owner ke Render + Neon dan dikonfirmasi berhasil).
Delapan area, dikerjakan sekaligus dalam satu rangkaian kerja:

### 1. Dashboard Owner — hapus kartu duplikat + Collapse/Expand

Kartu **"Total Pendapatan Barber"** dihapus (kartu "Total Komisi Barber"
tetap ada). Setiap kartu Dashboard sekarang bisa di-collapse/expand
(klik judulnya) plus tombol **Collapse All**/**Expand All** — status
collapse per kartu tersimpan di `localStorage`
(`mugen_dashboard_owner_collapse_v1`), bertahan lintas refresh/login ulang.
Diuji lewat browser sungguhan (Playwright): klik collapse → cek
`localStorage` → reload halaman → panah kartu tetap collapsed.

### 2-3. Role baru: 'staff' (Admin) — Hak Akses Admin dinamis

**Sebelum revisi ini, aplikasi cuma punya DUA role**: `admin` (label UI
"Owner", akses penuh) dan `barber`. Spesifikasi minta tingkat AKSES BARU
("Admin") yang hak aksesnya diatur bebas oleh Owner, bukan hardcode --
ini secara arsitektur adalah ROLE KETIGA, bukan sekadar Owner yang
dibatasi. Ditambahkan role `staff` (nilai database, BUKAN `admin` --
supaya tidak menimpa arti `admin`/Owner yang sudah ada di ~70 tempat kode)
yang tampil sebagai **"Admin"** di seluruh UI.

**`backend/app/permissions.py`** (baru): 22 key izin (`izin_dashboard_*`
×9, `izin_user_*` ×3, `izin_pengeluaran_*` ×3, `izin_backup_*` ×2,
`izin_laporan_pdf`, `izin_setting_*` ×4), disimpan sebagai baris di tabel
`settings` yang SUDAH ADA (bukan tabel baru — otomatis dialek-netral lewat
`db_compat.py`/PostgreSQL yang sudah ada). Default: 4 kartu Dashboard
(Nilai Service/Jumlah Service/Pengeluaran Toko/Penjualan Produk) ON,
SISANYA off sampai Owner mengaktifkan sendiri lewat Setting > Hak Akses
Admin (menu baru, Owner-murni).

**`auth.py`**: `require_owner_or_staff` (role 'admin' atau 'staff') dan
`require_permission(key)` (dependency factory — Owner SELALU lolos tanpa
syarat; 'staff' hanya lolos kalau Owner mengaktifkan `key` itu; 'barber'
selalu ditolak). Setiap endpoint yang relevan (Dashboard, User,
Pengeluaran, Backup, Laporan PDF, sebagian Setting) diubah memakainya.

**Deny-list KERAS** (tidak bisa di-override lewat toggle izin apa pun,
ditegakkan di `routers/pengaturan.py`): 'staff' tidak pernah boleh
menyasar akun ber-role 'admin' (Owner) ATAU 'staff' lain (hanya 'barber')
di endpoint ganti-password/nonaktifkan/aktifkan/buat-user; Owner terakhir
(role 'admin' aktif, hitung lewat `auth_db.hitung_owner_aktif()`) tidak
bisa dinonaktifkan oleh SIAPA PUN. Diuji end-to-end lewat curl: staff
dengan SELURUH izin User diberikan tetap mendapat 403 saat mencoba
menonaktifkan/ganti password akun Owner atau staff lain, atau membuat user
ber-role Owner/Admin baru; Owner mencoba menonaktifkan dirinya sendiri
sebagai Owner terakhir juga 403.

**Dashboard Admin** (`routers/dashboard.py::_filter_dashboard_untuk_staff`):
endpoint `GET /api/dashboard/owner` sekarang juga menerima 'staff', tapi
field yang tidak diizinkan Owner di-set `null` di response (bukan
disembunyikan di frontend saja) dan `per_barber`/grafik SAMA SEKALI tidak
dikirim (di luar cakupan Dashboard Admin sesuai spesifikasi). Frontend
(`dashboard_owner.js`) melewati kartu bernilai `null` sepenuhnya.

**Setting** (`pages/pengaturan.js`): tab yang dilihat 'staff' difilter
sesuai `izin_setting_*` (Identitas/Tampilan/User/Backup) — Komisi/Bonus
Service/Uang Harian/Barber/Layanan/Hak Akses Admin TETAP Owner-murni,
tidak pernah ada di daftar izin yang bisa diberikan. Tab User: dropdown
Role menampilkan "Owner"/"Admin"/"Barber" untuk Owner, HANYA "Barber"
untuk staff; tombol aksi pada baris Owner/Admin lain disembunyikan sama
sekali untuk aktor staff (bukan hanya ditolak backend).

**`routers/rekap.py`**: ditemukan SAAT audit -- endpoint ini sebelumnya
memakai `get_current_user` generik dengan logika "kalau bukan barber,
anggap seperti Owner" (tanpa mengenal role 'staff' yang baru dibuat), jadi
'staff' akan otomatis dapat akses PENUH tanpa batasan ke seluruh Rekap
begitu role ini ada, padahal Rekap tidak termasuk hak akses yang bisa
diberikan Owner. Ditambahkan penolakan eksplisit untuk role 'staff'.

### 4. Hapus total fitur Google Sheets

`google_sheets_client.py`, `sync_helper.py`, `sync_meta_db.py`,
`sync_migrasi.py`, `routers/sync.py`, `frontend/js/pages/sinkronisasi.js`
dihapus permanen; seluruh pemanggil `sync_async()` (input_data.py/
pengeluaran.py/produk.py) dan referensi di main.py/index.html/nav.js/
router.js/service-worker.js dibersihkan; `gspread`/`google-auth` dihapus
dari requirements.txt. Tabel `sync_meta` di `postgres_schema.py` tidak lagi
dibuat (tabel lama yang mungkin sudah ada di database produksi TIDAK
dihapus paksa -- dibiarkan sebagai sisa yang tidak dipakai lagi, sesuai
prinsip tidak melakukan operasi destruktif tanpa perlu).

### 5. Menu Backup: Laporan PDF + Backup PostgreSQL (perbaikan bug lama)

**`backend/app/laporan_pdf.py`** (baru, pakai `reportlab`): 3 jenis laporan
(Transaksi/Pengeluaran/Rekap Bulanan Barber), setiap halaman punya nama +
logo barbershop (kalau ada), judul, periode, tanggal cetak, nomor halaman,
dan nama akun yang mencetak (lihat `_header_footer_factory`). Endpoint
`GET /api/pengaturan/laporan/pdf` (Owner selalu boleh; staff butuh
`izin_laporan_pdf`). Diuji: PDF tervalidasi asli (`file` command +
`pypdf` text extraction mengonfirmasi seluruh elemen wajib ada), validasi
"bulan wajib diisi untuk Rekap Bulanan" mengembalikan 422 yang tepat.

**Bug ditemukan & diperbaiki SAAT audit (bukan diminta eksplisit, tapi
langsung relevan ke tahap ini)**: `pengaturan_backup.py` (Export/Import
Database) HANYA pernah menangani SQLite (`FileResponse(db.DB_PATH)`) --
sejak Postgres jadi database aktif di produksi, endpoint ini akan
mengunduh/menimpa file lokal yang TIDAK LAGI dipakai aplikasi sama sekali
(silently broken). Diperbaiki dengan jalur PostgreSQL terpisah
(`export_database_postgres()`/`import_database_postgres()`): snapshot
JSON seluruh tabel (bukan `pg_dump` biner, supaya tidak butuh binary
client Postgres terpasang di proses backend), dengan backup-otomatis-
sebelum-import yang sama seperti jalur SQLite. Jalur SQLite sendiri TIDAK
diubah sama sekali. Diuji lewat PostgreSQL 16 lokal (bukan Neon -- lihat
keterbatasan jaringan sandbox di bagian migrasi Postgres di atas): export
menghasilkan JSON valid, import mengembalikan seluruh isi tabel dengan
benar.

### 6. Setting → Tab Barber: hapus helper text basi

Teks "Uang Harian (Rp/hari, cair kalau Dry Cut + Cut & Wash hari itu ≥ 3)"
dihapus (sudah tidak akurat sejak Setting > Uang Harian punya acuan
service & target yang bisa diatur bebas Owner) — hanya label "Uang
Harian" yang tersisa, field & logika backend tidak disentuh sama sekali.

### Hasil Testing

- `python -m py_compile` seluruh backend, `node --check` seluruh file
  frontend yang diubah: lulus.
- Backend booted (SQLite) dan diuji lewat `curl` end-to-end: role staff
  dibuat, permission default-deny dikonfirmasi, setiap toggle izin diuji
  (grant → aksi berhasil, revoke → 403), seluruh deny-list (Owner-terakhir,
  staff-tidak-boleh-sasar-Owner/staff-lain) dikonfirmasi.
- **Browser sungguhan (Playwright + Chromium)**: login Owner → kartu
  "Total Pendapatan Barber" TIDAK ADA, "Total Komisi Barber" ADA → klik
  collapse → cek localStorage → reload → status collapse bertahan →
  Expand All berfungsi → tab "Hak Akses Admin" merender seluruh grup izin.
  Login staff → judul halaman "Dashboard Admin" (bukan "Dashboard
  Owner") → hanya kartu yang diizinkan tampil → sidebar HANYA
  Dashboard/Pengeluaran/Setting (Input Data/Rekap/Produk tersembunyi) →
  tab Setting HANYA "User" (satu-satunya yang diizinkan dalam skenario uji).
- Seluruh fitur yang diuji LULUS di kedua role (Owner tidak terpengaruh
  sama sekali, staff dibatasi persis sesuai izin yang diberikan).

### REVISI KEDUA: Input Data/Booking/Pengeluaran/Produk/Rekap dibuka penuh untuk Admin

Menindaklanjuti umpan balik: LIMA menu di atas (Input Data, Booking,
Pengeluaran, Produk, Rekap) sekarang bisa diakses 'staff' (Admin) **PENUH
sama persis seperti Owner**, TANPA sistem izin sama sekali -- bukan lagi
diblokir total (Input Data/Booking/Produk/Rekap) ataupun diatur granular
per-aksi (Pengeluaran, grup `izin_pengeluaran_*` dihapus total dari
`permissions.py`/tab Hak Akses Admin). Dashboard (kartu difilter) dan
Setting (tab difilter) TIDAK berubah -- tetap satu-satunya area yang diatur
lewat Hak Akses Admin.

Backend: seluruh endpoint di `routers/input_data.py`, `routers/booking.py`
(kecuali `/mine`, tetap `require_barber`), `routers/produk.py` diganti dari
`require_admin` menjadi `require_owner_or_staff`; `routers/pengeluaran.py`
POST/PUT/DELETE diganti dari `require_permission("izin_pengeluaran_*")`
menjadi `require_owner_or_staff`; `routers/rekap.py` — penolakan eksplisit
untuk role 'staff' (ditambahkan di revisi sebelumnya) dihapus.

Frontend: `nav.js` (kelima menu ditambahkan ke `roles` masing-masing),
`router.js` (gate disesuaikan/dihapus), dan — penting — variabel `isAdmin`
di `pages/booking.js`/`pages/input_data.js`/`pages/rekap.js` (sebelumnya
`user.role === "admin"` murni, mengontrol apakah tampilan Owner-lengkap
atau tampilan terbatas yang dirender) diperluas jadi
`user.role === "admin" || user.role === "staff"` -- tanpa ini, staff akan
tetap melihat tampilan versi terbatas walau endpoint backend-nya sudah
dibuka, karena ketiga halaman itu sebelumnya hanya pernah punya DUA jenis
tampilan (Owner-lengkap vs Barber-terbatas), belum pernah punya kasus role
ketiga yang butuh tampilan Owner-lengkap juga.

Diuji ulang end-to-end (curl): staff tanpa satu pun izin Pengeluaran
diberikan tetap bisa tambah/edit/hapus pengeluaran (200, bukan lagi 403);
staff bisa mengakses seluruh endpoint Input Data/Booking/Produk/Rekap
(200). Browser (Playwright): sidebar staff menampilkan keenam menu
(Dashboard/Input Data/Rekap/Booking/Pengeluaran/Produk/Setting), halaman
Booking/Rekap staff menampilkan tab LENGKAP sama seperti Owner (bukan versi
Barber), tab "Hak Akses Admin" tetap tidak pernah muncul untuk staff.


## Struktur Project

```
mugen-hair-pwa/
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── __init__.py             # BUGFIX: supaya `uvicorn app.main:app` dari backend/ juga bisa jalan
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
    ├── config.js             # SATU-SATUNYA tempat yang diedit untuk arahkan ke backend saat deploy
    ├── css/style.css        # palet warna sama dengan ui_theme.py (Dark Mode)
    ├── icons/                # TAHAP 13: ikon PWA lengkap (baru dibuat, sebelumnya tidak ada)
    │   ├── favicon.ico
    │   ├── icon-{72,96,128,144,152,192,384,512}.png
    │   ├── icon-maskable-{192,512}.png     # ikon adaptif Android
    │   └── apple-touch-icon.png            # ikon Home Screen iOS
    └── js/
        ├── app.js
        ├── brand.js              # TAHAP 10: identitas barbershop lintas halaman
        └── pages/
            ├── pengeluaran.js    # TAHAP 9: halaman CRUD Pengeluaran (khusus admin)
            ├── pengaturan.js     # TAHAP 10: halaman Setting (khusus admin)
            ├── produk.js         # TAHAP 8/11: halaman Produk (khusus admin)
            └── sinkronisasi.js   # TAHAP 12: halaman Status Sinkronisasi + Backup/Restore (khusus admin)
```

## Instalasi

Prasyarat:
- **Python 3.11+** (dipakai untuk mengembangkan & menguji versi ini — versi
  3.9+ kemungkinan besar juga jalan, tapi belum diuji).
- **pip**.
- Browser modern (Chrome/Edge/Firefox/Safari) untuk menjalankan frontend
  dan menguji instalasi PWA-nya.
- Tidak perlu Node.js/npm — frontend murni HTML/CSS/JS tanpa build step.

Langkah instalasi (sekali saja, atau tiap kali `requirements.txt` berubah):

```bash
git clone <url-repo-ini>
cd mugen-hair-pwa/backend

# (opsional tapi disarankan) buat virtual environment supaya dependency
# tidak campur dengan Python sistem:
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

Kalau `pip install` sukses tanpa error, instalasi selesai — lanjut ke
bagian **Menjalankan di Lokal** di bawah.

### Troubleshooting Windows: `bcrypt`/`passlib` error saat startup

Kode di `auth_db.py` sejak bugfix ini **tidak lagi memakai passlib sama
sekali** — hashing password langsung lewat library `bcrypt`, dan sudah
diverifikasi berjalan normal walau `passlib` masih ikut terpasang di
environment (dites persis dengan kombinasi `bcrypt==5.0.0` +
`passlib==1.7.4` berdampingan). Kalau setelah menarik kode terbaru masih
muncul error seperti:

```
AttributeError: module 'bcrypt' has no attribute '__about__'
ValueError: password cannot be longer than 72 bytes
```

itu HAMPIR PASTI berarti **kode yang sedang berjalan bukan kode
terbaru**, atau **instalasi `bcrypt` di virtual environment lokal
rusak/tidak bersih** — bukan bug di repository ini. Penyebab paling umum
di Windows: `pip install --upgrade` gagal mengganti file ekstensi native
(`.pyd`) versi lama dengan bersih kalau file itu sedang terkunci
(dipakai proses Python lain / antivirus / IDE), sehingga `pip show
bcrypt` melaporkan versi baru padahal file yang sebenarnya dimuat masih
versi lama yang rusak sebagian.

**Langkah verifikasi cepat** (jalankan dari `backend/app/`, dengan venv
yang aktif):

```bash
python -c "import auth_db; print(auth_db.hash_password('tes'))"
```

- Kalau baris ini mencetak hash (`$2b$...`) tanpa error → `auth_db.py`
  dan `bcrypt` di environment Anda sudah benar; masalah startup ada di
  tempat lain (cek langkah lain di bawah).
- Kalau baris ini SENDIRI sudah gagal dengan error yang sama → environment
  lokal Anda yang bermasalah, ikuti langkah perbaikan di bawah.

**Perbaikan (buat ulang virtual environment dari nol — JANGAN install di
atas venv lama)**:

```bash
# Windows (cmd/PowerShell), dari folder backend/:
rmdir /s /q .venv
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Pastikan juga:
1. Kode yang dijalankan benar-benar dari commit terbaru (`git log -1`,
   `git status` harus bersih dari perubahan lokal yang tidak disengaja).
2. Tidak ada folder `__pycache__` basi ikut ter-commit/tersalin manual di
   luar kendali git (hapus `backend/app/__pycache__/` kalau ada, aman
   dihapus kapan saja — akan dibuat ulang otomatis oleh Python).
3. Venv yang diaktifkan (`.venv\Scripts\activate`) benar-benar venv yang
   baru saja dipakai `pip install -r requirements.txt`, bukan venv/Python
   lain (umum kalau ada lebih dari satu instalasi Python di PATH).

## Menjalankan di Lokal (development)

**1. Jalankan backend** — dua cara berikut SAMA-SAMA berfungsi (dengan
venv yang sama dari langkah Instalasi), pilih mana yang lebih nyaman:

```bash
# Cara 1: dari folder backend/app/
cd backend/app
uvicorn main:app --reload --port 8000

# Cara 2: dari folder backend/ (module path)
cd backend
uvicorn app.main:app --reload --port 8000
```

Buka `http://localhost:8000/api/health` di browser — harus muncul
`{"status":"ok"}`. Saat pertama kali dijalankan (database masih kosong),
backend otomatis membuat SATU akun Owner lewat environment variable
`ADMIN_BOOTSTRAP_USERNAME`/`ADMIN_BOOTSTRAP_PASSWORD` (default:
`owner` / `ganti-password-ini` kalau env var tidak diisi — **wajib diganti**
sebelum dipakai sungguhan, lihat bagian Deployment).

Environment variable lain yang bisa diisi (semua opsional untuk development
lokal, sudah ada nilai default yang aman):

| Variable | Kegunaan | Default (lokal) |
|---|---|---|
| `ADMIN_BOOTSTRAP_USERNAME` | Username Owner pertama (hanya dipakai sekali saat database masih kosong) | `owner` |
| `ADMIN_BOOTSTRAP_PASSWORD` | Password Owner pertama | `ganti-password-ini` |
| `SECRET_KEY` | Kunci penandatanganan token login — **wajib diisi acak & rahasia saat deploy** | kunci development (TIDAK aman untuk produksi) |
| `ALLOWED_ORIGINS` | Daftar origin frontend yang boleh memanggil API ini (dipisah koma) — CORS | `localhost:5500,127.0.0.1:5500,localhost:3000,localhost:8000` (+ otomatis mengizinkan seluruh subdomain `*.onrender.com`, lihat kode) |
| `TENANT_SUBDOMAIN_BASE_DOMAIN` | FONDASI Multi-Tenant Phase 2.0: domain dasar untuk resolusi tenant lewat SUBDOMAIN (mis. diisi `mugenhair.app` supaya `toko-a.mugenhair.app` otomatis ter-resolve ke tenant slug `toko-a`, lihat `tenant_middleware.py`) | kosong (subdomain resolution MATI TOTAL -- tenant tetap bisa di-resolve lewat query string `?tenant=`/header `X-Tenant-Slug`/slug eksplisit di form Login) |
| `DATABASE_URL` | Connection string PostgreSQL (Neon/dsb) — kosong berarti pakai SQLite lokal (lihat bagian **Migrasi PostgreSQL**) | kosong (SQLite) |
| `PG_POOL_MIN` / `PG_POOL_MAX` | Ukuran connection pool ke PostgreSQL (hanya relevan kalau `DATABASE_URL` diisi) | `1` / `10` |
| `R2_ACCOUNT_ID` | Account ID Cloudflare — dipakai menyusun `R2_ENDPOINT_URL` otomatis kalau `R2_ENDPOINT_URL` tidak diisi terpisah (lihat bagian **Migrasi Cloudflare R2**) | kosong |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | Kredensial API Token R2 (Object Read & Write, dibatasi ke satu bucket) | kosong |
| `R2_BUCKET_NAME` | Nama bucket R2 tujuan upload | kosong |
| `R2_ENDPOINT_URL` | Endpoint S3-compatible R2 (`https://<account_id>.r2.cloudflarestorage.com`) — opsional kalau `R2_ACCOUNT_ID` sudah diisi | diturunkan dari `R2_ACCOUNT_ID` |
| `R2_PUBLIC_URL` | Domain publik R2 (CDN) — **disimpan, TIDAK dipakai jalur kode manapun saat ini** (bucket tetap private, backend tetap jadi gerbang akses satu-satunya, lihat r2_storage.py) | kosong |
| `GOOGLE_SHEET_ID` | ID spreadsheet Google Sheets tujuan sinkron (Tahap 12) | kosong (sinkron nonaktif) |
| `GOOGLE_CREDENTIALS_JSON` | Isi mentah file JSON service account Google (alternatif dari file `credentials.json`) | kosong |
| `SYNC_RETRY_INTERVAL_DETIK` | Jeda antar percobaan retry sinkron otomatis | `60` |
| `ADMIN_RESET_USERNAME` / `ADMIN_RESET_PASSWORD` | Buat/reset SATU akun admin di server yang sudah berjalan (lupa kredensial) — lihat bagian **Reset / Buat Akun Admin** di bawah | kosong (no-op) |

> Catatan: `GOOGLE_SHEET_ID`/`GOOGLE_CREDENTIALS_JSON`/`SYNC_RETRY_INTERVAL_DETIK` di tabel ini sudah TIDAK dipakai lagi sejak fitur Sinkronisasi Google Sheets dihapus total (lihat bagian **Sinkronisasi Google Sheets — DIHAPUS** di bawah) — baris ini tertinggal di tabel (dokumentasi basi, ditemukan saat audit migrasi R2, di luar cakupan pekerjaan itu untuk dibersihkan sekarang).

**2. Jalankan frontend** — karena murni file statis, bisa dibuka dengan
server statis apa saja. Contoh paling sederhana (dari folder `frontend/`):

```bash
cd frontend
python3 -m http.server 5500
```

Buka `http://localhost:5500/index.html` — `js/api.js` otomatis mengarah ke
`http://localhost:8000` saat diakses dari `localhost`/`127.0.0.1`, jadi
**tidak perlu edit apa pun** untuk development lokal (asal backend jalan di
port 8000 seperti langkah 1). Login dengan akun Owner dari langkah 1.

Alternatif lain untuk men-serve frontend saat development: ekstensi "Live
Server" di VS Code, atau `npx serve`, atau `php -S localhost:5500` — apa
saja yang bisa menyajikan file statis di localhost.

## Menjalankan Test

FONDASI Multi-Tenant Phase 1.1 (technical debt yang ditutup): seluruh
skenario isolasi tenant, migrasi database, dan regresi fitur sekarang
tersimpan permanen sebagai test suite pytest di `backend/tests/` (bukan
lagi script ad-hoc yang hilang begitu sesi kerja selesai), dan dijalankan
otomatis lewat GitHub Actions di setiap push/PR (lihat
`.github/workflows/backend-tests.yml`).

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest tests -v
```

Sebagian besar test (isolasi tenant, migrasi, regresi fitur) jalan murni
lewat SQLite temporer, tidak butuh setup tambahan apa pun. Satu test
(`test_backup_postgres.py`, verifikasi Export/Import Database terhadap
PostgreSQL sungguhan) butuh PostgreSQL lokal di `localhost:5432` dengan
database `mugen_test`, user `postgres`/password `postgres` — kalau tidak
tersedia, test itu **otomatis di-skip** (bukan gagal), lihat
`backend/tests/conftest.py::has_postgres()`. Override connection string
lewat environment variable `MUGEN_TEST_DATABASE_URL` kalau kredensial
lokal Anda berbeda.

## Deployment (Produksi)

Backend (FastAPI) dan frontend (statis) adalah **dua layanan terpisah** —
bisa dideploy ke platform yang sama atau berbeda. Panduan di bawah ini
generik (berlaku untuk Render, Railway, Fly.io, VPS biasa, dst) karena
platform hosting akhir belum ditentukan; sesuaikan istilah dengan platform
pilihan Anda.

### Backend

1. Deploy folder `backend/` sebagai layanan Python/ASGI (`uvicorn main:app`
   dari folder `backend/app/`, atau `gunicorn -k uvicorn.workers.UvicornWorker
   main:app` untuk beberapa worker sekaligus).
2. **Disk persisten wajib** — `mugen_hair.db` (SQLite) hidup di filesystem
   lokal container/server, BUKAN di database eksternal. Kalau platform
   hosting memakai container ephemeral (isi disk hilang tiap deploy/restart),
   pastikan `backend/app/` (atau minimal file `.db`-nya) di-mount ke volume
   persisten, atau data akan hilang setiap kali container di-restart.
3. Set environment variable produksi (lihat tabel di atas) — **WAJIB**
   diganti dari default:
   - `SECRET_KEY`: string acak & rahasia (mis. `python3 -c "import secrets;
     print(secrets.token_hex(32))"`).
   - `ADMIN_BOOTSTRAP_USERNAME` / `ADMIN_BOOTSTRAP_PASSWORD`: kredensial
     Owner pertama yang sungguhan (ganti password ini lewat menu Setting >
     User begitu berhasil login pertama kali).
   - `ALLOWED_ORIGINS`: domain tempat frontend dideploy (mis.
     `https://mugenhair.example.com`), dipisah koma kalau lebih dari satu.
   - (opsional) `GOOGLE_SHEET_ID` / `GOOGLE_CREDENTIALS_JSON` — lihat bagian
     **Sinkronisasi Google Sheets** di bawah.
4. Kalau sudah pernah pakai aplikasi Desktop dan ingin membawa data lama:
   copy manual file `mugen_hair.db` dari aplikasi Desktop ke
   `backend/app/mugen_hair.db` di server SEBELUM pertama kali dijalankan
   (lihat bagian **Backup & Restore Database** untuk cara lain memindahkan
   data lewat menu, tanpa akses langsung ke server).
5. Buka `https://<domain-backend>/api/health` — harus `{"status":"ok"}`.

### Frontend

FONDASI Multi-Tenant Phase 5: folder `frontend/` sekarang berisi **dua
bagian** dalam satu direktori — Landing Page publik (root `frontend/`,
path `/`) dan Dashboard PWA (`frontend/app/`, path `/app/`) — tapi
**tetap SATU deployment statis** (satu host, satu domain, dua path).
Jangan deploy `frontend/app/` sebagai site terpisah dari `frontend/` —
`frontend/app/index.html` memuat asetnya lewat path relatif ("js/...",
"css/...") yang HARUS tetap berada persis di `/app/js/...`, `/app/css/...`
dst supaya tidak 404.

1. Deploy folder `frontend/` (bukan `frontend/app/` saja) apa adanya ke
   hosting statis mana pun (Netlify, Vercel, GitHub Pages, S3+CloudFront,
   Render Static Site, Nginx, dst) — tidak ada proses build/bundler
   sungguhan, semua file HTML/CSS/JS sudah siap pakai langsung.
2. Edit **dua file** (isinya harus SAMA) supaya frontend tahu alamat
   backend yang benar:
   ```js
   // frontend/config.js DAN frontend/app/config.js -- KEDUANYA
   window.MUGEN_API_BASE = "https://<domain-backend-anda>";
   ```
   (Kalau hosting Anda mendukung *build command*, lihat subbagian
   **Render (dua service terpisah)** di bawah untuk cara mengisi ini lewat
   environment variable alih-alih edit file manual tiap deploy.)
3. Pastikan hosting Anda mengarahkan permintaan `/app` (TANPA garis miring
   akhir) ke `/app/` (DENGAN garis miring) — kalau tidak, path relatif di
   `frontend/app/index.html` salah resolve dan halaman tampil blank/putih.
   Kebanyakan hosting statis modern menangani ini otomatis; kalau tidak,
   tambahkan redirect manual (lihat `render.yaml` untuk contoh konkret di
   Render).
4. **HTTPS wajib** untuk PWA (installable + service worker) di produksi —
   browser hanya mengizinkan Service Worker aktif di origin HTTPS (kecuali
   `localhost`, yang dikecualikan khusus untuk development). Hampir semua
   hosting statis modern (Netlify/Vercel/GitHub Pages/Render/dst) sudah
   otomatis HTTPS; kalau self-host di VPS, pasang sertifikat (mis. Let's
   Encrypt via Certbot/Caddy).
5. Pastikan `ALLOWED_ORIGINS` di backend (langkah 3 di atas) sudah memuat
   domain frontend ini — kalau tidak, browser akan memblokir semua request
   API karena CORS.
6. Buka `https://<domain-frontend>/` (Landing Page) dan
   `https://<domain-frontend>/app/` (halaman Login Dashboard) — keduanya
   harus tampil tanpa error konsol browser.

### Render (dua service terpisah)

Arsitektur yang direkomendasikan sejak Phase 5: **backend sebagai Render
Web Service, frontend sebagai Render Static Site TERPISAH** (dua service,
dua URL berbeda). File `render.yaml` di root repo mendokumentasikan
konfigurasi lengkap kedua service ini (lihat komentar di dalamnya) —
bisa dipakai langsung lewat fitur **Blueprint** Render, atau sekadar jadi
referensi kalau Anda membuat keduanya manual lewat dashboard.

**Backend (Web Service)** — kalau belum ada:
1. Render Dashboard → **New > Web Service** → hubungkan repo ini.
2. **Root Directory**: `backend`. **Build Command**: `pip install -r
   requirements.txt`. **Start Command**: `cd app && uvicorn main:app
   --host 0.0.0.0 --port $PORT`. **Health Check Path**: `/api/health`.
3. Isi environment variable (lihat tabel di atas + `render.yaml`):
   `SECRET_KEY` (generate acak), `DATABASE_URL` (Neon PostgreSQL),
   `ADMIN_BOOTSTRAP_USERNAME`/`PASSWORD`,
   `SUPERADMIN_BOOTSTRAP_USERNAME`/`PASSWORD`, dan `MIDTRANS_*` kalau
   pembayaran sudah siap diaktifkan. **`ALLOWED_ORIGINS` diisi belakangan**
   (langkah 4 di bawah, setelah tahu URL frontend).
4. Deploy, catat URL yang diberikan Render (mis.
   `https://mugen-hair-api-xxxx.onrender.com`).

**Frontend (Static Site)** — terpisah dari service di atas:
1. Render Dashboard → **New > Static Site** → hubungkan repo YANG SAMA.
2. **Root Directory**: `frontend`. **Build Command**:
   ```
   test -n "$API_BASE_URL" && sed -i "s#window.MUGEN_API_BASE = .*#window.MUGEN_API_BASE = \"$API_BASE_URL\";#" config.js app/config.js
   ```
   (satu baris `sed`, BUKAN bundler — lihat `render.yaml` untuk versi
   lengkap yang juga mengisi domain di meta tag SEO). **Publish
   Directory**: `.` (folder `frontend` itu sendiri).
3. Environment variable: `API_BASE_URL` = URL backend dari langkah 4 di
   atas (TANPA trailing slash) — inilah mekanisme "jangan hardcode URL
   API", nilainya disuntikkan saat build, bukan ditulis di source code.
   Opsional: `SITE_URL` = URL Static Site ini sendiri (langkah 5 di
   bawah), dipakai mengganti placeholder domain di tag SEO/sitemap.
4. Tambahkan **Redirect Rule**: source `/app`, destination `/app/`, type
   Redirect (lihat catatan pada `render.yaml` soal kenapa ini wajib).
5. Deploy, catat URL Static Site ini (mis.
   `https://mugen-hair-frontend-xxxx.onrender.com`).
6. Kembali ke service **backend**, isi `ALLOWED_ORIGINS` dengan URL
   Static Site dari langkah 5 (walau subdomain `*.onrender.com` APAPUN
   sudah otomatis diizinkan lewat `allow_origin_regex` di `main.py` —
   lihat komentarnya — mengisi `ALLOWED_ORIGINS` secara eksplisit tetap
   praktik yang benar, dan WAJIB begitu Anda pindah ke custom domain).
   Simpan — Render otomatis restart service dengan CORS yang benar.
7. Verifikasi: buka Landing Page (`/`) dan Dashboard (`/app/`) di URL
   Static Site, pastikan tidak ada error CORS di console browser saat
   memuat data (Pricing/FAQ/Testimonial di Landing Page, login di
   Dashboard) — kalau ada, cek kembali langkah 6.

## Reset / Buat Akun Admin (Lupa Username/Password di Production)

Kalau server SUDAH berjalan (bukan instalasi baru) dan Owner lupa username
atau password, tidak ada cara reset lewat menu aplikasi itu sendiri
(ayam-telur: reset password lewat Setting > User butuh sudah login sebagai
admin). Untuk kasus ini, backend punya mekanisme "break-glass" yang HANYA
aktif kalau Anda mengisi dua environment variable secara eksplisit —
**default keduanya kosong, jadi tidak pernah otomatis/diam-diam mengubah
akun siapa pun** di deployment mana pun yang tidak sengaja mengisinya:

| Variable | Isi |
|---|---|
| `ADMIN_RESET_USERNAME` | Username admin yang mau dibuat/direset (mis. `admin`) |
| `ADMIN_RESET_PASSWORD` | Password baru untuk username itu (mis. `Admin123!`) |

**Langkah di Render** (berlaku sama untuk platform hosting lain, hanya
tempat mengisi environment variable-nya yang beda):

1. Buka dashboard Render → service backend → tab **Environment**.
2. Tambahkan dua environment variable di atas dengan nilai pilihan Anda.
3. Simpan — Render otomatis restart service dengan environment variable
   baru (kalau tidak otomatis, trigger **Manual Deploy > Restart**).
4. Cek log deploy: akan muncul baris
   `[ADMIN_RESET] Akun admin '<username>' berhasil dibuat/direset.` — ini
   konfirmasi berhasil TANPA menampilkan password di log.
5. Login ke aplikasi dengan username & password yang baru saja diisi.
6. **SEGERA setelah berhasil login** (langkah wajib, jangan dilewati):
   - Hapus KEMBALI kedua environment variable (`ADMIN_RESET_USERNAME` &
     `ADMIN_RESET_PASSWORD`) dari Render, lalu restart sekali lagi —
     kalau dibiarkan, **setiap restart server berikutnya akan mereset
     ulang ke password yang sama**, dan siapa pun yang tahu nilai
     environment variable itu (mis. tim lain yang punya akses dashboard
     Render) bisa memakainya untuk login.
   - Ganti password ke yang benar-benar rahasia lewat menu
     **Setting > User > Ganti Password**.

**Yang terjadi di balik layar** (`backend/app/auth_db.py`,
`reset_atau_buat_admin_darurat()`):
- Kalau username itu **sudah ada**: password-nya diganti, dipaksa jadi
  role `admin`, dan diaktifkan lagi kalau sebelumnya sempat dinonaktifkan.
- Kalau username itu **belum ada**: dibuat baru sebagai akun admin.
- **Data lain sama sekali tidak disentuh** — user lain, seluruh data
  barber/transaksi/produk/pengeluaran/pengaturan/riwayat sinkron tetap
  utuh persis seperti sebelumnya. Hanya SATU baris di tabel `users` yang
  diubah/ditambah.

## Backup & Restore Database

Dua tempat di aplikasi yang melakukan hal yang SAMA (memanggil endpoint
backend yang sama, `/api/pengaturan/backup/*`) — pakai yang mana saja
sesuai kenyamanan:
- Menu **Setting > Backup** (tab terakhir), atau
- Menu **Sinkronisasi** (bagian bawah halaman, di luar status sinkron).

**Backup (Export)**:
1. Login sebagai Owner.
2. Buka menu Setting atau Sinkronisasi, klik **Backup Database** / **Export
   Database**.
3. File `.db` (SQLite, salinan PERSIS database yang sedang berjalan,
   termasuk semua transaksi/komisi/produk/pengeluaran/pengaturan/dst) akan
   otomatis terunduh ke perangkat Anda. Simpan file ini di tempat aman
   (Google Drive, hard disk eksternal, dst) — inilah cara paling aman
   memindahkan/mengamankan seluruh data toko.

**Restore (Import)**:
1. Login sebagai Owner, buka menu Setting atau Sinkronisasi.
2. Pilih file `.db` hasil Backup sebelumnya di bagian **Restore Database** /
   **Import Database**.
3. Konfirmasi peringatan yang muncul (aksi ini MENGGANTI seluruh data yang
   sedang berjalan).
4. Backend otomatis membuat backup dari database yang SEDANG aktif ke
   `backend/app/backups/` (bertimestamp) SEBELUM menimpanya — jadi data
   sebelum restore tidak pernah hilang total walau ternyata salah pilih
   file. File yang diupload juga divalidasi harus benar-benar file SQLite
   valid (bukan sembarang file) sebelum diterima.
5. Halaman otomatis reload setelah restore berhasil, menampilkan data dari
   file yang baru diupload.

## Sinkronisasi Google Sheets — DIHAPUS

Fitur ini (dulu Tahap 12) sudah dihapus total (lihat bagian "REVISI:
Dashboard Collapse/Expand, Hak Akses Admin, Hapus Google Sheets, Laporan
PDF" di bawah) sejak migrasi ke PostgreSQL selesai dan menjadi satu-satunya
sumber data aplikasi ini — tidak ada lagi kebutuhan menyalin data ke Google
Sheets sebagai cadangan. `GOOGLE_SHEET_ID`/`GOOGLE_CREDENTIALS_JSON`/
`credentials.json`/`SYNC_RETRY_INTERVAL_DETIK` TIDAK dipakai lagi di
mana pun — aman dihapus dari environment variable server kalau sebelumnya
sempat diisi.

## Database & Kredensial — TIDAK ikut ke Git

`mugen_hair.db` **sengaja tidak di-commit** (lihat `.gitignore`) — karena
isinya data asli toko. Lihat bagian **Deployment** di atas untuk cara
menyiapkannya di server.

## Catatan Penting

- `database.py` di folder ini **tidak boleh diedit** kecuali memang ada
  perubahan logika bisnis yang diminta eksplisit — dan kalau itu terjadi,
  perubahan yang sama juga harus diterapkan ke aplikasi Python Desktop supaya
  keduanya tetap identik.
- Setiap tahap diuji dan dibandingkan hasilnya dengan aplikasi Desktop
  sebelum lanjut ke tahap berikutnya.
- Ganti `ADMIN_BOOTSTRAP_PASSWORD` dan `SECRET_KEY` dari nilai default
  SEBELUM aplikasi ini dipakai dengan data sungguhan (lihat bagian
  Deployment) — nilai default hanya aman untuk development lokal.

## TAHAP: File Upload (Logo/Hero/Foto/QRIS/Bukti) Dipindah ke Database

**Masalah**: Logo, Gallery, Hero Image/Video, Foto About, Background
Website, Foto Barber, QRIS, dan Bukti Reimburse terus "hilang" (gambar
rusak/404) di web maupun halaman booking publik. Root cause SAMA PERSIS
seperti "AUDIT KRITIS" migrasi PostgreSQL di atas (Render Free tier TIDAK
mendukung Persistent Disk sama sekali) — tapi migrasi itu dulu HANYA
memindahkan data TABEL database, isi file yang diupload lewat aplikasi
(disimpan sebagai file fisik di `backend/app/static/...`) tidak pernah
ikut dipindahkan, jadi tetap hilang tiap deploy/restart walau baris
database yang menyimpan NAMA filenya sudah persisten.

**Solusi**: konten file (bytes) disimpan LANGSUNG di kolom BLOB/BYTEA
database yang sudah persisten (sama seperti solusi data tabel), disk lokal
`backend/app/static/...` tidak dipakai lagi sama sekali untuk upload:
- **Aset slot tunggal** (Logo, Hero Image, Hero Video, Foto About,
  Background Website, QRIS — satu file aktif per fitur, diganti tiap
  upload baru): tabel baru generik `file_asset` (`key` PRIMARY KEY,
  `filename`, `content_type`, `data` BLOB/BYTEA, `updated_at`), dikelola
  modul baru `file_asset_db.py` (`simpan()`/`ambil()`/`ambil_meta()`/
  `hapus()` dipanggil per fitur dengan `key` berbeda).
- **Aset banyak baris** (Gallery, Foto Barber, Bukti Reimburse — bisa
  banyak sekaligus): kolom BLOB baru ditambahkan LANGSUNG ke tabel
  masing-masing yang sudah ada (`website_gallery.data`,
  `barbers.foto_data`, `reimburse.bukti_data`), supaya kepemilikan data
  tetap co-located dengan baris induknya (kolom `*_filename` yang lama
  TETAP dipakai untuk menentukan Content-Type dari ekstensi).
- Endpoint GET gambar/video (`routers/pengaturan.py`, `routers/website.py`,
  `routers/booking.py`, `routers/reimburse.py`) diganti dari
  `FileResponse(path, ...)` (baca dari disk) ke `Response(content=data,
  ...)` (serve dari memory) — pola yang sudah dipakai lama untuk PDF di
  `laporan_pdf.py`. **API contract TIDAK berubah** (endpoint tetap
  mengembalikan `_url` string dengan `?v=` cache-bust yang sama persis) —
  **tidak ada perubahan frontend sama sekali**.
- Migrasi kolom baru ke tabel yang SUDAH ADA (barbers/website_gallery/
  reimburse) memakai pola idempoten yang sama seperti seluruh migrasi
  lain di proyek ini: jalur SQLite lewat `PRAGMA table_info()` dicek
  SEBELUM `CREATE TABLE IF NOT EXISTS`, jalur PostgreSQL lewat
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` terpisah (BUKAN dibakukan ke
  blok `CREATE TABLE IF NOT EXISTS` yang jadi no-op untuk tabel yang sudah
  berdiri — kesalahan ini pernah menyebabkan bug produksi di tahap
  sebelumnya, lihat catatan Pengeluaran).
- Folder `backend/app/static/{logo,hero_image,hero_video,about,
  background,gallery,barber_foto,qris,reimburse_bukti}/` (beserta
  `.gitkeep`-nya) sudah tidak dipakai lagi dan dihapus dari repo.

**Trade-off yang diketahui/diterima**: `FileResponse` otomatis mengisi
header `Last-Modified`/`ETag` (mengaktifkan HTTP conditional GET/304),
`Response` biasa tidak — bukan masalah di sini karena aplikasi sudah
punya skema cache-busting sendiri lewat parameter `?v=<filename>` di
setiap URL gambar, jadi kebenaran gambar yang ditampilkan tidak bergantung
pada header itu.

**Di luar cakupan (gap lama, bukan regresi)**: `pengaturan_backup.py`
(`POSTGRES_BACKUP_TABLES`) sudah lebih dulu tidak mencakup tabel
`reimburse`/`website_gallery`/`slip_gaji`/`kasbon` dkk di fitur
Backup/Restore — tabel `file_asset` baru dan kolom BLOB baru ini
mengikuti gap yang sudah ada itu, bukan gap baru yang ditambahkan tahap
ini.

## Migrasi Cloudflare R2 (Storage File)

Lanjutan dari bagian **TAHAP: File Upload ... Dipindah ke Database** di
atas: file (Logo, Hero Image/Video, Foto About, Background Website, QRIS,
Foto Barber, Gallery, Bukti Reimburse) dipindah SEKALI LAGI — dari BLOB di
database (Neon) ke **Cloudflare R2** (object storage S3-compatible) —
supaya database hanya menyimpan METADATA (nama file, tipe, key objek R2),
bukan lagi isi byte file itu sendiri (database tetap ringan walau jumlah
file yang diupload terus bertambah).

### Arsitektur

- **Bucket R2 tetap PRIVATE** — backend TETAP jadi satu-satunya gerbang
  akses file, PERSIS seperti pola BLOB-di-database sebelumnya. Ini
  keputusan sadar (BUKAN default R2): audit kode menemukan seluruh frontend
  (`js/pages/booking.js`, `book_public.js`, `pengaturan.js`, `brand.js`)
  memakai pola `MUGEN_API_BASE + data.xxx_url` di puluhan tempat, yang
  mengasumsikan `xxx_url` adalah PATH RELATIF ke backend yang sama — kalau
  field itu diisi URL R2 absolut langsung, hasilnya jadi string gabungan
  yang rusak. Dengan backend tetap jadi proxy, **TIDAK ADA endpoint API
  ataupun kode frontend yang berubah sama sekali** — endpoint GET yang
  sudah ada (`GET /api/pengaturan/logo`, `GET /api/website/hero-image`,
  dst) sekarang membaca bytes dari R2 (lewat `r2_storage.get_bytes()`)
  alih-alih `SELECT ... BLOB`, tapi bentuk respons ke client identik.
- **`backend/app/r2_storage.py`** (baru) — klien S3-compatible generik
  lewat `boto3`, diarahkan ke endpoint R2 (bukan AWS): `upload()`/
  `get_bytes()`/`delete()`/`validasi_dan_beri_nama()`. Retry otomatis (3x,
  exponential backoff bawaan `botocore`) + timeout (connect 10 detik, baca
  30 detik) untuk kegagalan transient. `IS_ENABLED` = `False` kalau salah
  satu dari `R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`/`R2_BUCKET_NAME`/
  `R2_ENDPOINT_URL` kosong — dalam kondisi itu, jalur BLOB-di-database LAMA
  dipakai apa adanya (byte-identik dengan sebelum migrasi ini), supaya
  **development lokal tanpa kredensial R2 tetap 100% berfungsi** tanpa
  konfigurasi tambahan apa pun (pola yang sama seperti `DATABASE_URL`
  menentukan SQLite vs PostgreSQL di `db_compat.py`).
- **Struktur folder/prefix di bucket**:
  ```
  logos/      -- Logo Barbershop
  assets/     -- Hero Image, Hero Video, Foto About, Background Website
  barbers/    -- Foto Barber
  gallery/    -- Gallery (foto & video)
  payments/   -- QRIS, Bukti Reimburse
  ```
  (Tidak ada folder `customers/` — diaudit langsung, TIDAK ADA fitur "Foto
  Customer" di aplikasi ini sama sekali, jadi tidak dibuat.)
- **Nama file di bucket**: `uuid4().hex` + ekstensi asli (mis.
  `logos/3f9a1c...b2.png`) — SELALU unik per upload (bukan lagi nama
  deterministik seperti `logo.png`/`barber-3.jpg` sebelumnya), sekaligus
  memperbaiki bug cache-busting laten: nama file deterministik lama
  membuat parameter `?v=` TIDAK PERNAH berubah kalau ekstensi upload baru
  sama dengan yang lama, berpotensi membuat browser terus menampilkan
  gambar basi dari cache.

### Perubahan skema (idempotent, TIDAK menghapus/mengubah data lama)

Empat kolom baru (`*_r2_key`, TEXT, nullable) — `backend/app/
r2_storage_migrasi.py` (jalur SQLite) & `postgres_schema.py` (jalur
PostgreSQL, `ADD COLUMN IF NOT EXISTS`):
- `file_asset.r2_key`
- `website_gallery.r2_key`
- `barbers.foto_r2_key`
- `reimburse.bukti_r2_key`

Kolom BLOB lama (`file_asset.data`, `website_gallery.data`,
`barbers.foto_data`, `reimburse.bukti_data`) **TIDAK dihapus** — baris LAMA
(`*_r2_key IS NULL`) tetap dibaca dari situ sebagai fallback otomatis,
sampai dibackfill manual lewat `migrate_blobs_to_r2.py` (lihat di bawah).
File BARU (diupload setelah R2 dikonfigurasi) langsung ke R2 sepenuhnya,
kolom BLOB-nya dikosongkan (`NULL`, atau `b""` khusus `file_asset.data`
yang historis `NOT NULL` — placeholder murni, tidak pernah dibaca lagi
kalau `r2_key` terisi).

### Backfill file lama: `migrate_blobs_to_r2.py`

Script MANUAL (SATU KALI, tidak pernah dipanggil otomatis) untuk
mengupload file yang SUDAH ADA di kolom BLOB (dari sebelum R2
dikonfigurasi) ke R2, lalu mengisi kolom `*_r2_key`-nya. **Tidak
menghapus/mengubah kolom BLOB lama sama sekali** — murni redundan setelah
backfill (bisa dibersihkan manual belakangan sebagai keputusan terpisah).
Idempotent (baris yang sudah punya `r2_key` dilewati) & aman dijalankan
berulang.

```bash
# dari folder backend/app, dengan DATABASE_URL (Neon) DAN R2_* lengkap:
DATABASE_URL="postgresql://..." R2_ACCOUNT_ID=... R2_ACCESS_KEY_ID=... \
  R2_SECRET_ACCESS_KEY=... R2_BUCKET_NAME=... \
  python migrate_blobs_to_r2.py --dry-run   # lihat jumlah baris dulu
DATABASE_URL="postgresql://..." R2_ACCOUNT_ID=... ... python migrate_blobs_to_r2.py  # backfill sungguhan
```

### Validasi upload (BARU — sebelumnya sebagian besar tidak ada batas ukuran)

- Format file: tetap sama seperti sebelumnya per fitur (whitelist ekstensi
  masing-masing, tidak berubah).
- **Ukuran maksimum** (baru, `r2_storage.py`): gambar/dokumen 10MB, video
  tetap 50MB (batas lama, tidak berubah). Sebelum migrasi ini, HANYA video
  yang punya batas ukuran — audit menemukan Logo/Foto Barber/Bukti
  Reimburse/dst tidak pernah dibatasi sama sekali.
- Nama file unik (uuid4, lihat di atas).
- Kegagalan upload/koneksi ke R2 dilempar sebagai `r2_storage.R2Error`,
  ditangani setiap router upload sebagai **HTTP 502** dengan pesan jelas
  (sebelumnya: tidak relevan, BLOB-ke-database praktis tidak pernah gagal).

### Bug ditemukan & diperbaiki SAAT audit migrasi ini (bukan diminta eksplisit, tapi langsung relevan)

Tiga endpoint mengembalikan dict hasil `SELECT *` (dari `database.py`,
yang harus tetap identik dengan aplikasi Desktop) APA ADANYA sebagai JSON
— begitu barber/klaim yang disasar punya foto/bukti **sungguhan**
tersimpan (kolom BLOB berisi bytes asli, bukan `NULL`), FastAPI **crash
500** (`UnicodeDecodeError`) karena mencoba men-serialize bytes biner
sebagai JSON. Bug ini SUDAH ADA sejak kolom `foto_data`/`bukti_data`
dibuat (Tahap 16), tidak terkait R2 sama sekali — baru kelihatan sekarang
karena migrasi ini adalah pengujian end-to-end PERTAMA dengan foto/bukti
sungguhan pada endpoint-endpoint ini:
- **Dashboard Owner & Dashboard Barber** (`routers/dashboard.py`) — field
  `ringkasan["barber"]` (dari `database.get_ringkasan_barber_bulan()`).
- **Setting > Barber** (`routers/pengaturan.py`) — list, tambah, ubah.
- **Booking > status/urutan/foto Barber** (`routers/booking.py`).
- **Input Data / Slip Gaji / Kasbon / Reimburse / Izin & Cuti dropdown**
  (`routers/input_data.py`, `GET /barbers` & `GET /karyawan`).
- **Reimburse** (`reimburse_db.py::_lengkapi()`) — kolom `bukti_data` ADA
  LANGSUNG di baris `reimburse` itu sendiri (bukan lewat barber).

**Diperbaiki** dengan membuang field biner (`foto_data`/`foto_r2_key`/
`bukti_data`/`bukti_r2_key`) di lapisan router/API, TEPAT SEBELUM
dikembalikan ke client — BUKAN di `database.py` (yang harus tetap
identik dengan aplikasi Desktop). Diverifikasi frontend tidak pernah
membaca field itu langsung (selalu lewat `*_url` yang sudah dibangun
terpisah), jadi pembuangan ini tidak menghilangkan data apa pun yang
sebenarnya dipakai UI.

### Tidak diubah sama sekali

`database.py` (termasuk `SELECT *` yang jadi akar bug di atas — TIDAK
disentuh, sesuai aturan file ini harus identik dengan aplikasi Desktop),
seluruh endpoint API (path, method, bentuk request/response — hanya isi
byte yang berubah), seluruh kode frontend (`frontend/` — nol baris
diubah), rumus komisi/bonus/absensi/gaji.

### Pengujian

Diuji lewat `TestClient` (backend berjalan sungguhan, database SQLite
lokal — Cloudflare R2 sungguhan TIDAK bisa diakses dari sandbox
pengembangan ini, koneksi TCP keluar port 443/5432/dst ke domain
eksternal diblokir kebijakan jaringan sandbox, lihat catatan serupa di
bagian Migrasi PostgreSQL) — jalur R2 diuji lewat **client S3 tiruan**
(dependency-injection ke `r2_storage._client`, menyimpan objek di memory)
untuk memverifikasi seluruh pipeline upload/baca/hapus tanpa
menyentuh kode aslinya sama sekali:

1. **Jalur R2 nonaktif (development lokal, tanpa env var R2_*)**: seluruh
   7 endpoint upload (Logo, Hero Image, Hero Video, Foto About, Background
   Website, Gallery, Foto Barber, QRIS, Bukti Reimburse) diuji end-to-end
   (upload → baca → hapus) — byte-identik dengan perilaku sebelum migrasi
   ini, tidak ada regresi.
2. **Jalur R2 aktif (client S3 tiruan)**: seluruh 7 endpoint di atas diuji
   ulang — file tersimpan di object store tiruan dengan prefix yang benar
   (`logos/`, `assets/`, `barbers/`, `gallery/`, `payments/`), dibaca
   kembali dengan isi & Content-Type benar, **file lama otomatis terhapus
   dari R2** saat diganti (upload logo 2x → key pertama hilang dari store)
   maupun saat data induknya dihapus (hapus klaim Reimburse → key bukti
   ikut hilang; foto Barber lain yang tidak disentuh TETAP ada).
3. **Validasi**: format tidak didukung ditolak `422` (file lama TIDAK
   ikut terhapus), ukuran melebihi batas ditolak `422` dengan pesan jelas.
4. **Kegagalan R2** (client S3 tiruan yang sengaja dibuat gagal
   connect): endpoint upload mengembalikan `502` dengan pesan jelas,
   bukan crash `500` mentah.
5. **Backfill (`migrate_blobs_to_r2.py`)**: logika inti (SELECT baris
   `r2_key IS NULL`, upload, UPDATE `r2_key`) diverifikasi terhadap baris
   BLOB legacy yang sengaja disisipkan manual — berhasil ter-backfill,
   `r2_key` terisi benar, DAN kolom BLOB lama **tetap utuh** (tidak
   terhapus) setelahnya. Koneksi Postgres/Neon sungguhan tidak bisa diuji
   dari sandbox ini (lihat catatan jaringan di atas) — script menolak
   berjalan sama sekali kalau `DATABASE_URL` tidak mengarah ke PostgreSQL,
   mencegah backfill tidak sengaja jalan ke SQLite lokal.
6. **Regresi bug yang ditemukan** (lihat bagian di atas): Dashboard
   Owner/Barber, Setting > Barber, Booking > Foto Barber, Input Data
   dropdown, dan Reimburse semuanya diuji ULANG dengan barber/klaim yang
   BENAR-BENAR punya foto/bukti tersimpan — seluruhnya `200`, tidak ada
   lagi crash `500`.
7. `python -m py_compile` untuk seluruh file backend yang disentuh/baru —
   tidak ada syntax error.
