"""rekap_gabungan_db.py — Gabungan POS + Booking (Online & Mandiri) -> SATU baris Rekap
=============================================================================
PERMINTAAN OWNER: barber yang di hari yang sama dilayani lewat POS (walk-in
kasir) DAN Booking (Online maupun Mandiri -- keduanya sama-sama tabel
`bookings`, dibedakan `bookings.sumber` ('publik'/'kasir_mandiri'), TIDAK
pernah difilter di sini) sebelumnya menghasilkan 2 baris `transaksi`
terpisah di Rekap (sumber='pos' + sumber='booking', masing-masing dibangun
ulang sendiri-sendiri oleh pos_db.py/booking_db.py). Sekarang digabung jadi
SATU baris, sumber=SUMBER_POS_BOOKING, supaya Rekap tidak terlihat "pecah"
untuk satu barber di satu hari yang sama.

Modul TERPISAH (bukan ditaruh di pos_db.py atau booking_db.py) supaya tidak
ada impor siklik -- kedua modul itu akan sama-sama mengimpor modul ini,
sementara modul ini sendiri HANYA mengimpor database.py.

rebuild_transaksi_pos_booking_barber_hari() dipanggil dari KEDUA pos_db.py
(gantikan bekas _rebuild_transaksi_barber_hari()) dan booking_db.py
(gantikan bekas _rebuild_transaksi_booking_barber_hari()) -- SETIAP kali
salah satu sisi berubah (POS lunas/batal/hapus, booking verifikasi/batal/
hapus/reschedule), baris gabungan ini di-build ULANG dari SCRATCH dengan
membaca KEDUA sumber sekaligus (bukan cuma sisi yang baru berubah) --
supaya kontribusi sisi lain yang TIDAK berubah tetap ikut, tidak tertimpa
hilang. Idempotent & murah, aman dipanggil berkali-kali.

Manual Customer (sumber='manual_customer') SENGAJA TIDAK ikut digabung di
sini -- di luar permintaan Owner, tetap baris sendiri seperti sekarang.

`catatan` TIDAK pernah diisi di sini (baik rebuild POS maupun Booking yang
lama juga tidak pernah mengisi field ini)."""

import logging

import locks_db
from database import get_conn, hapus_transaksi, tambah_transaksi

logger = logging.getLogger(__name__)

SUMBER_POS_BOOKING = "pos_booking"

# BUGFIX UANG (audit "susuri menyeluruh" -- pola sama persis
# kasbon_db.py::_kunci_per_kasbon / slip_gaji_db.py::_kunci_per_slip):
# rebuild_transaksi_pos_booking_barber_hari() membaca kontribusi POS+
# Booking, HAPUS baris lama, lalu INSERT baris baru -- rangkaian baca-
# hapus-tulis itu TIDAK atomik dan SEBELUMNYA tidak dikunci sama sekali.
# Dua pemicu rebuild untuk barber+tanggal YANG SAMA nyaris bersamaan (mis.
# webhook PAID booking A datang tepat saat Kasir klik "Verifikasi" booking
# B, atau POS lunas, untuk barber & tanggal yang sama) bisa SAMA-SAMA
# membaca kontribusi SEBELUM salah satu sempat menghapus baris lama,
# sehingga KEDUANYA memanggil tambah_transaksi() dan omzet/komisi hari itu
# tercatat DOBEL. Lock per (barber_id, tanggal) menyerialkan seluruh
# rangkaian baca-hapus-tulis untuk kombinasi itu -- lewat factory bersama
# locks_db.py (code-review audit babak 2, catatan minor #2: sebelumnya
# modul ini dan kuota_libur_db.py masing-masing bikin defaultdict sendiri
# dengan pola identik; ditarik ke satu factory supaya perubahan strategi
# locking ke depan cukup di satu tempat).
_kunci_rekap = locks_db.buat_pengambil_kunci()


def _ambil_kontribusi_pos(tenant_id: int, barber_id: int, tanggal: str):
    """SAMA PERSIS query yang dulu ada di pos_db.py::
    _rebuild_transaksi_barber_hari() -- qty service dari SELURUH transaksi
    POS lunas hari itu (lintas customer), tips dijumlahkan lintas customer."""
    with get_conn() as conn:
        service_rows = [dict(r) for r in conn.execute(
            "SELECT pts.service_id FROM pos_transaksi_service pts "
            "JOIN pos_transaksi pt ON pt.id = pts.pos_transaksi_id "
            "WHERE pt.tenant_id = ? AND pt.tanggal = ? AND pt.status = 'lunas' AND pts.barber_id = ?",
            (tenant_id, tanggal, barber_id),
        ).fetchall()]
        total_tips = conn.execute(
            "SELECT COALESCE(SUM(ptbt.tips), 0) AS total FROM pos_transaksi_barber_tips ptbt "
            "JOIN pos_transaksi pt ON pt.id = ptbt.pos_transaksi_id "
            "WHERE pt.tenant_id = ? AND pt.tanggal = ? AND pt.status = 'lunas' AND ptbt.barber_id = ?",
            (tenant_id, tanggal, barber_id),
        ).fetchone()["total"]

    agregat = {}
    for r in service_rows:
        agregat[r["service_id"]] = agregat.get(r["service_id"], 0) + 1
    return agregat, total_tips


def _ambil_kontribusi_booking(tenant_id: int, barber_id: int, tanggal: str):
    """SAMA PERSIS query yang dulu ada di booking_db.py::
    _rebuild_transaksi_booking_barber_hari() -- qty service dari SELURUH
    booking terverifikasi+aktif hari itu (Online maupun Mandiri, tidak
    dibedakan). Booking tidak punya konsep tips."""
    with get_conn() as conn:
        service_rows = [dict(r) for r in conn.execute(
            "SELECT bi.service_id FROM booking_items bi "
            "JOIN bookings bk ON bk.id = bi.booking_id "
            "WHERE bk.tenant_id = ? AND bk.tanggal = ? AND bk.barber_id = ? "
            "AND bk.status_pembayaran = 'terverifikasi' AND bk.status_booking = 'aktif'",
            (tenant_id, tanggal, barber_id),
        ).fetchall()]

    agregat = {}
    for r in service_rows:
        agregat[r["service_id"]] = agregat.get(r["service_id"], 0) + 1
    return agregat


def rebuild_transaksi_pos_booking_barber_hari(tenant_id: int, barber_id: int, tanggal: str) -> None:
    """Hapus baris `transaksi` lama (kalau ada) sumber=SUMBER_POS_BOOKING
    untuk barber+tanggal ini, lalu bangun ULANG dari gabungan kontribusi
    POS + Booking hari itu (qty per service_id dijumlahkan lintas KEDUA
    sumber, tips HANYA dari POS). SELURUH rangkaian ini dikunci per
    (barber_id, tanggal) lewat _kunci_rekap() -- lihat komentar di
    _kunci_per_barber_tanggal di atas."""
    with _kunci_rekap(barber_id, tanggal):
        _rebuild_terkunci(tenant_id, barber_id, tanggal)


def _rebuild_terkunci(tenant_id: int, barber_id: int, tanggal: str) -> None:
    agregat_pos, tips = _ambil_kontribusi_pos(tenant_id, barber_id, tanggal)
    agregat_booking = _ambil_kontribusi_booking(tenant_id, barber_id, tanggal)

    agregat = dict(agregat_pos)
    for sid, qty in agregat_booking.items():
        agregat[sid] = agregat.get(sid, 0) + qty

    # BUGFIX (ditemukan audit "susuri keuangan Rekap POS"): database.py::
    # hapus_service() HANYA mengecek service_sudah_dipakai() lewat
    # transaksi_detail (histori yang SUDAH jadi) -- booking_items/
    # pos_transaksi_service (booking belum terverifikasi / POS belum
    # lunas) TIDAK ikut dicek, jadi service yang dipakai booking/POS yang
    # MASIH PENDING bisa terlanjur dihapus permanen Owner. Kalau ini
    # dibiarkan lolos ke tambah_transaksi() apa adanya, SATU service_id
    # yang hilang membuat SELURUH baris gabungan gagal dibuat (ValueError
    # di satu item membatalkan seluruh INSERT) -- SEBELUM penggabungan
    # POS+Booking, ini cuma menghapuskan kontribusi SATU sumber (baris
    # sumber lain tetap aman); SEKARANG baris gabungan berarti kegagalan
    # ini menghapuskan POS *dan* Booking SEKALIGUS dari Rekap hari itu.
    # Diperbaiki dengan memvalidasi service_id yang MASIH ADA lebih dulu,
    # membuang (+ log) HANYA item yang sudah terhapus, bukan menjatuhkan
    # seluruh baris.
    if agregat:
        with get_conn() as conn:
            placeholder = ", ".join("?" for _ in agregat)
            id_valid = {r["id"] for r in conn.execute(
                f"SELECT id FROM services WHERE id IN ({placeholder})", list(agregat.keys()),
            ).fetchall()}
        for sid in list(agregat.keys()):
            if sid not in id_valid:
                logger.error(
                    "Service id=%s (dipakai POS/Booking barber_id=%s, tanggal=%s) sudah dihapus "
                    "permanen -- item ini DILEWATI, kontribusi sumber lain tetap tersimpan.",
                    sid, barber_id, tanggal,
                )
                del agregat[sid]

    with get_conn() as conn:
        lama_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM transaksi WHERE barber_id = ? AND tanggal = ? AND sumber = ?",
            (barber_id, tanggal, SUMBER_POS_BOOKING),
        ).fetchall()]
    for tid in lama_ids:
        hapus_transaksi(tid)

    if not agregat:
        return

    items = [{"service_id": sid, "jumlah": qty} for sid, qty in agregat.items()]
    tambah_transaksi(tanggal=tanggal, barber_id=barber_id, items=items, tips=tips, sumber=SUMBER_POS_BOOKING)
