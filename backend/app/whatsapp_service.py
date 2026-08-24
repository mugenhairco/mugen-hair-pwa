"""whatsapp_service.py — FITUR Notifikasi WhatsApp Otomatis Booking: klien
Fonnte (pengiriman pesan WhatsApp)
=============================================================================
BEDA dari email_service.py (kredensial GLOBAL lewat env var RESEND_API_KEY,
satu pengirim untuk SELURUH tenant): token Fonnte di sini PER TENANT
(disimpan di tabel `settings` generik lewat database.py, key
"whatsapp_fonnte_token") -- keputusan produk eksplisit supaya pesan ke
customer benar-benar terkirim dari nomor WhatsApp TOKO itu sendiri (yang
sudah dihubungkan Owner ke akun Fonnte-nya sendiri lewat scan QR di situs
Fonnte), BUKAN dari satu nomor WhatsApp milik platform Rivoir untuk semua
tenant. Owner mengatur token ini lewat Setting > WhatsApp (lihat
routers/pengaturan.py, require_admin -- KHUSUS Owner, sama seperti tab
Komisi/Bonus Service, kredensial pihak ketiga TIDAK didelegasikan ke staff).

Token belum diisi -> kirim_whatsapp() TIDAK PERNAH memanggil jaringan sama
sekali, cukup mencatat log & mengembalikan False -- pemanggil (booking_db.py)
TETAP berhasil menyelesaikan operasi utamanya (buat booking, verifikasi
pembayaran, batalkan booking) walau pesan WhatsApp tidak terkirim, pola
SAMA PERSIS "best effort" seperti email_service.py::kirim_email()."""

import logging

import requests

import database as db

logger = logging.getLogger("mugen.whatsapp")

_FONNTE_URL = "https://api.fonnte.com/send"
_TIMEOUT_DETIK = 15

TOKEN_SETTING_KEY = "whatsapp_fonnte_token"

# REVISI: teks pesan bisa diatur sendiri per tenant (lihat whatsapp_templates.py
# untuk placeholder & default) -- SATU key settings per jenis pesan, kosong
# berarti "belum diubah, pakai default".
TEMPLATE_SETTING_KEYS = {
    "reminder_qris": "whatsapp_template_reminder_qris",
    "konfirmasi_pembayaran": "whatsapp_template_konfirmasi_pembayaran",
    "pembatalan": "whatsapp_template_pembatalan",
    "booking_luar_jam_operasional": "whatsapp_template_booking_luar_jam_operasional",
}


def get_token(tenant_id: int = None) -> str:
    return (db.get_setting(TOKEN_SETTING_KEY, "", tenant_id=tenant_id) or "").strip()


def set_token(token: str, tenant_id: int = None):
    db.set_setting(TOKEN_SETTING_KEY, (token or "").strip(), tenant_id=tenant_id)


def is_enabled(tenant_id: int = None) -> bool:
    return bool(get_token(tenant_id))


def get_templates(tenant_id: int = None) -> dict:
    """{jenis: teks_custom} -- teks KOSONG untuk jenis yang belum pernah
    diubah Owner (frontend/whatsapp_templates.render() yang menentukan
    fallback ke default, BUKAN di sini)."""
    return {jenis: (db.get_setting(key, "", tenant_id=tenant_id) or "")
            for jenis, key in TEMPLATE_SETTING_KEYS.items()}


def set_templates(templates: dict, tenant_id: int = None):
    tidak_dikenal = set(templates.keys()) - set(TEMPLATE_SETTING_KEYS.keys())
    if tidak_dikenal:
        raise ValueError(f"Jenis pesan tidak dikenal: {', '.join(sorted(tidak_dikenal))}")
    for jenis, teks in templates.items():
        db.set_setting(TEMPLATE_SETTING_KEYS[jenis], (teks or "").strip(), tenant_id=tenant_id)


def _format_nomor_fonnte(nomor: str) -> str:
    """Fonnte mengharapkan nomor tanpa "+" di depan (mis. "6281234567890")
    -- normalisasi longgar dari format apa pun yang lolos booking_db.py::
    _whatsapp_valid() (boleh diawali 08/+62/62)."""
    nomor = (nomor or "").strip().replace(" ", "").replace("-", "")
    if nomor.startswith("+"):
        nomor = nomor[1:]
    elif nomor.startswith("0"):
        nomor = "62" + nomor[1:]
    return nomor


def kirim_whatsapp(nomor_tujuan: str, pesan: str, tenant_id: int = None) -> bool:
    """Kirim SATU pesan teks WhatsApp lewat Fonnte, memakai token milik
    TENANT ini. SELALU aman dipanggil -- TIDAK PERNAH melempar exception ke
    pemanggil (booking_db.py), mengembalikan False (bukan crash) kalau
    token belum diisi ATAU permintaan ke Fonnte gagal (token salah, nomor
    tidak valid, jaringan turun, dst). Pemanggil TIDAK PERNAH boleh
    membiarkan hasil False di sini menggagalkan operasi utamanya (buat/
    verifikasi/batalkan booking) -- notifikasi WhatsApp murni "best
    effort", TIDAK ada mekanisme "Kirim Ulang" manual untuk pesan ini
    (beda dari email verifikasi yang punya tombol Kirim Ulang)."""
    token = get_token(tenant_id)
    if not token:
        logger.warning("WhatsApp KE %s TIDAK dikirim -- token Fonnte belum diisi (tenant_id=%s).",
                        nomor_tujuan, tenant_id)
        return False
    try:
        resp = requests.post(
            _FONNTE_URL,
            data={"target": _format_nomor_fonnte(nomor_tujuan), "message": pesan},
            headers={"Authorization": token},
            timeout=_TIMEOUT_DETIK,
        )
        if resp.status_code >= 400:
            logger.error("Fonnte menolak permintaan KE %s: HTTP %s %s", nomor_tujuan, resp.status_code, resp.text)
            return False
        hasil = resp.json()
        if hasil.get("status") is False:
            logger.error("Fonnte gagal mengirim KE %s: %s", nomor_tujuan, hasil.get("reason") or hasil)
            return False
        return True
    except Exception as e:
        logger.error("WhatsApp KE %s GAGAL (exception): %s: %s", nomor_tujuan, type(e).__name__, e)
        return False
