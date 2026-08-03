"""
file_asset_db.py — Penyimpanan file biner (gambar/video) slot tunggal
=============================================================================
Modul ini KHUSUS aset "slot tunggal" (satu file aktif per key, diganti
tiap upload baru): Logo (pengaturan_identitas.py), Hero Image/Hero Video/
Foto About/Background Website (website_content.py), QRIS (booking_db.py).
Aset "banyak baris" (Gallery, Foto Barber, Bukti Reimburse) TIDAK lewat
modul ini -- lihat website_content.py/booking_db.py/reimburse_db.py.

Migrasi Cloudflare R2 (Storage File): kalau r2_storage.IS_ENABLED (env var
R2_* lengkap), isi file diupload ke R2 dan HANYA object key-nya yang
disimpan di kolom `r2_key` -- kolom `data` (BLOB, historis NOT NULL) diisi
bytes KOSONG sebagai placeholder murni supaya constraint lama tetap
terpenuhi tanpa perlu ALTER COLUMN (yang tidak sesederhana itu di SQLite).
Kalau R2 TIDAK dikonfigurasi (mis. development lokal), jalur BLOB-di-
database LAMA dipakai apa adanya, byte-identik dengan sebelum migrasi R2 --
supaya development lokal tanpa kredensial R2 tetap 100% berfungsi.

Baris LAMA (sebelum migrasi R2, `r2_key IS NULL` tapi `data` berisi bytes
sungguhan) TETAP bisa dibaca lewat ambil() -- fallback otomatis ke kolom
`data` kalau `r2_key` kosong, sampai dibackfill manual lewat
migrate_blobs_to_r2.py (lihat README).

KEY_TO_PREFIX menentukan folder/prefix di bucket R2 untuk tiap key (lihat
README bagian struktur bucket).

Tabel baru murni milik modul ini -- init_file_asset_db() dipanggil dari
main.py on_startup() jalur SQLite. Jalur PostgreSQL: tabel yang SAMA
dibuat di postgres_schema.py.
"""

from datetime import datetime

import r2_storage
from database import get_conn, _kunci_tenant

KEY_TO_PREFIX = {
    "logo": "logos",
    "favicon": "logos",
    "hero_image": "assets",
    "hero_video": "assets",
    "about_foto": "assets",
    "qris": "payments",
}


def init_file_asset_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS file_asset (
                key           TEXT PRIMARY KEY,
                filename      TEXT NOT NULL,
                content_type  TEXT NOT NULL,
                data          BLOB NOT NULL,
                updated_at    TEXT NOT NULL
            )
        """)


def simpan(key: str, filename_asli: str, konten: bytes, mapping: dict, label: str,
           maks_ukuran_bytes: int | None = None, tenant_id: int = None) -> str:
    """Simpan/ganti file untuk `key` ini -- mapping = dict ekstensi->Content-Type
    (sama seperti yang sudah dipakai tiap pemanggil untuk validasi), label
    dipakai di pesan error, `maks_ukuran_bytes` opsional (default None =
    tidak ada batas, kompatibel dengan pemanggil lama yang sudah melakukan
    validasi ukurannya sendiri, mis. Hero Video). Return nama file yang
    tersimpan (dipakai pemanggil sebagai `?v=` cache-bust). File lama di R2
    (kalau ada) otomatis dihapus SETELAH file baru berhasil tersimpan
    (supaya tidak ada jeda tanpa file valid kalau upload baru gagal di
    tengah jalan).

    FONDASI Multi-Tenant Phase 1: `file_asset` TIDAK mendapat kolom
    tenant_id baru (`key TEXT PRIMARY KEY` -- sama alasannya dengan
    `settings`, lihat database.py::_kunci_tenant()) -- isolasi dilakukan
    dengan memprefix `key` dengan tenant_id SEBELUM query, murni di lapisan
    Python. Nama file R2 sendiri SUDAH unik global (uuid4, lihat
    r2_storage.validasi_dan_beri_nama()) -- prefix di sini murni supaya
    BARIS POINTER-nya di database tidak saling menimpa antar tenant, bukan
    supaya file-nya sendiri tidak bertabrakan (itu sudah aman sejak awal)."""
    nama_file, content_type = r2_storage.validasi_dan_beri_nama(filename_asli, konten, mapping, label, maks_ukuran_bytes)
    now = datetime.now().isoformat(timespec="seconds")
    key_db = _kunci_tenant(tenant_id, key)
    r2_key_lama = ambil_r2_key(key, tenant_id=tenant_id)

    if r2_storage.IS_ENABLED:
        r2_key_baru = r2_storage.upload(KEY_TO_PREFIX.get(key, "assets"), nama_file, konten, content_type)
        data_kolom = b""
    else:
        r2_key_baru = None
        data_kolom = konten

    with get_conn() as conn:
        existing = conn.execute("SELECT key FROM file_asset WHERE key = ?", (key_db,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE file_asset SET filename = ?, content_type = ?, data = ?, r2_key = ?, updated_at = ? WHERE key = ?",
                (nama_file, content_type, data_kolom, r2_key_baru, now, key_db),
            )
        else:
            conn.execute(
                "INSERT INTO file_asset (key, filename, content_type, data, r2_key, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (key_db, nama_file, content_type, data_kolom, r2_key_baru, now),
            )

    if r2_key_lama and r2_key_lama != r2_key_baru:
        r2_storage.delete(r2_key_lama)
    return nama_file


def ambil(key: str, tenant_id: int = None):
    """Return (data: bytes, content_type: str) kalau ada, atau (None, None).
    R2 diprioritaskan kalau `r2_key` terisi; kalau tidak (baris lama/R2
    nonaktif), fallback ke kolom `data` (BLOB) seperti sebelum migrasi R2."""
    with get_conn() as conn:
        row = conn.execute("SELECT content_type, data, r2_key FROM file_asset WHERE key = ?",
                            (_kunci_tenant(tenant_id, key),)).fetchone()
    if row is None:
        return None, None
    if row["r2_key"]:
        data, content_type = r2_storage.get_bytes(row["r2_key"])
        if data is not None:
            return data, content_type or row["content_type"]
    if row["data"]:
        return bytes(row["data"]), row["content_type"]
    return None, None


def ambil_meta(key: str, tenant_id: int = None):
    """Cuma nama file (untuk cache-bust ?v=...), TANPA fetch kolom `data`
    (bisa besar untuk gambar/video) -- dipakai endpoint GET pengaturan
    konten (get_identitas()/get_content()/get_payment_settings()) yang
    dipanggil jauh lebih sering daripada endpoint download gambar itu
    sendiri. Return filename atau None kalau belum ada."""
    with get_conn() as conn:
        row = conn.execute("SELECT filename FROM file_asset WHERE key = ?",
                            (_kunci_tenant(tenant_id, key),)).fetchone()
    return row["filename"] if row else None


def ambil_r2_key(key: str, tenant_id: int = None):
    with get_conn() as conn:
        row = conn.execute("SELECT r2_key FROM file_asset WHERE key = ?",
                            (_kunci_tenant(tenant_id, key),)).fetchone()
    return row["r2_key"] if row else None


def hapus(key: str, tenant_id: int = None):
    r2_key = ambil_r2_key(key, tenant_id=tenant_id)
    with get_conn() as conn:
        conn.execute("DELETE FROM file_asset WHERE key = ?", (_kunci_tenant(tenant_id, key),))
    if r2_key:
        r2_storage.delete(r2_key)
