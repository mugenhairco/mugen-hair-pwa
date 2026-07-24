"""sync_migrasi.py — Migrasi skema TAHAP 12 (Sinkronisasi Google Sheets)
=========================================================================
Terpisah dari database.py (sama seperti pengeluaran_migrasi.py /
pengaturan_migrasi.py di tahap-tahap sebelumnya) — database.py TIDAK
disentuh sama sekali.

Satu tabel baru, `sync_meta`: key-value generik (pola sama seperti tabel
`settings` yang sudah ada sejak Tahap 2) untuk menyimpan status
sinkronisasi (jumlah perubahan lokal, waktu sinkron terakhir, berhasil/
gagal, pesan error terakhir). TIDAK menyimpan data bisnis apa pun --
murni metadata tentang proses sinkron itu sendiri.
"""

from database import get_conn


def migrasi_sync():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
