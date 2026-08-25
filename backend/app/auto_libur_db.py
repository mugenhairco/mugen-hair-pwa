"""
auto_libur_db.py — Auto-Libur untuk Barber yang Tidak Absen
=============================================================================
PERMINTAAN OWNER: "jika role barber tidak absen maka otomatis direkap
dibuat libur (dan mengurangi kuota libur) dalam sebulan" -- HANYA aktif
kalau Owner mengaktifkan `auto_libur_tidak_absen_aktif` di Pengaturan
Izin & Cuti (izin_cuti_settings, default OFF -- tenant yang belum
mengaktifkannya TIDAK terpengaruh sama sekali).

Menjembatani DUA modul yang SENGAJA berdiri sendiri satu sama lain
(attendance_db.py dan izin_cuti_db.py, lihat docstring masing-masing) --
sengaja ditulis di file TERPISAH (bukan menambah logika ini ke salah satu
modul itu) supaya independensi keduanya untuk pemakaian lain tetap utuh.

TIDAK ADA infrastruktur scheduler/cron di proyek ini sama sekali (lihat
catatan panjang di faspay_settlement_db.py) -- mengikuti pola yang sama
persis: diproses lewat PEMICU MANUAL Owner/Admin (tombol "Proses Auto-
Libur" di Pengaturan Izin & Cuti), bukan job otomatis di background.

Definisi "hari kerja yang diharapkan" untuk seorang barber pada satu
tanggal (SEMUA syarat harus terpenuhi baru dianggap "seharusnya masuk"):
  1. Toko TIDAK toko_libur pada tanggal itu (booking_db.is_toko_libur).
  2. Tanggal itu termasuk hari_operasional toko (booking_db.is_hari_operasional).
  3. Barber itu TIDAK absensi_libur pada tanggal itu (Barber Holiday,
     booking_db.is_barber_libur).
  4. Barber itu TIDAK punya pengajuan izin_cuti (status pending/disetujui,
     jenis izin ATAU cuti) yang mencakup tanggal itu -- sudah ada alasan
     resmi, tidak perlu direkap ulang jadi auto-libur.
  5. Tanggal itu SUDAH LEWAT (< hari ini, WIB) -- TIDAK PERNAH memproses
     hari ini/masa depan, barber masih punya kesempatan check-in.

Kalau KELIMA syarat di atas terpenuhi DAN barber itu SAMA SEKALI tidak
punya baris attendance_logs untuk tanggal itu (benar-benar tidak pernah
check-in -- BUKAN sekadar lupa check-out/terlambat, itu urusan Absensi
sendiri, tidak disentuh di sini) -> dibuatkan SATU baris izin_cuti
otomatis (jenis='cuti', status='disetujui' LANGSUNG -- bukan 'pending',
karena ini catatan sistem atas kejadian yang SUDAH terjadi, bukan
permintaan yang perlu diputuskan Owner) yang otomatis ikut dihitung kuota
cuti lewat izin_cuti_db._kuota_terpakai_hari() yang SUDAH ADA -- TIDAK
PERLU logika kuota baru sama sekali di izin_cuti_db.py.

Ditulis LANGSUNG lewat SQL (bukan izin_cuti_db.buat_pengajuan()) supaya
TIDAK memicu notifikasi push per-hari (satu bulan penuh tidak masuk bisa
sampai ~20+ notifikasi berturut-turut ke barber & Owner/Admin -- spam,
bukan informasi berguna) -- ringkasan hasil proses dikembalikan sebagai
response API biasa, cukup dilihat sekali di UI Owner.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import booking_db
import database as db
import izin_cuti_db
from database import get_conn

logger = logging.getLogger("mugen.auto_libur")

WIB = ZoneInfo("Asia/Jakarta")

DIAJUKAN_OLEH_AUTO_LIBUR = "Sistem (Auto-Libur)"


def _hari_ini_wib() -> str:
    return datetime.now(WIB).strftime("%Y-%m-%d")


def _tanggal_list_bulan(tahun: int, bulan: int) -> list:
    """Seluruh tanggal (YYYY-MM-DD) di bulan itu yang SUDAH LEWAT (< hari
    ini) -- bulan berjalan otomatis berhenti di kemarin, bulan yang sudah
    lewat penuh mencakup semua tanggal, bulan yang belum mulai/masih
    depan menghasilkan list kosong."""
    hari_ini = _hari_ini_wib()
    awal = datetime(tahun, bulan, 1)
    bulan_berikutnya = datetime(tahun + 1, 1, 1) if bulan == 12 else datetime(tahun, bulan + 1, 1)
    akhir_eksklusif = bulan_berikutnya
    hasil = []
    d = awal
    while d < akhir_eksklusif:
        tgl = d.strftime("%Y-%m-%d")
        if tgl < hari_ini:
            hasil.append(tgl)
        d += timedelta(days=1)
    return hasil


def _sudah_ada_izin_cuti(conn, barber_id: int, tanggal: str) -> bool:
    """Barber sudah punya pengajuan izin_cuti (jenis apa pun, status
    pending/disetujui) yang mencakup tanggal ini -- sudah ada alasan
    resmi, JANGAN direkap ulang jadi auto-libur."""
    row = conn.execute(
        "SELECT 1 FROM izin_cuti WHERE barber_id = ? AND status IN ('pending', 'disetujui') "
        "AND tanggal_mulai <= ? AND tanggal_selesai >= ? LIMIT 1",
        (barber_id, tanggal, tanggal),
    ).fetchone()
    return row is not None


def _sudah_ada_attendance_log(conn, barber_id: int, tanggal: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM attendance_logs WHERE barber_id = ? AND tanggal = ? LIMIT 1",
        (barber_id, tanggal),
    ).fetchone()
    return row is not None


def _sudah_pernah_auto_libur(conn, barber_id: int, tanggal: str) -> bool:
    """Idempotensi -- kalau proses ini dijalankan ulang untuk bulan yang
    sama, TIDAK PERNAH membuat baris duplikat untuk kombinasi barber+
    tanggal yang sudah pernah diproses."""
    row = conn.execute(
        "SELECT 1 FROM izin_cuti WHERE barber_id = ? AND tanggal_mulai = ? AND tanggal_selesai = ? "
        "AND diajukan_oleh = ? LIMIT 1",
        (barber_id, tanggal, tanggal, DIAJUKAN_OLEH_AUTO_LIBUR),
    ).fetchone()
    return row is not None


def proses_auto_libur(tenant_id: int, tahun: int, bulan: int) -> dict:
    """Return {"jumlah_dibuat": int, "detail": [{"barber_id","nama_barber","tanggal":[...]}]}.
    Raise ValueError kalau Owner belum mengaktifkan auto_libur_tidak_absen_aktif."""
    settings = izin_cuti_db.get_cuti_settings(tenant_id)
    if not settings.get("auto_libur_tidak_absen_aktif"):
        raise ValueError("Auto-Libur belum diaktifkan. Aktifkan dulu lewat Pengaturan Izin & Cuti.")

    tanggal_list = _tanggal_list_bulan(tahun, bulan)
    barbers = db.get_barbers(hanya_aktif=True, tenant_id=tenant_id)
    now = datetime.now().isoformat(timespec="seconds")

    jumlah_dibuat = 0
    detail_per_barber = {}
    with get_conn() as conn:
        for barber in barbers:
            barber_id = barber["id"]
            for tanggal in tanggal_list:
                if booking_db.is_toko_libur(tanggal, tenant_id=tenant_id):
                    continue
                if not booking_db.is_hari_operasional(tanggal, tenant_id=tenant_id):
                    continue
                if booking_db.is_barber_libur(barber_id, tanggal):
                    continue
                if _sudah_ada_izin_cuti(conn, barber_id, tanggal):
                    continue
                if _sudah_ada_attendance_log(conn, barber_id, tanggal):
                    continue
                if _sudah_pernah_auto_libur(conn, barber_id, tanggal):
                    continue

                conn.execute(
                    """INSERT INTO izin_cuti (barber_id, jenis, tanggal_mulai, tanggal_selesai, alasan,
                                               status, diajukan_oleh, disetujui_oleh, tanggal_approval,
                                               created_at, updated_at)
                       VALUES (?, 'cuti', ?, ?, ?, 'disetujui', ?, ?, ?, ?, ?)""",
                    (barber_id, tanggal, tanggal,
                     "Tidak melakukan absen check-in pada tanggal ini (dicatat otomatis oleh sistem).",
                     DIAJUKAN_OLEH_AUTO_LIBUR, DIAJUKAN_OLEH_AUTO_LIBUR, tanggal[:10], now, now),
                )
                jumlah_dibuat += 1
                detail_per_barber.setdefault(barber_id, {"barber_id": barber_id, "nama_barber": barber["nama"],
                                                           "tanggal": []})
                detail_per_barber[barber_id]["tanggal"].append(tanggal)

    logger.info("Auto-Libur diproses: tenant_id=%s periode=%s-%s, %d baris dibuat.",
                tenant_id, tahun, bulan, jumlah_dibuat)
    return {"jumlah_dibuat": jumlah_dibuat, "detail": list(detail_per_barber.values())}
