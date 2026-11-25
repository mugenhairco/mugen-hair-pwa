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
rekap_gabungan_db.rebuild_transaksi_pos_booking_barber_hari() menghapus
baris `transaksi` lama (kalau ada) untuk barber+tanggal itu lalu
membangunnya ULANG dari SELURUH transaksi POS lunas HARI ITU DIGABUNG
dengan kontribusi Booking (Online/Mandiri) yang sama (qty service
dijumlahkan lintas KEDUA sumber, PERMINTAAN Owner lanjutan -- lihat
rekap_gabungan_db.py) -- hasilnya SELALU 1 baris transaksi per barber per
hari di Rekap, walau banyak customer walk-in berbeda dibayar sepanjang
hari (real-time, TANPA tombol "Tutup & Simpan" terpisah).

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
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import gateway_client_base
import manual_customer_db
import payment_provider_client
import push_service
import rekap_gabungan_db
import snap_payment_db
from database import (get_barber, get_conn, get_produk, get_service, get_setting, get_stok_produk,
                       hapus_mutasi_produk, jual_produk, set_setting)

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
        # BUGFIX PERFORMA (audit "susuri menyeluruh, apa saja yang membebani
        # server" -- kategori sama dengan idx_snap_payment_transactions_
        # booking_id yang sudah diperbaiki sebelumnya): tabel ini TIDAK
        # PERNAH punya index di kolom yang di-query terus-menerus padahal
        # sudah dipakai sejak awal fitur POS -- rekap_gabungan_db.py::
        # _ambil_kontribusi_pos() (JOIN pos_transaksi WHERE tenant_id+
        # tanggal+status, dipanggil SETIAP kali POS/Booking berubah) dan
        # get_transaksi_hari_ini() (tenant_id+tanggal, tampilan "Transaksi
        # Hari Ini") keduanya full table scan tanpa ini. Murni mempercepat
        # baca, TIDAK mengubah perilaku apa pun.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_transaksi_tenant_tanggal ON pos_transaksi(tenant_id, tanggal)")
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
    CANCELLED, ATAU manual lewat tombol "Batalkan" Kasir (routers/pos.py) --
    transaksi POS yang gatewaynya gagal/kedaluwarsa/dibatalkan, TIDAK PERNAH
    menyentuh Rekap/stok produk (belum pernah 'lunas')."""
    pos = get_pos_transaksi(pos_id)
    if pos is None:
        raise ValueError("Transaksi Point of Sale tidak ditemukan.")
    if pos["status"] != "menunggu":
        return pos
    with get_conn() as conn:
        conn.execute("UPDATE pos_transaksi SET status = 'batal', updated_at = ? WHERE id = ?",
                     (datetime.now().isoformat(timespec="seconds"), pos_id))
    # BUGFIX (audit "susuri menyeluruh, apakah ada bug" -- pola PERSIS bug
    # yang sudah diperbaiki di booking_db.py::batalkan_booking()): titik ini
    # SEBELUMNYA hanya mengubah pos_transaksi.status -- transaksi Payment
    # Gateway (snap_payment_transactions) milik POS ini TIDAK PERNAH ikut
    # ditandai batal kalau masih CREATED/PENDING saat Kasir klik "Batalkan"
    # manual (webhook FAILED/EXPIRED/CANCELLED dari Faspay sendiri sudah
    # benar lewat snap_webhook.py::terapkan_status_transaksi(), yang
    # memperbarui snap_payment_transactions SEBELUM men-cascade ke sini --
    # jalur ITU sudah aman). Akibatnya KHUSUS jalur manual Kasir: kalau
    # customer TETAP scan & bayar QR/VA setelah Kasir membatalkan, webhook
    # PAID dari Faspay tetap datang & snap_payment_transactions tetap
    # ditandai PAID -- tapi tandai_lunas_dari_gateway() di atas melihat
    # pos_transaksi.status sudah 'batal' (bukan 'menunggu') dan diam-diam
    # no-op. HASIL: uang customer BENAR-BENAR diterima toko, tapi TIDAK
    # ADA stok berkurang, TIDAK ADA baris Rekap -- sama sekali tidak
    # tercatat di aplikasi.
    #
    # Perbaikan: tandai transaksi gateway (kalau ada & masih CREATED/
    # PENDING) jadi CANCELLED di SINI juga, lewat snap_payment_db.
    # update_status() LANGSUNG -- BUKAN snap_webhook.terapkan_status_
    # transaksi() (yang men-cascade balik ke sini lewat _cascade_pos() ->
    # batalkan_pos() untuk status FAILED/EXPIRED/CANCELLED, lihat
    # snap_webhook.py -- kalau dipanggil dari sini akan jadi rekursi tak
    # berujung). update_status() sendiri sudah idempoten & TIDAK men-
    # cascade apa pun, aman dipanggil berkali-kali/dari jalur mana pun.
    transaksi_gateway = snap_payment_db.get_transaksi_terkini_untuk_pos(pos_id)
    if transaksi_gateway is not None and transaksi_gateway["status"] in (
        snap_payment_db.STATUS_CREATED, snap_payment_db.STATUS_PENDING,
    ):
        snap_payment_db.update_status(transaksi_gateway["id"], snap_payment_db.STATUS_CANCELLED, sumber="batalkan_pos_admin")
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
    # FITUR Notifikasi Push "Transaksi POS Baru" (PERMINTAAN Owner, "kerjakan
    # dengan teliti" -- lihat catatan panjang di _kirim_notifikasi_push_pos_
    # lunas() di bawah): titik SATU-SATUNYA tempat pembayaran POS (cash/
    # QRIS manual/gateway, ketiganya lewat _tandai_lunas() ini) benar-benar
    # jadi 'lunas' -- aman dipakai untuk memicu push TANPA risiko dobel
    # (CAS rowcount di atas sudah menjamin blok ini hanya jalan SEKALI per
    # transaksi, sama seperti _proses_setelah_lunas()).
    _jalankan_di_belakang(_kirim_notifikasi_push_pos_lunas, pos)
    return get_pos_transaksi(pos_id)


def _jalankan_di_belakang(fn, *args):
    """PERBAIKAN PERFORMA -- pola SAMA PERSIS booking_db.py::
    _jalankan_di_belakang()/izin_cuti_db.py::_jalankan_di_belakang(): Push
    (pywebpush, timeout 10 detik PER penerima, lihat push_service.py) adalah
    panggilan HTTP KELUAR yang bisa lambat/macet -- dipanggil LANGSUNG di
    jalur checkout POS akan menahan respons Kasir (cash/QRIS manual/
    verifikasi gateway) sampai push-nya selesai/timeout. Dipindah ke thread
    terpisah (daemon -- tidak menahan proses berhenti) supaya respons
    checkout langsung balik begitu DATABASE-nya sendiri selesai; `fn`
    (_kirim_notifikasi_push_pos_lunas() di bawah) SUDAH membungkus isinya
    sendiri dengan try/except (tidak pernah melempar ke pemanggil)."""
    threading.Thread(target=fn, args=args, daemon=True).start()


def _kirim_notifikasi_push_pos_lunas(pos: dict) -> None:
    """FITUR Notifikasi Push "Transaksi POS Baru" (dilaporkan Owner: "Tab
    Transaksi Hari Ini tidak menyuntik data diam-diam kalau ada user lain
    yang input" -- perbaikan SEBELUMNYA, lihat catatan "pos_transaksi" di
    api.js, hanya membuat tab itu fetch ulang PENUH begitu dibuka/dipindah-
    balik lagi, BUKAN real-time sama sekali selama tab itu sedang dilihat.
    "Kerjakan dengan teliti" -- permintaan Owner untuk benar-benar real-
    time, pola SAMA PERSIS booking_db.py::_kirim_notifikasi_push_booking_
    baru() -- best effort, TIDAK PERNAH melempar exception maupun
    menggagalkan checkout utamanya kalau push gagal/belum dikonfigurasi
    (lihat push_service.IS_ENABLED).

    Audiens: role admin/staff SATU tenant ini SAJA (SAMA seperti gerbang
    akses menu Point of Sale sendiri, lihat nav.js: `roles: ["admin",
    "staff"]`, izin "izin_pos_lihat") -- TIDAK ada audiens Barber terpisah
    seperti booking_baru (Barber tidak pernah punya akses menu POS sama
    sekali, lihat nav.js)."""
    tenant_id = pos.get("tenant_id")
    try:
        push_service.kirim_ke_role(
            tenant_id, ["admin", "staff"],
            title="Transaksi POS Baru",
            body=f"{pos.get('nama_barber') or 'Transaksi'} -- Rp {pos.get('total_harga', 0):,}".replace(",", "."),
            url="/app/#/pos",
            # FITUR Auto-Refresh Transaksi Hari Ini via Push: `jenis`
            # diteruskan ke payload push (lihat push_service.py) supaya
            # service-worker.js bisa merelai postMessage ke tab yang
            # terbuka -- app.js lalu memanggil PagePos.suntikTransaksiBaru()
            # kalau #/pos sedang terbuka, TANPA menambah polling/timer
            # jaringan apa pun (murni reaksi atas push yang memang sudah
            # dikirim backend saat transaksi lunas).
            jenis="pos_transaksi_lunas",
            # PERMINTAAN Owner (suntik diam-diam ke Transaksi Hari Ini,
            # BUKAN cuma "muat ulang diam-diam"): kirim baris POS LENGKAP
            # (hasil get_pos_transaksi(), lihat pemanggil fungsi ini) apa
            # adanya -- frontend (pages/pos.js::suntikTransaksiBaru()) sudah
            # punya logika SAMA PERSIS yang dipakai checkout milik sesi
            # sendiri (_suntikTransaksiBaru()) untuk menyisipkannya langsung
            # ke tabel yang sedang tampil TANPA fetch ulang. Lihat catatan
            # panjang soal batas ukuran payload di push_service.py.
            data=pos,
        )
    except Exception as e:
        _logger.error("Notifikasi push transaksi POS #%s GAGAL disiapkan: %s: %s",
                       pos.get("id"), type(e).__name__, e)


def _proses_setelah_lunas(pos: dict) -> None:
    """Pecah SATU pembayaran yang baru lunas jadi dua cascade terpisah
    (PERMINTAAN Owner -- "satu kali scan untuk Service + Produk, tapi
    rekapannya nanti terpisah"): Service -> rebuild baris Rekap gabungan
    POS+Booking 1x/barber/hari (lihat rekap_gabungan_db.py), Produk ->
    reuse TOTAL database.jual_produk() per item (TIDAK diagregasi, lihat
    docstring modul)."""
    for b in pos["daftar_barber"]:
        if b["barber_id"] is not None:
            rekap_gabungan_db.rebuild_transaksi_pos_booking_barber_hari(pos["tenant_id"], b["barber_id"], pos["tanggal"])
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


# PERMINTAAN Owner (gabung POS+Booking jadi 1 baris Rekap per barber/hari):
# bekas _transaksi_lama_pos()/_rebuild_transaksi_barber_hari() di sini
# sudah DIHAPUS -- gantikan dengan rekap_gabungan_db.py yang membaca KEDUA
# sumber (POS + Booking) sekaligus setiap kali salah satunya berubah,
# lihat modul itu untuk detail lengkap.


def get_rekap_transaksi_ids(pos_id: int) -> list:
    """FITUR "Rekap tidak refresh, cuma tambah baris diam-diam" (PERMINTAAN
    Owner, lihat docstring routers/rekap.py::rekap_transaksi_baris() --
    "pola sama Transaksi Hari Ini POS/Booking Mandiri", TAPI sebelumnya
    HANYA pernah dipakai Input Data, tidak pernah benar-benar disambungkan
    ke POS): dipanggil endpoint lunas (bayar-cash/verifikasi/status PAID)
    SETELAH transaksi POS ini lunas -- cari id baris `transaksi` (Rekap)
    milik SETIAP barber yang terlibat transaksi ini untuk tanggal yang
    sama, supaya frontend bisa suntik baris itu ke Rekap (kalau sedang
    terbuka sesi ini) TANPA fetch ulang seluruh daftar/skeleton loading.
    Read-only murni -- TIDAK membangun ulang apa pun (itu sudah terjadi di
    _proses_setelah_lunas()/rekap_gabungan_db.py), aman dipanggil kapan
    saja SETELAH status 'lunas'. `sumber` dicari sebagai
    rekap_gabungan_db.SUMBER_POS_BOOKING (PERMINTAAN Owner: baris Rekap
    POS+Booking sekarang digabung jadi satu, lihat modul itu)."""
    pos = get_pos_transaksi(pos_id)
    if pos is None:
        return []
    barber_ids = {b["barber_id"] for b in pos["daftar_barber"] if b.get("barber_id") is not None}
    if not barber_ids:
        return []
    with get_conn() as conn:
        placeholder = ", ".join("?" for _ in barber_ids)
        rows = conn.execute(
            f"SELECT id FROM transaksi WHERE tanggal = ? AND sumber = ? AND barber_id IN ({placeholder})",
            [pos["tanggal"], rekap_gabungan_db.SUMBER_POS_BOOKING, *barber_ids],
        ).fetchall()
    return [r["id"] for r in rows]


def reset_hari_pos(tenant_id: int, tanggal: str) -> None:
    """Dipanggil manual_customer_db.reset_hari() (tombol "Reset Semua
    Transaksi Hari Ini") kalau mode tanggal ini == "pos" -- hapus SELURUH
    baris pos_transaksi tanggal ini (cascade otomatis menghapus service/
    produk/tips anaknya), LALU bangun ULANG baris Rekap gabungan POS+
    Booking untuk SETIAP barber yang pernah muncul di pos_transaksi_service
    tanggal ini (BUKAN hapus manual -- PERMINTAAN Owner: kontribusi Booking
    yang sah untuk barber+tanggal yang SAMA tidak boleh ikut hilang cuma
    gara-gara Admin mereset data POS saja; urutan sengaja dibalik supaya
    pos_transaksi SUDAH kosong saat rebuild membaca ulang, hasilnya
    otomatis menyusut ke kontribusi Booking saja kalau ada, atau hilang
    total kalau Booking juga kosong). Mutasi stok produk yang SUDAH
    tercatat (database.produk_mutasi) SENGAJA TIDAK ikut dibalik di sini --
    TIDAK pernah jadi bagian mode Input Data (lihat docstring modul),
    Admin membalikkannya sendiri lewat Produk > Riwayat Mutasi kalau
    memang perlu (tombol Hapus Mutasi yang sudah ada, konsisten dengan
    cara produk dikelola di seluruh aplikasi ini)."""
    with get_conn() as conn:
        barber_ids = [r["barber_id"] for r in conn.execute(
            "SELECT DISTINCT pts.barber_id FROM pos_transaksi_service pts "
            "JOIN pos_transaksi pt ON pt.id = pts.pos_transaksi_id "
            "WHERE pt.tenant_id = ? AND pt.tanggal = ? AND pts.barber_id IS NOT NULL",
            (tenant_id, tanggal),
        ).fetchall()]
        conn.execute("DELETE FROM pos_transaksi WHERE tenant_id = ? AND tanggal = ?", (tenant_id, tanggal))
    for bid in barber_ids:
        rekap_gabungan_db.rebuild_transaksi_pos_booking_barber_hari(tenant_id, bid, tanggal)


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
      terlibat transaksi ini (lihat rekap_gabungan_db.py), TANPA transaksi
      yang baru dihapus (kontribusi Booking di barber+tanggal yang sama,
      kalau ada, tetap ikut terbaca ulang -- tidak ikut terhapus)."""
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
            rekap_gabungan_db.rebuild_transaksi_pos_booking_barber_hari(tenant_id, b["barber_id"], pos["tanggal"])


# ---------------------------------------------------------------------------
# Tab "Transaksi Hari Ini" -- gabungan Booking (lunas/terverifikasi) + POS
# ---------------------------------------------------------------------------

def get_transaksi_hari_ini(tenant_id: int, tanggal: str) -> dict:
    """{"service": [...], "produk": [...]} -- HANYA transaksi lunas/
    terverifikasi (PERMINTAAN Owner), field ringkas saja (nama barber/
    service/produk, nominal, tips, jam) TANPA komisi (PERMINTAAN Owner
    -- tips SEKARANG ditampilkan terpisah per baris, lihat "tips" di
    bawah; komisi tetap tidak pernah ditampilkan di sini).

    FITUR Rekonsiliasi Pembayaran Booking (PERMINTAAN Owner): booking
    yang dibayar di muka untuk layanan di tanggal LAIN (customer booking
    hari ini untuk besok, bayar QRIS/Gateway hari ini juga) sebelumnya
    bikin "Rincian Pembayaran Hari Ini"/Total Keseluruhan tidak sinkron
    dengan uang fisik/settlement yang BENERAN diterima hari itu (uang
    yang sudah masuk hari ini malah baru dihitung besok, saat layanannya
    terjadi). Sekarang "rincian_metode"/"total_keseluruhan" dihitung dari
    tanggal PEMBAYARAN diterima (bukan tanggal layanan), dan "penyesuaian"
    (list baris +/- , dipakai pages/pos.js menampilkan rincian warna
    merah) menjelaskan selisihnya secara transparan:
    - "tambah": booking yang pembayarannya diterima tanggal INI untuk
      layanan di tanggal LAIN -- uangnya MASUK ke total hari ini.
    - "kurang": booking untuk LAYANAN tanggal ini yang pembayarannya
      SUDAH diterima di tanggal LAIN -- informasional saja (uangnya
      TIDAK ikut dihitung di total hari ini, sudah benar dari sono lewat
      query tanggal pembayaran di atas, baris "kurang" ini cuma
      menjelaskan KENAPA baris Service-nya tidak nongol di uang)."""
    import booking_db  # import lokal: hindari import siklik (booking_db tidak perlu tahu pos_db sama sekali)

    service_items = []
    produk_items = []
    # Rincian total per metode pembayaran (PERMINTAAN Owner) -- dihitung
    # dari total_harga MENTAH tiap transaksi (service + tips + produk
    # SEKALIGUS, bukan dari service_items/produk_items yang di bawah sudah
    # dipecah per baris tampilan & SENGAJA tidak menyertakan tips).
    rincian_metode = {"gateway": 0, "qris": 0, "cash": 0}

    # FITUR "Detail Transaksi Hari Ini" (PERMINTAAN Owner): rekap per NAMA
    # service digabung dari KEDUA sumber (Kasir walk-in + Booking Online),
    # dijumlahkan satu hari penuh -- {"Dry Cut": {"jumlah": 7, "nominal":
    # 700000}, ...}. Scope-nya SAMA PERSIS service_items di atas (tanggal
    # LAYANAN hari ini, status_pembayaran terverifikasi untuk booking) --
    # BUKAN tanggal pembayaran seperti rincian_metode/total_keseluruhan.
    agregat_service = {}
    total_tips = 0

    def _tambah_agregat(nama, harga):
        a = agregat_service.setdefault(nama, {"jumlah": 0, "nominal": 0})
        a["jumlah"] += 1
        a["nominal"] += harga

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
            for s in b["daftar_service"]:
                _tambah_agregat(s["nama"], s["harga"])
            total_tips += b["tips"]
            service_items.append({
                "sumber": "pos", "pos_id": pos["id"], "jam": pos["jam"],
                # Dipakai dropdown "Filter Barber" di pages/pos.js -- id, BUKAN
                # nama (nama bisa sama antar barber berbeda, walau jarang).
                "barber_id": b["barber_id"], "nama_barber": b["nama"],
                "daftar_service": ", ".join(s["nama"] for s in b["daftar_service"]),
                "nominal": sum(s["harga"] for s in b["daftar_service"]),
                # FITUR Tampilkan Tips (PERMINTAAN Owner): tips tetap TIDAK
                # ikut "nominal" di atas (nominal = harga service murni,
                # dipakai juga filter/rekap lain yang sudah ada) -- kolom
                # terpisah supaya jelas rinciannya, walau "Total Keseluruhan"/
                # rincian_metode di bawah SUDAH menghitungnya sejak awal
                # (dari total_harga mentah, lihat catatan di atas).
                "tips": b["tips"],
            })
        for p in pos["daftar_produk"]:
            produk_items.append({
                "sumber": "pos", "pos_id": pos["id"], "jam": pos["jam"], "nama_produk": p["nama"],
                "jumlah": p["jumlah"], "nominal": p["harga_satuan"] * p["jumlah"],
            })

    # FITUR Rekonsiliasi Pembayaran Booking (PERMINTAAN Owner): daftar
    # Service (appointment hari ini) TETAP berdasarkan tanggal LAYANAN
    # (booking untuk hari ini, siapa saja yang akan datang) -- TIDAK
    # berubah. Yang berubah: uang/rincian_metode TIDAK lagi dihitung dari
    # loop yang sama ini (lihat loop baru di bawah, berdasarkan tanggal
    # PEMBAYARAN diterima) -- loop ini SEKARANG murni membangun daftar
    # tampilan + menandai baris mana yang pembayarannya sudah diterima di
    # tanggal LAIN (dibayar di muka untuk booking tanggal mendatang, atau
    # kasus langka dibayar belakangan) supaya frontend bisa menandainya
    # (font merah, lihat pages/pos.js) -- uangnya SENDIRI sudah/akan
    # dihitung di hari pembayaran yang sebenarnya, BUKAN di sini, supaya
    # tidak dihitung dua kali.
    penyesuaian = []  # [{"arah": "tambah"|"kurang", "nominal": int, "label": str}]
    booking_ids_untuk_rincian = []  # dipakai query booking_items itemized di bawah
    for b in booking_db.get_booking_list(tenant_id=tenant_id, tanggal=tanggal, status_booking="aktif"):
        if b.get("status_pembayaran") != "terverifikasi":
            continue
        booking_ids_untuk_rincian.append(b["id"])
        tanggal_bayar = booking_db.tanggal_wib_dari_timestamp(b.get("pembayaran_diterima_at"))
        dibayar_tanggal_lain = tanggal_bayar if tanggal_bayar and tanggal_bayar != tanggal else None
        service_items.append({
            "sumber": "booking", "jam": b["jam_mulai"],
            "barber_id": b["barber_id"], "nama_barber": b["nama_barber"],
            "daftar_service": b["daftar_service"], "nominal": b["total_harga"],
            # PERMINTAAN Owner: tampilkan nama customer di Transaksi Hari Ini
            # -- HANYA baris sumber="booking" (online maupun kasir_mandiri,
            # keduanya sama-sama tabel `bookings` jadi customer_nama SELALU
            # ada) yang dapat field ini. Baris sumber="pos" (Kasir walk-in,
            # lihat loop pos_rows di atas) SENGAJA TIDAK dapat field ini --
            # form checkout Kasir tidak pernah menanyakan nama customer sama
            # sekali, kolomnya tidak ada di tabel pos_transaksi (beda topik
            # dari permintaan ini, lihat percakapan Owner).
            "nama_customer": b.get("customer_nama"),
            # FITUR Rekonsiliasi Pembayaran Booking: tanggal pembayaran
            # diterima (WIB), HANYA diisi kalau BEDA dari tanggal layanan
            # ini -- pages/pos.js memakainya untuk font merah + keterangan
            # "sudah dibayar tanggal X" di baris ini.
            "dibayar_tanggal_lain": dibayar_tanggal_lain,
        })
        if dibayar_tanggal_lain:
            penyesuaian.append({
                "arah": "kurang", "nominal": b["total_harga"],
                "label": f"{b.get('customer_nama') or b['nama_barber']} -- sudah dibayar tanggal {dibayar_tanggal_lain}",
            })

    # Rincian pembayaran/Total Keseluruhan booking: berdasarkan tanggal
    # PEMBAYARAN diterima (BUKAN tanggal layanan di loop atas) -- supaya
    # cocok dengan rekonsiliasi kas/settlement QRIS-Gateway hari ini
    # (uang yang BENERAN masuk hari ini, termasuk booking yang dibayar di
    # muka untuk layanan tanggal lain, TIDAK termasuk booking hari ini
    # yang sudah dibayar di hari sebelumnya -- lihat
    # booking_db.get_booking_terverifikasi_by_tanggal_bayar()).
    for b in booking_db.get_booking_terverifikasi_by_tanggal_bayar(tenant_id, tanggal):
        metode_b = b.get("metode_pembayaran")
        rincian_metode[metode_b] = rincian_metode.get(metode_b, 0) + (b.get("total_harga") or 0)
        if b["tanggal"] != tanggal:
            penyesuaian.append({
                "arah": "tambah", "nominal": b["total_harga"],
                "label": f"{b.get('customer_nama') or b['nama_barber']} -- booking tanggal {b['tanggal']}",
            })

    # Itemized nama_service+harga per booking HANYA tersedia di tabel
    # booking_items (booking_db.get_booking_list() sendiri cuma mengirim
    # string gabungan tanpa harga per item, lihat daftar_service di atas)
    # -- satu query batch untuk seluruh booking yang masuk service_items
    # hari ini, digabung ke agregat_service yang sama dengan Kasir/POS.
    if booking_ids_untuk_rincian:
        placeholder = ", ".join("?" for _ in booking_ids_untuk_rincian)
        with get_conn() as conn:
            item_rows = conn.execute(
                f"SELECT nama_service, harga FROM booking_items WHERE booking_id IN ({placeholder})",
                booking_ids_untuk_rincian,
            ).fetchall()
        for it in item_rows:
            _tambah_agregat(it["nama_service"], it["harga"])

    rincian_service = sorted(
        [{"nama": nama, "jumlah": v["jumlah"], "nominal": v["nominal"]} for nama, v in agregat_service.items()],
        key=lambda x: -x["nominal"],
    )
    total_produk = sum(p["nominal"] for p in produk_items)

    service_items.sort(key=lambda x: x["jam"])
    produk_items.sort(key=lambda x: x["jam"])
    return {
        "service": service_items, "produk": produk_items,
        "rincian_metode": rincian_metode,
        "total_keseluruhan": sum(rincian_metode.values()),
        "penyesuaian": penyesuaian,
        "rincian_service": rincian_service,
        "total_service": sum(v["nominal"] for v in agregat_service.values()),
        "total_tips": total_tips,
        "total_produk": total_produk,
    }
