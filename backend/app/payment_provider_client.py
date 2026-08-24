"""payment_provider_client.py — Seam Payment Gateway DINAMIS (bukan Faspay
selamanya)
=============================================================================
SATU-SATUNYA modul yang boleh dipanggil routers/booking.py & routers/billing.py
untuk membuat transaksi checkout gateway (VA/QRIS/Direct Debit) -- dispatcher
TIPIS, BUKAN kerangka plugin. Segala hal yang spesifik Faspay (RSA signing,
nama field SNAP, kode status, isi provider_response) TETAP tinggal 100% di
dalam snap_advance_client.py/snap_webhook.py -- modul ini SENGAJA hanya
mengenal bentuk generik yang sudah dimiliki snap_payment_db.py (channel,
va_number, qr_url, qr_content, status), BUKAN bentuk mentah wire Faspay.

Kalau provider berganti di masa depan: buat `*_client.py` baru + tulis ulang
modul ini supaya dispatch ke situ -- routers/booking.py & routers/billing.py
TIDAK PERLU disentuh sama sekali. Rekonsiliasi manual ("Cek Ulang ke
Provider") SENGAJA TIDAK lewat seam ini (tetap manggil snap_webhook.py
langsung, sama seperti pola booking_gateway_webhook.py) -- rekonsiliasi pada
dasarnya butuh pengetahuan detail kode status provider yang tidak berguna
digeneralisasi selama baru ada SATU provider sungguhan (YAGNI)."""

import snap_advance_client
import snap_advance_db

PROVIDER_ID = "snap_advance"


def is_enabled() -> bool:
    return snap_advance_client.is_enabled()


def is_production() -> bool:
    return snap_advance_client.is_production()


def channel_aktif() -> list:
    """Daftar channel ("va"/"qris"/...) yang SUDAH dicentang aktif Super
    Admin -- lihat snap_advance_db.py::_KUNCI_CHANNEL_AKTIF. Direct Debit
    TIDAK PERNAH muncul di sini (belum selectable Super Admin, lihat
    snap_advance_db.py), jadi otomatis tidak pernah ditawarkan ke customer."""
    return snap_advance_db.get_config()["snap_channel_aktif"]


def channel_label(channel: str) -> str | None:
    """Label tampilan untuk customer -- None kalau channel belum dikonfigurasi
    Super Admin sama sekali. VA TIDAK PUNYA satu label tunggal lagi (fitur
    multi-bank -- lihat va_bank_aktif() di bawah untuk daftar bank aktif)."""
    cfg = snap_advance_db.get_config()
    if channel == "qris":
        return snap_advance_db.QRIS_CHANNEL_CODE_LABEL.get(cfg["snap_qris_channel_code"])
    return None


def va_bank_aktif() -> dict:
    """Daftar bank VA yang Super Admin centang aktif -- {channelCode: label}
    (mis. {"702": "BCA VA (Dynamic)"}), dipakai frontend menampilkan pilihan
    bank ke customer DAN backend (routers/booking.py & routers/billing.py)
    memvalidasi bank_code yang dikirim customer benar-benar salah satu yang
    aktif. Difilter ke VA_CHANNEL_CODE_LABEL supaya kode basi/tidak dikenal
    (kalau ada) tidak ikut tampil."""
    cfg = snap_advance_db.get_config()
    return {kode: snap_advance_db.VA_CHANNEL_CODE_LABEL[kode]
            for kode in cfg["snap_va_bank_aktif"] if kode in snap_advance_db.VA_CHANNEL_CODE_LABEL}


def buat_transaksi(channel: str, payment_reference: str, amount: int, customer_details: dict,
                    channel_code: str | None = None) -> dict:
    """Dispatch MURNI berdasarkan channel -- mengembalikan bentuk generik
    {va_number, qr_content, qr_url, provider_transaction_id, expired_at,
    provider_response} (subset field terisi tergantung channel), SUDAH
    dalam bentuk yang siap dioper langsung ke
    snap_payment_db.catat_hasil_create_transaction(). `channel_code` WAJIB
    diisi kalau channel="va" (bank yang dipilih customer, fitur multi-bank
    VA) -- pemanggil (routers/booking.py & routers/billing.py) WAJIB
    memvalidasi dulu ke va_bank_aktif() SEBELUM sampai ke sini."""
    if channel == "va":
        if not channel_code:
            raise ValueError("channel_code (bank VA) wajib diisi untuk channel='va'.")
        return snap_advance_client.buat_transaksi_va(payment_reference, amount, customer_details,
                                                       channel_code=channel_code)
    if channel == "qris":
        return snap_advance_client.buat_transaksi_qris(payment_reference, amount, customer_details)
    if channel == "direct_debit":
        raise snap_advance_client.pending_faspay(
            "Direct Debit checkout",
            "Registrasi/Account Binding Direct Debit belum dikonfirmasi Faspay -- belum dibuka untuk customer."
        )
    raise ValueError(f"Channel pembayaran tidak dikenal: {channel!r}")
