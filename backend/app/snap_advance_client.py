"""snap_advance_client.py — Klien Faspay SNAP Advance
=============================================================================
Migrasi Faspay SNAP Advance -- lihat laporan analisis "Faspay SNAP Migration"
(Tahap 2) untuk sumber & batasan lengkap. Provider BARU, TERPISAH TOTAL dari
payment_gateway_client.py/billing_gateway_client.py (Xpress v4, TIDAK
disentuh sama sekali di sini -- tetap berjalan penuh selama masa transisi).

INTERFACE modul ini (nama fungsi/parameter) SENGAJA meniru pola
payment_gateway_client.py (is_enabled(), buat_transaksi_*(),
verifikasi_signature_webhook(), cek_status_transaksi()) SESUAI instruksi
migrasi #1 "gunakan abstraction/interface payment gateway yang sudah ada
apabila masih kompatibel" -- supaya pemanggil di lapisan atas (snap_payment_db.py/
snap_webhook.py) TIDAK PERNAH perlu tahu detail wire-protocol provider,
sama seperti routers/booking.py TIDAK PERNAH perlu tahu detail Xpress v4.

=============================================================================
STATUS IMPLEMENTASI -- JUJUR, TIDAK ADA YANG DIKARANG
=============================================================================
SEMUA fungsi create-transaction/inquiry/webhook-parsing DI BAWAH INI MELEMPAR
PENDING FASPAY -- BUKAN bug, SENGAJA -- karena TIDAK SATU PUN dari berikut
ini terkonfirmasi dari dokumentasi resmi Faspay ATAU kredensial sandbox
sungguhan (docs.faspay.co.id tidak bisa diakses dari lingkungan pengembangan
ini, lihat laporan analisis):
  - Endpoint get-token B2B Faspay (path persis).
  - Endpoint create Dynamic VA Faspay (path persis, field request/response).
  - Endpoint create Dynamic QRIS Faspay (path DIDUGA `/v1.0/qr/qr-mpm-generate`
    dari cuplikan pencarian publik -- field response SEBAGIAN diketahui
    `responseCode/referenceNo/partnerReferenceNo/qrContent/qrUrl`, TAPI
    field REQUEST lengkap & tabel kode error TIDAK terverifikasi -- risiko
    salah masih terlalu tinggi untuk diklaim "terimplementasi", jadi TETAP
    PENDING FASPAY, bukan ditebak sebagian).
  - Jalur teknis Dynamic E-Wallet SAMA SEKALI (lihat laporan Tahap 2.3 --
    bahkan produk SNAP mana yang melayaninya belum jelas).
  - String-to-sign PERSIS untuk signature RSA-SHA256 di tiap endpoint.
  - Skema JSON webhook/payment notification SNAP Faspay yang sesungguhnya.

Primitif kriptografi generik (RSA-SHA256, standar SNAP -- lihat
gateway_client_base.py::sign_sha256_rsa()/verify_sha256_rsa()) SUDAH
diimplementasikan sungguhan (bukan stub) karena itu murni algoritma publik,
BUKAN detail spesifik Faspay -- modul INI yang merangkai string-to-sign
memanggilnya, dan bagian MERANGKAI itulah yang PENDING FASPAY.

Begitu Faspay mengonfirmasi detail di atas (dokumentasi lengkap dan/atau
kredensial sandbox), isi fungsi PENDING di bawah diganti panggilan
gateway_client_base.post_json()/get_json() sungguhan -- SIGNATURE fungsi
(nama & parameter) TIDAK perlu berubah, jadi snap_payment_db.py/snap_webhook.py
TIDAK perlu disentuh sama sekali saat itu terjadi."""

import gateway_client_base as core
import snap_advance_db

_TIMEOUT_DEFAULT = 30


class SnapAdvancePendingError(core.GatewayError):
    """Ditandai TERPISAH dari GatewayError generik (walau tetap turunannya,
    supaya router yang sudah menangkap GatewayError otomatis ikut menangkap
    ini) -- supaya log/monitoring bisa membedakan dengan jelas "belum
    diimplementasikan karena menunggu Faspay" dari kegagalan jaringan/
    provider sungguhan (GatewayTimeoutError/GatewayRequestError)."""


def pending_faspay(area: str, detail: str) -> SnapAdvancePendingError:
    return SnapAdvancePendingError(
        f"SNAP Advance -- {area}: PENDING FASPAY. {detail} "
        f"Lihat laporan analisis \"Faspay SNAP Migration\" (Tahap 2) & docstring modul ini."
    )


def is_enabled() -> bool:
    """Config MINIMAL sudah diisi Super Admin -- BUKAN jaminan create-
    transaction sungguhan berfungsi (lihat catatan modul), murni penanda
    "siap dicoba begitu implementasi PENDING di bawah selesai"."""
    return snap_advance_db.get_config()["enabled"]


def is_production() -> bool:
    return snap_advance_db.get_config()["snap_environment"] == "production"


def _base_url(is_prod: bool) -> str:
    """Dipakai NANTI oleh fungsi create-transaction/token sungguhan begitu
    diimplementasikan (lihat catatan modul) -- BELUM dipanggil di mana pun
    hari ini (seluruh fungsi PENDING FASPAY di bawah melempar error SEBELUM
    sempat butuh base URL apa pun), disiapkan di sini supaya urutan
    pengisian nanti tinggal menyambungkan, bukan menulis dari nol."""
    cfg = snap_advance_db.get_config()
    url = cfg["snap_production_base_url"] if is_prod else cfg["snap_sandbox_base_url"]
    if not url:
        raise core.GatewayNotConfiguredError(
            f"Base URL SNAP Advance ({'production' if is_prod else 'sandbox'}) belum diisi Super Admin -- "
            f"PENDING FASPAY (URL resmi belum dikonfirmasi, lihat laporan analisis)."
        )
    return url


def ambil_token_b2b() -> str:
    """Token akses B2B SNAP (pola standar: signature Asymmetric atas
    `client_id + "|" + X-TIMESTAMP` -> POST ke endpoint access-token ->
    terima access_token dipakai untuk memanggil layanan API selanjutnya).
    PENDING FASPAY -- endpoint get-token persis (path/header lengkap/masa
    berlaku token) belum terkonfirmasi."""
    cfg = snap_advance_db.get_config()
    if not cfg["enabled"]:
        raise core.GatewayNotConfiguredError(
            "SNAP Advance belum dikonfigurasi Super Admin (Merchant ID/Client ID/Client Secret/Private Key kosong)."
        )
    raise pending_faspay(
        "ambil_token_b2b()",
        "Endpoint get-token B2B Faspay (path, header X-CLIENT-KEY/X-TIMESTAMP lengkap, format respons) belum terkonfirmasi.",
    )


def buat_transaksi_va(payment_reference: str, amount: int, customer_details: dict = None) -> dict:
    """Create Dynamic VA -- return dict berisi MINIMAL `va_number`/`expired_at`/
    `provider_transaction_id` kalau sudah diimplementasikan sungguhan.
    PENDING FASPAY -- endpoint create VA (path, field request/response
    persis) belum terkonfirmasi dari dokumentasi resmi manapun yang bisa
    diakses (lihat laporan analisis Tahap 2.1: bentuk UMUM terkonfirmasi --
    virtualAccountNo/expiry/inquiry/callback -- tapi skema JSON PERSIS
    tidak)."""
    raise pending_faspay(
        "Dynamic VA -- buat_transaksi_va()",
        "Endpoint create VA Faspay (path, field request/response persis, format virtualAccountNo) belum terkonfirmasi.",
    )


def buat_transaksi_qris(payment_reference: str, amount: int, customer_details: dict = None) -> dict:
    """Create Dynamic QRIS -- return dict berisi MINIMAL `qr_content`/`qr_url`/
    `expired_at`/`provider_transaction_id` kalau sudah diimplementasikan
    sungguhan. PENDING FASPAY -- endpoint DIDUGA `/v1.0/qr/qr-mpm-generate`
    (cuplikan pencarian publik SNAP QRIS, lihat laporan analisis Tahap 2.2),
    response DIDUGA berisi `qrContent`/`qrUrl`/`referenceNo`/`partnerReferenceNo`
    -- TAPI field REQUEST lengkap, tabel kode error, dan durasi expiry
    default TIDAK terverifikasi. SENGAJA TETAP tidak diimplementasikan
    (bukan ditebak sebagian) -- payment production TIDAK BOLEH dibangun di
    atas skema yang separuh dikonfirmasi separuh ditebak."""
    raise pending_faspay(
        "Dynamic QRIS -- buat_transaksi_qris()",
        "Endpoint diduga /v1.0/qr/qr-mpm-generate (belum diverifikasi penuh) -- field request lengkap & tabel kode error belum terkonfirmasi.",
    )


def buat_transaksi_ewallet(payment_reference: str, amount: int, ewallet_provider: str,
                            customer_details: dict = None) -> dict:
    """Create Dynamic E-Wallet -- PENDING FASPAY TOTAL (lihat laporan
    analisis Tahap 2.3): bahkan JALUR TEKNISNYA belum jelas -- apakah lewat
    SNAP QRIS (customer scan dari app e-wallet) atau API terpisah non-SNAP
    (skema signature SHA1(MD5()) lama, bukan RSA-SHA256). TIDAK ADA satu pun
    detail (endpoint/field/redirect-atau-deeplink) yang bisa dipastikan."""
    raise pending_faspay(
        "Dynamic E-Wallet -- buat_transaksi_ewallet()",
        "Jalur teknis E-Wallet (SNAP QRIS reuse vs API terpisah non-SNAP) belum terkonfirmasi Faspay sama sekali -- lihat laporan analisis Tahap 2.3.",
    )


def cek_status_transaksi(payment_reference: str) -> dict:
    """Inquiry/Cek Status manual -- untuk fitur "Cek Ulang ke Provider"
    (rekonsiliasi transaksi yang macet karena webhook tidak pernah sampai,
    pola sama seperti booking_gateway_webhook.rekonsiliasi_manual()).
    PENDING FASPAY -- endpoint inquiry per channel belum terkonfirmasi."""
    raise pending_faspay(
        "Inquiry/Cek Status -- cek_status_transaksi()",
        "Endpoint inquiry status SNAP Advance per channel (VA/QRIS/E-Wallet) belum terkonfirmasi.",
    )


def verifikasi_signature_webhook(raw_body: str, signature_header: str, timestamp_header: str = None) -> bool:
    """Verifikasi X-SIGNATURE webhook -- PENDING FASPAY: primitif
    kriptografinya SENDIRI sudah nyata (gateway_client_base.verify_sha256_rsa()),
    tapi STRING-TO-SIGN PERSIS yang Faspay pakai untuk webhook (field apa
    saja yang digabung, urutannya) belum terkonfirmasi -- memanggil
    verify_sha256_rsa() dengan string-to-sign yang DITEBAK justru LEBIH
    BERBAHAYA daripada menolak semua notifikasi (bisa menerima notifikasi
    palsu yang kebetulan lolos formula yang salah) -- SENGAJA tetap
    menolak (PENDING) sampai formula resmi terkonfirmasi."""
    raise pending_faspay(
        "Verifikasi signature webhook -- verifikasi_signature_webhook()",
        "String-to-sign persis untuk Payment Notification SNAP Faspay (field & urutan yang digabung sebelum RSA-SHA256) belum terkonfirmasi.",
    )
