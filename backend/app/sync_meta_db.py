"""sync_meta_db.py — TAHAP 12
Baca/tulis tabel `sync_meta` (dibuat oleh sync_migrasi.py). Terpisah dari
database.py, sama seperti auth_db.py/pengeluaran_db.py di tahap-tahap
sebelumnya. Isinya HANYA metadata proses sinkron (bukan data bisnis),
jadi tidak ada satu pun fungsi di sini yang menyentuh tabel transaksi/
pengeluaran/produk/dst."""

from database import get_conn


def get_meta(key: str, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM sync_meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row is not None else default


def get_meta_int(key: str, default: int = 0) -> int:
    val = get_meta(key)
    try:
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def set_meta(key: str, value) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sync_meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, "" if value is None else str(value)),
        )


def increment_write_counter() -> int:
    """Dipanggil setiap ada data yang baru disimpan lokal (lihat sync_helper.
    sync_async()). Nilai baru langsung dikembalikan supaya sync_helper bisa
    tahu 'sampai perubahan ke berapa' snapshot yang sedang dia kirim, tanpa
    query terpisah lagi."""
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM sync_meta WHERE key = 'write_counter'").fetchone()
        current = int(row["value"]) if row and row["value"] else 0
        baru = current + 1
        conn.execute(
            "INSERT INTO sync_meta (key, value) VALUES ('write_counter', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(baru),),
        )
        return baru
