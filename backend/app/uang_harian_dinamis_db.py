"""
uang_harian_dinamis_db.py — FITUR Uang Harian Dinamis Berdasarkan Absensi
=============================================================================
Sebelum modul ini ada, Uang Harian (database.py::hitung_uang_harian_per_hari)
MURNI berbasis jumlah service hari itu (>= target = cair penuh, < target =
Rp0) -- SAMA SEKALI tidak memandang data Absensi (jam masuk/pulang, toleransi,
limit bulanan). Modul ini menambah KEMAMPUAN OPSIONAL (opt-in PER TENANT,
default MATI) supaya Tenant bisa memilih data Absensi (toleransi harian dan/
atau limit bulanan, keterlambatan dan pulang lebih awal diatur TERPISAH) dan/
atau jumlah service sebagai dasar potongan Uang Harian.

TIDAK MENGUBAH modul Absensi (attendance_db.py) sama sekali -- HANYA MEMBACA
attendance_settings/attendance_logs milik modul itu (read-only dari sini).
Satu pengecualian: attendance_settings punya SATU kolom baru
(toleransi_pulang_awal_menit, lihat attendance_db.py::DEFAULT_SETTINGS) yang
KHUSUS dipakai modul ini -- logika Absensi sendiri (status/badge/keterangan)
TIDAK PERNAH membaca kolom itu, jadi perilaku Absensi tidak berubah sama
sekali. Toleransi keterlambatan & limit bulanan (keterlambatan MAUPUN pulang
awal) SENGAJA TIDAK diduplikasi di sini -- diambil LANGSUNG dari
attendance_settings (satu sumber kebenaran, keputusan eksplisit Owner) lewat
attendance_db.get_settings().

KONSEP INTI (lihat get_config() untuk bentuk lengkap konfigurasi):
- `aktif=False` (default) -- Uang Harian TETAP memakai sistem LAMA
  (database.py, murni jumlah service) TANPA PERUBAHAN SAMA SEKALI. Ini
  menjamin backward compatibility total untuk Tenant yang belum opt-in.
- `aktif=True` -- Uang Harian sekarang dievaluasi PER HARI ABSENSI (bukan
  lagi per hari ada transaksi service) lewat evaluasi_hari() di bawah:
  toleransi harian & limit bulanan (keterlambatan dan pulang awal diatur
  TERPISAH, masing-masing punya toggle gunakan_toleransi/gunakan_limit
  sendiri -- SENGAJA tidak dipaksa satu "mode global", supaya kombinasi
  asimetris seperti "Keterlambatan: Hanya Toleransi, Pulang Awal: Hanya
  Limit" tetap bisa diatur) memicu SATU potongan (bukan dijumlahkan -- lihat
  MAX() di evaluasi_hari()), digabung dengan Service Rule (opsional,
  MENGGANTIKAN total aturan service lama selama `aktif=True` -- reuse
  service acuan yang SAMA dari database.get_uang_harian_acuan_ids(), hanya
  ambang minimal & konsekuensinya yang baru/berbeda).

KOREKSI ABSENSI: TIDAK ADA logika koreksi khusus di modul ini sama sekali --
attendance_db._terapkan_koreksi_ke_log() SUDAH menulis ulang attendance_logs
begitu koreksi disetujui (Approved), jadi evaluasi_hari() di bawah (yang
membaca attendance_logs APA ADANYA, live, setiap dipanggil -- TIDAK ADA nilai
yang disimpan/dibekukan di sini) otomatis memakai data terbaru. Koreksi
Pending/Rejected tidak pernah menyentuh attendance_logs, jadi otomatis tidak
memengaruhi apa pun di sini juga -- persis seperti permintaan "jangan
finalisasi selama Pending". Slip Gaji (slip_gaji_db.py) TETAP membekukan
nilai SEKALI saat dibuat (perilaku lama, tidak diubah) -- kalau koreksi
disetujui SETELAH slip dibuat, slip lama TIDAK otomatis berubah (sama seperti
transaksi lain yang diedit setelah slip dibuat), Admin/Owner perlu membuat
ulang slip kalau mau angka terbaru.
"""

from datetime import datetime

import attendance_db
from database import get_conn, get_uang_harian_acuan_ids, target_uang_harian_per_hari

MODE_KOMBINASI_VALID = {"OR", "AND"}
SERVICE_RULE_MODE_VALID = {"TIDAK_DIGUNAKAN", "SYARAT", "POTONGAN"}

DEFAULT_CONFIG = {
    "aktif": False,
    "keterlambatan_gunakan_toleransi": False,
    "keterlambatan_gunakan_limit": False,
    "keterlambatan_potongan_persen": 0,
    "pulang_awal_gunakan_toleransi": False,
    "pulang_awal_gunakan_limit": False,
    "pulang_awal_potongan_persen": 0,
    "kombinasi_metode": "OR",
    "service_rule_mode": "TIDAK_DIGUNAKAN",
    "service_rule_minimal": 0,
    "service_rule_potongan_persen": 0,
}


def init_uang_harian_dinamis_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS uang_harian_dinamis_settings (
                tenant_id                       INTEGER PRIMARY KEY,
                aktif                           INTEGER NOT NULL DEFAULT 0,
                keterlambatan_gunakan_toleransi INTEGER NOT NULL DEFAULT 0,
                keterlambatan_gunakan_limit     INTEGER NOT NULL DEFAULT 0,
                keterlambatan_potongan_persen   INTEGER NOT NULL DEFAULT 0,
                pulang_awal_gunakan_toleransi   INTEGER NOT NULL DEFAULT 0,
                pulang_awal_gunakan_limit       INTEGER NOT NULL DEFAULT 0,
                pulang_awal_potongan_persen     INTEGER NOT NULL DEFAULT 0,
                kombinasi_metode                TEXT NOT NULL DEFAULT 'OR',
                service_rule_mode                TEXT NOT NULL DEFAULT 'TIDAK_DIGUNAKAN',
                service_rule_minimal            INTEGER NOT NULL DEFAULT 0,
                service_rule_potongan_persen    INTEGER NOT NULL DEFAULT 0,
                updated_at                       TEXT
            )
        """)


# ---------------------------------------------------------------------------
# KONFIGURASI (per tenant)
# ---------------------------------------------------------------------------

def get_config(tenant_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM uang_harian_dinamis_settings WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()
    if not row:
        return {"tenant_id": tenant_id, **DEFAULT_CONFIG}
    hasil = dict(row)
    hasil["aktif"] = bool(hasil["aktif"])
    hasil["keterlambatan_gunakan_toleransi"] = bool(hasil["keterlambatan_gunakan_toleransi"])
    hasil["keterlambatan_gunakan_limit"] = bool(hasil["keterlambatan_gunakan_limit"])
    hasil["pulang_awal_gunakan_toleransi"] = bool(hasil["pulang_awal_gunakan_toleransi"])
    hasil["pulang_awal_gunakan_limit"] = bool(hasil["pulang_awal_gunakan_limit"])
    return hasil


def set_config(tenant_id: int, **fields) -> dict:
    """`fields` boleh sebagian saja (None = pertahankan nilai lama) -- pola
    sama seperti attendance_db.set_settings(). Validasi persentase 0-100 dan
    enum dilakukan di sini, BUKAN di router, supaya konsisten dipakai dari
    mana pun (termasuk test langsung ke modul ini)."""
    existing = get_config(tenant_id)
    baru = dict(existing)
    for key in DEFAULT_CONFIG:
        if key in fields and fields[key] is not None:
            baru[key] = fields[key]

    for key in ("keterlambatan_potongan_persen", "pulang_awal_potongan_persen", "service_rule_potongan_persen"):
        if not (0 <= int(baru[key]) <= 100):
            raise ValueError("Potongan harus antara 0-100%.")
    if baru["kombinasi_metode"] not in MODE_KOMBINASI_VALID:
        raise ValueError(f"Metode kombinasi tidak valid, pilih salah satu: {sorted(MODE_KOMBINASI_VALID)}.")
    if baru["service_rule_mode"] not in SERVICE_RULE_MODE_VALID:
        raise ValueError(f"Mode Service Rule tidak valid, pilih salah satu: {sorted(SERVICE_RULE_MODE_VALID)}.")
    if int(baru["service_rule_minimal"]) < 0:
        raise ValueError("Minimal Service tidak boleh negatif.")

    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO uang_harian_dinamis_settings
                   (tenant_id, aktif, keterlambatan_gunakan_toleransi, keterlambatan_gunakan_limit,
                    keterlambatan_potongan_persen, pulang_awal_gunakan_toleransi, pulang_awal_gunakan_limit,
                    pulang_awal_potongan_persen, kombinasi_metode, service_rule_mode, service_rule_minimal,
                    service_rule_potongan_persen, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (tenant_id) DO UPDATE SET
                    aktif = excluded.aktif,
                    keterlambatan_gunakan_toleransi = excluded.keterlambatan_gunakan_toleransi,
                    keterlambatan_gunakan_limit = excluded.keterlambatan_gunakan_limit,
                    keterlambatan_potongan_persen = excluded.keterlambatan_potongan_persen,
                    pulang_awal_gunakan_toleransi = excluded.pulang_awal_gunakan_toleransi,
                    pulang_awal_gunakan_limit = excluded.pulang_awal_gunakan_limit,
                    pulang_awal_potongan_persen = excluded.pulang_awal_potongan_persen,
                    kombinasi_metode = excluded.kombinasi_metode,
                    service_rule_mode = excluded.service_rule_mode,
                    service_rule_minimal = excluded.service_rule_minimal,
                    service_rule_potongan_persen = excluded.service_rule_potongan_persen,
                    updated_at = excluded.updated_at""",
            (tenant_id, int(baru["aktif"]), int(baru["keterlambatan_gunakan_toleransi"]),
             int(baru["keterlambatan_gunakan_limit"]), int(baru["keterlambatan_potongan_persen"]),
             int(baru["pulang_awal_gunakan_toleransi"]), int(baru["pulang_awal_gunakan_limit"]),
             int(baru["pulang_awal_potongan_persen"]), baru["kombinasi_metode"], baru["service_rule_mode"],
             int(baru["service_rule_minimal"]), int(baru["service_rule_potongan_persen"]), now),
        )
    return get_config(tenant_id)


# ---------------------------------------------------------------------------
# AKUMULASI LIMIT BULANAN (berurutan tanggal, SAMA PERSIS logika "sudah
# habis" attendance_db.hitung_ringkasan_bulan() -- direplikasi di sini,
# BUKAN dipanggil langsung, karena fungsi itu mengembalikan teks keterangan
# siap tampil, bukan angka mentah per tanggal yang evaluasi_hari() butuhkan).
# ---------------------------------------------------------------------------

def _akumulasi_limit_bulan(barber_id: int, tenant_id: int, tahun: int, bulan: int) -> dict:
    """{tanggal: {"terlambat_menit": int|None, "terlambat_limit_lampaui": bool,
                  "pulang_awal_menit": int|None, "pulang_awal_limit_lampaui": bool}}
    -- SATU pass urut tanggal naik, meniru persis attendance_db.hitung_ringkasan_bulan()
    supaya "limit habis" di sini SELALU konsisten dengan yang sudah tampil di
    Absensi (>=, bukan >)."""
    settings = attendance_db.get_settings(tenant_id)
    batas_terlambat = settings["batas_menit_terlambat"]
    batas_pulang_awal = settings["batas_menit_pulang_awal"]
    prefix = f"{tahun:04d}-{bulan:02d}"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(
            """SELECT * FROM attendance_logs WHERE barber_id = ? AND tenant_id = ?
                   AND tanggal LIKE ? ORDER BY tanggal ASC""",
            (barber_id, tenant_id, prefix + "-%"),
        ).fetchall()]

    total_terlambat = 0
    total_pulang_awal = 0
    hasil: dict[str, dict] = {}
    for row in rows:
        menit_terlambat = attendance_db._menit_terlambat_baris(row, settings)
        terlambat_lampaui = False
        if menit_terlambat is not None:
            total_terlambat += menit_terlambat
            terlambat_lampaui = total_terlambat >= batas_terlambat
        menit_pulang_awal = attendance_db._menit_pulang_awal_baris(row, settings)
        pulang_awal_lampaui = False
        if menit_pulang_awal is not None:
            total_pulang_awal += menit_pulang_awal
            pulang_awal_lampaui = total_pulang_awal >= batas_pulang_awal
        hasil[row["tanggal"]] = {
            "terlambat_menit": menit_terlambat,
            "terlambat_limit_lampaui": terlambat_lampaui,
            "pulang_awal_menit": menit_pulang_awal,
            "pulang_awal_limit_lampaui": pulang_awal_lampaui,
        }
    return hasil


# ---------------------------------------------------------------------------
# EVALUASI SATU HARI
# ---------------------------------------------------------------------------

def _jumlah_service_acuan_hari(barber_id: int, tanggal: str, acuan_ids: set) -> int:
    if not acuan_ids:
        return 0
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT td.service_id, td.jumlah FROM transaksi_detail td
               JOIN transaksi t ON t.id = td.transaksi_id
               WHERE t.barber_id = ? AND t.tanggal = ?""",
            (barber_id, tanggal),
        ).fetchall()
    return sum(r["jumlah"] for r in rows if r["service_id"] in acuan_ids)


def evaluasi_hari(barber: dict, tanggal: str, config: dict, akumulasi_hari: dict | None) -> dict:
    """Evaluasi SATU hari untuk SATU barber -- `akumulasi_hari` adalah entri
    {tanggal: {...}} dari _akumulasi_limit_bulan() milik BULAN tanggal ini
    (caller yang menyediakan, supaya walau dipanggil untuk banyak hari
    sekaligus, bulan yang sama tidak dihitung ulang berkali-kali -- lihat
    hitung_uang_harian_dinamis_bulan()/_rentang() di bawah).

    Mengembalikan breakdown LENGKAP (lihat kunci "final" untuk nominal akhir)
    -- dipakai baik oleh agregat bulan/rentang (hanya ambil "final") maupun
    endpoint breakdown transparan (routers, tampilkan semua kunci apa
    adanya, lihat section 17 permintaan Owner)."""
    tenant_id = barber.get("tenant_id")
    nominal_dasar = int(barber["uang_harian"] or 0)
    info = (akumulasi_hari or {}).get(tanggal, {})

    menit_terlambat = info.get("terlambat_menit")
    menit_pulang_awal = info.get("pulang_awal_menit")

    settings = attendance_db.get_settings(tenant_id)

    def _evaluasi_jenis(prefix: str, menit: int | None, toleransi_menit: int, limit_lampaui: bool) -> dict:
        gunakan_toleransi = config[f"{prefix}_gunakan_toleransi"]
        gunakan_limit = config[f"{prefix}_gunakan_limit"]
        toleransi_dilanggar = bool(gunakan_toleransi and menit is not None and menit > toleransi_menit)
        limit_dilanggar = bool(gunakan_limit and limit_lampaui and menit is not None and menit > 0)
        if gunakan_toleransi and gunakan_limit:
            dilanggar = ((toleransi_dilanggar or limit_dilanggar) if config["kombinasi_metode"] == "OR"
                         else (toleransi_dilanggar and limit_dilanggar))
        elif gunakan_toleransi:
            dilanggar = toleransi_dilanggar
        elif gunakan_limit:
            dilanggar = limit_dilanggar
        else:
            dilanggar = False
        return {
            "menit": menit or 0,
            "gunakan_toleransi": gunakan_toleransi,
            "toleransi_menit": toleransi_menit,
            "toleransi_dilanggar": toleransi_dilanggar,
            "gunakan_limit": gunakan_limit,
            "limit_lampaui": bool(limit_lampaui),
            "dilanggar": dilanggar,
            "potongan_persen": config[f"{prefix}_potongan_persen"] if dilanggar else 0,
        }

    keterlambatan = _evaluasi_jenis("keterlambatan", menit_terlambat, settings["toleransi_menit"],
                                     info.get("terlambat_limit_lampaui", False))
    pulang_awal = _evaluasi_jenis("pulang_awal", menit_pulang_awal, settings["toleransi_pulang_awal_menit"] or 0,
                                   info.get("pulang_awal_limit_lampaui", False))

    # Section 11: kejadian keterlambatan DAN pulang awal di hari yang sama
    # TIDAK dijumlahkan -- ambil potongan TERBESAR (MAX), bukan SUM.
    potongan_absensi = max(keterlambatan["potongan_persen"], pulang_awal["potongan_persen"])

    acuan_ids = set(get_uang_harian_acuan_ids(tenant_id=tenant_id))
    jumlah_service = _jumlah_service_acuan_hari(barber["id"], tanggal, acuan_ids)
    service_mode = config["service_rule_mode"]
    service_minimal = config["service_rule_minimal"]
    service_terpenuhi = jumlah_service >= service_minimal
    service = {
        "mode": service_mode,
        "jumlah": jumlah_service,
        "minimal": service_minimal,
        "terpenuhi": service_terpenuhi,
        "potongan_persen": 0,
    }

    if service_mode == "SYARAT" and not service_terpenuhi:
        # Section 13: syarat service tidak terpenuhi -> Rp0 mutlak, absensi
        # tidak lagi relevan (bukan ditumpuk/dijumlahkan dengan potongan
        # absensi -- literal "Rp0" di spesifikasi, bukan "0 - potongan lain").
        potongan_final = 100
    else:
        if service_mode == "POTONGAN" and not service_terpenuhi:
            service["potongan_persen"] = config["service_rule_potongan_persen"]
        # Section 13: service TIDAK menghilangkan potongan absensi (dan
        # sebaliknya) -- gabungkan dengan prinsip MAX yang sama seperti
        # section 11 (bukan dijumlahkan).
        potongan_final = max(potongan_absensi, service["potongan_persen"])

    final = round(nominal_dasar * (100 - potongan_final) / 100)
    return {
        "tanggal": tanggal,
        "uang_harian_dasar": nominal_dasar,
        "keterlambatan": keterlambatan,
        "pulang_awal": pulang_awal,
        "service": service,
        "potongan_persen": potongan_final,
        "uang_harian_final": final,
    }


# ---------------------------------------------------------------------------
# AGREGAT BULAN / RENTANG -- bentuk return SAMA seperti
# database.hitung_uang_harian_bulan()/_rentang() (cuma int) supaya
# database.py bisa mengganti pemanggilan tanpa mengubah caller lain.
# ---------------------------------------------------------------------------

def hitung_uang_harian_dinamis_bulan(barber: dict, tahun: int, bulan: int) -> int:
    tenant_id = barber.get("tenant_id")
    config = get_config(tenant_id)
    akumulasi = _akumulasi_limit_bulan(barber["id"], tenant_id, tahun, bulan)
    total = 0
    for tanggal in akumulasi:
        total += evaluasi_hari(barber, tanggal, config, akumulasi)["uang_harian_final"]
    return total


def hitung_uang_harian_dinamis_rentang(barber: dict, tanggal_mulai: str, tanggal_selesai: str) -> int:
    """Rentang bebas (Laporan PDF) -- BISA melintasi 2+ bulan kalender,
    jadi akumulasi limit dihitung PER BULAN yang tercakup (limit reset tiap
    tanggal 1, sama seperti Absensi) lalu digabung."""
    tenant_id = barber.get("tenant_id")
    config = get_config(tenant_id)
    mulai = datetime.strptime(tanggal_mulai, "%Y-%m-%d")
    selesai = datetime.strptime(tanggal_selesai, "%Y-%m-%d")
    total = 0
    akumulasi_cache: dict[tuple[int, int], dict] = {}
    tahun, bulan = mulai.year, mulai.month
    while (tahun, bulan) <= (selesai.year, selesai.month):
        if (tahun, bulan) not in akumulasi_cache:
            akumulasi_cache[(tahun, bulan)] = _akumulasi_limit_bulan(barber["id"], tenant_id, tahun, bulan)
        akumulasi = akumulasi_cache[(tahun, bulan)]
        for tanggal in akumulasi:
            if tanggal_mulai <= tanggal <= tanggal_selesai:
                total += evaluasi_hari(barber, tanggal, config, akumulasi)["uang_harian_final"]
        bulan += 1
        if bulan > 12:
            bulan = 1
            tahun += 1
    return total


def breakdown_hari(barber: dict, tanggal: str) -> dict:
    """Versi TRANSPARAN evaluasi_hari() untuk SATU hari -- dipakai endpoint
    detail/UI breakdown (section 17). `akumulasi_hari` dihitung ulang di sini
    (satu bulan) karena ini dipanggil per-hari, bukan dari loop bulanan."""
    tenant_id = barber.get("tenant_id")
    config = get_config(tenant_id)
    if not config["aktif"]:
        target = target_uang_harian_per_hari(tenant_id=tenant_id)
        acuan_ids = set(get_uang_harian_acuan_ids(tenant_id=tenant_id))
        jumlah = _jumlah_service_acuan_hari(barber["id"], tanggal, acuan_ids)
        nominal_dasar = int(barber["uang_harian"] or 0)
        terpenuhi = jumlah >= target
        return {
            "tanggal": tanggal,
            "aktif": False,
            "uang_harian_dasar": nominal_dasar,
            "service": {"mode": "SYARAT_LAMA", "jumlah": jumlah, "minimal": target, "terpenuhi": terpenuhi,
                        "potongan_persen": 0 if terpenuhi else 100},
            "potongan_persen": 0 if terpenuhi else 100,
            "uang_harian_final": nominal_dasar if terpenuhi else 0,
        }
    tahun, bulan = int(tanggal[:4]), int(tanggal[5:7])
    akumulasi = _akumulasi_limit_bulan(barber["id"], tenant_id, tahun, bulan)
    hasil = evaluasi_hari(barber, tanggal, config, akumulasi)
    hasil["aktif"] = True
    return hasil
