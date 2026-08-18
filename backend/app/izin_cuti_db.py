"""
izin_cuti_db.py — Modul Karyawan: Izin & Cuti (Fase 5)
=============================================================================
Fase 5 (terakhir dari Modul Karyawan) dari permintaan besar "Modul Karyawan/
Keuangan/Pembayaran". Izin & Cuti = pengajuan izin/cuti barber (jenis
'izin'/'cuti', rentang tanggal_mulai..tanggal_selesai, alasan), disetujui/
ditolak Owner/Admin (status 'pending'/'disetujui'/'ditolak',
catatan_approval) -- pola akses SAMA PERSIS seperti reimburse_db.py
(self-service: barber boleh mengajukan/mengedit/menghapus MILIKNYA sendiri
selama masih 'pending', approve/reject eksklusif Owner/Admin).

SENGAJA TIDAK terhubung ke apa pun di luar dirinya sendiri -- TIDAK
mengubah `barbers.status_booking`/logika ketersediaan booking (yang sudah
punya konsep 'cuti' sendiri, lihat booking_db.py STATUS_BOOKING_VALID),
TIDAK terhubung ke Slip Gaji. Murni sistem pengajuan+riwayat+notifikasi
berdiri sendiri, sesuai cakupan spesifikasi asli ("Pengajuan izin/cuti,
alasan, tanggal mulai/selesai, status, riwayat, notifikasi admin/owner").

Tabel baru murni milik modul ini -- init_izin_cuti_db() dipanggil dari
main.py on_startup() jalur SQLite. Jalur PostgreSQL: tabel yang SAMA
dibuat di postgres_schema.py.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import push_service
from database import get_conn, get_barber

logger = logging.getLogger("mugen.izin_cuti")

WIB = ZoneInfo("Asia/Jakarta")

JENIS_VALID = {"izin", "cuti"}
STATUS_VALID = {"pending", "disetujui", "ditolak"}
_JENIS_LABEL = {"izin": "Izin", "cuti": "Cuti"}

# FITUR Kebijakan Cuti Dinamis (feedback Owner): SEMUA nilai di sini 0/off
# secara default -- tenant yang belum pernah membuka kartu "Pengaturan
# Izin & Cuti" (menu Pengaturan > Karyawan) TIDAK terpengaruh sama sekali,
# byte-for-byte sama seperti sebelum fitur ini ada. Skenario di bawah
# (kuota, H-min, maksimal bersamaan) HANYA berlaku utk jenis='cuti' --
# jenis='izin' TIDAK PERNAH divalidasi lewat mesin ini (izin = ad-hoc/
# sakit/keperluan mendadak, tidak masuk akal dibatasi lead-time/kuota
# terjadwal seperti cuti).
DEFAULT_CUTI_SETTINGS = {
    "kuota_periode_bulan": 0,   # 0 = kuota TIDAK digunakan
    "kuota_maksimal_hari": 0,
    "kuota_boleh_dipecah": True,
    "h_min_pengajuan": 0,       # 0 = tidak ada minimal H- sama sekali
    "maksimal_bersamaan": 0,    # 0 = tidak dibatasi
}


def _hari_ini_wib() -> str:
    return datetime.now(WIB).strftime("%Y-%m-%d")


def init_izin_cuti_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS izin_cuti (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                barber_id         INTEGER NOT NULL,
                jenis             TEXT NOT NULL,
                tanggal_mulai     TEXT NOT NULL,
                tanggal_selesai   TEXT NOT NULL,
                alasan            TEXT NOT NULL,
                status            TEXT NOT NULL DEFAULT 'pending',
                catatan_approval  TEXT,
                diajukan_oleh     TEXT,
                disetujui_oleh    TEXT,
                tanggal_approval  TEXT,
                created_at        TEXT NOT NULL,
                updated_at        TEXT,
                FOREIGN KEY (barber_id) REFERENCES barbers(id)
            )
        """)
        # FITUR Kebijakan Cuti Dinamis: SATU baris per tenant (konvensi
        # "id = tenant_id", pola sama attendance_settings/
        # uang_harian_dinamis_settings).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS izin_cuti_settings (
                tenant_id              INTEGER PRIMARY KEY,
                kuota_periode_bulan    INTEGER NOT NULL DEFAULT 0,
                kuota_maksimal_hari    INTEGER NOT NULL DEFAULT 0,
                kuota_boleh_dipecah    INTEGER NOT NULL DEFAULT 1,
                h_min_pengajuan        INTEGER NOT NULL DEFAULT 0,
                maksimal_bersamaan     INTEGER NOT NULL DEFAULT 0,
                updated_at             TEXT
            )
        """)


# ---------------------------------------------------------------------------
# KEBIJAKAN CUTI DINAMIS (per tenant) -- lihat DEFAULT_CUTI_SETTINGS di atas
# ---------------------------------------------------------------------------

def _pastikan_baris_settings(conn, tenant_id: int):
    conn.execute(
        """INSERT INTO izin_cuti_settings (tenant_id, kuota_periode_bulan, kuota_maksimal_hari,
                                            kuota_boleh_dipecah, h_min_pengajuan, maksimal_bersamaan)
           VALUES (?, 0, 0, 1, 0, 0) ON CONFLICT DO NOTHING""",
        (tenant_id,),
    )


def get_cuti_settings(tenant_id: int) -> dict:
    with get_conn() as conn:
        _pastikan_baris_settings(conn, tenant_id)
        row = conn.execute("SELECT * FROM izin_cuti_settings WHERE tenant_id = ?", (tenant_id,)).fetchone()
    if not row:
        return {"tenant_id": tenant_id, **DEFAULT_CUTI_SETTINGS}
    hasil = dict(row)
    hasil["kuota_boleh_dipecah"] = bool(hasil["kuota_boleh_dipecah"])
    return hasil


def set_cuti_settings(tenant_id: int, **fields) -> dict:
    """`fields` boleh sebagian saja (None = pertahankan nilai lama) -- pola
    sama seperti attendance_db.set_settings()/uang_harian_dinamis_db.set_config()."""
    existing = get_cuti_settings(tenant_id)
    baru = dict(existing)
    for key in DEFAULT_CUTI_SETTINGS:
        if key in fields and fields[key] is not None:
            baru[key] = fields[key]

    for key in ("kuota_periode_bulan", "kuota_maksimal_hari", "h_min_pengajuan", "maksimal_bersamaan"):
        if int(baru[key]) < 0:
            raise ValueError(f"{key} tidak boleh negatif.")
    if int(baru["kuota_periode_bulan"]) > 0 and int(baru["kuota_maksimal_hari"]) <= 0:
        raise ValueError("Maksimal Cuti (hari) wajib diisi lebih dari 0 kalau Periode Kuota diaktifkan.")

    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO izin_cuti_settings
                   (tenant_id, kuota_periode_bulan, kuota_maksimal_hari, kuota_boleh_dipecah,
                    h_min_pengajuan, maksimal_bersamaan, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (tenant_id) DO UPDATE SET
                    kuota_periode_bulan = excluded.kuota_periode_bulan,
                    kuota_maksimal_hari = excluded.kuota_maksimal_hari,
                    kuota_boleh_dipecah = excluded.kuota_boleh_dipecah,
                    h_min_pengajuan = excluded.h_min_pengajuan,
                    maksimal_bersamaan = excluded.maksimal_bersamaan,
                    updated_at = excluded.updated_at""",
            (tenant_id, int(baru["kuota_periode_bulan"]), int(baru["kuota_maksimal_hari"]),
             int(bool(baru["kuota_boleh_dipecah"])), int(baru["h_min_pengajuan"]), int(baru["maksimal_bersamaan"]),
             now),
        )
    return get_cuti_settings(tenant_id)


def _hitung_durasi_hari(tanggal_mulai: str, tanggal_selesai: str) -> int:
    mulai = datetime.strptime(tanggal_mulai, "%Y-%m-%d")
    selesai = datetime.strptime(tanggal_selesai, "%Y-%m-%d")
    return (selesai - mulai).days + 1


def _periode_kuota(tanggal: str, periode_bulan: int) -> tuple:
    """Bucket kuota DIANGKAR ke tahun kalender (Januari) -- bukan rolling
    window dari tanggal pengajuan pertama. periode_bulan=3 -> Jan-Mar/Apr-
    Jun/Jul-Sep/Okt-Des (4 kuartal/tahun), periode_bulan=12 -> Jan-Des SATU
    periode/tahun, sesuai KEDUA contoh spesifikasi Owner ("kuota 10 hari
    setiap 3 bulan": Jan+Feb+Mar dijumlahkan; "kuota tahunan": Jan..Des
    dijumlahkan). Return (tanggal_awal_periode, tanggal_akhir_periode)
    string YYYY-MM-DD, MENCAKUP tanggal yang diberikan.
    Periode ditentukan HANYA dari `tanggal_mulai` pengajuan -- cuti yang
    melintasi batas periode (mis. 30 Des - 2 Jan) disederhanakan dianggap
    SELURUHNYA masuk periode tanggal_mulai-nya."""
    dt = datetime.strptime(tanggal, "%Y-%m-%d")
    bulan_awal = ((dt.month - 1) // periode_bulan) * periode_bulan + 1
    awal = datetime(dt.year, bulan_awal, 1)
    bulan_akhir_eksklusif = bulan_awal + periode_bulan
    if bulan_akhir_eksklusif > 12:
        akhir_eksklusif = datetime(dt.year + 1, bulan_akhir_eksklusif - 12, 1)
    else:
        akhir_eksklusif = datetime(dt.year, bulan_akhir_eksklusif, 1)
    akhir = akhir_eksklusif - timedelta(days=1)
    return awal.strftime("%Y-%m-%d"), akhir.strftime("%Y-%m-%d")


def _kuota_terpakai_hari(barber_id: int, periode_awal: str, periode_akhir: str,
                          kecuali_pengajuan_id: int = None) -> int:
    """Jumlah hari cuti (jenis='cuti', status pending ATAU disetujui --
    LEWATI 'ditolak' dan pengajuan yang sudah dihapus, sesuai permintaan
    Owner) milik barber ini yang tanggal_mulai-nya jatuh di periode ini."""
    q = ("SELECT tanggal_mulai, tanggal_selesai FROM izin_cuti "
         "WHERE barber_id = ? AND jenis = 'cuti' AND status IN ('pending', 'disetujui') "
         "AND tanggal_mulai >= ? AND tanggal_mulai <= ?")
    params = [barber_id, periode_awal, periode_akhir]
    if kecuali_pengajuan_id is not None:
        q += " AND id != ?"; params.append(kecuali_pengajuan_id)
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return sum(_hitung_durasi_hari(r["tanggal_mulai"], r["tanggal_selesai"]) for r in rows)


def _jumlah_bersamaan_maksimal(tenant_id: int, tanggal_mulai: str, tanggal_selesai: str,
                                kecuali_barber_id: int = None, kecuali_pengajuan_id: int = None) -> int:
    """Jumlah TERBESAR barber (LAIN, jenis='cuti', status pending/disetujui)
    yang cuti-nya beririsan dengan SALAH SATU tanggal dalam rentang
    [tanggal_mulai, tanggal_selesai] -- dicek PER HARI (bukan cuma overlap
    rentang keseluruhan), sesuai contoh spesifikasi Owner (limit 2 orang:
    A 16-19 Juli + B 18-20 Juli diizinkan karena maks 2 org/hari, tapi C
    19-21 Juli ditolak karena tanggal 19 sudah 2 orang)."""
    q = ("SELECT DISTINCT i.barber_id, i.tanggal_mulai, i.tanggal_selesai FROM izin_cuti i "
         "JOIN barbers b ON b.id = i.barber_id "
         "WHERE b.tenant_id = ? AND i.jenis = 'cuti' AND i.status IN ('pending', 'disetujui') "
         "AND i.tanggal_mulai <= ? AND i.tanggal_selesai >= ?")
    params = [tenant_id, tanggal_selesai, tanggal_mulai]
    if kecuali_pengajuan_id is not None:
        q += " AND i.id != ?"; params.append(kecuali_pengajuan_id)
    with get_conn() as conn:
        existing = [dict(r) for r in conn.execute(q, params).fetchall()]

    mulai_dt = datetime.strptime(tanggal_mulai, "%Y-%m-%d")
    selesai_dt = datetime.strptime(tanggal_selesai, "%Y-%m-%d")
    maksimal_per_hari = 0
    hari = mulai_dt
    while hari <= selesai_dt:
        tgl = hari.strftime("%Y-%m-%d")
        jumlah = sum(1 for r in existing
                     if r["tanggal_mulai"] <= tgl <= r["tanggal_selesai"] and r["barber_id"] != kecuali_barber_id)
        maksimal_per_hari = max(maksimal_per_hari, jumlah)
        hari += timedelta(days=1)
    return maksimal_per_hari


def _validasi_kebijakan_cuti(barber_id: int, tenant_id: int, jenis: str, tanggal_mulai: str,
                              tanggal_selesai: str, kecuali_pengajuan_id: int = None) -> None:
    """Raise ValueError (pesan siap tampil) kalau melanggar kebijakan --
    HANYA berlaku jenis='cuti' (lihat DEFAULT_CUTI_SETTINGS di atas), dan
    HANYA dipanggil kalau pemanggil BUKAN Owner/Admin/Staff (lihat param
    `override` di buat_pengajuan()/edit_pengajuan() di bawah -- Owner/
    Admin/Staff SELALU boleh melewati kebijakan ini)."""
    if jenis != "cuti" or tenant_id is None:
        return
    settings = get_cuti_settings(tenant_id)

    if settings["h_min_pengajuan"] > 0:
        selisih_hari = (datetime.strptime(tanggal_mulai, "%Y-%m-%d").date()
                         - datetime.strptime(_hari_ini_wib(), "%Y-%m-%d").date()).days
        if selisih_hari < settings["h_min_pengajuan"]:
            raise ValueError(
                f"Pengajuan cuti harus dilakukan minimal H-{settings['h_min_pengajuan']} "
                f"sebelum tanggal cuti."
            )

    if settings["maksimal_bersamaan"] > 0:
        jumlah = _jumlah_bersamaan_maksimal(tenant_id, tanggal_mulai, tanggal_selesai,
                                             kecuali_barber_id=barber_id,
                                             kecuali_pengajuan_id=kecuali_pengajuan_id)
        if jumlah + 1 > settings["maksimal_bersamaan"]:
            raise ValueError(
                f"Sudah ada {jumlah} karyawan lain yang cuti pada salah satu tanggal di rentang ini "
                f"(maksimal {settings['maksimal_bersamaan']} orang bersamaan)."
            )

    if settings["kuota_periode_bulan"] > 0 and settings["kuota_maksimal_hari"] > 0:
        periode_awal, periode_akhir = _periode_kuota(tanggal_mulai, settings["kuota_periode_bulan"])
        terpakai = _kuota_terpakai_hari(barber_id, periode_awal, periode_akhir,
                                         kecuali_pengajuan_id=kecuali_pengajuan_id)
        if not settings["kuota_boleh_dipecah"] and terpakai > 0:
            raise ValueError(
                "Kuota cuti periode ini tidak boleh dipecah, dan sudah ada pengajuan cuti lain "
                "di periode yang sama."
            )
        durasi_baru = _hitung_durasi_hari(tanggal_mulai, tanggal_selesai)
        if terpakai + durasi_baru > settings["kuota_maksimal_hari"]:
            sisa = max(0, settings["kuota_maksimal_hari"] - terpakai)
            raise ValueError(
                f"Kuota cuti periode ini ({periode_awal} s/d {periode_akhir}) tersisa {sisa} hari, "
                f"pengajuan ini {durasi_baru} hari."
            )


def _lengkapi(row: dict) -> dict:
    barber = get_barber(row["barber_id"])
    row["nama_barber"] = barber["nama"] if barber else "(barber terhapus)"
    # FONDASI Multi-Tenant Phase 1.1: izin_cuti TIDAK punya kolom tenant_id
    # sendiri (di-scope TRANSITIF lewat barbers.tenant_id, barber_id NOT
    # NULL) -- diselipkan di sini untuk fetch-then-authorize.
    row["tenant_id"] = barber["tenant_id"] if barber else None
    return row


def get_pengajuan(pengajuan_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM izin_cuti WHERE id = ?", (pengajuan_id,)).fetchone()
        return _lengkapi(dict(row)) if row else None


def get_pengajuan_list(barber_id: int = None, status: str = None, jenis: str = None,
                        tahun: int = None, bulan: int = None, tenant_id: int = None) -> list:
    """FONDASI Multi-Tenant Phase 1.1: `tenant_id` opsional, JOIN tambahan
    ke barbers HANYA ditambahkan kalau diisi (endpoint ber-login WAJIB
    mengisi ini)."""
    q = "SELECT i.* FROM izin_cuti i"
    if tenant_id is not None:
        q += " JOIN barbers b ON b.id = i.barber_id"
    q += " WHERE 1=1"
    params = []
    if tenant_id is not None:
        q += " AND b.tenant_id = ?"; params.append(tenant_id)
    if barber_id is not None:
        q += " AND i.barber_id = ?"; params.append(barber_id)
    if status is not None:
        q += " AND i.status = ?"; params.append(status)
    if jenis is not None:
        q += " AND i.jenis = ?"; params.append(jenis)
    if tahun is not None:
        q += " AND i.tanggal_mulai LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND i.tanggal_mulai LIKE ?"; params.append(f"%-{bulan:02d}-%")
    q += " ORDER BY i.tanggal_mulai DESC, i.id DESC"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    return [_lengkapi(r) for r in rows]


def get_jumlah_pending(tenant_id: int = None) -> int:
    """Dipakai badge notifikasi sidebar (Owner/Admin) -- lihat izin_notif.js."""
    q = "SELECT COUNT(*) AS jumlah FROM izin_cuti i"
    if tenant_id is not None:
        q += " JOIN barbers b ON b.id = i.barber_id"
    q += " WHERE i.status = 'pending'"
    params = []
    if tenant_id is not None:
        q += " AND b.tenant_id = ?"; params.append(tenant_id)
    with get_conn() as conn:
        row = conn.execute(q, params).fetchone()
    return int(row["jumlah"] or 0)


def _kirim_notifikasi_push_pengajuan_baru(pengajuan: dict):
    """FITUR Notifikasi Push: "best effort" -- TIDAK PERNAH melempar
    exception/menggagalkan pengajuan utamanya (pola sama persis
    booking_db.py::_kirim_notifikasi_push_booking_baru()). Ke role
    admin/staff (yang approve/reject) -- audiens SAMA seperti badge
    get_jumlah_pending() (izin_notif.js)."""
    try:
        push_service.kirim_ke_role(
            pengajuan.get("tenant_id"), ["admin", "staff"],
            title=f"Pengajuan {_JENIS_LABEL.get(pengajuan['jenis'], pengajuan['jenis'])} Baru",
            body=f"{pengajuan.get('nama_barber')} mengajukan {pengajuan['tanggal_mulai']} s/d {pengajuan['tanggal_selesai']}.",
            url="/app/#/izin-cuti",
        )
    except Exception as e:
        logger.error("Notifikasi push pengajuan #%s GAGAL disiapkan: %s: %s", pengajuan.get("id"), type(e).__name__, e)


def _kirim_notifikasi_push_status_pengajuan(pengajuan: dict):
    """Ke akun login barber ybs SAJA (bukan role admin/staff seperti
    fungsi di atas) -- status pengajuannya sendiri yang berubah."""
    try:
        status_label = "Disetujui" if pengajuan["status"] == "disetujui" else "Ditolak"
        push_service.kirim_ke_barber(
            pengajuan["barber_id"],
            title=f"Pengajuan {_JENIS_LABEL.get(pengajuan['jenis'], pengajuan['jenis'])} {status_label}",
            body=f"Pengajuan {pengajuan['tanggal_mulai']} s/d {pengajuan['tanggal_selesai']} Anda {status_label.lower()}.",
            url="/app/#/izin-cuti",
        )
    except Exception as e:
        logger.error("Notifikasi push status pengajuan #%s GAGAL disiapkan: %s: %s", pengajuan.get("id"), type(e).__name__, e)


def buat_pengajuan(barber_id: int, jenis: str, tanggal_mulai: str, tanggal_selesai: str,
                    alasan: str, diajukan_oleh: str = "", tenant_id: int = None,
                    override: bool = False) -> dict:
    """`override=True` (KHUSUS Owner/Admin/Staff, lihat routers/izin_cuti.py)
    melewati SELURUH kebijakan cuti dinamis (_validasi_kebijakan_cuti() di
    atas) -- barber (override=False, default) selalu tunduk padanya."""
    barber = get_barber(barber_id)
    if barber is None or (tenant_id is not None and barber["tenant_id"] != tenant_id):
        raise ValueError("Barber tidak ditemukan.")
    if jenis not in JENIS_VALID:
        raise ValueError(f"Jenis tidak dikenal: {jenis}")
    datetime.strptime(tanggal_mulai, "%Y-%m-%d")
    datetime.strptime(tanggal_selesai, "%Y-%m-%d")
    if tanggal_mulai > tanggal_selesai:
        raise ValueError("Tanggal Mulai tidak boleh setelah Tanggal Selesai.")
    alasan = (alasan or "").strip()
    if not alasan:
        raise ValueError("Alasan wajib diisi.")
    if not override:
        _validasi_kebijakan_cuti(barber_id, tenant_id if tenant_id is not None else barber["tenant_id"],
                                  jenis, tanggal_mulai, tanggal_selesai)
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO izin_cuti (barber_id, jenis, tanggal_mulai, tanggal_selesai, alasan, status,
                                       diajukan_oleh, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (barber_id, jenis, tanggal_mulai, tanggal_selesai, alasan, diajukan_oleh, now),
        )
        pengajuan_id = cur.lastrowid
    pengajuan_baru = get_pengajuan(pengajuan_id)
    _kirim_notifikasi_push_pengajuan_baru(pengajuan_baru)
    return pengajuan_baru


def edit_pengajuan(pengajuan_id: int, jenis: str = None, tanggal_mulai: str = None,
                    tanggal_selesai: str = None, alasan: str = None, override: bool = False) -> dict:
    existing = get_pengajuan(pengajuan_id)
    if existing is None:
        raise ValueError("Pengajuan tidak ditemukan.")
    if existing["status"] != "pending":
        raise ValueError("Pengajuan yang sudah diproses (Disetujui/Ditolak) tidak bisa diedit lagi.")
    jenis_baru = jenis if jenis is not None else existing["jenis"]
    if jenis_baru not in JENIS_VALID:
        raise ValueError(f"Jenis tidak dikenal: {jenis_baru}")
    mulai_baru = tanggal_mulai if tanggal_mulai is not None else existing["tanggal_mulai"]
    selesai_baru = tanggal_selesai if tanggal_selesai is not None else existing["tanggal_selesai"]
    if tanggal_mulai is not None:
        datetime.strptime(mulai_baru, "%Y-%m-%d")
    if tanggal_selesai is not None:
        datetime.strptime(selesai_baru, "%Y-%m-%d")
    if mulai_baru > selesai_baru:
        raise ValueError("Tanggal Mulai tidak boleh setelah Tanggal Selesai.")
    alasan_baru = alasan.strip() if alasan is not None else existing["alasan"]
    if alasan is not None and not alasan_baru:
        raise ValueError("Alasan wajib diisi.")
    # FITUR Kebijakan Cuti Dinamis: divalidasi ULANG di sini (bukan cuma
    # buat_pengajuan()) supaya barber tidak bisa melewati kebijakan dengan
    # mengajukan tanggal yang valid lalu langsung mengedit ke tanggal yang
    # sebenarnya melanggar -- `kecuali_pengajuan_id` mengeluarkan baris
    # ybs sendiri dari hitungan overlap/kuota (bukan dianggap "orang lain").
    if not override:
        _validasi_kebijakan_cuti(existing["barber_id"], existing.get("tenant_id"), jenis_baru,
                                  mulai_baru, selesai_baru, kecuali_pengajuan_id=pengajuan_id)
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """UPDATE izin_cuti SET jenis = ?, tanggal_mulai = ?, tanggal_selesai = ?, alasan = ?,
                   updated_at = ? WHERE id = ?""",
            (jenis_baru, mulai_baru, selesai_baru, alasan_baru, now, pengajuan_id),
        )
    return get_pengajuan(pengajuan_id)


def hapus_pengajuan(pengajuan_id: int):
    existing = get_pengajuan(pengajuan_id)
    if existing is None:
        raise ValueError("Pengajuan tidak ditemukan.")
    if existing["status"] != "pending":
        raise ValueError("Pengajuan yang sudah diproses (Disetujui/Ditolak) tidak bisa dihapus lagi.")
    with get_conn() as conn:
        conn.execute("DELETE FROM izin_cuti WHERE id = ?", (pengajuan_id,))


def set_status_pengajuan(pengajuan_id: int, status: str, catatan_approval: str = "",
                          disetujui_oleh: str = "") -> dict:
    if status not in {"disetujui", "ditolak"}:
        raise ValueError(f"Status tidak dikenal: {status}")
    existing = get_pengajuan(pengajuan_id)
    if existing is None:
        raise ValueError("Pengajuan tidak ditemukan.")
    if existing["status"] != "pending":
        raise ValueError("Pengajuan ini sudah diproses sebelumnya.")
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """UPDATE izin_cuti SET status = ?, catatan_approval = ?, disetujui_oleh = ?,
                   tanggal_approval = ?, updated_at = ? WHERE id = ?""",
            (status, (catatan_approval or "").strip(), disetujui_oleh, now[:10], now, pengajuan_id),
        )
    pengajuan_baru = get_pengajuan(pengajuan_id)
    _kirim_notifikasi_push_status_pengajuan(pengajuan_baru)
    return pengajuan_baru
