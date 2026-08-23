"""transaction_report_db.py — Riwayat Transaksi Super Admin (Implementasi
Payment Gateway & Riwayat Transaksi Multi-Tenant)
=============================================================================
Lapisan LAPORAN read-only lintas-tenant untuk Super Admin -- MURNI
menggabungkan dua sumber yang SUDAH ADA (booking_gateway_db.py untuk
transaksi booking, billing_invoice_db.py untuk invoice langganan SaaS) jadi
SATU bentuk tampilan yang seragam, TIDAK menambah tabel baru, TIDAK
mengubah cara kerja/skema kedua modul sumbernya sama sekali. Ini BUKAN
"business logic ketiga" yang menyatukan dua sistem -- murni presentasi
untuk monitoring, sesuai instruksi arsitektur ("Riwayat transaksi" tetap
terpisah per modul, laporan Super Admin ini hanya MEMBACA keduanya).

Digabung di PYTHON (bukan SQL UNION) supaya tidak bergantung pada dialek
SQLite/PostgreSQL yang sama untuk sintaks UNION lintas tabel dengan kolom
berbeda -- volume transaksi platform ini kecil (SaaS niche), performa
gabung-di-memori bukan masalah.

Status pembayaran DINORMALISASI ke satu kosakata Indonesia (lihat
_STATUS_LANGGANAN_KE_UNIFIED) HANYA untuk keperluan tampilan/filter di
laporan ini -- TIDAK PERNAH menulis balik ke subscription_invoices/
booking_payment_transactions, kolom `status` asli kedua tabel itu TETAP
apa adanya."""

import billing_db
import billing_invoice_db
import booking_gateway_db
import tenant_db

JENIS_VALID = {"booking", "langganan"}
STATUS_UNIFIED_VALID = {"menunggu_pembayaran", "diproses", "berhasil", "gagal", "kedaluwarsa", "dibatalkan", "refund"}

_STATUS_LANGGANAN_KE_UNIFIED = {
    "pending": "menunggu_pembayaran",
    "paid": "berhasil",
    "denied": "gagal",
    "cancelled": "dibatalkan",
    "expired": "kedaluwarsa",
}

# Riwayat Langganan Tenant / Riwayat Booking Tenant (restrukturisasi Super
# Admin, dua daftar terpisah): label "Jenis Transaksi" yang eksplisit untuk
# tiap baris -- MURNI turunan tampilan dari status_unified/perbandingan
# `urutan` paket, TIDAK ADA kolom baru di subscription_invoices/
# booking_payment_transactions, TIDAK menyentuh billing.py::checkout()/
# downgrade() sama sekali. "Downgrade" & "Refund" SENGAJA TIDAK ADA di sini
# -- downgrade() tidak pernah lewat Payment Gateway (gratis, tidak ada
# invoice sama sekali) dan subscription_invoices belum punya status
# "refund" (belum ada fitur refund langganan), jadi keduanya bukan
# peristiwa pembayaran nyata yang bisa dilaporkan di ledger ini.
_STATUS_LANGGANAN_NON_PAID_KE_JENIS = {
    "pending": "Menunggu Pembayaran",
    "denied": "Pembayaran Gagal",
    "cancelled": "Dibatalkan",
    "expired": "Kedaluwarsa",
}

_STATUS_BOOKING_KE_JENIS = {
    "berhasil": "Payment Booking",
    "refund": "Refund Booking",
    "gagal": "Pembayaran Gagal",
    "kedaluwarsa": "Expired",
    "dibatalkan": "Dibatalkan",
    "menunggu_pembayaran": "Menunggu Pembayaran",
    "diproses": "Diproses",
}


def _urutan_paket_map() -> dict:
    return {p["kode"]: p["urutan"] for p in billing_db.list_packages(hanya_aktif=False)}


def _isi_jenis_transaksi_langganan(baris_langganan: list) -> None:
    """Mengisi field `jenis_transaksi` (Langganan Baru/Perpanjangan
    Langganan/Upgrade Paket/dst) di tempat (in-place) -- HARUS dipanggil
    dengan SELURUH invoice tenant terkait (bukan hasil yang sudah
    difilter), supaya "invoice paid pertama tenant ini" & "paket
    sebelumnya" dihitung dari riwayat lengkap, bukan dari potongan hasil
    filter tanggal/status yang kebetulan dipakai Super Admin saat itu."""
    urutan_paket = _urutan_paket_map()
    per_tenant: dict[int, list] = {}
    for b in baris_langganan:
        per_tenant.setdefault(b["tenant_id"], []).append(b)

    for daftar in per_tenant.values():
        # Tiebreak dengan `id` (bukan cuma `created_at`) -- dua invoice
        # bisa lahir di detik yang sama (mis. dua checkout beruntun cepat),
        # `created_at` (timespec detik) saja bisa seri lalu jatuh balik ke
        # urutan asal daftar (ORDER BY id DESC dari billing_invoice_db.
        # list_invoices()), yang KEBALIK dari urutan kronologis sungguhan.
        daftar_urut = sorted(daftar, key=lambda b: (b["created_at"], b["id"]))
        urutan_sebelumnya = None
        for b in daftar_urut:
            if b["status_asli"] != "paid":
                b["jenis_transaksi"] = _STATUS_LANGGANAN_NON_PAID_KE_JENIS.get(b["status_asli"], b["status_asli"])
                continue
            urutan_sekarang = urutan_paket.get(b["package_kode"])
            if urutan_sebelumnya is None:
                b["jenis_transaksi"] = "Langganan Baru"
            elif urutan_sekarang is not None and urutan_sekarang > urutan_sebelumnya:
                b["jenis_transaksi"] = "Upgrade Paket"
            else:
                # Sama, atau lebih rendah (downgrade lewat checkout bukan
                # kategori yang dilaporkan -- lihat catatan di atas modul):
                # tetap dicatat sebagai Perpanjangan Langganan.
                b["jenis_transaksi"] = "Perpanjangan Langganan"
            urutan_sebelumnya = urutan_sekarang if urutan_sekarang is not None else urutan_sebelumnya


def _tenant_nama_map() -> dict:
    return {t["id"]: t["nama_barbershop"] for t in tenant_db.list_tenants()}


def _dari_booking(row: dict) -> dict:
    return {
        "jenis": "booking",
        "id": row["id"],
        "nomor_transaksi": row["nomor_transaksi"],
        "tanggal": row["created_at"],
        "tenant_id": row["tenant_id"],
        "tenant_nama": row["tenant_nama"],
        "customer_nama": row["customer_nama"],
        "booking_id": row["booking_id"],
        "barber_nama": row["barber_nama"],
        "layanan": row["layanan"],
        "nominal": row["nominal"],
        "metode_pembayaran": row["metode_pembayaran"],
        "channel_pembayaran": row["channel_pembayaran"],
        "status_unified": row["status_pembayaran"],
        "status_asli": row["status_pembayaran"],
        "jenis_transaksi": _STATUS_BOOKING_KE_JENIS.get(row["status_pembayaran"], row["status_pembayaran"]),
        "transaction_id_provider": row["transaction_id_provider"],
        "reference_id_provider": row["reference_id_provider"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "paid_at": row["paid_at"],
    }


def _dari_langganan(row: dict, nama_tenant: dict) -> dict:
    return {
        "jenis": "langganan",
        "id": row["id"],
        "nomor_transaksi": row["nomor_invoice"],
        "tanggal": row["created_at"],
        "tenant_id": row["tenant_id"],
        "tenant_nama": nama_tenant.get(row["tenant_id"], "-"),
        "customer_nama": None,
        "booking_id": None,
        "barber_nama": None,
        "layanan": f"Paket {row['package_nama']}",
        "package_kode": row["package_kode"],
        "periode_mulai": row["periode_mulai"],
        "periode_selesai": row["periode_selesai"],
        "nominal": row["jumlah"],
        "metode_pembayaran": row["metode_pembayaran"] or "gateway",
        "channel_pembayaran": row["payment_type"],
        "status_unified": _STATUS_LANGGANAN_KE_UNIFIED.get(row["status"], row["status"]),
        "status_asli": row["status"],
        "jenis_transaksi": None,  # diisi _isi_jenis_transaksi_langganan() -- butuh riwayat lengkap tenant
        "transaction_id_provider": row["order_id"],
        "reference_id_provider": None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "paid_at": row["paid_at"],
    }


def _kumpulkan_semua() -> list:
    nama_tenant = _tenant_nama_map()
    hasil_booking = [_dari_booking(r) for r in booking_gateway_db.list_semua_transaksi()]
    hasil_langganan = [_dari_langganan(r, nama_tenant) for r in billing_invoice_db.list_invoices(tenant_id=None)]
    _isi_jenis_transaksi_langganan(hasil_langganan)
    return hasil_booking + hasil_langganan


def list_transactions(tenant_id: int = None, tanggal_mulai: str = None, tanggal_selesai: str = None,
                       status: str = None, metode_pembayaran: str = None, channel_pembayaran: str = None,
                       jenis: str = None, cari: str = None) -> list:
    """`status` di sini SELALU kosakata UNIFIED (lihat STATUS_UNIFIED_VALID),
    BUKAN status asli tabel sumber -- caller (routers/transaction_report.py)
    yang menerjemahkan dari query param."""
    data = _kumpulkan_semua()
    if jenis is not None:
        data = [d for d in data if d["jenis"] == jenis]
    if tenant_id is not None:
        data = [d for d in data if d["tenant_id"] == tenant_id]
    if tanggal_mulai is not None:
        # BUGFIX (audit): `tanggal` di baris hasil selalu datetime ISO
        # LENGKAP (mis. "2026-08-17T14:32:00"), sedangkan `tanggal_mulai`
        # bisa dikirim sebagai tanggal polos ("2026-08-17") -- pemanggil
        # yang lupa memberi jam (bukan cuma frontend Super Admin yang
        # kebetulan SUDAH menambahkan "T00:00:00"/"T23:59:59" secara
        # defensif) tetap harus dapat hasil yang benar. Kalau formatnya
        # tanggal polos, normalisasi ke AWAL hari itu supaya perbandingan
        # string tetap benar apa pun panjang `tanggal` di baris data.
        batas_mulai = tanggal_mulai if "T" in tanggal_mulai else f"{tanggal_mulai}T00:00:00"
        data = [d for d in data if d["tanggal"] >= batas_mulai]
    if tanggal_selesai is not None:
        # BUGFIX (audit): tanpa normalisasi ini, `tanggal_selesai` tanggal
        # polos ("2026-08-17") secara perbandingan STRING lebih KECIL dari
        # SEMUA datetime lengkap di hari yang sama ("2026-08-17T00:00:01"
        # dst, karena "2026-08-17" adalah PREFIX yang jadi string "lebih
        # pendek" = "lebih kecil") -- hampir seluruh transaksi hari
        # terakhir rentang jadi ter-exclude diam-diam, baik di tampilan
        # layar maupun file export CSV (keduanya lewat fungsi yang sama).
        batas_selesai = tanggal_selesai if "T" in tanggal_selesai else f"{tanggal_selesai}T23:59:59"
        data = [d for d in data if d["tanggal"] <= batas_selesai]
    if status is not None:
        data = [d for d in data if d["status_unified"] == status]
    if metode_pembayaran is not None:
        data = [d for d in data if d["metode_pembayaran"] == metode_pembayaran]
    if channel_pembayaran is not None:
        data = [d for d in data if d["channel_pembayaran"] == channel_pembayaran]
    if cari:
        kata = cari.strip().lower()
        def cocok(d):
            haystack = " ".join(str(v) for v in [
                d["nomor_transaksi"], d["tenant_nama"], d["customer_nama"], d["booking_id"],
                d["transaction_id_provider"], d["reference_id_provider"],
            ] if v is not None).lower()
            return kata in haystack
        data = [d for d in data if cocok(d)]
    data.sort(key=lambda d: d["tanggal"], reverse=True)
    return data


def get_summary(transactions: list) -> dict:
    """Dihitung dari daftar yang SUDAH difilter (list_transactions()) --
    "Total transaksi dan omzet per tenant sesuai filter" berarti ringkasan
    ini WAJIB mengikuti filter yang sama, bukan dihitung ulang dari semua
    data mentah."""
    per_tenant = {}
    for d in transactions:
        key = d["tenant_id"]
        if key not in per_tenant:
            per_tenant[key] = {"tenant_id": key, "tenant_nama": d["tenant_nama"], "jumlah_transaksi": 0, "omzet": 0}
        per_tenant[key]["jumlah_transaksi"] += 1
        if d["status_unified"] == "berhasil":
            per_tenant[key]["omzet"] += d["nominal"]

    return {
        "total_transaksi": len(transactions),
        "total_booking": sum(1 for d in transactions if d["jenis"] == "booking"),
        "total_langganan": sum(1 for d in transactions if d["jenis"] == "langganan"),
        "total_berhasil": sum(1 for d in transactions if d["status_unified"] == "berhasil"),
        "total_pending": sum(1 for d in transactions if d["status_unified"] in ("menunggu_pembayaran", "diproses")),
        "total_gagal": sum(1 for d in transactions if d["status_unified"] == "gagal"),
        "total_dibatalkan": sum(1 for d in transactions if d["status_unified"] in ("dibatalkan", "kedaluwarsa")),
        "total_nilai": sum(d["nominal"] for d in transactions if d["status_unified"] == "berhasil"),
        "per_tenant": sorted(per_tenant.values(), key=lambda t: t["omzet"], reverse=True),
    }


def get_transaction_detail(jenis: str, transaction_id: int) -> dict | None:
    if jenis not in JENIS_VALID:
        raise ValueError(f"Jenis transaksi tidak dikenal: {jenis}")
    if jenis == "booking":
        row = booking_gateway_db.get_transaksi(transaction_id)
        if row is None:
            return None
        hasil = _dari_booking(row)
        hasil["raw_notification"] = row["raw_notification"]
        hasil["status_log"] = booking_gateway_db.list_status_log(transaction_id)
        hasil["checkout_token"] = row["checkout_token"]
        hasil["checkout_redirect_url"] = row["checkout_redirect_url"]
        return hasil
    row = billing_invoice_db.get_invoice(transaction_id)
    if row is None:
        return None
    nama_tenant = _tenant_nama_map()
    # jenis_transaksi (Langganan Baru/Perpanjangan/Upgrade) butuh SELURUH
    # riwayat invoice tenant ini, bukan cuma baris ini sendiri -- lihat
    # docstring _isi_jenis_transaksi_langganan().
    riwayat_tenant = [_dari_langganan(r, nama_tenant) for r in billing_invoice_db.list_invoices(tenant_id=row["tenant_id"])]
    _isi_jenis_transaksi_langganan(riwayat_tenant)
    hasil = next(d for d in riwayat_tenant if d["id"] == row["id"])
    hasil["raw_notification"] = row["raw_notification"]
    hasil["status_log"] = billing_invoice_db.list_status_log(transaction_id)
    return hasil
