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
from database import (get_barber, get_conn, get_produk, get_service, get_setting, get_stok_produk,
                       hapus_mutasi_produk, hapus_transaksi, jual_produk, set_setting, tambah_transaksi)

WIB = ZoneInfo("Asia/Jakarta")

STATUS_VALID = {"menunggu", "lunas", "batal"}
# PERMINTAAN Owner: "Cash" sekarang ditawarkan juga di Point of Sale (kasir
# input nominal uang diterima, sistem hitung kembalian -- lihat
# bayar_cash() di bawah), BUKAN hanya qris/gateway seperti sebelumnya.
METODE_VALID = {"qris", "gateway", "cash"}

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
        # FITUR Cash di POS (PERMINTAAN Owner): nominal uang yang diterima
        # Kasir dari customer + kembalian yang dihitung sistem (uang_diterima
        # - total_harga), lihat bayar_cash(). Nullable (NULL untuk transaksi
        # metode lain), ALTER TABLE guard supaya aman dijalankan berkali-kali
        # terhadap database yang sudah ada.
        kolom_pt = [r["name"] for r in conn.execute("PRAGMA table_info(pos_transaksi)").fetchall()]
        if "uang_diterima" not in kolom_pt:
            conn.execute("ALTER TABLE pos_transaksi ADD COLUMN uang_diterima INTEGER")
        if "kembalian" not in kolom_pt:
            conn.execute("ALTER TABLE pos_transaksi ADD COLUMN kembalian INTEGER")
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
        # FITUR Keranjang Multi-Barber (PERMINTAAN Owner: "anak cukur Barber
        # A, bapak cukur Barber B, mau 1 kali scan" & "tips manual per
        # barber") -- `barber_id` di sini (BUKAN lagi header pos_transaksi)
        # yang menentukan baris service ini milik barber mana, supaya satu
        # checkout/satu pembayaran bisa mencakup BEBERAPA barber sekaligus.
        # Nullable murni supaya ALTER TABLE ini aman dijalankan berkali-kali
        # tanpa backfill (fitur ini baru, belum ada data produksi lama).
        kolom_pts = [r["name"] for r in conn.execute("PRAGMA table_info(pos_transaksi_service)").fetchall()]
        if "barber_id" not in kolom_pts:
            conn.execute("ALTER TABLE pos_transaksi_service ADD COLUMN barber_id INTEGER")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pos_transaksi_barber_tips (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                pos_transaksi_id  INTEGER NOT NULL,
                barber_id         INTEGER NOT NULL,
                tips              INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (pos_transaksi_id) REFERENCES pos_transaksi(id) ON DELETE CASCADE
            )
        """)


# ---------------------------------------------------------------------------
# Toggle Cash khusus POS (PERMINTAAN Owner: "apakah bisa mengaktifkan
# metode cash hanya untuk pos ini, jika diaktifkan yang cash untuk
# booking tidak otomatis aktif?") -- setting TERPISAH dari
# `booking_metode_aktif` (booking_db.py), jadi mengaktifkan Cash untuk
# POS TIDAK PERNAH ikut mengaktifkan Cash untuk Booking publik, atau
# sebaliknya. Disimpan lewat tabel `settings` generik yang sudah ada
# (pola SAMA PERSIS database.py::uang_harian_syarat_aktif_tenant()),
# TIDAK butuh tabel/kolom baru sama sekali.
# ---------------------------------------------------------------------------

def get_pos_cash_aktif(tenant_id: int) -> bool:
    return get_setting("pos_cash_aktif", "0", tenant_id=tenant_id) == "1"


def set_pos_cash_aktif(tenant_id: int, aktif: bool) -> None:
    set_setting("pos_cash_aktif", "1" if aktif else "0", tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# CRUD pos_transaksi
# ---------------------------------------------------------------------------

def _pastikan_barber_tenant_sama(barber_id: int, tenant_id: int) -> None:
    barber = get_barber(barber_id)
    if barber is None or barber.get("tenant_id") != tenant_id:
        raise ValueError("Barber tidak ditemukan.")


def _lengkapi(row: dict) -> dict:
    """PERUBAHAN Keranjang Multi-Barber: `daftar_barber` adalah struktur
    UTAMA sekarang -- list {barber_id, nama, daftar_service, tips}, satu
    entri per barber yang ada di checkout ini (biasanya cuma 1, bisa lebih
    kalau kasir gabung beberapa orang beda barber jadi satu pembayaran).
    `daftar_service`/`nama_barber` di level atas TETAP ada (diratakan dari
    daftar_barber) supaya caller lama (mis. get_transaksi_hari_ini()) tidak
    perlu tahu strukturnya berubah."""
    with get_conn() as conn:
        service_rows = [dict(r) for r in conn.execute(
            "SELECT service_id, barber_id FROM pos_transaksi_service WHERE pos_transaksi_id = ? ORDER BY id ASC",
            (row["id"],),
        ).fetchall()]
        produk_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM pos_transaksi_produk WHERE pos_transaksi_id = ? ORDER BY id ASC",
            (row["id"],),
        ).fetchall()]
        tips_rows = [dict(r) for r in conn.execute(
            "SELECT barber_id, tips FROM pos_transaksi_barber_tips WHERE pos_transaksi_id = ?",
            (row["id"],),
        ).fetchall()]
    tips_per_barber = {t["barber_id"]: t["tips"] for t in tips_rows}

    # Fallback untuk baris LAMA (sebelum fitur ini ada): service_id tanpa
    # barber_id tersimpan (NULL) -- anggap milik header barber_id lama,
    # supaya riwayat yang sudah ada tidak tiba-tiba kosong.
    barber_urutan = []  # jaga urutan kemunculan, bukan sorted
    kelompok = {}  # barber_id -> list service dict
    for r in service_rows:
        bid = r["barber_id"] if r["barber_id"] is not None else row.get("barber_id")
        if bid not in kelompok:
            kelompok[bid] = []
            barber_urutan.append(bid)
        s = get_service(r["service_id"])
        if s is not None:
            kelompok[bid].append({"id": s["id"], "nama": s["nama"], "harga": s["harga"]})

    row["daftar_barber"] = []
    row["daftar_service"] = []
    for bid in barber_urutan:
        barber = get_barber(bid) if bid is not None else None
        row["daftar_barber"].append({
            "barber_id": bid,
            "nama": barber["nama"] if barber else "(barber terhapus)",
            "daftar_service": kelompok[bid],
            "tips": tips_per_barber.get(bid, 0),
        })
        row["daftar_service"].extend(kelompok[bid])
    row["total_tips"] = sum(tips_per_barber.values())

    row["daftar_produk"] = []
    for p in produk_rows:
        produk = get_produk(p["produk_id"])
        row["daftar_produk"].append({
            "id": p["produk_id"], "nama": produk["nama"] if produk else "(produk terhapus)",
            "jumlah": p["jumlah"], "harga_satuan": p["harga_satuan"], "mutasi_id": p.get("mutasi_id"),
        })
    row["nama_barber"] = ", ".join(b["nama"] for b in row["daftar_barber"]) if row["daftar_barber"] else None
    return row


def get_pos_transaksi(pos_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM pos_transaksi WHERE id = ?", (pos_id,)).fetchone()
        return _lengkapi(dict(row)) if row else None


def buat_transaksi(tenant_id: int, jasa_items: list = None, produk_items: list = None,
                    metode_pembayaran: str = None, channel: str = None, bank_code: str = None,
                    dibuat_oleh: str = None) -> dict:
    """FITUR Keranjang Multi-Barber (PERMINTAAN Owner -- "anak cukur Barber
    A, bapak cukur Barber B, mau 1 kali scan" & "tips manual per barber"):
    `jasa_items` = list of {"barber_id": int, "service_ids": list[int],
    "tips": int (opsional, default 0)} -- SATU entri per barber yang
    dipakai di checkout ini (kasir ulang entri ini di keranjang kalau ada
    lebih dari satu customer/barber dalam satu kali pembayaran). `tips`
    MASUK ke total yang ditagihkan (satu kali scan mencakup service +
    tips sekaligus, PERMINTAAN Owner eksplisit: tips manual kasir, bukan
    dihitung/dibagi otomatis sistem).

    `produk_items` = list of {"produk_id": int, "jumlah": int}, TETAP
    tenant-wide (tidak terikat barber manapun, lihat docstring modul).
    Validasi stok di sini MURNI pre-check (snapshot saat checkout dibuat)
    -- cek OTORITATIF sesungguhnya tetap di database.jual_produk() saat
    pembayaran lunas (lihat _proses_setelah_lunas()), supaya race jarang
    (stok berubah di antara checkout dibuat & lunas) tidak pernah membuat
    stok negatif."""
    if metode_pembayaran not in METODE_VALID:
        raise ValueError(f"Metode pembayaran Point of Sale tidak dikenal: {metode_pembayaran}")
    if metode_pembayaran == "gateway" and not channel:
        raise ValueError("Channel (VA/QRIS) wajib diisi untuk metode gateway.")
    jasa_items = jasa_items or []
    produk_items = produk_items or []
    if not jasa_items and not produk_items:
        raise ValueError("Pilih minimal satu Service atau Produk.")

    total = 0
    jasa_bersih = []  # [{"barber_id": int, "service_ids": [...], "tips": int}]
    for item in jasa_items:
        bid = item.get("barber_id")
        sids = item.get("service_ids") or []
        tips = int(item.get("tips") or 0)
        if bid is None:
            raise ValueError("Barber wajib dipilih untuk setiap entri di keranjang.")
        if not sids:
            raise ValueError("Pilih minimal satu Service untuk setiap barber di keranjang.")
        if tips < 0:
            raise ValueError("Tips tidak boleh negatif.")
        _pastikan_barber_tenant_sama(bid, tenant_id)
        for sid in sids:
            s = get_service(sid)
            if s is None or (s.get("tenant_id") is not None and s.get("tenant_id") != tenant_id):
                raise ValueError(f"Service #{sid} tidak ditemukan.")
            total += s["harga"]
        total += tips
        jasa_bersih.append({"barber_id": bid, "service_ids": sids, "tips": tips})

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
    if jasa_bersih:
        manual_customer_db.pastikan_mode(tenant_id, tanggal, "pos")

    # Header `barber_id` (legacy, murni kemudahan tampilan): diisi HANYA
    # kalau checkout ini cuma mencakup SATU barber (kasus paling umum) --
    # NULL kalau lintas-barber, supaya tidak menyesatkan (lihat
    # _lengkapi(), sumber kebenaran sesungguhnya SEKARANG daftar_barber,
    # dibangun dari pos_transaksi_service.barber_id per baris).
    barber_unik = {it["barber_id"] for it in jasa_bersih}
    header_barber_id = next(iter(barber_unik)) if len(barber_unik) == 1 else None

    now = datetime.now().isoformat(timespec="seconds")
    jam = _sekarang_wib().strftime("%H:%M")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO pos_transaksi (tenant_id, tanggal, jam, barber_id, metode_pembayaran, channel, "
            "status, total_harga, dibuat_oleh, created_at) VALUES (?, ?, ?, ?, ?, ?, 'menunggu', ?, ?, ?)",
            (tenant_id, tanggal, jam, header_barber_id, metode_pembayaran, channel, total, dibuat_oleh, now),
        )
        pos_id = cur.lastrowid
        for item in jasa_bersih:
            for sid in item["service_ids"]:
                conn.execute(
                    "INSERT INTO pos_transaksi_service (pos_transaksi_id, service_id, barber_id) VALUES (?, ?, ?)",
                    (pos_id, sid, item["barber_id"]),
                )
            if item["tips"] > 0:
                conn.execute(
                    "INSERT INTO pos_transaksi_barber_tips (pos_transaksi_id, barber_id, tips) VALUES (?, ?, ?)",
                    (pos_id, item["barber_id"], item["tips"]),
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


def bayar_cash(pos_id: int, tenant_id: int, uang_diterima: int) -> dict:
    """Tombol "Selesaikan Transaksi" di layar Kasir (metode Cash) -- Kasir
    input nominal uang yang benar-benar diterima dari customer, sistem
    menghitung kembalian (uang_diterima - total_harga) lalu transaksi
    LANGSUNG lunas (TIDAK ada status menunggu konfirmasi provider/kasir
    lain, uang tunai sudah diterima di tempat SAAT itu juga)."""
    pos = get_pos_transaksi(pos_id)
    if pos is None or pos["tenant_id"] != tenant_id:
        raise ValueError("Transaksi Point of Sale tidak ditemukan.")
    if pos["metode_pembayaran"] != "cash":
        raise ValueError("Pembayaran Cash hanya berlaku untuk transaksi metode Cash.")
    if pos["status"] != "menunggu":
        raise ValueError("Transaksi ini sudah diproses sebelumnya.")
    uang_diterima = int(uang_diterima or 0)
    if uang_diterima < pos["total_harga"]:
        raise ValueError("Uang diterima kurang dari total pembayaran.")
    kembalian = uang_diterima - pos["total_harga"]
    with get_conn() as conn:
        conn.execute(
            "UPDATE pos_transaksi SET uang_diterima = ?, kembalian = ? WHERE id = ?",
            (uang_diterima, kembalian, pos_id),
        )
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
    for b in pos["daftar_barber"]:
        if b["barber_id"] is not None:
            _rebuild_transaksi_barber_hari(pos["tenant_id"], b["barber_id"], pos["tanggal"])
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


def _transaksi_lama_pos(barber_id: int, tanggal: str):
    """Cari baris `transaksi` (Rekap) hasil rebuild POS SEBELUMNYA untuk
    barber+tanggal ini -- dicari langsung lewat barber_id+tanggal+sumber='pos'
    (BUKAN lagi lewat pos_transaksi.transaksi_id, kolom header itu sudah
    tidak punya arti tunggal sejak satu pos_transaksi bisa mencakup
    BEBERAPA barber sekaligus -- lihat FITUR Keranjang Multi-Barber)."""
    with get_conn() as conn:
        return [r["id"] for r in conn.execute(
            "SELECT id FROM transaksi WHERE barber_id = ? AND tanggal = ? AND sumber = 'pos'",
            (barber_id, tanggal),
        ).fetchall()]


def _rebuild_transaksi_barber_hari(tenant_id: int, barber_id: int, tanggal: str) -> None:
    """REUSE pola manual_customer_db._buat_transaksi_gabungan()/
    _sinkronkan_transaksi_hari() (ditulis ulang di sini karena sumber
    datanya tabel pos_transaksi, bukan manual_customer_transaksi) --
    hapus baris `transaksi` lama (kalau ada) untuk barber+tanggal ini yang
    berasal dari POS, lalu bangun ULANG dari SELURUH transaksi POS lunas
    hari itu (qty service dijumlahkan lintas customer, tips dijumlahkan
    lintas customer) -- hasilnya SELALU 1 baris transaksi per barber per
    hari, PERMINTAAN Owner eksplisit. Dipanggil per-barber (BUKAN per
    pos_transaksi) -- satu pos_transaksi lintas-barber memicu ini
    SEKALI untuk SETIAP barber yang terlibat (lihat _proses_setelah_lunas())."""
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

    for tid in _transaksi_lama_pos(barber_id, tanggal):
        hapus_transaksi(tid)

    if not agregat:
        return

    items = [{"service_id": sid, "jumlah": qty} for sid, qty in agregat.items()]
    tambah_transaksi(tanggal=tanggal, barber_id=barber_id, items=items, tips=total_tips, sumber="pos")


def reset_hari_pos(tenant_id: int, tanggal: str) -> None:
    """Dipanggil manual_customer_db.reset_hari() (tombol "Reset Semua
    Transaksi Hari Ini") kalau mode tanggal ini == "pos" -- hapus baris
    `transaksi` hasil rebuild (kalau ada, untuk SETIAP barber yang pernah
    muncul di pos_transaksi_service tanggal ini) + SELURUH baris
    pos_transaksi tanggal ini (cascade otomatis menghapus service/produk/
    tips anaknya). Mutasi stok produk yang SUDAH tercatat (database.
    produk_mutasi) SENGAJA TIDAK ikut dibalik di sini -- TIDAK pernah jadi
    bagian mode Input Data (lihat docstring modul), Admin membalikkannya
    sendiri lewat Produk > Riwayat Mutasi kalau memang perlu (tombol Hapus
    Mutasi yang sudah ada, konsisten dengan cara produk dikelola di seluruh
    aplikasi ini)."""
    with get_conn() as conn:
        barber_ids = [r["barber_id"] for r in conn.execute(
            "SELECT DISTINCT pts.barber_id FROM pos_transaksi_service pts "
            "JOIN pos_transaksi pt ON pt.id = pts.pos_transaksi_id "
            "WHERE pt.tenant_id = ? AND pt.tanggal = ? AND pts.barber_id IS NOT NULL",
            (tenant_id, tanggal),
        ).fetchall()]
    for bid in barber_ids:
        for tid in _transaksi_lama_pos(bid, tanggal):
            hapus_transaksi(tid)
    with get_conn() as conn:
        conn.execute("DELETE FROM pos_transaksi WHERE tenant_id = ? AND tanggal = ?", (tenant_id, tanggal))


def hapus_transaksi_lunas(pos_id: int, tenant_id: int) -> None:
    """Tombol Hapus per baris di tab "Transaksi Hari Ini" (PERMINTAAN
    Owner: transaksi yang terlanjur salah input bisa langsung dihapus baris
    itu saja, TANPA perlu "Reset Semua Transaksi Hari Ini") -- HANYA
    berlaku untuk transaksi POS yang SUDAH 'lunas' (satu-satunya status
    yang tampil di tab itu, lihat get_transaksi_hari_ini()). Membalikkan
    SEMUA efek lunas:
    - Produk: reuse TOTAL database.hapus_mutasi_produk() per item (SAMA
      PERSIS cara Admin membalikkan mutasi lewat Produk > Riwayat Mutasi)
      -- bisa DITOLAK (ValueError) kalau stoknya sudah terlanjur kepakai
      di mutasi berikutnya, lihat docstring fungsi itu. Dijalankan
      SEBELUM pos_transaksi dihapus supaya penolakan ini tidak meninggalkan
      state setengah jalan (pos_transaksi UTUH kalau ValueError dilempar).
    - Service: Rekap barber+hari di-hitung ULANG untuk SETIAP barber yang
      terlibat transaksi ini (lihat _rebuild_transaksi_barber_hari()),
      TANPA transaksi yang baru dihapus."""
    pos = get_pos_transaksi(pos_id)
    if pos is None or pos["tenant_id"] != tenant_id:
        raise ValueError("Transaksi Point of Sale tidak ditemukan.")
    if pos["status"] != "lunas":
        raise ValueError("Hanya transaksi yang sudah lunas yang bisa dihapus dari sini.")

    for item in pos["daftar_produk"]:
        if item.get("mutasi_id") is not None:
            hapus_mutasi_produk(item["mutasi_id"])

    with get_conn() as conn:
        conn.execute("DELETE FROM pos_transaksi WHERE id = ?", (pos_id,))

    for b in pos["daftar_barber"]:
        if b["barber_id"] is not None:
            _rebuild_transaksi_barber_hari(tenant_id, b["barber_id"], pos["tanggal"])


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
    # Rincian total per metode pembayaran (PERMINTAAN Owner) -- dihitung
    # dari total_harga MENTAH tiap transaksi (service + tips + produk
    # SEKALIGUS, bukan dari service_items/produk_items yang di bawah sudah
    # dipecah per baris tampilan & SENGAJA tidak menyertakan tips).
    rincian_metode = {"gateway": 0, "qris": 0, "cash": 0}

    with get_conn() as conn:
        pos_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM pos_transaksi WHERE tenant_id = ? AND tanggal = ? AND status = 'lunas' ORDER BY jam ASC",
            (tenant_id, tanggal),
        ).fetchall()]
    for r in pos_rows:
        rincian_metode[r["metode_pembayaran"]] = rincian_metode.get(r["metode_pembayaran"], 0) + r["total_harga"]
        pos = _lengkapi(r)
        # Satu BARIS per BARBER (bukan lagi per pos_transaksi) -- checkout
        # lintas-barber (FITUR Keranjang Multi-Barber) ditampilkan terpisah
        # per barber supaya "Barber"/"Service" tetap jelas siapa mengerjakan
        # apa, walau satu pembayaran/satu scan mencakup semuanya sekaligus.
        # `pos_id` disertakan (HANYA utk sumber="pos") supaya tombol Hapus
        # tahu transaksi POS mana yang mau dihapus -- menghapus salah SATU
        # barisnya (service ATAU produk) menghapus SELURUH transaksi POS
        # itu (satu kesatuan satu pembayaran, lihat hapus_transaksi_lunas()).
        for b in pos["daftar_barber"]:
            if not b["daftar_service"]:
                continue
            service_items.append({
                "sumber": "pos", "pos_id": pos["id"], "jam": pos["jam"], "nama_barber": b["nama"],
                "daftar_service": ", ".join(s["nama"] for s in b["daftar_service"]),
                "nominal": sum(s["harga"] for s in b["daftar_service"]),
            })
        for p in pos["daftar_produk"]:
            produk_items.append({
                "sumber": "pos", "pos_id": pos["id"], "jam": pos["jam"], "nama_produk": p["nama"],
                "jumlah": p["jumlah"], "nominal": p["harga_satuan"] * p["jumlah"],
            })

    for b in booking_db.get_booking_list(tenant_id=tenant_id, tanggal=tanggal, status_booking="aktif"):
        if b.get("status_pembayaran") != "terverifikasi":
            continue
        metode_b = b.get("metode_pembayaran")
        rincian_metode[metode_b] = rincian_metode.get(metode_b, 0) + (b.get("total_harga") or 0)
        service_items.append({
            "sumber": "booking", "jam": b["jam_mulai"], "nama_barber": b["nama_barber"],
            "daftar_service": b["daftar_service"], "nominal": b["total_harga"],
        })

    service_items.sort(key=lambda x: x["jam"])
    produk_items.sort(key=lambda x: x["jam"])
    return {
        "service": service_items, "produk": produk_items,
        "rincian_metode": rincian_metode,
        "total_keseluruhan": sum(rincian_metode.values()),
    }
