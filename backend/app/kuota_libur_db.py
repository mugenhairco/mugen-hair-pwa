"""
kuota_libur_db.py — Kuota Libur Bulanan (cascade Tandai Libur manual -> Cuti)
=============================================================================
PERMINTAAN OWNER: Barber Holiday/Libur (Input Data > Tandai Libur, MANUAL --
lihat database.py::tandai_libur(), routers/input_data.py) sekarang punya
jatah "Kuota Libur per Bulan" opsional (Owner-editable di Pengaturan Izin &
Cuti, izin_cuti_settings.kuota_libur_bulanan, 0 = tidak dibatasi/tidak
dipakai -- Tandai Libur berjalan seperti biasa tanpa cascade apa pun).

SELAMA kuota bulan itu (per barber, reset tiap bulan kalender) belum habis,
Tandai Libur berjalan seperti biasa (baris absensi_libur, sumber NULL,
TIDAK menyentuh Izin & Cuti sama sekali). Begitu kuota bulan itu SUDAH
HABIS, Tandai Libur BERIKUTNYA untuk barber yang sama di bulan yang sama
OTOMATIS dicatat sebagai CUTI (disetujui otomatis, mengurangi kuota
gabungan Izin & Cuti, izin_cuti_settings.kuota_gabungan_hari) -- BUKAN
Libur (lihat tandai_libur_dengan_kuota()). Kalau KEDUA kuota itu (Libur
DAN Izin & Cuti) SAMA-SAMA habis, tanggal TETAP dicatat sebagai Libur
(supaya rekap tetap lengkap, tidak hilang begitu saja) TAPI ditandai
sumber='kelebihan_kuota' -- dipakai Rekap Bulanan (routers/rekap.py) dan
ringkasan kuota (routers/izin_cuti.py) untuk menstabilo baris itu merah.

Modul ini MENGGANTIKAN auto_libur_db.py (fitur "Auto-Libur Tidak Absen" --
barber yang lupa Check In otomatis dicatat Libur/Cuti -- SUDAH DIHAPUS
TOTAL atas permintaan Owner, lihat riwayat git). Kuota Libur di sini HANYA
dipicu MANUAL oleh Admin/Owner lewat Input Data > Tandai Libur -- TIDAK
ADA loop/sweep/proses otomatis apa pun di modul ini.
"""

from datetime import datetime

import attendance_db
import database as db
import izin_cuti_db
from database import get_conn

SUMBER_KELEBIHAN_KUOTA = "kelebihan_kuota"
DIAJUKAN_OLEH_KUOTA_LIBUR = "Sistem (Kuota Libur Habis)"


def migrasi_absensi_libur_sumber():
    """JALUR SQLITE SAJA (dipanggil dari main.py::on_startup() bersama
    migrasi_*() lain) -- PRAGMA table_info() di bawah ini SQL SQLite murni.
    Menambah kolom `sumber` ke `absensi_libur` (idempotent). Jalur
    PostgreSQL: kolom yang sama sudah langsung dibuat lewat
    `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` di postgres_schema.py."""
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(absensi_libur)").fetchall()]
        if "sumber" not in kolom:
            conn.execute("ALTER TABLE absensi_libur ADD COLUMN sumber TEXT")


def _libur_terpakai_bulan_ini(barber_id: int, tahun: int, bulan: int) -> int:
    """Jumlah SEMUA baris absensi_libur bulan itu (Libur manual biasa
    MAUPUN yang ditandai 'kelebihan_kuota') -- SATU jatah "Libur/bulan"
    untuk semuanya, bukan hitungan terpisah per sumber."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS jumlah FROM absensi_libur WHERE barber_id = ? AND tanggal LIKE ?",
            (barber_id, f"{tahun:04d}-{bulan:02d}-%"),
        ).fetchone()
    return row["jumlah"]


def get_sisa_kuota_libur_bulan_ini(barber_id: int, tenant_id: int) -> dict:
    """Kartu "Sisa Kuota Libur" (Absensi barber & Owner) -- BEDA dari kuota
    gabungan Izin&Cuti (izin_cuti_db.get_sisa_kuota(), yang anchor ke
    periode Owner-editable) -- Kuota Libur SELALU reset per BULAN KALENDER
    (WIB, attendance_db.tanggal_hari_ini()), TIDAK ikut periode Izin&Cuti
    sama sekali. Return
    {"aktif": bool, "kuota": int|None, "terpakai": int|None,
    "sisa": int|None} -- `aktif`=False (field lain None) kalau Owner belum
    mengisi kuota_libur_bulanan (0/default, fitur ini tidak dipakai)."""
    settings = izin_cuti_db.get_cuti_settings(tenant_id)
    kuota = settings.get("kuota_libur_bulanan", 0)
    if kuota <= 0:
        return {"aktif": False, "kuota": None, "terpakai": None, "sisa": None}
    hari_ini = attendance_db.tanggal_hari_ini()
    tahun, bulan = int(hari_ini[:4]), int(hari_ini[5:7])
    terpakai = _libur_terpakai_bulan_ini(barber_id, tahun, bulan)
    return {"aktif": True, "kuota": kuota, "terpakai": terpakai, "sisa": max(0, kuota - terpakai)}


def ada_kelebihan_kuota_bulan_ini(barber_id: int, tahun: int, bulan: int) -> bool:
    """Dipakai Rekap Bulanan (routers/rekap.py) dan ringkasan kuota
    (routers/izin_cuti.py) untuk stabilo merah -- True kalau ADA minimal
    satu tanggal bulan ini yang ditandai Libur PADAHAL Kuota Libur bulanan
    DAN kuota gabungan Izin&Cuti SAMA-SAMA sudah habis (lihat
    tandai_libur_dengan_kuota())."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS jumlah FROM absensi_libur WHERE barber_id = ? AND tanggal LIKE ? AND sumber = ?",
            (barber_id, f"{tahun:04d}-{bulan:02d}-%", SUMBER_KELEBIHAN_KUOTA),
        ).fetchone()
    return row["jumlah"] > 0


def ada_kelebihan_kuota_bulan_ini_sekarang(barber_id: int) -> bool:
    """Wrapper ada_kelebihan_kuota_bulan_ini() utk BULAN KALENDER BERJALAN
    -- dipakai routers/izin_cuti.py::ambil_sisa_kuota_semua_barber() (tabel
    ringkasan kuota Absensi > Owner)."""
    hari_ini = attendance_db.tanggal_hari_ini()
    return ada_kelebihan_kuota_bulan_ini(barber_id, int(hari_ini[:4]), int(hari_ini[5:7]))


# ---------------------------------------------------------------------------
# PERMINTAAN OWNER: tanda visual BEDA di kolom Keterangan Rekap Transaksi
# untuk DUA kasus Tandai Libur yang sebenarnya TIDAK murni dari kuota Libur
# sendiri -- supaya Owner bisa lihat langsung tanggal mana yang sebenarnya
# "nebeng" kuota lain, tanpa harus buka Absensi/Izin & Cuti satu-satu.
# ---------------------------------------------------------------------------

def _tanggal_filter(q: str, params: list, kolom_tanggal: str, tahun: int, bulan: int,
                     tanggal: str, tanggal_mulai: str, tanggal_selesai: str) -> str:
    if tahun is not None:
        q += f" AND {kolom_tanggal} LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += f" AND {kolom_tanggal} LIKE ?"; params.append(f"%-{bulan:02d}-%")
    if tanggal is not None:
        q += f" AND {kolom_tanggal} = ?"; params.append(tanggal)
    if tanggal_mulai is not None:
        q += f" AND {kolom_tanggal} >= ?"; params.append(tanggal_mulai)
    if tanggal_selesai is not None:
        q += f" AND {kolom_tanggal} <= ?"; params.append(tanggal_selesai)
    return q


def _tanggal_cuti_otomatis_kuota_habis(barber_id: int = None, tahun: int = None, bulan: int = None,
                                        tanggal: str = None, tanggal_mulai: str = None,
                                        tanggal_selesai: str = None, tenant_id: int = None) -> set:
    """Set (barber_id, tanggal) yang Cuti-nya BUKAN pengajuan asli barber/Owner
    -- OTOMATIS dicatat sistem karena kuota Libur bulanan sudah habis
    sementara kuota gabungan Izin&Cuti masih ada sisa (cabang `sisa is None
    or sisa > 0` di tandai_libur_dengan_kuota()). Baris ini TIDAK ADA di
    absensi_libur sama sekali (tersimpan di izin_cuti)."""
    q = "SELECT ic.barber_id AS barber_id, ic.tanggal_mulai AS tanggal FROM izin_cuti ic"
    if tenant_id is not None:
        q += " JOIN barbers b ON b.id = ic.barber_id"
    q += " WHERE ic.diajukan_oleh = ? AND ic.status = 'disetujui'"
    params = [DIAJUKAN_OLEH_KUOTA_LIBUR]
    if tenant_id is not None:
        q += " AND b.tenant_id = ?"; params.append(tenant_id)
    if barber_id is not None:
        q += " AND ic.barber_id = ?"; params.append(barber_id)
    q = _tanggal_filter(q, params, "ic.tanggal_mulai", tahun, bulan, tanggal, tanggal_mulai, tanggal_selesai)
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return {(r["barber_id"], r["tanggal"]) for r in rows}


def _tanggal_libur_kelebihan_kuota(barber_id: int = None, tahun: int = None, bulan: int = None,
                                    tanggal: str = None, tanggal_mulai: str = None,
                                    tanggal_selesai: str = None, tenant_id: int = None) -> set:
    """Set (barber_id, tanggal) yang dicatat Libur TAPI kuota Libur DAN kuota
    gabungan Izin&Cuti SAMA-SAMA sudah habis (sumber='kelebihan_kuota')."""
    q = "SELECT al.barber_id AS barber_id, al.tanggal AS tanggal FROM absensi_libur al"
    if tenant_id is not None:
        q += " JOIN barbers b ON b.id = al.barber_id"
    q += " WHERE al.sumber = ?"
    params = [SUMBER_KELEBIHAN_KUOTA]
    if tenant_id is not None:
        q += " AND b.tenant_id = ?"; params.append(tenant_id)
    if barber_id is not None:
        q += " AND al.barber_id = ?"; params.append(barber_id)
    q = _tanggal_filter(q, params, "al.tanggal", tahun, bulan, tanggal, tanggal_mulai, tanggal_selesai)
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return {(r["barber_id"], r["tanggal"]) for r in rows}


def tandai_rekap_transaksi_kuota(data: list, tahun: int = None, bulan: int = None, barber_id: int = None,
                                  tanggal: str = None, tanggal_mulai: str = None, tanggal_selesai: str = None,
                                  tenant_id: int = None) -> list:
    """PERMINTAAN OWNER: dipanggil routers/rekap.py SETELAH
    db.get_rekap_transaksi_list() (pola sama seperti reimburse_db/kasbon_db/
    data_non_barber_db.gabung_ke_rekap_transaksi()) -- menandai dua kasus
    Tandai Libur yang sebenarnya "nebeng" kuota lain, BUKAN kuota Libur asli:

    1. "Libur ⚠️" -- tanggal yang OTOMATIS tercatat Cuti oleh sistem karena
       kuota Libur bulan itu sudah habis. Baris ini belum pernah ada sama
       sekali di Rekap Transaksi sebelumnya (tersimpan di izin_cuti, bukan
       absensi_libur) -- ditambahkan sebagai baris baru tipe "libur" (pil
       Ket. yang sama), tapi diberi flag `dari_kuota_cuti_izin=True` supaya
       frontend TIDAK menampilkan tombol Hapus Keterangan Libur (tidak ada
       apa pun untuk dihapus di absensi_libur -- pembatalannya harus lewat
       Izin & Cuti, bukan endpoint Libur).
    2. "Libur 🔴" -- tanggal yang kuota Libur DAN kuota gabungan Izin&Cuti
       SAMA-SAMA sudah habis (sumber='kelebihan_kuota'). Baris ini SUDAH
       ada di `data` (dari get_libur_list()), tinggal keterangan-nya
       ditandai -- tombol Hapus Keterangan Libur TETAP ada seperti biasa
       (baris ini memang baris Libur asli di absensi_libur)."""
    cuti_otomatis = _tanggal_cuti_otomatis_kuota_habis(barber_id, tahun, bulan, tanggal, tanggal_mulai,
                                                        tanggal_selesai, tenant_id)
    kelebihan_kuota = _tanggal_libur_kelebihan_kuota(barber_id, tahun, bulan, tanggal, tanggal_mulai,
                                                      tanggal_selesai, tenant_id)
    if not cuti_otomatis and not kelebihan_kuota:
        return data

    for r in data:
        if r.get("tipe") == "libur" and (r["barber_id"], r["tanggal"]) in kelebihan_kuota:
            r["keterangan"] = "; ".join(
                "Libur 🔴" if bagian == "Libur" else bagian for bagian in r["keterangan"].split("; ")
            )

    for (bid, tgl) in cuti_otomatis:
        cocok = [r for r in data if r["barber_id"] == bid and r["tanggal"] == tgl]
        if cocok:
            for r in cocok:
                lama = (r.get("keterangan") or "").strip()
                r["keterangan"] = "; ".join(x for x in [lama, "Libur ⚠️"] if x and x != "-")
                r["dari_kuota_cuti_izin"] = True
            continue
        barber = db.get_barber(bid)
        if barber is None:
            continue
        data.append({
            "tipe": "libur",
            "tanggal": tgl,
            "barber_id": bid,
            "nama_barber": barber["nama"],
            "daftar_service": "",
            "jumlah_service": 0,
            "tips": 0,
            "uang_harian": 0,
            "pendapatan": 0,
            "keterangan": "Libur ⚠️",
            "dari_kuota_cuti_izin": True,
        })

    data.sort(key=lambda r: r["nama_barber"])
    data.sort(key=lambda r: r["tanggal"], reverse=True)
    return data


def tandai_libur_dengan_kuota(barber_id: int, tenant_id: int, tanggal: str) -> str:
    """Dipanggil routers/input_data.py SEBAGAI PENGGANTI database.tandai_libur()
    langsung -- menerapkan cascade Kuota Libur (lihat modul docstring) SAAT
    Admin/Owner menandai Libur manual untuk satu tanggal. Return
    'libur' | 'cuti' | 'kelebihan_kuota' supaya caller (router) bisa
    memberi tahu Admin/Owner persis apa yang terjadi.

    PERMINTAAN OWNER: Tandai Libur DITOLAK (ValueError) kalau tanggal ini
    sudah tercakup pengajuan Izin/Cuti yang DISETUJUI milik barber yang
    sama -- validasi arah SEBALIKNYA dari yang sudah ada di
    izin_cuti_db.buat_pengajuan() (yang menolak pengajuan baru di atas
    tanggal yang sudah Libur). Tanpa ini, satu tanggal bisa tercatat
    GANDA (Libur DAN Cuti/Izin sekaligus) -- bikin Rekap & Bonus Customer
    (hari_libur) salah hitung."""
    pengajuan_aktif = izin_cuti_db.get_pengajuan_aktif_pada_tanggal(barber_id, tanggal)
    if pengajuan_aktif is not None:
        jenis_label = "Izin" if pengajuan_aktif["jenis"] == "izin" else "Cuti"
        raise ValueError(
            f"Tidak bisa ditandai Libur -- barber ini tercatat sedang {jenis_label} pada tanggal ini "
            f"({pengajuan_aktif['tanggal_mulai']} s/d {pengajuan_aktif['tanggal_selesai']})."
        )

    settings = izin_cuti_db.get_cuti_settings(tenant_id)
    kuota = settings.get("kuota_libur_bulanan", 0)
    if kuota <= 0:
        db.tandai_libur(barber_id, tanggal)
        return "libur"

    tahun, bulan = int(tanggal[:4]), int(tanggal[5:7])
    terpakai = _libur_terpakai_bulan_ini(barber_id, tahun, bulan)
    if terpakai < kuota:
        db.tandai_libur(barber_id, tanggal)
        return "libur"

    sisa = izin_cuti_db.get_sisa_kuota_gabungan_pada_tanggal(barber_id, tenant_id, tanggal)
    if sisa is None or sisa > 0:
        now = datetime.now().isoformat(timespec="seconds")
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO izin_cuti (barber_id, jenis, tanggal_mulai, tanggal_selesai, alasan,
                                           status, diajukan_oleh, disetujui_oleh, tanggal_approval,
                                           created_at, updated_at)
                   VALUES (?, 'cuti', ?, ?, ?, 'disetujui', ?, ?, ?, ?, ?)""",
                (barber_id, tanggal, tanggal,
                 "Kuota Libur bulan ini sudah habis (dicatat otomatis sebagai Cuti).",
                 DIAJUKAN_OLEH_KUOTA_LIBUR, DIAJUKAN_OLEH_KUOTA_LIBUR, tanggal[:10], now, now),
            )
        return "cuti"

    db.tandai_libur(barber_id, tanggal, sumber=SUMBER_KELEBIHAN_KUOTA)
    return "kelebihan_kuota"
