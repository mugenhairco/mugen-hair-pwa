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

from database import get_conn, hapus_transaksi, tambah_transaksi

logger = logging.getLogger(__name__)

SUMBER_POS_BOOKING = "pos_booking"


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
    sumber, tips HANYA dari POS)."""
    agregat_pos, tips = _ambil_kontribusi_pos(tenant_id, barber_id, tanggal)
    agregat_booking = _ambil_kontribusi_booking(tenant_id, barber_id, tanggal)

    agregat = dict(agregat_pos)
    for sid, qty in agregat_booking.items():
        agregat[sid] = agregat.get(sid, 0) + qty

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
    try:
        tambah_transaksi(tanggal=tanggal, barber_id=barber_id, items=items, tips=tips, sumber=SUMBER_POS_BOOKING)
    except ValueError:
        # Service yang dipakai POS/booking ini sudah dihapus permanen Owner
        # SEBELUM sempat lunas/terverifikasi -- dicatat ke log server supaya
        # bisa ditelusuri, TIDAK dilempar ke pemanggil (pembayaran/verifikasi
        # TIDAK BOLEH gagal gara-gara ini).
        logger.error(
            "Gagal sinkronkan POS/Booking ke Rekap (barber_id=%s, tanggal=%s) -- "
            "kemungkinan service sudah dihapus permanen.", barber_id, tanggal, exc_info=True,
        )
