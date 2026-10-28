"""pos_db.py — Point of Sale (Kasir walk-in + Transaksi Hari Ini)
=============================================================================
FITUR BARU (diminta Owner): menu "Point of Sale" untuk customer yang datang
LANGSUNG ke toko (walk-in, bukan booking online) -- Kasir pilih Barber dan/
atau Produk, pilih Service, lalu Payment (QRIS manual foto yang di-upload
Superadmin, ATAU Payment Gateway Faspay SNAP -- metode & channel yang SAMA
PERSIS dipakai booking publik, lihat booking_db.get_payment_settings()).
Satu kali scan/pembayaran bisa mencakup Service + Produk sekaligus.

INTEGRASI KE REKAP (PERMINTAAN EKSPLISIT Owner -- "saya tidak ingin 1 barber
banyak baris dalam satu hari, saya ingin seperti menu Rekap sekarang, 1 baris
untuk 1 barber"): begitu SATU transaksi POS (bagian Service-nya) lunas,
_rebuild_transaksi_barber_hari() di bawah menghapus baris `transaksi` lama
(kalau ada) untuk barber+tanggal itu lalu membangunnya ULANG dari SELURUH
transaksi POS lunas hari itu (qty service dijumlahkan) -- hasilnya SELALU 1
baris transaksi per barber per hari di Rekap, persis seperti Input Barber/
Manual Customer, walau banyak customer walk-in berbeda dibayar sepanjang
hari (real-time, TANPA tombol "Tutup & Simpan" terpisah). Pola rebuild ini
REUSE TOTAL manual_customer_db._buat_transaksi_gabungan()/
_sinkronkan_transaksi_hari() (DITULIS ULANG di sini karena sumber datanya
beda tabel, BUKAN logika baru).

Mode "satu tanggal satu mode" (manual_customer_db.MODE_VALID) diperluas
dengan "pos" -- SATU tanggal tidak bisa pakai Input Barber/Manual Customer
BERSAMAAN dengan POS (PERMINTAAN Owner: "harus eksklusif"). Diklaim SEKALI
saat transaksi POS Service PERTAMA pada tanggal itu DIBUAT (bukan saat
lunas -- supaya konflik mode ketahuan SEBELUM pembayaran diterima, bukan
sesudahnya saat sudah tidak bisa dibatalkan lagi).

Bagian Produk SENGAJA TIDAK ikut sistem mode ini sama sekali -- reuse TOTAL
database.jual_produk() apa adanya (1 baris mutasi per produk per penjualan,
SAMA PERSIS seperti input manual dari menu Produk yang sudah ada, TIDAK
digabung/diagregasi) -- PERMINTAAN Owner eksplisit: "tidak perlu bikin
mekanisme gabung 1 baris per hari seperti Service" untuk Produk.

Payment: reuse TOTAL payment_provider_client.py + snap_payment_db.py (tipe
transaksi baru TRANSACTION_TYPE_POS) + snap_webhook.py (cascade baru
_cascade_pos()) -- pola SAMA PERSIS routers/booking.py::public_buat_booking()
untuk metode "gateway". Metode "qris" (manual, foto yang di-upload
Superadmin) TIDAK memanggil provider apa pun -- status tetap 'menunggu'
sampai Kasir klik "Payment Diterima" (lihat verifikasi_manual())."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import gateway_client_base
import manual_customer_db
import payment_provider_client
import snap_payment_db
from database import (get_barber, get_conn, get_produk, get_service, get_stok_produk, hapus_transaksi,
                       jual_produk, tambah_transaksi)

WIB = ZoneInfo("Asia/Jakarta")

STATUS_VALID = {"menunggu", "lunas", "batal"}
METODE_VALID = {"qris", "gateway"}

_logger = logging.getLogger("mugen.pos")


def _sekarang_wib() -> datetime:
    return datetime.now(WIB)


def init_pos_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pos_transaksi (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id          INTEGER NOT NULL,
                tanggal            TEXT NOT NULL,
                jam                TEXT NOT NULL,
                barber_id          INTEGER,
                metode_pembayaran  TEXT NOT NULL,
                channel            TEXT,
                status             TEXT NOT NULL DEFAULT 'menunggu',
                total_harga        INTEGER NOT NULL,
                payment_reference  TEXT,
                transaksi_id       INTEGER,
                dibuat_oleh        TEXT,
                created_at         TEXT NOT NULL,
                updated_at         TEXT,
                paid_at            TEXT
            )
        """)
        # `service_id`/`produk_id` SENGAJA TANPA "FOREIGN KEY ... REFERENCES"
        # (pola sama seperti manual_customer_transaksi_service, lihat catatan
        # lengkap "HOTFIX DEPLOY" di manual_customer_db.py -- tabel
        # produksi PostgreSQL ternyata tidak selalu punya constraint UNIQUE/
        # PRIMARY KEY murni pada services.id/produk.id).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pos_transaksi_service (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                pos_transaksi_id  INTEGER NOT NULL,
                service_id        INTEGER NOT NULL,
                FOREIGN KEY (pos_transaksi_id) REFERENCES pos_transaksi(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pos_transaksi_produk (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                pos_transaksi_id  INTEGER NOT NULL,
                produk_id         INTEGER NOT NULL,
                jumlah            INTEGER NOT NULL,
                harga_satuan      INTEGER NOT NULL,
                mutasi_id         INTEGER,
                FOREIGN KEY (pos_transaksi_id) REFERENCES pos_transaksi(id) ON DELETE CASCADE
            )
        """)


# ---------------------------------------------------------------------------
# CRUD pos_transaksi
# ---------------------------------------------------------------------------

def _pastikan_barber_tenant_sama(barber_id: int, tenant_id: int) -> None:
    barber = get_barber(barber_id)
    if barber is None or barber.get("tenant_id") != tenant_id:
        raise ValueError("Barber tidak ditemukan.")


def _lengkapi(row: dict) -> dict:
    with get_conn() as conn:
        service_ids = [r["service_id"] for r in conn.execute(
            "SELECT service_id FROM pos_transaksi_service WHERE pos_transaksi_id = ? ORDER BY id ASC",
            (row["id"],),
        ).fetchall()]
        produk_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM pos_transaksi_produk WHERE pos_transaksi_id = ? ORDER BY id ASC",
            (row["id"],),
        ).fetchall()]
    row["daftar_service"] = []
    for sid in service_ids:
        s = get_service(sid)
        if s is not None:
            row["daftar_service"].append({"id": s["id"], "nama": s["nama"], "harga": s["harga"]})
    row["daftar_produk"] = []
    for p in produk_rows:
        produk = get_produk(p["produk_id"])
        row["daftar_produk"].append({
            "id": p["produk_id"], "nama": produk["nama"] if produk else "(produk terhapus)",
            "jumlah": p["jumlah"], "harga_satuan": p["harga_satuan"], "mutasi_id": p.get("mutasi_id"),
        })
    if row.get("barber_id") is not None:
        barber = get_barber(row["barber_id"])
        row["nama_barber"] = barber["nama"] if barber else "(barber terhapus)"
    else:
        row["nama_barber"] = None
    return row


def get_pos_transaksi(pos_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM pos_transaksi WHERE id = ?", (pos_id,)).fetchone()
        return _lengkapi(dict(row)) if row else None


def buat_transaksi(tenant_id: int, barber_id: int = None, service_ids: list = None,
                    produk_items: list = None, metode_pembayaran: str = None,
                    channel: str = None, bank_code: str = None, dibuat_oleh: str = None) -> dict:
    """`produk_items` = list of {"produk_id": int, "jumlah": int}. Validasi
    stok di sini MURNI pre-check (snapshot saat checkout dibuat) -- cek
    OTORITATIF sesungguhnya tetap di database.jual_produk() saat pembayaran
    lunas (lihat _proses_setelah_lunas()), supaya race jarang (stok berubah
    di antara checkout dibuat & lunas) tidak pernah membuat stok negatif."""
    if metode_pembayaran not in METODE_VALID:
        raise ValueError(f"Metode pembayaran Point of Sale tidak dikenal: {metode_pembayaran}")
    if metode_pembayaran == "gateway" and not channel:
        raise ValueError("Channel (VA/QRIS) wajib diisi untuk metode gateway.")
    service_ids = service_ids or []
    produk_items = produk_items or []
    if not service_ids and not produk_items:
        raise ValueError("Pilih minimal satu Service atau Produk.")
    if service_ids and barber_id is None:
        raise ValueError("Barber wajib dipilih kalau ada Service.")
    if barber_id is not None:
        _pastikan_barber_tenant_sama(barber_id, tenant_id)

    total = 0
    for sid in service_ids:
        s = get_service(sid)
        if s is None or (s.get("tenant_id") is not None and s.get("tenant_id") != tenant_id):
            raise ValueError(f"Service #{sid} tidak ditemukan.")
        total += s["harga"]

    produk_bersih = []
    for item in produk_items:
        pid = item.get("produk_id")
        jumlah = int(item.get("jumlah") or 0)
        if jumlah <= 0:
            raise ValueError("Jumlah produk harus lebih dari 0.")
        p = get_produk(pid)
        if p is None or p.get("tenant_id") != tenant_id:
            raise ValueError(f"Produk #{pid} tidak ditemukan.")
        stok = get_stok_produk(pid)
        if stok < jumlah:
            raise ValueError(f"Stok {p['nama']} tidak cukup (sisa {stok}).")
        produk_bersih.append((p, jumlah))
        total += p["harga_jual"] * jumlah

    if total <= 0:
        raise ValueError("Total transaksi harus lebih dari 0.")

    tanggal = _sekarang_wib().strftime("%Y-%m-%d")
    # Mode eksklusif ("satu tanggal satu mode", PERMINTAAN Owner) -- diklaim
    # SEKARANG (saat dibuat), SEBELUM pembayaran apa pun diminta, supaya
    # konflik mode (tanggal ini sudah dipakai Input Barber/Manual Customer)
    # ketahuan & ditolak SEBELUM customer membayar, bukan sesudahnya saat
    # tidak bisa dibatalkan lagi. Produk TIDAK ikut (lihat docstring modul).
    if service_ids:
        manual_customer_db.pastikan_mode(tenant_id, tanggal, "pos")

    now = datetime.now().isoformat(timespec="seconds")
    jam = _sekarang_wib().strftime("%H:%M")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO pos_transaksi (tenant_id, tanggal, jam, barber_id, metode_pembayaran, channel, "
            "status, total_harga, dibuat_oleh, created_at) VALUES (?, ?, ?, ?, ?, ?, 'menunggu', ?, ?, ?)",
            (tenant_id, tanggal, jam, barber_id, metode_pembayaran, channel, total, dibuat_oleh, now),
        )
        pos_id = cur.lastrowid
        for sid in service_ids:
            conn.execute(
                "INSERT INTO pos_transaksi_service (pos_transaksi_id, service_id) VALUES (?, ?)",
                (pos_id, sid),
            )
        for p, jumlah in produk_bersih:
            conn.execute(
                "INSERT INTO pos_transaksi_produk (pos_transaksi_id, produk_id, jumlah, harga_satuan) "
                "VALUES (?, ?, ?, ?)",
                (pos_id, p["id"], jumlah, p["harga_jual"]),
            )

    if metode_pembayaran != "gateway":
        return get_pos_transaksi(pos_id)

    # Metode "gateway" -- pola SAMA PERSIS routers/booking.py::
    # public_buat_booking(): catat transaksi SNAP lokal CREATED dulu, baru
    # panggil provider, baru catat hasilnya.
    snap_row = snap_payment_db.buat_transaksi(
        snap_payment_db.TRANSACTION_TYPE_POS, tenant_id, total,
        pos_transaksi_id=pos_id, channel=channel,
        channel_code=bank_code if channel == "va" else None,
    )
    customer_details = {"nama": "Walk-in Customer (Point of Sale)", "whatsapp": ""}
    try:
        hasil = payment_provider_client.buat_transaksi(
            channel, snap_row["payment_reference"], total, customer_details,
            channel_code=bank_code if channel == "va" else None,
        )
    except gateway_client_base.GatewayError as e:
        snap_payment_db.update_status(snap_row["id"], snap_payment_db.STATUS_FAILED, sumber="create_gagal")
        with get_conn() as conn:
            conn.execute("UPDATE pos_transaksi SET status = 'batal', updated_at = ? WHERE id = ?",
                         (datetime.now().isoformat(timespec="seconds"), pos_id))
        raise ValueError(f"Gagal membuat transaksi pembayaran: {e}")

    snap_payment_db.catat_hasil_create_transaction(
        snap_row["id"], provider_transaction_id=hasil.get("provider_transaction_id"),
        va_number=hasil.get("va_number"), qr_content=hasil.get("qr_content"), qr_url=hasil.get("qr_url"),
        expired_at=hasil.get("expired_at"), provider_response=hasil.get("provider_response"), status="PENDING",
    )
    with get_conn() as conn:
        conn.execute("UPDATE pos_transaksi SET payment_reference = ? WHERE id = ?",
                     (snap_row["payment_reference"], pos_id))

    pos = get_pos_transaksi(pos_id)
    pos["channel_code"] = hasil.get("channel_code") or bank_code
    pos["va_number"] = hasil.get("va_number")
    pos["qr_url"] = hasil.get("qr_url")
    pos["qr_content"] = hasil.get("qr_content")
    return pos


# ---------------------------------------------------------------------------
# Verifikasi pembayaran (manual "Payment Diterima" & cascade webhook gateway)
# ---------------------------------------------------------------------------

def verifikasi_manual(pos_id: int, tenant_id: int) -> dict:
    """Tombol "Payment Diterima" di layar Kasir (metode QRIS manual) --
    Kasir sendiri yang melihat notifikasi masuk ke rekening/HP toko, TIDAK
    ada verifikasi provider otomatis untuk metode ini (sama seperti QRIS
    manual booking publik)."""
    pos = get_pos_transaksi(pos_id)
    if pos is None or pos["tenant_id"] != tenant_id:
        raise ValueError("Transaksi Point of Sale tidak ditemukan.")
    if pos["metode_pembayaran"] != "qris":
        raise ValueError("Verifikasi manual hanya berlaku untuk metode QRIS.")
    if pos["status"] != "menunggu":
        raise ValueError("Transaksi ini sudah diproses sebelumnya.")
    return _tandai_lunas(pos_id)


def tandai_lunas_dari_gateway(pos_id: int) -> dict:
    """Dipanggil snap_webhook.py::_cascade_pos() saat status PAID -- TIDAK
    ADA admin manusia di jalur webhook (pola sama persis _cascade_booking())."""
    pos = get_pos_transaksi(pos_id)
    if pos is None:
        raise ValueError("Transaksi Point of Sale tidak ditemukan.")
    if pos["status"] != "menunggu":
        return pos
    return _tandai_lunas(pos_id)


def batalkan_pos(pos_id: int) -> dict:
    """Dipanggil snap_webhook.py::_cascade_pos() saat status FAILED/EXPIRED/
    CANCELLED -- transaksi POS yang gatewaynya gagal/kedaluwarsa, TIDAK
    PERNAH menyentuh Rekap/stok produk (belum pernah 'lunas')."""
    pos = get_pos_transaksi(pos_id)
    if pos is None:
        raise ValueError("Transaksi Point of Sale tidak ditemukan.")
    if pos["status"] != "menunggu":
        return pos
    with get_conn() as conn:
        conn.execute("UPDATE pos_transaksi SET status = 'batal', updated_at = ? WHERE id = ?",
                     (datetime.now().isoformat(timespec="seconds"), pos_id))
    return get_pos_transaksi(pos_id)


def _tandai_lunas(pos_id: int) -> dict:
    """Compare-and-swap (pola sama persis snap_payment_db.update_status())
    -- cegah proses_setelah_lunas() berjalan dobel kalau dipanggil nyaris
    bersamaan (mis. webhook + "Cek Ulang ke Provider" manual)."""
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE pos_transaksi SET status = 'lunas', paid_at = ?, updated_at = ? "
            "WHERE id = ? AND status = 'menunggu'",
            (now, now, pos_id),
        )
    if cur.rowcount == 0:
        return get_pos_transaksi(pos_id)
    pos = get_pos_transaksi(pos_id)
    _proses_setelah_lunas(pos)
    return get_pos_transaksi(pos_id)


def _proses_setelah_lunas(pos: dict) -> None:
    """Pecah SATU pembayaran yang baru lunas jadi dua cascade terpisah
    (PERMINTAAN Owner -- "satu kali scan untuk Service + Produk, tapi
    rekapannya nanti terpisah"): Service -> rebuild baris Rekap 1x/barber/
    hari (lihat _rebuild_transaksi_barber_hari()), Produk -> reuse TOTAL
    database.jual_produk() per item (TIDAK diagregasi, lihat docstring
    modul)."""
    if pos["daftar_service"] and pos["barber_id"] is not None:
        _rebuild_transaksi_barber_hari(pos["tenant_id"], pos["barber_id"], pos["tanggal"])
    for item in pos["daftar_produk"]:
        try:
            mutasi_id = jual_produk(
                item["id"], pos["tanggal"], item["jumlah"],
                catatan=f"Point of Sale #{pos['id']}", sumber="pos",
            )
            with get_conn() as conn:
                conn.execute(
                    "UPDATE pos_transaksi_produk SET mutasi_id = ? WHERE pos_transaksi_id = ? AND produk_id = ?",
                    (mutasi_id, pos["id"], item["id"]),
                )
        except ValueError:
            # Stok berubah di antara checkout dibuat & lunas (race jarang,
            # mis. dua Kasir checkout produk yang sama hampir bersamaan) --
            # pembayaran SUDAH diterima, TIDAK bisa dibatalkan lagi di sini.
            # Dicatat sebagai error server (Admin menyelesaikan manual lewat
            # Produk > Riwayat Mutasi, mis. restock/koreksi), TIDAK dilempar
            # ke pemanggil -- status pos_transaksi TETAP 'lunas' (uang sudah
            # diterima, cascade produk yang gagal bukan alasan membalik itu).
            _logger.error(
                "Gagal mencatat mutasi jual produk #%s untuk POS #%s (stok kemungkinan berubah).",
                item["id"], pos["id"], exc_info=True,
            )


def _rebuild_transaksi_barber_hari(tenant_id: int, barber_id: int, tanggal: str) -> None:
    """REUSE pola manual_customer_db._buat_transaksi_gabungan()/
    _sinkronkan_transaksi_hari() (ditulis ulang di sini karena sumber
    datanya tabel pos_transaksi, bukan manual_customer_transaksi) --
    hapus baris `transaksi` lama (kalau ada) untuk barber+tanggal ini yang
    berasal dari POS, lalu bangun ULANG dari SELURUH transaksi POS lunas
    hari itu (qty service dijumlahkan lintas customer) -- hasilnya SELALU 1
    baris transaksi per barber per hari, PERMINTAAN Owner eksplisit."""
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM pos_transaksi WHERE tenant_id = ? AND barber_id = ? AND tanggal = ? AND status = 'lunas'",
            (tenant_id, barber_id, tanggal),
        ).fetchall()]
    transaksi_lama = {r["transaksi_id"] for r in rows if r.get("transaksi_id") is not None}

    agregat = {}
    for r in rows:
        with get_conn() as conn:
            service_ids = [x["service_id"] for x in conn.execute(
                "SELECT service_id FROM pos_transaksi_service WHERE pos_transaksi_id = ?", (r["id"],),
            ).fetchall()]
        for sid in service_ids:
            agregat[sid] = agregat.get(sid, 0) + 1

    for tid in transaksi_lama:
        hapus_transaksi(tid)

    if not agregat:
        with get_conn() as conn:
            conn.execute(
                "UPDATE pos_transaksi SET transaksi_id = NULL WHERE tenant_id = ? AND barber_id = ? AND tanggal = ?",
                (tenant_id, barber_id, tanggal),
            )
        return

    items = [{"service_id": sid, "jumlah": qty} for sid, qty in agregat.items()]
    transaksi_id = tambah_transaksi(tanggal=tanggal, barber_id=barber_id, items=items, sumber="pos")
    with get_conn() as conn:
        conn.execute(
            "UPDATE pos_transaksi SET transaksi_id = ? "
            "WHERE tenant_id = ? AND barber_id = ? AND tanggal = ? AND status = 'lunas'",
            (transaksi_id, tenant_id, barber_id, tanggal),
        )


def reset_hari_pos(tenant_id: int, tanggal: str) -> None:
    """Dipanggil manual_customer_db.reset_hari() (tombol "Reset Semua
    Transaksi Hari Ini") kalau mode tanggal ini == "pos" -- hapus baris
    `transaksi` hasil rebuild (kalau ada) + SELURUH baris pos_transaksi
    tanggal ini. Mutasi stok produk yang SUDAH tercatat (database.
    produk_mutasi) SENGAJA TIDAK ikut dibalik di sini -- TIDAK pernah jadi
    bagian mode Input Data (lihat docstring modul), Admin membalikkannya
    sendiri lewat Produk > Riwayat Mutasi kalau memang perlu (tombol Hapus
    Mutasi yang sudah ada, konsisten dengan cara produk dikelola di seluruh
    aplikasi ini)."""
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, transaksi_id FROM pos_transaksi WHERE tenant_id = ? AND tanggal = ?",
            (tenant_id, tanggal),
        ).fetchall()]
    for tid in {r["transaksi_id"] for r in rows if r.get("transaksi_id") is not None}:
        hapus_transaksi(tid)
    with get_conn() as conn:
        conn.execute("DELETE FROM pos_transaksi WHERE tenant_id = ? AND tanggal = ?", (tenant_id, tanggal))


# ---------------------------------------------------------------------------
# Tab "Transaksi Hari Ini" -- gabungan Booking (lunas/terverifikasi) + POS
# ---------------------------------------------------------------------------

def get_transaksi_hari_ini(tenant_id: int, tanggal: str) -> dict:
    """{"service": [...], "produk": [...]} -- HANYA transaksi lunas/
    terverifikasi (PERMINTAAN Owner), field ringkas saja (nama barber/
    service/produk, nominal, jam) TANPA komisi/tips (PERMINTAAN Owner --
    "dihitung sama, tapi jangan tampilkan")."""
    import booking_db  # import lokal: hindari import siklik (booking_db tidak perlu tahu pos_db sama sekali)

    service_items = []
    produk_items = []

    with get_conn() as conn:
        pos_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM pos_transaksi WHERE tenant_id = ? AND tanggal = ? AND status = 'lunas' ORDER BY jam ASC",
            (tenant_id, tanggal),
        ).fetchall()]
    for r in pos_rows:
        pos = _lengkapi(r)
        if pos["daftar_service"]:
            service_items.append({
                "sumber": "pos", "jam": pos["jam"], "nama_barber": pos["nama_barber"],
                "daftar_service": ", ".join(s["nama"] for s in pos["daftar_service"]),
                "nominal": sum(s["harga"] for s in pos["daftar_service"]),
            })
        for p in pos["daftar_produk"]:
            produk_items.append({
                "sumber": "pos", "jam": pos["jam"], "nama_produk": p["nama"],
                "jumlah": p["jumlah"], "nominal": p["harga_satuan"] * p["jumlah"],
            })

    for b in booking_db.get_booking_list(tenant_id=tenant_id, tanggal=tanggal, status_booking="aktif"):
        if b.get("status_pembayaran") != "terverifikasi":
            continue
        service_items.append({
            "sumber": "booking", "jam": b["jam_mulai"], "nama_barber": b["nama_barber"],
            "daftar_service": b["daftar_service"], "nominal": b["total_harga"],
        })

    service_items.sort(key=lambda x: x["jam"])
    produk_items.sort(key=lambda x: x["jam"])
    return {"service": service_items, "produk": produk_items}
