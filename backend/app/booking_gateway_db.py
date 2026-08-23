"""booking_gateway_db.py — Riwayat Transaksi & Pengelolaan Pembayaran Payment
Gateway Booking Customer (Implementasi Payment Gateway & Riwayat Transaksi
Multi-Tenant)
=============================================================================
CRUD `booking_payment_transactions`/`booking_payment_status_log` (lihat
booking_gateway_migrasi.py untuk skema). TERPISAH TOTAL dari
billing_invoice_db.py (riwayat invoice langganan SaaS) -- dua jenis
transaksi, dua modul riwayat, TIDAK saling bergantung/berbagi logika sama
sekali (lihat catatan arsitektur di payment_gateway_client.py).

Isolasi Multi-Tenant: SETIAP fungsi baca di sini WAJIB dipanggil dengan
`tenant_id` dari endpoint tenant-login (routers/booking.py, lihat
Depends(require_owner_or_staff)) -- pengecualian HANYA fungsi yang memang
dipakai webhook (get_by_order_id()) atau Super Admin lintas-tenant
(transaction_report_db.py), yang keduanya TIDAK menerima tenant_id dari
input pengguna biasa sama sekali (order_id dari provider, atau akses
require_superadmin)."""

import json
import uuid
from datetime import datetime

import db_compat
from database import get_conn

STATUS_VALID = {"menunggu_pembayaran", "diproses", "berhasil", "gagal", "kedaluwarsa", "dibatalkan", "refund"}
STATUS_FINAL = {"berhasil", "gagal", "kedaluwarsa", "dibatalkan", "refund"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def buat_order_id(tenant_id: int, booking_id: int) -> str:
    """Murni generate string (TIDAK menyentuh DB) -- dipakai sebagai
    `transaction_details.order_id` di panggilan provider SEBELUM baris
    transaksi ini benar-benar dibuat (pola sama seperti
    billing_invoice_db.buat_order_id())."""
    return f"BOOK-{tenant_id}-{booking_id}-{uuid.uuid4().hex[:12]}"


def _buat_nomor_transaksi() -> str:
    """Fallback LAMA (TRX-YYYYMMDD-HEX8) -- HANYA dipakai kalau pemanggil
    tidak mengoper `nomor_transaksi` (lihat buat_transaksi()), mis. booking
    lama yang belum punya bookings.nomor_transaksi (kolom NULL, dibuat
    sebelum Format Baru Nomor Transaksi Booking ada). Booking BARU normal
    SELALU mengoper nomor_transaksi milik booking-nya sendiri (dibuat
    booking_db.buat_booking(), format [JAM KONFIRMASI][MENIT KONFIRMASI]
    [TANGGAL BOOKING][BULAN BOOKING][JAM BOOKING][INISIAL TENANT]) supaya
    SATU nomor yang sama tampil konsisten di layar pembayaran customer,
    Riwayat Transaksi, dan Super Admin -- BUKAN dua nomor berbeda untuk
    booking yang sama."""
    return f"TRX-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"


def buat_transaksi(order_id: str, tenant_id: int, tenant_nama: str, booking_id: int,
                    customer_nama: str, barber_nama: str, layanan: str, nominal: int,
                    checkout_token: str = None, checkout_redirect_url: str = None,
                    nomor_transaksi: str = None) -> dict:
    nomor_dasar = nomor_transaksi or _buat_nomor_transaksi()
    now = _now()
    # Format Baru Nomor Transaksi Booking TIDAK menyertakan bagian acak
    # apa pun (permintaan Owner, lihat booking_db.py::
    # _buat_nomor_transaksi_booking()) -- beda dari _buat_nomor_transaksi()
    # lama yang selalu bersufiks UUID (praktis tidak pernah tabrakan).
    # `nomor_transaksi` di tabel ini TETAP UNIQUE (kolom lama, TIDAK
    # diubah) -- SECARA TEORI bisa tabrakan (dua tenant berinisial sama +
    # konfirmasi di menit sama + tanggal&jam booking sama, kebetulan yang
    # jarang tapi bukan mustahil). Pengaman JAGA-JAGA murni di sini (BUKAN
    # mengubah format nomor untuk kasus normal): kalau tabrakan, tambahkan
    # sufiks "-2"/"-3"/dst dan coba lagi -- booking yang baru dibuat TIDAK
    # PERNAH gagal checkout hanya karena nomor tampilannya kebetulan sama.
    percobaan = 0
    while True:
        percobaan += 1
        nomor_coba = nomor_dasar if percobaan == 1 else f"{nomor_dasar}-{percobaan}"
        try:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO booking_payment_transactions "
                    "(tenant_id, tenant_nama, booking_id, order_id, nomor_transaksi, customer_nama, barber_nama, "
                    "layanan, nominal, metode_pembayaran, status_pembayaran, checkout_token, checkout_redirect_url, "
                    "created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'gateway', 'menunggu_pembayaran', ?, ?, ?, ?)",
                    (tenant_id, tenant_nama, booking_id, order_id, nomor_coba, customer_nama, barber_nama,
                     layanan, nominal, checkout_token, checkout_redirect_url, now, now),
                )
            break
        except db_compat.IntegrityError:
            if percobaan >= 5:
                raise
    return get_transaksi_by_order_id(order_id)


def get_transaksi(transaksi_id: int, tenant_id: int = None) -> dict | None:
    """`tenant_id` WAJIB diisi dari endpoint tenant-login (lihat docstring
    modul) -- None HANYA untuk Super Admin/webhook internal."""
    with get_conn() as conn:
        if tenant_id is not None:
            row = conn.execute(
                "SELECT * FROM booking_payment_transactions WHERE id = ? AND tenant_id = ?",
                (transaksi_id, tenant_id),
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM booking_payment_transactions WHERE id = ?", (transaksi_id,)).fetchone()
        return dict(row) if row else None


def get_transaksi_by_order_id(order_id: str) -> dict | None:
    """Dipakai booking_gateway_webhook.py -- order_id datang dari payload
    notifikasi provider, BUKAN dari sesi tenant manapun, jadi TIDAK
    di-scope tenant_id di sini (tenant_id hasil query yang dipakai untuk
    cascading update selanjutnya)."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM booking_payment_transactions WHERE order_id = ?", (order_id,)).fetchone()
        return dict(row) if row else None


def get_transaksi_terkini_untuk_booking(booking_id: int) -> dict | None:
    """Transaksi PALING BARU untuk satu booking (SATU booking bisa punya
    lebih dari satu percobaan checkout kalau yang sebelumnya expired/gagal)
    -- dipakai booking_db.py untuk memperkaya Daftar/Detail Booking dengan
    status Payment Gateway TANPA mengubah kolom bookings.status_pembayaran
    yang sudah ada."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM booking_payment_transactions WHERE booking_id = ? ORDER BY id DESC LIMIT 1",
            (booking_id,),
        ).fetchone()
        return dict(row) if row else None


def get_transaksi_terkini_untuk_booking_batch(booking_ids: list) -> dict:
    """Versi BATCH get_transaksi_terkini_untuk_booking() -- dipakai
    booking_db.get_booking_list() supaya memperkaya SATU HALAMAN booking
    tidak memicu satu query terpisah per baris (pola sama seperti
    batch-fetch booking_items di fungsi itu). Return {booking_id: baris
    transaksi TERBARU}, HANYA untuk booking yang punya transaksi (metode
    gateway) -- booking_id yang tidak punya percobaan checkout sama sekali
    TIDAK muncul sebagai key."""
    if not booking_ids:
        return {}
    placeholder = ", ".join("?" for _ in booking_ids)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM booking_payment_transactions WHERE booking_id IN ({placeholder}) ORDER BY id ASC",
            booking_ids,
        ).fetchall()
    hasil = {}
    for r in rows:
        hasil[r["booking_id"]] = dict(r)  # baris TERAKHIR per booking_id menang (ORDER BY id ASC)
    return hasil


def list_transaksi(tenant_id: int, tanggal_mulai: str = None, tanggal_selesai: str = None,
                    status_pembayaran: str = None, metode_pembayaran: str = None) -> list:
    """SELALU di-scope tenant_id -- dipanggil HANYA dari endpoint
    tenant-login (routers/booking.py)."""
    q = "SELECT * FROM booking_payment_transactions WHERE tenant_id = ?"
    params = [tenant_id]
    if tanggal_mulai is not None:
        q += " AND created_at >= ?"; params.append(tanggal_mulai)
    if tanggal_selesai is not None:
        q += " AND created_at <= ?"; params.append(tanggal_selesai)
    if status_pembayaran is not None:
        q += " AND status_pembayaran = ?"; params.append(status_pembayaran)
    if metode_pembayaran is not None:
        q += " AND metode_pembayaran = ?"; params.append(metode_pembayaran)
    q += " ORDER BY id DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def list_semua_transaksi(tanggal_mulai: str = None, tanggal_selesai: str = None) -> list:
    """TANPA scope tenant_id -- HANYA dipanggil transaction_report_db.py
    (Super Admin, require_superadmin) untuk monitoring lintas-tenant."""
    q = "SELECT * FROM booking_payment_transactions WHERE 1=1"
    params = []
    if tanggal_mulai is not None:
        q += " AND created_at >= ?"; params.append(tanggal_mulai)
    if tanggal_selesai is not None:
        q += " AND created_at <= ?"; params.append(tanggal_selesai)
    q += " ORDER BY id DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def update_status(transaksi_id: int, status_baru: str, sumber: str = "webhook", **extra_fields) -> dict:
    """Idempoten -- kalau status_baru SAMA dengan status tersimpan, tidak
    ada apa pun yang diubah/dicatat lagi (pola sama persis dengan
    billing_webhook.py -- mencegah notifikasi duplikat memicu efek samping
    dobel). `extra_fields` yang diizinkan: channel_pembayaran,
    transaction_id_provider, reference_id_provider, raw_notification,
    paid_at.

    AUDIT (Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant --
    perbaikan pasca-audit kesiapan): webhook provider TIDAK MENJAMIN urutan
    pengiriman -- retry/network delay bisa membuat notifikasi LAMA (mis.
    "pending"/"deny"/"cancel" yang sempat tertunda) datang SETELAH notifikasi
    "settlement" yang sudah lebih dulu diproses. TANPA penjagaan ini,
    transaksi yang SUDAH final (STATUS_FINAL) bisa "diturunkan" lagi oleh
    notifikasi basi tersebut -- pemanggil (booking_gateway_webhook.py) lalu
    ikut mengeksekusi cascade-nya (mis. batalkan_booking() untuk booking yang
    SUDAH DIBAYAR). Begitu status SUDAH final, HANYA satu transisi lanjutan
    yang sah: "berhasil" -> "refund" (peristiwa PASCA pembayaran selesai) --
    transisi final lain (termasuk final->final maupun final->non-final)
    DITOLAK, dicatat ke status_log dengan sumber "webhook_diabaikan"/
    "rekonsiliasi_diabaikan" untuk audit/troubleshooting, TANPA mengubah
    status_pembayaran tersimpan. Pemanggil WAJIB mengecek return value --
    kalau status_pembayaran hasilnya TIDAK SAMA dengan status_baru yang
    diminta, berarti transisi ini ditolak guard ini (lihat
    booking_gateway_webhook.py::_terapkan_status())."""
    if status_baru not in STATUS_VALID:
        raise ValueError(f"Status pembayaran booking tidak dikenal: {status_baru}")
    transaksi = get_transaksi(transaksi_id)
    if transaksi is None:
        raise ValueError("Transaksi tidak ditemukan.")
    status_lama = transaksi["status_pembayaran"]
    if status_lama == status_baru:
        return transaksi
    if status_lama in STATUS_FINAL and not (status_lama == "berhasil" and status_baru == "refund"):
        sumber_diabaikan = "rekonsiliasi_diabaikan" if sumber == "rekonsiliasi_manual" else "webhook_diabaikan"
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO booking_payment_status_log (transaction_id, status_lama, status_baru, sumber, waktu) "
                "VALUES (?, ?, ?, ?, ?)",
                (transaksi_id, status_lama, status_baru, sumber_diabaikan, _now()),
            )
        return transaksi

    kolom_diizinkan = {"channel_pembayaran", "transaction_id_provider", "reference_id_provider",
                        "raw_notification", "paid_at"}
    # `v is not None`: pemanggil (booking_gateway_webhook.py::_terapkan_status())
    # SELALU meneruskan seluruh field ini apa adanya (termasuk None kalau
    # notifikasi/respons provider tidak menyertakannya) -- None WAJIB berarti
    # "jangan sentuh kolom ini", BUKAN "timpa jadi NULL", supaya paid_at/
    # transaction_id_provider/dst yang sudah tercatat tidak pernah terhapus
    # oleh transisi status lanjutan yang responsnya lebih minim (mis.
    # "berhasil" -> "refund" TIDAK boleh menghapus paid_at yang sudah ada).
    aman = {k: v for k, v in extra_fields.items() if k in kolom_diizinkan and v is not None}
    aman["status_pembayaran"] = status_baru
    set_clause = ", ".join(f"{k} = ?" for k in aman)
    with get_conn() as conn:
        # BUGFIX (audit, race condition): dulu pengecekan status_lama di atas
        # dan UPDATE ini dua langkah terpisah (check-then-act) -- dua
        # notifikasi webhook nyaris bersamaan untuk transaksi yang SAMA bisa
        # SAMA-SAMA lolos pengecekan lalu SAMA-SAMA menulis (Faspay
        # mendokumentasikan retry). UPDATE sekarang bersyarat
        # `AND status_pembayaran = ?` (compare-and-swap atomik di level SQL)
        # -- kalau GAGAL (rowcount 0, status sudah berubah oleh proses lain
        # di antara baca & tulis kita), fungsi ini dipanggil ULANG dari awal
        # terhadap state TERBARU supaya seluruh pengecekan idempoten/final
        # dinilai ulang, bukan diam-diam menimpa/dobel mencatat log.
        cur = conn.execute(
            f"UPDATE booking_payment_transactions SET {set_clause}, updated_at = ? "
            f"WHERE id = ? AND status_pembayaran = ?",
            list(aman.values()) + [_now(), transaksi_id, status_lama],
        )
        if cur.rowcount == 0:
            gagal_race = True
        else:
            conn.execute(
                "INSERT INTO booking_payment_status_log (transaction_id, status_lama, status_baru, sumber, waktu) "
                "VALUES (?, ?, ?, ?, ?)",
                (transaksi_id, status_lama, status_baru, sumber, _now()),
            )
            gagal_race = False
    if gagal_race:
        return update_status(transaksi_id, status_baru, sumber=sumber, **extra_fields)
    return get_transaksi(transaksi_id)


def list_status_log(transaksi_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM booking_payment_status_log WHERE transaction_id = ? ORDER BY id ASC", (transaksi_id,)
        ).fetchall()
        return [dict(r) for r in rows]
