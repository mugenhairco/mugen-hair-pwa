"""
pengeluaran_migrasi.py — Migrasi skema TAHAP 9 (Pengeluaran CRUD)
==================================================================
File ini SENGAJA dipisah dari database.py (sesuai instruksi Tahap 9:
"jangan mengubah database.py kecuali benar-benar diperlukan").

Tabel `pengeluaran` sudah dibuat sejak Tahap 2 di database.py, tapi baru
punya kolom dasar (tanggal, keterangan, jumlah). Tahap 9 butuh field
tambahan: kategori, barber (opsional), dan status aktif. File ini
menambahkan kolom-kolom itu lewat ALTER TABLE, BUKAN membuat ulang tabel.

Aman dipanggil berulang kali (idempotent) — hanya menambah kolom kalau
belum ada, dan TIDAK PERNAH menghapus atau menimpa data lama yang sudah
ada di tabel `pengeluaran`.
"""

from database import get_conn


def migrasi_pengeluaran():
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(pengeluaran)").fetchall()]

        if "kategori" not in kolom:
            conn.execute("ALTER TABLE pengeluaran ADD COLUMN kategori TEXT")
        if "barber_id" not in kolom:
            # Opsional: pengeluaran toko pada umumnya tidak terkait barber
            # manapun, tapi beberapa kategori (mis. reimburse barber) perlu
            # dikaitkan ke satu barber tertentu.
            conn.execute("ALTER TABLE pengeluaran ADD COLUMN barber_id INTEGER REFERENCES barbers(id)")
        if "aktif" not in kolom:
            conn.execute("ALTER TABLE pengeluaran ADD COLUMN aktif INTEGER NOT NULL DEFAULT 1")

        # Sumber Dana (Tahap 12): setiap pengeluaran ditandai berasal dari
        # kas toko ('kas', otomatis mengurangi Uang Kas lewat kas_penyesuaian)
        # atau uang pribadi karyawan yang dipakai dulu ('karyawan', otomatis
        # membuat klaim Reimburse tersambung). kas_penyesuaian_id/reimburse_id
        # menyimpan baris terkait yang dibuat otomatis di modul lain.
        if "sumber_dana" not in kolom:
            conn.execute("ALTER TABLE pengeluaran ADD COLUMN sumber_dana TEXT NOT NULL DEFAULT 'kas'")
        if "kas_penyesuaian_id" not in kolom:
            conn.execute("ALTER TABLE pengeluaran ADD COLUMN kas_penyesuaian_id INTEGER REFERENCES kas_penyesuaian(id)")
        if "reimburse_id" not in kolom:
            conn.execute("ALTER TABLE pengeluaran ADD COLUMN reimburse_id INTEGER REFERENCES reimburse(id)")

        # Data lama (dicatat sebelum Tahap 9, sebelum kolom kategori ada)
        # diberi kategori default supaya tidak kosong/null di UI & filter.
        conn.execute("UPDATE pengeluaran SET kategori = 'Lainnya' WHERE kategori IS NULL")
        conn.execute("UPDATE pengeluaran SET sumber_dana = 'kas' WHERE sumber_dana IS NULL")
