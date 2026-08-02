"""
data_non_barber_db.py — Input Data Non-Barber (Kasir/OB/Kru/role lainnya)
=============================================================================
Permintaan: "Perbaiki sistem agar mendukung Barber dan Non-Barber tanpa
mengubah sistem Barber yang sudah berjalan." Modul ini SENGAJA berdiri
sendiri (tabel baru murni, TIDAK menyentuh/menggantikan slip_gaji_db.py
ataupun tabel `transaksi` milik Barber) -- ini "Input Data" untuk karyawan
Non-Barber, setara konsepnya dengan tabel `transaksi` untuk Barber: satu
baris = satu periode kerja (gaji dihitung dari Hari Masuk x Gaji per Hari,
BUKAN dari komisi/jasa potong rambut seperti Barber).

Slip Gaji (slip_gaji_db.py) TETAP ada dan TIDAK diubah sama sekali --
modul itu tetap jalur formal generate+bayar+kunci payroll bulanan/periode,
terpisah dari pencatatan harian/periodik di sini. Kedua modul ini boleh
sama-sama dipakai Owner, tidak saling bergantung.

barber_id di sini SELALU merujuk ke baris tabel `barbers` yang jabatan-nya
BUKAN 'barber' (lihat _pastikan_non_barber() di bawah) -- nama kolom tetap
'barber_id' mengikuti konvensi tabel `barbers` yang sudah ada (menyimpan
SEMUA karyawan, bukan cuma barber, lihat database.get_karyawan())."""

from datetime import datetime

from database import get_conn, get_barber


def init_data_non_barber_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS data_non_barber (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                barber_id        INTEGER NOT NULL,
                tanggal_mulai    TEXT NOT NULL,
                tanggal_selesai  TEXT NOT NULL,
                gaji_per_hari    INTEGER NOT NULL DEFAULT 0,
                hari_masuk       INTEGER NOT NULL DEFAULT 0,
                hari_libur       INTEGER NOT NULL DEFAULT 0,
                bonus            INTEGER NOT NULL DEFAULT 0,
                potongan         INTEGER NOT NULL DEFAULT 0,
                catatan          TEXT,
                total_gaji       INTEGER NOT NULL DEFAULT 0,
                dibuat_oleh      TEXT,
                created_at       TEXT NOT NULL,
                updated_at       TEXT,
                FOREIGN KEY (barber_id) REFERENCES barbers(id)
            )
        """)


def _lengkapi(row: dict) -> dict:
    barber = get_barber(row["barber_id"])
    row["nama_barber"] = barber["nama"] if barber else "(karyawan terhapus)"
    row["jabatan"] = barber["jabatan"] if barber else None
    # FONDASI Multi-Tenant Phase 1.1: data_non_barber TIDAK punya kolom
    # tenant_id sendiri (di-scope TRANSITIF lewat barbers.tenant_id,
    # barber_id NOT NULL) -- diselipkan di sini untuk fetch-then-authorize.
    row["tenant_id"] = barber["tenant_id"] if barber else None
    return row


def _pastikan_non_barber(barber_id: int, tenant_id: int = None) -> dict:
    barber = get_barber(barber_id)
    if barber is None or (tenant_id is not None and barber["tenant_id"] != tenant_id):
        raise ValueError("Karyawan tidak ditemukan.")
    if (barber.get("jabatan") or "barber") == "barber":
        raise ValueError(
            "Karyawan ini berjabatan Barber -- gunakan Input Data Barber (sistem yang sudah ada), "
            "bukan Input Data Non-Barber."
        )
    return barber


def get_data_non_barber(entry_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM data_non_barber WHERE id = ?", (entry_id,)).fetchone()
        return _lengkapi(dict(row)) if row else None


def get_data_non_barber_list(barber_id: int = None, tahun: int = None, bulan: int = None,
                              tanggal_mulai: str = None, tanggal_selesai: str = None,
                              tenant_id: int = None) -> list:
    """tahun/bulan (dipakai tampilan layar) DIDERIVE dari tanggal_mulai --
    pola sama seperti slip_gaji_db.py untuk periode rentang tanggal bebas
    Kasir/OB/Kru. tanggal_mulai/tanggal_selesai (dipakai periode PDF rentang
    tanggal bebas) BEDA -- filter entri yang tanggal_mulai-nya jatuh di
    dalam rentang itu (inklusif).

    FONDASI Multi-Tenant Phase 1.1: `tenant_id` opsional, JOIN tambahan ke
    barbers HANYA ditambahkan kalau diisi (endpoint ber-login WAJIB mengisi
    ini)."""
    q = "SELECT d.* FROM data_non_barber d"
    if tenant_id is not None:
        q += " JOIN barbers b ON b.id = d.barber_id"
    q += " WHERE 1=1"
    params = []
    if tenant_id is not None:
        q += " AND b.tenant_id = ?"; params.append(tenant_id)
    if barber_id is not None:
        q += " AND d.barber_id = ?"; params.append(barber_id)
    if tahun is not None:
        q += " AND d.tanggal_mulai LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND d.tanggal_mulai LIKE ?"; params.append(f"%-{bulan:02d}-%")
    if tanggal_mulai is not None:
        q += " AND d.tanggal_mulai >= ?"; params.append(tanggal_mulai)
    if tanggal_selesai is not None:
        q += " AND d.tanggal_mulai <= ?"; params.append(tanggal_selesai)
    q += " ORDER BY d.tanggal_mulai DESC, d.id DESC"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    return [_lengkapi(r) for r in rows]


def _hitung_total(gaji_per_hari: int, hari_masuk: int, bonus: int, potongan: int) -> int:
    return gaji_per_hari * hari_masuk + bonus - potongan


def tambah_data_non_barber(barber_id: int, tanggal_mulai: str, tanggal_selesai: str, gaji_per_hari: int,
                            hari_masuk: int, hari_libur: int = 0, bonus: int = 0, potongan: int = 0,
                            catatan: str = "", dibuat_oleh: str = "", tenant_id: int = None) -> dict:
    _pastikan_non_barber(barber_id, tenant_id)
    datetime.strptime(tanggal_mulai, "%Y-%m-%d")  # raise ValueError kalau format salah
    datetime.strptime(tanggal_selesai, "%Y-%m-%d")
    if tanggal_selesai < tanggal_mulai:
        raise ValueError("Tanggal Selesai tidak boleh sebelum Tanggal Mulai.")
    gaji_per_hari = int(gaji_per_hari or 0)
    hari_masuk = int(hari_masuk or 0)
    hari_libur = int(hari_libur or 0)
    bonus = int(bonus or 0)
    potongan = int(potongan or 0)
    if gaji_per_hari < 0:
        raise ValueError("Gaji per Hari tidak boleh negatif.")
    if hari_masuk < 0:
        raise ValueError("Jumlah Hari Masuk tidak boleh negatif.")
    if hari_libur < 0:
        raise ValueError("Jumlah Hari Libur tidak boleh negatif.")
    if bonus < 0:
        raise ValueError("Bonus tidak boleh negatif.")
    if potongan < 0:
        raise ValueError("Potongan tidak boleh negatif.")
    total_gaji = _hitung_total(gaji_per_hari, hari_masuk, bonus, potongan)
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO data_non_barber
                   (barber_id, tanggal_mulai, tanggal_selesai, gaji_per_hari, hari_masuk, hari_libur,
                    bonus, potongan, catatan, total_gaji, dibuat_oleh, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (barber_id, tanggal_mulai, tanggal_selesai, gaji_per_hari, hari_masuk, hari_libur,
             bonus, potongan, (catatan or "").strip(), total_gaji, dibuat_oleh, now),
        )
        entry_id = cur.lastrowid
    return get_data_non_barber(entry_id)


def edit_data_non_barber(entry_id: int, barber_id: int = None, tanggal_mulai: str = None,
                          tanggal_selesai: str = None, gaji_per_hari: int = None, hari_masuk: int = None,
                          hari_libur: int = None, bonus: int = None, potongan: int = None,
                          catatan: str = None, tenant_id: int = None) -> dict:
    existing = get_data_non_barber(entry_id)
    if existing is None:
        raise ValueError("Data Non-Barber tidak ditemukan.")

    barber_id_baru = barber_id if barber_id is not None else existing["barber_id"]
    _pastikan_non_barber(barber_id_baru, tenant_id)

    tanggal_mulai_baru = tanggal_mulai if tanggal_mulai is not None else existing["tanggal_mulai"]
    tanggal_selesai_baru = tanggal_selesai if tanggal_selesai is not None else existing["tanggal_selesai"]
    if tanggal_mulai is not None:
        datetime.strptime(tanggal_mulai_baru, "%Y-%m-%d")
    if tanggal_selesai is not None:
        datetime.strptime(tanggal_selesai_baru, "%Y-%m-%d")
    if tanggal_selesai_baru < tanggal_mulai_baru:
        raise ValueError("Tanggal Selesai tidak boleh sebelum Tanggal Mulai.")

    gaji_per_hari_baru = int(gaji_per_hari) if gaji_per_hari is not None else existing["gaji_per_hari"]
    hari_masuk_baru = int(hari_masuk) if hari_masuk is not None else existing["hari_masuk"]
    hari_libur_baru = int(hari_libur) if hari_libur is not None else existing["hari_libur"]
    bonus_baru = int(bonus) if bonus is not None else existing["bonus"]
    potongan_baru = int(potongan) if potongan is not None else existing["potongan"]
    if gaji_per_hari_baru < 0:
        raise ValueError("Gaji per Hari tidak boleh negatif.")
    if hari_masuk_baru < 0:
        raise ValueError("Jumlah Hari Masuk tidak boleh negatif.")
    if hari_libur_baru < 0:
        raise ValueError("Jumlah Hari Libur tidak boleh negatif.")
    if bonus_baru < 0:
        raise ValueError("Bonus tidak boleh negatif.")
    if potongan_baru < 0:
        raise ValueError("Potongan tidak boleh negatif.")
    catatan_baru = catatan.strip() if catatan is not None else existing["catatan"]
    total_gaji = _hitung_total(gaji_per_hari_baru, hari_masuk_baru, bonus_baru, potongan_baru)

    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """UPDATE data_non_barber SET barber_id = ?, tanggal_mulai = ?, tanggal_selesai = ?,
                   gaji_per_hari = ?, hari_masuk = ?, hari_libur = ?, bonus = ?, potongan = ?,
                   catatan = ?, total_gaji = ?, updated_at = ?
               WHERE id = ?""",
            (barber_id_baru, tanggal_mulai_baru, tanggal_selesai_baru, gaji_per_hari_baru, hari_masuk_baru,
             hari_libur_baru, bonus_baru, potongan_baru, catatan_baru, total_gaji, now, entry_id),
        )
    return get_data_non_barber(entry_id)


def hapus_data_non_barber(entry_id: int):
    existing = get_data_non_barber(entry_id)
    if existing is None:
        raise ValueError("Data Non-Barber tidak ditemukan.")
    with get_conn() as conn:
        conn.execute("DELETE FROM data_non_barber WHERE id = ?", (entry_id,))


# ---------------------------------------------------------------------------
# Integrasi Rekap Transaksi -- lihat catatan di docstring modul ini kenapa
# Non-Barber TIDAK dicampur ke tabel `transaksi` Barber. Baris di sini
# APAPUN gabungan sama pendapatan/kasbon/reimburse-nya SUDAH final (bukan
# nilai baru dihitung ulang di sini) -- pola sama seperti reimburse_db.py/
# kasbon_db.py gabung_ke_rekap_transaksi(), dipanggil dari layer pemanggil
# (routers/rekap.py & laporan_pdf.py), BUKAN dari database.py sendiri
# (circular import: modul ini mengimpor database.py).
# ---------------------------------------------------------------------------

def gabung_ke_rekap_transaksi(baris: list, tahun: int = None, bulan: int = None, barber_id: int = None,
                               tanggal_mulai: str = None, tanggal_selesai: str = None,
                               tenant_id: int = None) -> list:
    """Menggabungkan `baris` (hasil database.get_rekap_transaksi_list(),
    biasanya sudah digabung dengan baris Reimburse/Kasbon) dengan baris Gaji
    Non-Barber (Input Data Non-Barber) pada periode yang sama. `tanggal`
    baris = tanggal_mulai periode gaji ini (dipakai urutan/tampilan kolom
    Tanggal, SAMA polanya seperti Reimburse pakai tanggal_approval) --
    tanggal_selesai + catatan ditaruh di kolom Keterangan supaya rentang
    periodenya tetap jelas walau kolom Tanggal cuma satu tanggal.

    'pendapatan' = total_gaji APA ADANYA (sudah termasuk Bonus - Potongan,
    lihat tambah_data_non_barber()) -- TIDAK dihitung ulang di sini, sama
    prinsipnya seperti seluruh modul lain di file ini."""
    entri = get_data_non_barber_list(barber_id=barber_id, tahun=tahun, bulan=bulan,
                                      tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai,
                                      tenant_id=tenant_id)
    for e in entri:
        bagian_ket = [f"Periode: {e['tanggal_mulai']} s/d {e['tanggal_selesai']}"]
        if e.get("catatan"):
            bagian_ket.append(f"Catatan: {e['catatan']}")
        baris.append({
            "tipe": "non_barber",
            "id": e["id"],
            "tanggal": e["tanggal_mulai"],
            "barber_id": e["barber_id"],
            "nama_barber": e["nama_barber"],
            "jabatan": e["jabatan"],
            "daftar_service": "",
            "jumlah_service": 0,
            "tips": 0,
            "uang_harian": 0,
            "pendapatan": e["total_gaji"],
            "keterangan": "; ".join(bagian_ket),
            "catatan": e.get("catatan") or "",  # field mentah -- dipakai rekap_ringkasan.py
        })
    baris.sort(key=lambda r: r["nama_barber"])
    baris.sort(key=lambda r: r["tanggal"], reverse=True)
    return baris
