"""
file_asset_db.py — Penyimpanan file biner (gambar/video) slot tunggal
=============================================================================
Ganti penyimpanan file lokal (backend/app/static/...) yang TERBUKTI hilang
tiap deploy/restart di Render Free tier (tidak mendukung Persistent Disk
sama sekali -- lihat README) -- konten file (bytes) disimpan LANGSUNG di
database yang sudah persisten (sama seperti solusi yang sudah dipakai utk
data transaksi/setting, migrasi ke PostgreSQL/Neon).

Modul ini KHUSUS aset "slot tunggal" (satu file aktif per key, diganti
tiap upload baru): Logo (pengaturan_identitas.py), Hero Image/Hero Video/
Foto About/Background Website (website_content.py), QRIS (booking_db.py).
Aset "banyak baris" (Gallery, Foto Barber, Bukti Reimburse) TIDAK lewat
modul ini -- kolom BLOB ditambahkan LANGSUNG ke tabel masing-masing
(website_gallery.data, barbers.foto_data, reimburse.bukti_data) di
modulnya sendiri, supaya kepemilikan data tetap co-located dengan baris
induknya (pola yang sudah dipakai `bukti_filename` dkk).

Tabel baru murni milik modul ini -- init_file_asset_db() dipanggil dari
main.py on_startup() jalur SQLite. Jalur PostgreSQL: tabel yang SAMA
dibuat di postgres_schema.py.
"""

from datetime import datetime

from database import get_conn


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


def simpan(key: str, filename_asli: str, konten: bytes, mapping: dict, label: str) -> str:
    """Simpan/ganti file untuk `key` ini -- mapping = dict ekstensi->Content-Type
    (sama seperti yang sudah dipakai tiap pemanggil untuk validasi), label
    dipakai di pesan error. Return nama file yang tersimpan (dipakai
    pemanggil sebagai `?v=` cache-bust)."""
    ext = filename_asli.rsplit(".", 1)[-1].lower() if "." in filename_asli else ""
    if ext not in mapping:
        raise ValueError(f"Format {label} tidak didukung.")
    if not konten:
        raise ValueError(f"File {label} kosong.")
    nama_file = f"{key}.{ext}"
    content_type = mapping[ext]
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        existing = conn.execute("SELECT key FROM file_asset WHERE key = ?", (key,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE file_asset SET filename = ?, content_type = ?, data = ?, updated_at = ? WHERE key = ?",
                (nama_file, content_type, konten, now, key),
            )
        else:
            conn.execute(
                "INSERT INTO file_asset (key, filename, content_type, data, updated_at) VALUES (?, ?, ?, ?, ?)",
                (key, nama_file, content_type, konten, now),
            )
    return nama_file


def ambil(key: str):
    """Return (data: bytes, content_type: str) kalau ada, atau (None, None)."""
    with get_conn() as conn:
        row = conn.execute("SELECT content_type, data FROM file_asset WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None, None
    return bytes(row["data"]), row["content_type"]


def ambil_meta(key: str):
    """Cuma nama file (untuk cache-bust ?v=...), TANPA fetch kolom `data`
    (bisa besar untuk gambar/video) -- dipakai endpoint GET pengaturan
    konten (get_identitas()/get_content()/get_payment_settings()) yang
    dipanggil jauh lebih sering daripada endpoint download gambar itu
    sendiri. Return filename atau None kalau belum ada."""
    with get_conn() as conn:
        row = conn.execute("SELECT filename FROM file_asset WHERE key = ?", (key,)).fetchone()
    return row["filename"] if row else None


def hapus(key: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM file_asset WHERE key = ?", (key,))
