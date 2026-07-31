"""
pengaturan_backup.py — Backup Database (TAHAP 10; PostgreSQL: tahap lanjutan)
=============================================================================
SQLite (DATABASE_URL kosong):
Export: kirim file .db apa adanya (dipakai lewat FileResponse di router,
tidak butuh fungsi di sini).
Import: mengganti file database yang sedang dipakai dengan file upload.
Ini operasi BERISIKO, jadi:
1. Validasi dulu file yang diupload benar-benar file SQLite (cek magic
   header), supaya tidak menimpa database yang jalan dengan file sampah.
2. SELALU backup database yang sedang aktif ke folder backups/ (dengan
   timestamp) SEBELUM menimpanya — supaya data lama tidak pernah hilang
   total walau admin salah upload file.

FONDASI Multi-Tenant Phase 1.1: baik SQLite maupun Postgres di file ini
bisa menampung LEBIH DARI SATU tenant (row-based multi-tenancy, lihat
tenant_migrasi.py) -- BUG SERIUS yang diperbaiki di sini: sebelum Phase
1.1, export_database_postgres()/import_database_postgres() SAMA SEKALI
TIDAK memfilter per tenant (SELECT * / DELETE+INSERT ulang SELURUH tabel
bisnis lintas tenant), sehingga Owner tenant mana pun yang punya izin
Backup bisa: (a) mengunduh dump JSON berisi data SELURUH tenant lain
(termasuk password_hash user tenant lain), dan (b) MENGHAPUS & MENIMPA
data SELURUH tenant lain sekaligus lewat satu kali Import. Diperbaiki
dengan memfilter export/import Postgres per tenant_id (langsung untuk
tabel yang punya kolom tenant_id sendiri, JOIN untuk tabel yang di-scope
transitif -- persis kategori yang sama dipakai tenant_migrasi.py).

Jalur SQLite: file .db adalah SATU FILE UTUH (tidak ada cara mem-filter
sebagian baris lewat copy file) -- Export/Import lewat file di jalur ini
HANYA aman dipakai kalau instalasi SQLite itu memang HANYA berisi SATU
tenant (kasus umum: instalasi lokal/legacy sebelum multi-tenant aktif).
Router (routers/pengaturan.py) menolak Export/Import jalur SQLite kalau
tabel `tenants` sudah berisi LEBIH DARI SATU tenant (lihat
_tolak_backup_sqlite_multi_tenant()) -- deployment produksi multi-tenant
WAJIB memakai PostgreSQL, yang di-scope per tenant di bawah.

PostgreSQL (DATABASE_URL diisi) -- TIDAK ada satu file tunggal yang bisa
di-copy seperti SQLite, jadi Export/Import di sini memakai snapshot JSON
seluruh tabel MILIK SATU TENANT (bukan pg_dump biner -- lebih portabel,
tidak butuh binary client Postgres terpasang di proses backend) lewat
export_database_postgres()/import_database_postgres() di bawah. Router
(routers/pengaturan.py) memilih fungsi mana yang dipanggil berdasarkan
db_compat.IS_POSTGRES.
"""

import json
import os
import shutil
from datetime import datetime

import db_compat
from database import DB_PATH, get_conn

SQLITE_MAGIC = b"SQLite format 3\x00"
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "backups")

# Tabel yang punya kolom tenant_id LANGSUNG (sama persis daftar
# tenant_migrasi.py::_TABEL_TENANT_LANGSUNG, kecuali pengeluaran/produk/
# pemasukan/kas_* yang TIDAK diikutkan di sini -- backup ini sengaja
# mencakup HANYA data inti operasional barbershop sejak Tahap 10, belum
# diperluas ke seluruh modul Karyawan/Keuangan yang lahir belakangan;
# lihat technical debt di laporan hardening Phase 1.1).
POSTGRES_BACKUP_TABEL_LANGSUNG = [
    "barbers", "services", "produk", "pengeluaran", "users",
    "bookings", "closed_slot", "toko_libur",
]

# Tabel yang TIDAK punya kolom tenant_id sendiri (di-scope TRANSITIF lewat
# JOIN ke tabel induk langsung) -- kategori SAMA PERSIS dipakai di seluruh
# proyek ini (lihat tenant_migrasi.py, kasbon_db.py, dst). Value = klausa
# JOIN...WHERE dari alias "t" (tabel ini) ke tenant_id, dengan SATU
# parameter placeholder ('?') untuk tenant_id.
POSTGRES_BACKUP_TABEL_TRANSITIF = {
    "transaksi": "JOIN barbers b ON b.id = t.barber_id WHERE b.tenant_id = ?",
    "transaksi_detail": ("JOIN transaksi tr ON tr.id = t.transaksi_id "
                          "JOIN barbers b ON b.id = tr.barber_id WHERE b.tenant_id = ?"),
    "absensi_libur": "JOIN barbers b ON b.id = t.barber_id WHERE b.tenant_id = ?",
    "produk_mutasi": "JOIN produk p ON p.id = t.produk_id WHERE p.tenant_id = ?",
    "booking_items": "JOIN bookings bk ON bk.id = t.booking_id WHERE bk.tenant_id = ?",
}

# Urutan SISIPKAN saat import (induk dulu, FK-safe) -- urutan hapus (anak
# dulu) yang sesungguhnya dijalankan ada di _hapus_scoped() di bawah
# (butuh sintaks DELETE...WHERE id IN (SELECT...) berbeda per tabel,
# jadi ditulis eksplisit, bukan di-generate dari daftar ini) -- daftar
# ini murni acuan urutan KEBALIKANNYA untuk INSERT.
_URUTAN_SISIP = [
    "services", "barbers", "users", "pengeluaran",
    "absensi_libur", "transaksi", "transaksi_detail",
    "produk", "produk_mutasi",
    "toko_libur", "bookings", "closed_slot", "booking_items",
]

POSTGRES_BACKUP_FORMAT = "mugen-postgres-backup-v2"


def validasi_file_sqlite(konten: bytes):
    if len(konten) < len(SQLITE_MAGIC) or konten[: len(SQLITE_MAGIC)] != SQLITE_MAGIC:
        raise ValueError("File yang diupload bukan file database SQLite yang valid (.db).")


def sqlite_punya_lebih_dari_satu_tenant() -> bool:
    """Dipakai router untuk menolak Export/Import SQLite (operasi file
    UTUH, tidak bisa difilter per tenant) kalau instalasi ini kebetulan
    sudah punya lebih dari satu tenant -- lihat penjelasan di docstring
    modul ini. PENTING: pakai database.get_conn() (dialek SQLite asli),
    BUKAN db_compat.get_conn() (connection pool Postgres-ONLY, dipakai
    fungsi lain di file ini yang memang HANYA pernah dipanggil saat
    db_compat.IS_POSTGRES True) -- fungsi ini justru dipanggil dari jalur
    SQLite (db_compat.IS_POSTGRES False), jadi harus lewat database.py."""
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM tenants").fetchone()
    return int(row["n"] or 0) > 1


def buat_backup_sebelum_import() -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tujuan = os.path.join(BACKUP_DIR, f"mugen_hair_sebelum_import_{stamp}.db")
    if os.path.isfile(DB_PATH):
        shutil.copy2(DB_PATH, tujuan)
    return tujuan


def import_database(konten: bytes) -> str:
    """Return path backup yang dibuat sebelum penimpaan (untuk ditampilkan ke admin)."""
    validasi_file_sqlite(konten)
    backup_path = buat_backup_sebelum_import()
    with open(DB_PATH, "wb") as fh:
        fh.write(konten)
    return backup_path


def export_database_postgres(tenant_id: int) -> bytes:
    with db_compat.get_conn() as conn:
        tabel = {}
        for t in POSTGRES_BACKUP_TABEL_LANGSUNG:
            tabel[t] = [dict(r) for r in conn.execute(
                f"SELECT * FROM {t} WHERE tenant_id = ?", (tenant_id,)).fetchall()]
        for t, join_where in POSTGRES_BACKUP_TABEL_TRANSITIF.items():
            tabel[t] = [dict(r) for r in conn.execute(
                f"SELECT t.* FROM {t} t {join_where}", (tenant_id,)).fetchall()]
        # settings: tenant-scoped lewat prefix "<tenant_id>:" pada key
        # (lihat database.py::_kunci_tenant()), BUKAN kolom tenant_id.
        tabel["settings"] = [dict(r) for r in conn.execute(
            "SELECT * FROM settings WHERE key LIKE ?", (f"{tenant_id}:%",)).fetchall()]
    return json.dumps({"format": POSTGRES_BACKUP_FORMAT, "tenant_id": tenant_id,
                        "dibuat_pada": datetime.now().isoformat(),
                        "tabel": tabel}, default=str, ensure_ascii=False).encode("utf-8")


def _backup_json_sebelum_import_postgres(tenant_id: int) -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tujuan = os.path.join(BACKUP_DIR, f"mugen_hair_postgres_tenant{tenant_id}_sebelum_import_{stamp}.json")
    with open(tujuan, "wb") as fh:
        fh.write(export_database_postgres(tenant_id))
    return tujuan


def import_database_postgres(konten: bytes, tenant_id: int) -> str:
    """Return path backup JSON yang dibuat sebelum penimpaan. Mengganti
    SELURUH isi tabel bisnis MILIK TENANT INI SAJA dengan isi file yang
    diupload (DELETE lalu INSERT ulang per tabel, tenant-scoped, urutan
    FK-safe / kebalikannya untuk hapus), dalam SATU transaksi -- kalau ada
    baris yang gagal (termasuk id yang sudah dipakai baris tenant LAIN,
    lihat catatan di bawah), seluruhnya di-rollback (lihat
    db_compat.get_conn()), tidak pernah database setengah-terisi ATAUPUN
    data tenant lain ikut tersentuh.

    FONDASI Multi-Tenant Phase 1.1: `tenant_id` (dari akun yang sedang
    login, BUKAN dari isi file) dua lapis penjagaannya -- (1) file yang
    `tenant_id`-nya TIDAK SAMA dengan akun yang meng-import ditolak total
    (mencegah admin tenant A tidak sengaja/sengaja me-restore backup
    tenant B ke akunnya sendiri), (2) SETIAP baris yang disisipkan
    dipaksa memakai `tenant_id` akun yang login (bukan nilai apa pun yang
    ada di file), jadi walau isi file diedit manual, baris tidak akan
    pernah tersimpan mengatasnamakan tenant lain. `id` asli tetap
    dipertahankan (bukan auto-increment ulang) supaya relasi antar tabel
    di file tetap konsisten -- karena id bersifat GLOBAL lintas tenant
    (satu urutan SERIAL dipakai bersama), backup HANYA bisa di-restore
    kalau id-id itu tidak sedang dipakai baris tenant LAIN saat ini;
    kalau bentrok, PostgreSQL menolak lewat UNIQUE violation dan seluruh
    operasi dibatalkan (bukan korupsi silang-tenant) -- kasus wajar:
    me-restore backup tenant ini sendiri yang diambil sebelumnya."""
    try:
        data = json.loads(konten)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("File yang diupload bukan file backup JSON PostgreSQL yang valid.")
    if data.get("format") != POSTGRES_BACKUP_FORMAT:
        raise ValueError("Format file backup tidak dikenali untuk PostgreSQL.")
    if data.get("tenant_id") != tenant_id:
        raise ValueError(
            "File backup ini bukan milik toko Anda -- tidak bisa di-restore ke akun ini "
            "(setiap backup hanya bisa dikembalikan ke toko yang sama)."
        )

    backup_path = _backup_json_sebelum_import_postgres(tenant_id)

    try:
        with db_compat.get_conn() as conn:
            # Urutan hapus (anak dulu, FK-safe) untuk seluruh tabel milik
            # tenant ini -- lihat _hapus_scoped() di bawah untuk detail
            # per tabel (langsung vs transitif lewat JOIN).
            _hapus_scoped(conn, tenant_id)
            conn.execute("DELETE FROM settings WHERE key LIKE ?", (f"{tenant_id}:%",))

            for t in _URUTAN_SISIP:
                baris = data.get("tabel", {}).get(t) or []
                if not baris:
                    continue
                langsung = t in POSTGRES_BACKUP_TABEL_LANGSUNG
                for r in baris:
                    r = dict(r)
                    if langsung:
                        r["tenant_id"] = tenant_id  # JANGAN PERNAH percaya nilai dari file.
                    kolom = list(r.keys())
                    placeholder = ", ".join("?" for _ in kolom)
                    daftar_kolom = ", ".join(kolom)
                    conn.execute(
                        f"INSERT INTO {t} ({daftar_kolom}) VALUES ({placeholder})",
                        tuple(r[k] for k in kolom),
                    )
                if "id" in (baris[0].keys() if baris else []):
                    conn.execute(
                        f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM {t}), 1), true)"
                    )

            baris_settings = data.get("tabel", {}).get("settings") or []
            for r in baris_settings:
                r = dict(r)
                if not str(r.get("key", "")).startswith(f"{tenant_id}:"):
                    continue  # jangan pernah sisipkan key milik tenant lain walau ada di file
                conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (r["key"], r["value"]))
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(
            "Import gagal (transaksi dibatalkan, tidak ada data yang berubah) -- kemungkinan "
            f"besar backup ini bukan diambil dari toko yang sama persis: {e}"
        )
    return backup_path


def _hapus_scoped(conn, tenant_id: int):
    """Hapus baris tabel TRANSITIF milik tenant ini (anak dulu, FK-safe),
    lalu baris tabel LANGSUNG -- dipisah dari import_database_postgres()
    murni supaya sintaks DELETE...USING per tabel (beda-beda join-nya)
    tetap mudah dibaca, bukan di-generate string manipulation."""
    conn.execute("""
        DELETE FROM booking_items WHERE booking_id IN (
            SELECT id FROM bookings WHERE tenant_id = ?)
    """, (tenant_id,))
    conn.execute("DELETE FROM closed_slot WHERE tenant_id = ?", (tenant_id,))
    conn.execute("DELETE FROM bookings WHERE tenant_id = ?", (tenant_id,))
    conn.execute("DELETE FROM toko_libur WHERE tenant_id = ?", (tenant_id,))
    conn.execute("""
        DELETE FROM produk_mutasi WHERE produk_id IN (
            SELECT id FROM produk WHERE tenant_id = ?)
    """, (tenant_id,))
    conn.execute("DELETE FROM produk WHERE tenant_id = ?", (tenant_id,))
    conn.execute("""
        DELETE FROM transaksi_detail WHERE transaksi_id IN (
            SELECT tr.id FROM transaksi tr JOIN barbers b ON b.id = tr.barber_id WHERE b.tenant_id = ?)
    """, (tenant_id,))
    conn.execute("""
        DELETE FROM transaksi WHERE barber_id IN (
            SELECT id FROM barbers WHERE tenant_id = ?)
    """, (tenant_id,))
    conn.execute("""
        DELETE FROM absensi_libur WHERE barber_id IN (
            SELECT id FROM barbers WHERE tenant_id = ?)
    """, (tenant_id,))
    conn.execute("DELETE FROM pengeluaran WHERE tenant_id = ?", (tenant_id,))
    conn.execute("DELETE FROM users WHERE tenant_id = ?", (tenant_id,))
    conn.execute("DELETE FROM barbers WHERE tenant_id = ?", (tenant_id,))
    conn.execute("DELETE FROM services WHERE tenant_id = ?", (tenant_id,))
