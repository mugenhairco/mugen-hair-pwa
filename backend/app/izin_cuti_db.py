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

# FITUR Kebijakan Cuti Dinamis (feedback Owner) + REVISI Sistem Dinamis
# Cuti & Izin (permintaan Owner, Agustus 2026, lihat izin_cuti_migrasi.py):
# SEMUA nilai di sini 0/off/'terpisah' secara default -- tenant yang belum
# pernah membuka kartu "Pengaturan Izin & Cuti" (menu Pengaturan >
# Karyawan) TIDAK terpengaruh sama sekali, byte-for-byte sama seperti
# sebelum fitur ini ada.
#
# ATURAN IZIN & CUTI SENGAJA DIPISAH TOTAL (permintaan Owner eksplisit --
# mengubah salah satu TIDAK BOLEH memengaruhi yang lain): H-min pakai
# field terpisah (h_min_pengajuan = cuti, h_min_pengajuan_izin = izin).
# Kuota juga py field terpisah per jenis (kuota_maksimal_hari = cuti,
# kuota_izin_hari = izin) KECUALI mode_kuota='gabungan', di mana keduanya
# memakai SATU saldo bersama (kuota_gabungan_hari) -- lihat
# _validasi_kebijakan_pengajuan() di bawah. `maksimal_bersamaan` (batas
# jumlah karyawan cuti bersamaan) TETAP HANYA berlaku utk jenis='cuti'
# (tidak diminta Owner untuk izin, cakupan sengaja tidak diperluas).
#
# Periode kuota TIDAK LAGI selalu diangkar ke Januari (tahun kalender) --
# `periode_mulai_dasar` (tanggal, Owner-editable) jadi titik angkar bebas,
# lihat _periode_kuota(). Kuota periode ("kuota_periode_bulan" > 0) HANYA
# aktif kalau `periode_mulai_dasar` juga terisi, dan HANYA berlaku untuk
# tanggal_mulai pengajuan >= periode_mulai_dasar -- tanggal SEBELUM itu
# (data lama, sebelum sistem kuota dinamis ada) TIDAK PERNAH divalidasi
# lewat mesin ini sama sekali (lihat tabel riwayat terpisah
# `izin_cuti_saldo_awal`, murni catatan/tampilan, di izin_cuti_migrasi.py).
DEFAULT_CUTI_SETTINGS = {
    "kuota_periode_bulan": 0,      # 0 = kuota TIDAK digunakan
    "kuota_maksimal_hari": 0,      # kuota CUTI (mode 'terpisah')
    "kuota_boleh_dipecah": True,
    "h_min_pengajuan": 0,          # H-min CUTI -- 0 = tidak ada minimal H- sama sekali
    "maksimal_bersamaan": 0,       # 0 = tidak dibatasi -- HANYA cuti
    "mode_kuota": "terpisah",      # 'terpisah' | 'gabungan'
    "kuota_izin_hari": 0,          # kuota IZIN (mode 'terpisah')
    "kuota_gabungan_hari": 0,      # kuota BERSAMA izin+cuti (mode 'gabungan')
    "periode_mulai_dasar": None,   # tanggal YYYY-MM-DD, angkar periode -- None = kuota periode nonaktif
    "h_min_pengajuan_izin": 0,     # H-min IZIN -- terpisah total dari h_min_pengajuan (cuti)
    "auto_libur_tidak_absen_aktif": False,  # lihat auto_libur_db.py -- default OFF
}

MODE_KUOTA_VALID = {"terpisah", "gabungan"}


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
        # uang_harian_dinamis_settings). Kolom mode_kuota/kuota_izin_hari/
        # kuota_gabungan_hari/periode_mulai_dasar/h_min_pengajuan_izin --
        # lihat izin_cuti_migrasi.py untuk instalasi LAMA (ALTER TABLE
        # idempoten); di sini cukup untuk instalasi BARU (CREATE TABLE
        # langsung menyertakan kolom lengkap).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS izin_cuti_settings (
                tenant_id              INTEGER PRIMARY KEY,
                kuota_periode_bulan    INTEGER NOT NULL DEFAULT 0,
                kuota_maksimal_hari    INTEGER NOT NULL DEFAULT 0,
                kuota_boleh_dipecah    INTEGER NOT NULL DEFAULT 1,
                h_min_pengajuan        INTEGER NOT NULL DEFAULT 0,
                maksimal_bersamaan     INTEGER NOT NULL DEFAULT 0,
                mode_kuota             TEXT NOT NULL DEFAULT 'terpisah',
                kuota_izin_hari        INTEGER NOT NULL DEFAULT 0,
                kuota_gabungan_hari    INTEGER NOT NULL DEFAULT 0,
                periode_mulai_dasar    TEXT,
                h_min_pengajuan_izin   INTEGER NOT NULL DEFAULT 0,
                auto_libur_tidak_absen_aktif INTEGER NOT NULL DEFAULT 0,
                updated_at             TEXT
            )
        """)
        # REVISI Sistem Dinamis Cuti & Izin: snapshot HISTORIS saldo cuti
        # per titik cut-off (mis. migrasi Agustus 2026) -- murni
        # catatan/tampilan, TIDAK PERNAH ikut dihitung mesin kuota dinamis
        # (lihat _validasi_kebijakan_pengajuan()). Lihat izin_cuti_migrasi.py
        # untuk seed data awal.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS izin_cuti_saldo_awal (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id       INTEGER NOT NULL,
                barber_id       INTEGER NOT NULL,
                jenis           TEXT NOT NULL DEFAULT 'cuti',
                saldo_hari      INTEGER NOT NULL,
                berlaku_sampai  TEXT NOT NULL,
                catatan         TEXT,
                created_at      TEXT NOT NULL,
                FOREIGN KEY (barber_id) REFERENCES barbers(id)
            )
        """)


# ---------------------------------------------------------------------------
# KEBIJAKAN CUTI DINAMIS (per tenant) -- lihat DEFAULT_CUTI_SETTINGS di atas
# ---------------------------------------------------------------------------

def _pastikan_baris_settings(conn, tenant_id: int):
    conn.execute(
        """INSERT INTO izin_cuti_settings (tenant_id, kuota_periode_bulan, kuota_maksimal_hari,
                                            kuota_boleh_dipecah, h_min_pengajuan, maksimal_bersamaan,
                                            mode_kuota, kuota_izin_hari, kuota_gabungan_hari,
                                            periode_mulai_dasar, h_min_pengajuan_izin,
                                            auto_libur_tidak_absen_aktif)
           VALUES (?, 0, 0, 1, 0, 0, 'terpisah', 0, 0, NULL, 0, 0) ON CONFLICT DO NOTHING""",
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
    hasil["auto_libur_tidak_absen_aktif"] = bool(hasil.get("auto_libur_tidak_absen_aktif"))
    return hasil


def set_cuti_settings(tenant_id: int, **fields) -> dict:
    """`fields` boleh sebagian saja (None = pertahankan nilai lama) -- pola
    sama seperti attendance_db.set_settings()/uang_harian_dinamis_db.set_config().
    REVISI Sistem Dinamis Cuti & Izin: `mode_kuota` menentukan kuota mana
    yang wajib diisi kalau kuota periode diaktifkan -- 'terpisah' butuh
    MINIMAL SALAH SATU dari kuota_maksimal_hari (cuti) atau kuota_izin_hari
    (izin), 'gabungan' butuh kuota_gabungan_hari. `periode_mulai_dasar`
    (tanggal angkar periode) WAJIB diisi begitu kuota periode diaktifkan --
    lihat izin_cuti_db.py modul docstring/_periode_kuota() kenapa ini
    menggantikan angkar Januari yang lama."""
    existing = get_cuti_settings(tenant_id)
    baru = dict(existing)
    for key in DEFAULT_CUTI_SETTINGS:
        if key in fields and fields[key] is not None:
            baru[key] = fields[key]

    for key in ("kuota_periode_bulan", "kuota_maksimal_hari", "h_min_pengajuan", "maksimal_bersamaan",
                "kuota_izin_hari", "kuota_gabungan_hari", "h_min_pengajuan_izin"):
        if int(baru[key]) < 0:
            raise ValueError(f"{key} tidak boleh negatif.")
    if baru["mode_kuota"] not in MODE_KUOTA_VALID:
        raise ValueError(f"mode_kuota tidak dikenal: {baru['mode_kuota']!r} (harus 'terpisah' atau 'gabungan').")

    if int(baru["kuota_periode_bulan"]) > 0:
        if not baru.get("periode_mulai_dasar"):
            raise ValueError("Tanggal Mulai Periode wajib diisi kalau Periode Kuota diaktifkan.")
        if baru["mode_kuota"] == "gabungan":
            if int(baru["kuota_gabungan_hari"]) <= 0:
                raise ValueError("Kuota Gabungan (hari) wajib diisi lebih dari 0 kalau Periode Kuota "
                                  "diaktifkan (Mode Gabungan).")
        else:
            if int(baru["kuota_maksimal_hari"]) <= 0 and int(baru["kuota_izin_hari"]) <= 0:
                raise ValueError("Minimal salah satu dari Kuota Cuti atau Kuota Izin (hari) wajib diisi "
                                  "lebih dari 0 kalau Periode Kuota diaktifkan.")

    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO izin_cuti_settings
                   (tenant_id, kuota_periode_bulan, kuota_maksimal_hari, kuota_boleh_dipecah,
                    h_min_pengajuan, maksimal_bersamaan, mode_kuota, kuota_izin_hari,
                    kuota_gabungan_hari, periode_mulai_dasar, h_min_pengajuan_izin,
                    auto_libur_tidak_absen_aktif, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (tenant_id) DO UPDATE SET
                    kuota_periode_bulan = excluded.kuota_periode_bulan,
                    kuota_maksimal_hari = excluded.kuota_maksimal_hari,
                    kuota_boleh_dipecah = excluded.kuota_boleh_dipecah,
                    h_min_pengajuan = excluded.h_min_pengajuan,
                    maksimal_bersamaan = excluded.maksimal_bersamaan,
                    mode_kuota = excluded.mode_kuota,
                    kuota_izin_hari = excluded.kuota_izin_hari,
                    kuota_gabungan_hari = excluded.kuota_gabungan_hari,
                    periode_mulai_dasar = excluded.periode_mulai_dasar,
                    h_min_pengajuan_izin = excluded.h_min_pengajuan_izin,
                    auto_libur_tidak_absen_aktif = excluded.auto_libur_tidak_absen_aktif,
                    updated_at = excluded.updated_at""",
            (tenant_id, int(baru["kuota_periode_bulan"]), int(baru["kuota_maksimal_hari"]),
             int(bool(baru["kuota_boleh_dipecah"])), int(baru["h_min_pengajuan"]), int(baru["maksimal_bersamaan"]),
             baru["mode_kuota"], int(baru["kuota_izin_hari"]), int(baru["kuota_gabungan_hari"]),
             baru["periode_mulai_dasar"], int(baru["h_min_pengajuan_izin"]),
             int(bool(baru["auto_libur_tidak_absen_aktif"])), now),
        )
    return get_cuti_settings(tenant_id)


def _hitung_durasi_hari(tanggal_mulai: str, tanggal_selesai: str) -> int:
    mulai = datetime.strptime(tanggal_mulai, "%Y-%m-%d")
    selesai = datetime.strptime(tanggal_selesai, "%Y-%m-%d")
    return (selesai - mulai).days + 1


def _periode_kuota(tanggal: str, periode_bulan: int, anchor: str) -> tuple:
    """REVISI Sistem Dinamis Cuti & Izin (permintaan Owner): bucket kuota
    DIANGKAR ke `anchor` (periode_mulai_dasar, tanggal Owner-editable lewat
    Pengaturan Izin & Cuti) -- BUKAN LAGI selalu Januari/tahun kalender
    seperti sebelumnya. HANYA komponen tahun+bulan `anchor` yang dipakai
    (tanggal presisinya diabaikan -- setiap bucket periode selalu dimulai
    tanggal 1 suatu bulan, sama seperti perilaku lama). periode_bulan=3
    dari anchor "2026-09-01" -> Sep-Nov/Des-Feb/Mar-Mei/dst, periode_bulan=12
    -> SATU periode 12 bulan penuh dari bulan anchor, sesuai KEDUA contoh
    spesifikasi Owner ("kuota 10 hari setiap 3 bulan", "kuota tahunan").
    Return (tanggal_awal_periode, tanggal_akhir_periode) string YYYY-MM-DD,
    MENCAKUP tanggal yang diberikan -- termasuk tanggal SEBELUM anchor
    (index periode negatif, floor division Python sudah benar untuk itu).
    Periode ditentukan HANYA dari `tanggal_mulai` pengajuan -- cuti/izin
    yang melintasi batas periode (mis. akhir periode ke awal periode
    berikutnya) disederhanakan dianggap SELURUHNYA masuk periode
    tanggal_mulai-nya (TIDAK BERUBAH dari perilaku lama)."""
    dt = datetime.strptime(tanggal, "%Y-%m-%d")
    anchor_dt = datetime.strptime(anchor, "%Y-%m-%d")
    bulan_sejak_anchor = (dt.year - anchor_dt.year) * 12 + (dt.month - anchor_dt.month)
    indeks_periode = bulan_sejak_anchor // periode_bulan  # floor division -- benar juga untuk negatif
    total_bulan_awal = (anchor_dt.year * 12 + (anchor_dt.month - 1)) + indeks_periode * periode_bulan
    tahun_awal, bulan_awal0 = divmod(total_bulan_awal, 12)
    awal = datetime(tahun_awal, bulan_awal0 + 1, 1)
    total_bulan_akhir_eksklusif = total_bulan_awal + periode_bulan
    tahun_akhir, bulan_akhir0 = divmod(total_bulan_akhir_eksklusif, 12)
    akhir_eksklusif = datetime(tahun_akhir, bulan_akhir0 + 1, 1)
    akhir = akhir_eksklusif - timedelta(days=1)
    return awal.strftime("%Y-%m-%d"), akhir.strftime("%Y-%m-%d")


def _kuota_terpakai_hari(barber_id: int, periode_awal: str, periode_akhir: str,
                          jenis_filter: str = None, kecuali_pengajuan_id: int = None) -> int:
    """Jumlah hari (status pending ATAU disetujui -- LEWATI 'ditolak' dan
    pengajuan yang sudah dihapus, sesuai permintaan Owner) milik barber ini
    yang tanggal_mulai-nya jatuh di periode ini. `jenis_filter`: 'izin'
    atau 'cuti' (mode kuota 'terpisah', hanya jenis itu yang dihitung),
    atau None (mode 'gabungan' -- izin+cuti dijumlahkan bersama ke SATU
    saldo, permintaan Owner eksplisit)."""
    q = ("SELECT tanggal_mulai, tanggal_selesai FROM izin_cuti "
         "WHERE barber_id = ? AND status IN ('pending', 'disetujui') "
         "AND tanggal_mulai >= ? AND tanggal_mulai <= ?")
    params = [barber_id, periode_awal, periode_akhir]
    if jenis_filter is not None:
        q += " AND jenis = ?"; params.append(jenis_filter)
    else:
        q += " AND jenis IN ('izin', 'cuti')"
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


def _kuota_field_untuk(jenis: str, mode_kuota: str) -> tuple:
    """Return (nama_field_kuota_di_settings, jenis_filter_untuk_hitung_terpakai,
    label_untuk_pesan_error). mode 'gabungan': izin & cuti berbagi SATU
    saldo (kuota_gabungan_hari, jenis_filter=None = keduanya dijumlahkan).
    mode 'terpisah' (default): masing-masing jenis punya saldo sendiri."""
    if mode_kuota == "gabungan":
        return "kuota_gabungan_hari", None, "izin & cuti (gabungan)"
    if jenis == "cuti":
        return "kuota_maksimal_hari", "cuti", "cuti"
    return "kuota_izin_hari", "izin", "izin"


def _validasi_kebijakan_pengajuan(barber_id: int, tenant_id: int, jenis: str, tanggal_mulai: str,
                                   tanggal_selesai: str, kecuali_pengajuan_id: int = None) -> None:
    """Raise ValueError (pesan siap tampil) kalau melanggar kebijakan --
    HANYA dipanggil kalau pemanggil BUKAN Owner/Admin/Staff (lihat param
    `override` di buat_pengajuan()/edit_pengajuan() di bawah -- Owner/
    Admin/Staff SELALU boleh melewati kebijakan ini).

    REVISI Sistem Dinamis Cuti & Izin (permintaan Owner): dulu fungsi ini
    HANYA berlaku jenis='cuti' (izin 100% terkecuali) -- sekarang izin
    JUGA divalidasi, tapi lewat field pengaturan SENDIRI yang terpisah
    total dari cuti (h_min_pengajuan_izin/kuota_izin_hari, BUKAN
    h_min_pengajuan/kuota_maksimal_hari milik cuti) -- default-nya tetap
    0/off, jadi tenant yang belum pernah mengatur apa pun TIDAK
    terpengaruh (izin tetap bisa diajukan kapan saja seperti sebelumnya).
    `maksimal_bersamaan` TETAP HANYA berlaku cuti (tidak diperluas ke
    izin -- tidak diminta Owner)."""
    if tenant_id is None:
        return
    settings = get_cuti_settings(tenant_id)

    h_min_key = "h_min_pengajuan" if jenis == "cuti" else "h_min_pengajuan_izin"
    h_min = settings[h_min_key]
    if h_min > 0:
        selisih_hari = (datetime.strptime(tanggal_mulai, "%Y-%m-%d").date()
                         - datetime.strptime(_hari_ini_wib(), "%Y-%m-%d").date()).days
        if selisih_hari < h_min:
            label_jenis = _JENIS_LABEL.get(jenis, jenis).lower()
            raise ValueError(
                f"Pengajuan {label_jenis} harus dilakukan minimal H-{h_min} sebelum tanggal {label_jenis}."
            )

    if jenis == "cuti" and settings["maksimal_bersamaan"] > 0:
        jumlah = _jumlah_bersamaan_maksimal(tenant_id, tanggal_mulai, tanggal_selesai,
                                             kecuali_barber_id=barber_id,
                                             kecuali_pengajuan_id=kecuali_pengajuan_id)
        if jumlah + 1 > settings["maksimal_bersamaan"]:
            raise ValueError(
                f"Sudah ada {jumlah} karyawan lain yang cuti pada salah satu tanggal di rentang ini "
                f"(maksimal {settings['maksimal_bersamaan']} orang bersamaan)."
            )

    # REVISI Sistem Dinamis: kuota periode HANYA berlaku untuk tanggal_mulai
    # >= periode_mulai_dasar -- tanggal SEBELUM itu (data lama, sebelum
    # sistem kuota dinamis diaktifkan) tidak pernah divalidasi lewat mesin
    # ini (lihat izin_cuti_saldo_awal, tabel riwayat/catatan terpisah).
    if (settings["kuota_periode_bulan"] > 0 and settings["periode_mulai_dasar"]
            and tanggal_mulai >= settings["periode_mulai_dasar"]):
        kuota_field, jenis_filter, label = _kuota_field_untuk(jenis, settings["mode_kuota"])
        kuota = settings[kuota_field]
        if kuota > 0:
            periode_awal, periode_akhir = _periode_kuota(tanggal_mulai, settings["kuota_periode_bulan"],
                                                           settings["periode_mulai_dasar"])
            terpakai = _kuota_terpakai_hari(barber_id, periode_awal, periode_akhir, jenis_filter,
                                             kecuali_pengajuan_id=kecuali_pengajuan_id)
            if not settings["kuota_boleh_dipecah"] and terpakai > 0:
                raise ValueError(
                    f"Kuota {label} periode ini tidak boleh dipecah, dan sudah ada pengajuan lain "
                    f"di periode yang sama."
                )
            durasi_baru = _hitung_durasi_hari(tanggal_mulai, tanggal_selesai)
            if terpakai + durasi_baru > kuota:
                sisa = max(0, kuota - terpakai)
                raise ValueError(
                    f"Kuota {label} periode ini ({periode_awal} s/d {periode_akhir}) tersisa {sisa} hari, "
                    f"pengajuan ini {durasi_baru} hari."
                )


def get_saldo_awal(tenant_id: int, barber_id: int = None) -> list:
    """REVISI Sistem Dinamis Cuti & Izin: baca snapshot HISTORIS saldo cuti
    (mis. migrasi Agustus 2026, lihat izin_cuti_migrasi.py) -- MURNI
    catatan/tampilan, TIDAK ikut dihitung _validasi_kebijakan_pengajuan()
    sama sekali (lihat catatan `periode_mulai_dasar` di sana)."""
    q = "SELECT * FROM izin_cuti_saldo_awal WHERE tenant_id = ?"
    params = [tenant_id]
    if barber_id is not None:
        q += " AND barber_id = ?"; params.append(barber_id)
    q += " ORDER BY berlaku_sampai DESC, id ASC"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    for r in rows:
        barber = get_barber(r["barber_id"])
        r["nama_barber"] = barber["nama"] if barber else "(barber terhapus)"
    return rows


def get_sisa_kuota(barber_id: int, tenant_id: int) -> dict:
    """REVISI Sistem Dinamis Cuti & Izin: hitung sisa kuota SAAT INI
    (periode aktif yang mencakup hari ini) untuk ditampilkan ke barber/
    Owner -- TIDAK PERNAH menyimpan angka saldo yang bisa "basi"/tidak
    sinkron (dihitung ULANG live dari riwayat pengajuan tiap dipanggil,
    pola sama seperti _validasi_kebijakan_pengajuan()). Kalau kuota
    periode belum diaktifkan (kuota_periode_bulan=0 atau
    periode_mulai_dasar kosong) ATAU hari ini masih sebelum
    periode_mulai_dasar, `aktif`=False dan seluruh field sisa/kuota None
    (lihat get_saldo_awal() untuk catatan historis sebelum periode aktif)."""
    settings = get_cuti_settings(tenant_id)
    hari_ini = _hari_ini_wib()
    hasil = {
        "aktif": False, "mode_kuota": settings["mode_kuota"],
        "periode_awal": None, "periode_akhir": None,
        "sisa_izin": None, "kuota_izin": None,
        "sisa_cuti": None, "kuota_cuti": None,
        "sisa_gabungan": None, "kuota_gabungan": None,
    }
    if not (settings["kuota_periode_bulan"] > 0 and settings["periode_mulai_dasar"]
            and hari_ini >= settings["periode_mulai_dasar"]):
        return hasil
    periode_awal, periode_akhir = _periode_kuota(hari_ini, settings["kuota_periode_bulan"],
                                                  settings["periode_mulai_dasar"])
    hasil["aktif"] = True
    hasil["periode_awal"] = periode_awal
    hasil["periode_akhir"] = periode_akhir
    if settings["mode_kuota"] == "gabungan":
        kuota = settings["kuota_gabungan_hari"]
        if kuota > 0:
            terpakai = _kuota_terpakai_hari(barber_id, periode_awal, periode_akhir, None)
            hasil["kuota_gabungan"] = kuota
            hasil["sisa_gabungan"] = max(0, kuota - terpakai)
    else:
        if settings["kuota_izin_hari"] > 0:
            terpakai_izin = _kuota_terpakai_hari(barber_id, periode_awal, periode_akhir, "izin")
            hasil["kuota_izin"] = settings["kuota_izin_hari"]
            hasil["sisa_izin"] = max(0, settings["kuota_izin_hari"] - terpakai_izin)
        if settings["kuota_maksimal_hari"] > 0:
            terpakai_cuti = _kuota_terpakai_hari(barber_id, periode_awal, periode_akhir, "cuti")
            hasil["kuota_cuti"] = settings["kuota_maksimal_hari"]
            hasil["sisa_cuti"] = max(0, settings["kuota_maksimal_hari"] - terpakai_cuti)
    return hasil


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


def get_info_cuti_marquee(tenant_id: int) -> list:
    """FITUR Running Text Info Cuti (Absensi Barber, lihat absensi.js::
    renderCutiMarquee()) -- fungsi BACA baru, TIDAK mengubah query/logika
    apa pun di atas. Hanya jenis='cuti' (izin ad-hoc tidak relevan untuk
    pengumuman terjadwal ini), field MINIMAL (nama_barber/status/tanggal
    SAJA -- TIDAK menyertakan alasan/catatan_approval, privasi antar-barber
    tidak semestinya bocor lewat running text tenant-wide).

    Dua kelompok, ditentukan dari status & tanggal_mulai relatif hari ini:
      - 'sedang_cuti': status='disetujui' DAN hari ini ada di dalam rentang
        tanggal_mulai..tanggal_selesai.
      - 'pengajuan': belum dimulai (tanggal_mulai > hari ini), status
        'pending' ATAU 'disetujui' -- cuti yang sudah disetujui tapi
        belum mulai TETAP relevan diinformasikan ke barber lain, bukan
        cuma yang masih menunggu keputusan.
    'ditolak' TIDAK PERNAH ikut. Pengajuan 'pending' yang tanggal_mulai-nya
    sudah lewat (belum diputuskan padahal harusnya sudah mulai) SENGAJA
    dilewati -- tidak cocok masuk kategori manapun (bukan 'sedang cuti'
    karena belum disetujui, bukan 'pengajuan belum mulai' karena tanggalnya
    sudah lewat)."""
    hari_ini = _hari_ini_wib()
    q = ("SELECT i.tanggal_mulai, i.tanggal_selesai, i.status, b.nama AS nama_barber "
         "FROM izin_cuti i JOIN barbers b ON b.id = i.barber_id "
         "WHERE b.tenant_id = ? AND i.jenis = 'cuti' AND i.status != 'ditolak' AND i.tanggal_selesai >= ? "
         "ORDER BY i.tanggal_mulai ASC")
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(q, (tenant_id, hari_ini)).fetchall()]
    hasil = []
    for r in rows:
        if r["status"] == "disetujui" and r["tanggal_mulai"] <= hari_ini <= r["tanggal_selesai"]:
            info_status = "sedang_cuti"
        elif r["tanggal_mulai"] > hari_ini:
            info_status = "pengajuan"
        else:
            continue
        hasil.append({
            "nama_barber": r["nama_barber"], "status": info_status,
            "tanggal_mulai": r["tanggal_mulai"], "tanggal_selesai": r["tanggal_selesai"],
        })
    return hasil


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
        _validasi_kebijakan_pengajuan(barber_id, tenant_id if tenant_id is not None else barber["tenant_id"],
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
        _validasi_kebijakan_pengajuan(existing["barber_id"], existing.get("tenant_id"), jenis_baru,
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
