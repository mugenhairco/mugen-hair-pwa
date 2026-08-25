"""
izin_cuti_migrasi.py — Migrasi Sistem Kuota Izin & Cuti Dinamis
=============================================================================
PERMINTAAN OWNER (Agustus 2026): "PENYESUAIAN & SISTEM DINAMIS CUTI DAN
IZIN" -- kebijakan kuota cuti lama (izin_cuti_settings, lihat
izin_cuti_db.py) hanya berlaku untuk jenis='cuti', periode SELALU
diangkar ke Januari (tahun kalender), dan tidak ada kuota/H-min terpisah
untuk jenis='izin'. Migrasi ini:

1. Menambah kolom baru ke `izin_cuti_settings` (idempotent, pola PRAGMA
   table_info() sama seperti karyawan_migrasi.py) supaya Owner bisa
   mengatur: mode kuota (terpisah/gabungan), kuota izin & cuti (atau
   gabungan) secara independen, tanggal mulai periode (anchor -- BUKAN
   lagi selalu Januari), H- minimal pengajuan izin (terpisah dari H-min
   cuti yang sudah ada), dan `auto_libur_tidak_absen_aktif` (default OFF
   -- barber yang tidak check-in pada hari kerja otomatis direkap jadi
   cuti & mengurangi kuota, lihat auto_libur_db.py).
2. Membuat tabel baru `izin_cuti_saldo_awal` -- snapshot HISTORIS saldo
   cuti karyawan per titik cut-off (murni catatan/tampilan, TIDAK
   pernah ikut dihitung mesin kuota dinamis -- lihat izin_cuti_db.py::
   _validasi_kebijakan_pengajuan(), yang mengabaikan tanggal SEBELUM
   `periode_mulai_dasar`). Riwayat pengajuan (`izin_cuti`) TIDAK disentuh
   sama sekali oleh migrasi ini.
3. SEKALI SAJA (idempotent lewat cek baris yang sudah ada, bukan flag
   settings) men-seed titik cut-off awal sesuai instruksi Owner: saldo
   akhir 31 Agustus 2026 untuk 5 karyawan (Jack/Roma/Rafik/Rendi/Mifta),
   dan konfigurasi periode dinamis pertama (10 hari/3 bulan mulai
   1 September 2026) -- HANYA untuk tenant yang benar-benar punya
   KELIMA nama karyawan itu sekaligus (heuristik pencocokan nama,
   case-insensitive/trim -- lihat _cari_tenant_seed_awal() di bawah).
   Tenant lain (termasuk tenant baru di masa depan) TIDAK tersentuh sama
   sekali oleh langkah #3 -- HANYA langkah #1 (kolom baru, semua default
   0/off/'terpisah', byte-for-byte backward compatible) yang berlaku
   universal, sama seperti seluruh migrasi kebijakan dinamis sebelumnya
   di modul ini.
"""

import logging

from database import get_conn

logger = logging.getLogger("mugen.izin_cuti_migrasi")

# Nama 5 karyawan persis seperti disebutkan Owner -- HANYA dipakai untuk
# mencocokkan tenant mana yang menerima seed cut-off Agustus 2026 di bawah,
# dibandingkan case-insensitive & di-trim supaya tidak gagal gara-gara
# spasi/kapitalisasi kecil di data asli.
_SALDO_AWAL_AGUSTUS_2026 = {
    "jack": 5,
    "roma": 3,
    "rafik": 7,
    "rendi": 0,
    "mifta": 0,
}
_CUTOFF_AGUSTUS_2026 = "2026-08-31"
_PERIODE_MULAI_DASAR_AWAL = "2026-09-01"
_PERIODE_BULAN_AWAL = 3
_KUOTA_CUTI_AWAL = 10


def migrasi_izin_cuti():
    """JALUR SQLITE SAJA (dipanggil dari main.py::on_startup() bersama
    migrasi_*() lain) -- PRAGMA table_info() di bawah ini SQL SQLite murni,
    tidak berlaku di PostgreSQL. Jalur PostgreSQL: kolom yang sama sudah
    langsung dibuat lewat `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` di
    postgres_schema.py (blok izin_cuti_settings). Seed data (langkah #3
    docstring modul ini) SENGAJA dipisah ke seed_konfigurasi_awal_agustus_2026()
    di bawah -- fungsi itu portable (SQL biasa lewat get_conn(), TANPA
    PRAGMA) sehingga dipanggil TERPISAH dari main.py untuk KEDUA jalur
    (lihat main.py::on_startup(), bagian bersama setelah percabangan
    SQLite/PostgreSQL, pola sama seperti _bootstrap_admin_pertama())."""
    with get_conn() as conn:
        _migrasi_kolom_settings_dinamis(conn)
        _migrasi_tabel_saldo_awal(conn)


def _migrasi_kolom_settings_dinamis(conn):
    kolom = [r["name"] for r in conn.execute("PRAGMA table_info(izin_cuti_settings)").fetchall()]
    if "mode_kuota" not in kolom:
        conn.execute("ALTER TABLE izin_cuti_settings ADD COLUMN mode_kuota TEXT NOT NULL DEFAULT 'terpisah'")
    if "kuota_izin_hari" not in kolom:
        conn.execute("ALTER TABLE izin_cuti_settings ADD COLUMN kuota_izin_hari INTEGER NOT NULL DEFAULT 0")
    if "kuota_gabungan_hari" not in kolom:
        conn.execute("ALTER TABLE izin_cuti_settings ADD COLUMN kuota_gabungan_hari INTEGER NOT NULL DEFAULT 0")
    if "periode_mulai_dasar" not in kolom:
        conn.execute("ALTER TABLE izin_cuti_settings ADD COLUMN periode_mulai_dasar TEXT")
    if "h_min_pengajuan_izin" not in kolom:
        conn.execute("ALTER TABLE izin_cuti_settings ADD COLUMN h_min_pengajuan_izin INTEGER NOT NULL DEFAULT 0")
    if "auto_libur_tidak_absen_aktif" not in kolom:
        conn.execute("ALTER TABLE izin_cuti_settings ADD COLUMN auto_libur_tidak_absen_aktif INTEGER NOT NULL DEFAULT 0")


def _migrasi_tabel_saldo_awal(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS izin_cuti_saldo_awal (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id       INTEGER NOT NULL,
            barber_id       INTEGER NOT NULL,
            jenis           TEXT NOT NULL DEFAULT 'cuti',
            saldo_hari      INTEGER NOT NULL,
            berlaku_sampai  TEXT NOT NULL,
            catatan         TEXT,
            created_at      TEXT NOT NULL,
            FOREIGN KEY (barber_id) REFERENCES barbers(id)
        )
    """)


def _cari_tenant_seed_awal(conn):
    """Cari tenant yang barbers-nya (aktif atau tidak -- nama tetap harus
    cocok persis) memuat KELIMA nama di _SALDO_AWAL_AGUSTUS_2026 sekaligus.
    Return tenant_id, atau None kalau tidak ada/lebih dari satu tenant yang
    cocok (ambigu -- sengaja tidak menebak, lebih aman diam daripada salah
    tenant)."""
    rows = conn.execute("SELECT tenant_id, LOWER(TRIM(nama)) AS nama_norm FROM barbers "
                         "WHERE tenant_id IS NOT NULL").fetchall()
    per_tenant = {}
    for r in rows:
        per_tenant.setdefault(r["tenant_id"], set()).add(r["nama_norm"])
    target = set(_SALDO_AWAL_AGUSTUS_2026.keys())
    cocok = [tid for tid, nama_set in per_tenant.items() if target.issubset(nama_set)]
    if len(cocok) == 1:
        return cocok[0]
    if len(cocok) == 0:
        logger.info("Seed saldo awal Izin & Cuti (Agustus 2026): tidak ada tenant dengan kelima "
                     "nama karyawan (Jack/Roma/Rafik/Rendi/Mifta) -- dilewati (no-op).")
    else:
        logger.warning("Seed saldo awal Izin & Cuti (Agustus 2026): %d tenant sama-sama punya "
                        "kelima nama karyawan itu -- AMBIGU, dilewati supaya tidak salah sasaran. "
                        "Isi manual lewat Pengaturan Izin & Cuti kalau perlu.", len(cocok))
    return None


def seed_konfigurasi_awal_agustus_2026():
    """PORTABLE (SQL biasa lewat get_conn(), TANPA PRAGMA) -- SENGAJA
    dipisah dari migrasi_izin_cuti() (yang SQLite-only) supaya bisa
    dipanggil dari main.py::on_startup() untuk KEDUA jalur DB (SQLite
    MAUPUN PostgreSQL), di bagian bersama SETELAH percabangan (pola sama
    seperti _bootstrap_admin_pertama()) -- tabel yang disentuh di sini
    (izin_cuti_settings/izin_cuti_saldo_awal/barbers) sudah pasti ada di
    titik itu untuk kedua jalur (SQLite: init_izin_cuti_db() jalur biasa;
    PostgreSQL: postgres_schema.create_all()).

    SEKALI SAJA (idempotent lewat cek baris `izin_cuti_saldo_awal` yang
    sudah ada untuk tenant+cutoff ini, BUKAN flag settings terpisah --
    kalau baris itu sudah ada, migrasi sebelumnya SUDAH menyelesaikan
    seluruh langkah ini, termasuk konfigurasi periode, jadi aman berhenti
    lebih awal). Import izin_cuti_db di DALAM fungsi (bukan di atas modul)
    supaya urutan impor main.py tetap bebas -- izin_cuti_db sendiri TIDAK
    mengimpor modul ini (menghindari import siklik)."""
    import izin_cuti_db

    with get_conn() as conn:
        tenant_id = _cari_tenant_seed_awal(conn)
        if tenant_id is None:
            return
        sudah_ada = conn.execute(
            "SELECT 1 FROM izin_cuti_saldo_awal WHERE tenant_id = ? AND berlaku_sampai = ? LIMIT 1",
            (tenant_id, _CUTOFF_AGUSTUS_2026),
        ).fetchone()
        if sudah_ada:
            return
        barbers = conn.execute(
            "SELECT id, LOWER(TRIM(nama)) AS nama_norm FROM barbers WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchall()
        id_per_nama = {b["nama_norm"]: b["id"] for b in barbers}
        from datetime import datetime
        now = datetime.now().isoformat(timespec="seconds")
        jumlah_dicatat = 0
        for nama, saldo in _SALDO_AWAL_AGUSTUS_2026.items():
            barber_id = id_per_nama.get(nama)
            if barber_id is None:
                continue
            conn.execute(
                """INSERT INTO izin_cuti_saldo_awal
                       (tenant_id, barber_id, jenis, saldo_hari, berlaku_sampai, catatan, created_at)
                   VALUES (?, ?, 'cuti', ?, ?, ?, ?)""",
                (tenant_id, barber_id, saldo, _CUTOFF_AGUSTUS_2026,
                 "Penyesuaian saldo cuti awal (migrasi sistem kuota dinamis, permintaan Owner).", now),
            )
            jumlah_dicatat += 1
        logger.info("Seed saldo awal Izin & Cuti (Agustus 2026): tenant_id=%s, %d baris dicatat.",
                     tenant_id, jumlah_dicatat)

    # Konfigurasi periode dinamis pertama: 10 hari cuti / 3 bulan, mulai
    # 1 September 2026 -- HANYA kalau tenant ini belum pernah mengatur
    # kuota_periode_bulan sama sekali (Owner mungkin sudah mengubahnya
    # sendiri lewat UI sebelum migrasi ini sempat jalan lagi -- TIDAK
    # PERNAH menimpa pengaturan yang sudah diisi Owner).
    settings = izin_cuti_db.get_cuti_settings(tenant_id)
    if settings["kuota_periode_bulan"] == 0 and not settings["periode_mulai_dasar"]:
        izin_cuti_db.set_cuti_settings(
            tenant_id,
            kuota_periode_bulan=_PERIODE_BULAN_AWAL,
            kuota_maksimal_hari=_KUOTA_CUTI_AWAL,
            periode_mulai_dasar=_PERIODE_MULAI_DASAR_AWAL,
        )
        logger.info("Seed konfigurasi periode Izin & Cuti awal: tenant_id=%s, %d hari/%d bulan mulai %s.",
                     tenant_id, _KUOTA_CUTI_AWAL, _PERIODE_BULAN_AWAL, _PERIODE_MULAI_DASAR_AWAL)
