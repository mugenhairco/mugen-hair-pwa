"""user_roles_db.py — Role Custom per Tenant (FITUR Role User Custom, diminta Owner)
=============================================================================
REVISI BESAR (Oktober 2026, lihat permissions.py): Role "Admin" BAWAAN/
DEFAULT DIHAPUS TOTAL. Tidak ada lagi konsep "Role spesial" -- SEMUA akun
'staff' WAJIB punya Role di sini (users.custom_role_id WAJIB terisi),
Owner bebas menamainya apa saja ("Staff", "Kasir", apa pun) dan mengatur
checklist izinnya sendiri lewat tree permissions.PERMISSION_TREE. Role
BARU yang baru dibuat Owner mulai KOSONG (fail-CLOSED, semua izin False)
-- Owner men-checklist sendiri dari nol, tidak ada default apa pun.

Bagian dari struktur USER -> ROLE -> HAK AKSES (lihat permissions.py).
`get_role_permission_keys()`/`set_role_permission_keys()` di bawah adalah
titik gabung dengan permissions.py::get_all(role_id=...)/set_bulk(...).

MIGRASI SEKALI JALAN (migrasi_role_staff_default(), dipanggil main.py saat
startup, SETELAH init_user_roles_db() -- lihat fungsinya di bawah):
memindahkan akun 'staff' yang SEBELUM revisi ini memakai Role "Admin"
bawaan (custom_role_id NULL, izin dari tabel `settings` tenant-wide) ke
sebuah Role baru bernama "Staff" per tenant, MEMBAWA izin lama tenant itu
apa adanya (plus warisan eksplisit untuk key yang baru ditambahkan tree
ini -- lihat komentar per key di fungsi itu) -- supaya TIDAK ADA akun yang
mendadak terkunci begitu revisi ini di-deploy."""

from datetime import datetime

from database import get_conn


def init_user_roles_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_roles (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id    INTEGER,
                nama         TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )
        """)
        # role_id BOLEH pakai FK (tabel ini BARU, dibuat sekaligus dengan
        # PRIMARY KEY yang benar sejak awal -- BUKAN tabel produksi lama
        # yang jadi sumber insiden FK di postgres_schema.py, pola sama
        # seperti subscription_package_features di billing_db.py) --
        # ON DELETE CASCADE otomatis membersihkan checklist izin begitu
        # role-nya dihapus.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_role_permissions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id      INTEGER NOT NULL,
                izin_key     TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                UNIQUE(role_id, izin_key),
                FOREIGN KEY (role_id) REFERENCES user_roles(id) ON DELETE CASCADE
            )
        """)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def list_roles(tenant_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM user_roles WHERE tenant_id = ? ORDER BY nama, id", (tenant_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_role(role_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM user_roles WHERE id = ?", (role_id,)).fetchone()
        return dict(row) if row else None


def create_role(tenant_id: int, nama: str) -> dict:
    nama = (nama or "").strip()
    if not nama:
        raise ValueError("Nama role tidak boleh kosong.")
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO user_roles (tenant_id, nama, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (tenant_id, nama, now, now),
        )
        role_id = cur.lastrowid
    return get_role(role_id)


def rename_role(role_id: int, nama: str) -> dict:
    if get_role(role_id) is None:
        raise ValueError("Role tidak ditemukan.")
    nama = (nama or "").strip()
    if not nama:
        raise ValueError("Nama role tidak boleh kosong.")
    with get_conn() as conn:
        conn.execute("UPDATE user_roles SET nama = ?, updated_at = ? WHERE id = ?", (nama, _now(), role_id))
    return get_role(role_id)


def delete_role(role_id: int):
    """Hapus PERMANEN -- ON DELETE CASCADE melepas checklist izin role ini
    (user_role_permissions). REVISI (hapus Role "Admin" bawaan/default):
    `custom_role_id = NULL` TIDAK LAGI punya arti "balik ke default" --
    jadi BERBEDA dari sebelumnya, modul ini SEKARANG MEMBLOKIR penghapusan
    kalau masih ada akun yang memakai role ini (pemanggil, routers/
    pengaturan.py::hapus_user_role(), WAJIB memastikan dulu lewat
    auth_db.hitung_user_dengan_custom_role_id() -- dicek ULANG di sini
    juga sebagai lapis kedua, defense in depth) -- Owner harus memindahkan
    akun yang terkena ke Role lain dahulu, supaya tidak ada akun yang
    diam-diam kehilangan seluruh izinnya."""
    if get_role(role_id) is None:
        raise ValueError("Role tidak ditemukan.")
    import auth_db  # import lokal: hindari import siklik (auth_db.py -> database.py)
    jumlah = auth_db.hitung_user_dengan_custom_role_id(role_id)
    if jumlah > 0:
        raise ValueError(f"Role ini masih dipakai {jumlah} akun. Pindahkan akun tersebut ke Role lain dahulu.")
    with get_conn() as conn:
        conn.execute("DELETE FROM user_roles WHERE id = ?", (role_id,))


# Default LAMA (sebelum REVISI Hak Akses, PERMISSION_DEFS versi lama) --
# HANYA dipakai migrasi_role_staff_default() di bawah untuk membaca nilai
# "efektif" tenant SEBELUM revisi ini (permissions.py SEKARANG, versi
# PERMISSION_TREE, TIDAK PUNYA konsep default sama sekali -- SEMUA fail-
# CLOSED kalau tidak ada baris `settings` eksplisit, lihat get_all()).
# Tanpa tabel ini, migrasi akan salah membaca key yang TIDAK PERNAH
# ditulis eksplisit ke `settings` (karena Owner tidak pernah mengubahnya
# dari default) sebagai False, padahal PERMISSION_DEFS lama men-default-
# kannya True -- mengunci staff yang sebelumnya memang punya akses.
# ARSIP HISTORIS -- JANGAN diubah lagi, jangan dihapus key manapun di
# sini walau key-nya sendiri sudah tidak ada di PERMISSION_TREE baru.
_DEFAULT_LAMA_SEBELUM_REVISI = {
    "izin_dashboard_nilai_service": True, "izin_dashboard_jumlah_service": True,
    "izin_dashboard_pengeluaran_toko": True, "izin_dashboard_penjualan_produk": True,
    "izin_dashboard_total_komisi": False, "izin_dashboard_total_tips": False,
    "izin_dashboard_uang_harian": False, "izin_dashboard_bonus_customer": False,
    "izin_dashboard_laba_kotor": False,
    "izin_user_tambah": False, "izin_user_hapus": False, "izin_user_ganti_password": False,
    "izin_backup_export": False, "izin_backup_import": False,
    "izin_laporan_pdf": False,
    "izin_slip_gaji": False, "izin_kasbon": False, "izin_komisi": False,
    "izin_reimburse": False, "izin_cuti_karyawan": False,
    "izin_setting_tampilan": False, "izin_setting_user": False, "izin_setting_backup": False,
    "izin_setting_branding": False,
    "izin_absensi_pengaturan": False, "izin_absensi_koreksi": False,
    "izin_booking_kelola": True, "izin_booking_batalkan": True, "izin_booking_hapus": False,
    "izin_booking_pengaturan": True,
    "izin_produk_kelola": True, "izin_produk_hapus": True,
    "izin_pengeluaran_kelola": True, "izin_pengeluaran_hapus": True,
    "izin_pemasukan_kelola": True, "izin_pemasukan_hapus": True,
    "izin_uang_kas_kelola": True, "izin_uang_kas_hapus": True,
    "izin_data_non_barber_kelola": True, "izin_data_non_barber_hapus": True,
    "izin_input_data_kelola": True, "izin_input_data_hapus": True,
    "izin_riwayat_transaksi": True, "izin_settlement_faspay": False,
    "izin_dashboard_lihat": True, "izin_input_data_lihat": True, "izin_rekap_lihat": True,
    "izin_slip_gaji_lihat": False, "izin_kasbon_lihat": False, "izin_komisi_lihat": False,
    "izin_reimburse_lihat": False, "izin_cuti_karyawan_lihat": False,
    "izin_absensi_lihat": True, "izin_booking_lihat": True, "izin_riwayat_transaksi_lihat": True,
    "izin_pemasukan_lihat": True, "izin_pengeluaran_lihat": True, "izin_uang_kas_lihat": True,
    "izin_produk_lihat": True, "izin_settlement_faspay_lihat": False,
}


def _baca_izin_lama_dengan_default(tenant_id: int) -> dict:
    """Versi "dengan default lama" dari permissions.get_all(role_id=None)
    -- HANYA dipakai migrasi_role_staff_default() di bawah, lihat catatan
    _DEFAULT_LAMA_SEBELUM_REVISI di atas untuk alasan lengkap kenapa
    permissions.get_all() yang SEKARANG (fail-closed, tanpa default) tidak
    boleh dipakai langsung untuk membaca nilai historis ini."""
    import database as db  # import lokal: hindari import siklik
    semua = db.get_all_settings(tenant_id=tenant_id)
    hasil = {}
    for key, default in _DEFAULT_LAMA_SEBELUM_REVISI.items():
        nilai = semua.get(key)
        hasil[key] = (nilai == "1") if nilai is not None else default
    return hasil


def migrasi_role_staff_default():
    """Migrasi SEKALI JALAN (idempotent, aman dipanggil setiap startup) --
    lihat docstring modul untuk latar belakang lengkap. Untuk SETIAP tenant
    yang masih punya akun 'staff' dengan custom_role_id NULL: buat (atau
    pakai ulang, idempotent -- lihat guard nama "Staff" di bawah) SATU Role
    bernama "Staff", isi checklist izinnya dari nilai LAMA tenant itu
    (tabel `settings`, lewat _baca_izin_lama_dengan_default() -- BUKAN
    permissions.get_all(role_id=None), yang SEKARANG fail-closed tanpa
    default, lihat catatan _DEFAULT_LAMA_SEBELUM_REVISI di atas) ditambah
    warisan eksplisit untuk key yang BARU ditambahkan tree ini (key yang
    dulu TIDAK ADA izin_* apa pun -- supaya staff lama tidak kehilangan
    akses yang sebelumnya memang reachable tanpa gerbang apa pun), lalu
    tempelkan SEMUA akun staff tenant itu ke Role baru tersebut."""
    import auth_db  # import lokal: hindari import siklik
    import permissions  # import lokal: hindari import siklik
    import tenant_db  # import lokal: hindari import siklik

    for tenant in tenant_db.list_tenants():
        tid = tenant["id"]
        staff_tanpa_role = auth_db.get_user_list_tanpa_role(tid)
        if not staff_tanpa_role:
            continue  # sudah bermigrasi, atau tenant ini belum/tidak punya staff -- idempotent

        role = next((r for r in list_roles(tid) if r["nama"] == "Staff"), None)
        if role is None:
            role = create_role(tid, "Staff")

        lama = _baca_izin_lama_dengan_default(tid)
        baru = dict(lama)

        def _warisi(key_baru, key_lama=None, selalu=None):
            baru[key_baru] = selalu if selalu is not None else lama.get(key_lama, False)

        # Key BARU (tidak ada sama sekali di katalog izin_* lama) -- warisi
        # dari cakupan LAMA yang paling mendekati, supaya staff yang sudah
        # ada tidak mendadak kehilangan akses yang dulu memang reachable.
        _warisi("izin_slip_gaji_hapus", "izin_slip_gaji")
        _warisi("izin_kasbon_hapus", "izin_kasbon")
        _warisi("izin_komisi_hapus", "izin_komisi")
        _warisi("izin_reimburse_tambah", "izin_reimburse")
        _warisi("izin_reimburse_hapus", "izin_reimburse")
        _warisi("izin_cuti_karyawan_hapus", "izin_cuti_karyawan")
        _warisi("izin_absensi_dashboard", "izin_absensi_lihat")
        _warisi("izin_absensi_limit", "izin_absensi_lihat")
        _warisi("izin_absensi_export_excel", "izin_absensi_lihat")  # dulu TANPA izin_* apa pun (hanya gate paket)
        _warisi("izin_booking_list", "izin_booking_kelola")
        _warisi("izin_booking_calendar", "izin_booking_kelola")
        _warisi("izin_booking_barber_holiday", "izin_booking_kelola")
        _warisi("izin_booking_closed_slot", "izin_booking_kelola")
        _warisi("izin_booking_operating_hours", "izin_booking_pengaturan")
        _warisi("izin_booking_payment_settings", "izin_booking_pengaturan")
        _warisi("izin_booking_settings", "izin_booking_pengaturan")
        _warisi("izin_booking_website_content", selalu=False)  # dulu Owner-only (hardcoded booking.js)
        _warisi("izin_whatsapp_lihat", selalu=False)  # dulu Owner-only (hardcoded nav.js)
        _warisi("izin_whatsapp_notifikasi_booking", selalu=False)
        _warisi("izin_whatsapp_reminder_absensi", selalu=False)
        _warisi("izin_rekap_transaksi", "izin_rekap_lihat")
        _warisi("izin_rekap_bulanan", "izin_rekap_lihat")
        _warisi("izin_rekap_pengeluaran", selalu=True)  # dulu TANPA izin_* apa pun -- semua staff reachable (celah lama)
        _warisi("izin_manual_customer", "izin_input_data_kelola")  # dulu memakai izin_input_data_kelola/hapus
        _warisi("izin_produk_mutasi", "izin_produk_kelola")
        _warisi("izin_produk_riwayat_mutasi", "izin_produk_lihat")
        setting_lama_manapun = any(lama.get(k) for k in (
            "izin_setting_branding", "izin_setting_tampilan", "izin_setting_user", "izin_setting_backup"))
        _warisi("izin_setting_lihat", selalu=setting_lama_manapun)
        _warisi("izin_setting_komisi", selalu=False)  # dulu Owner-only
        _warisi("izin_setting_bonus_service", selalu=False)
        _warisi("izin_setting_uang_harian", selalu=False)
        _warisi("izin_setting_karyawan", selalu=False)
        _warisi("izin_setting_layanan", selalu=False)
        _warisi("izin_setting_subscription", selalu=False)

        aktif = {k for k, v in baru.items() if v and k in permissions.PERMISSION_KEYS}
        set_role_permission_keys(role["id"], aktif)

        for u in staff_tanpa_role:
            auth_db.set_custom_role(u["id"], role["id"])


def get_role_permission_keys(role_id: int) -> set:
    """Set kode izin_* yang AKTIF (True) untuk role ini -- kode yang TIDAK
    ada di sini dianggap False (fail-CLOSED, lihat catatan modul di atas).
    Dipanggil permissions.py::get_all(role_id=...) untuk mengisi dict
    lengkap {key: bool} dari katalog permissions.PERMISSION_TREE."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT izin_key FROM user_role_permissions WHERE role_id = ?", (role_id,)
        ).fetchall()
        return {r["izin_key"] for r in rows}


def set_role_permission_keys(role_id: int, keys: set):
    """GANTI TOTAL daftar izin aktif role ini jadi `keys` -- pola sama
    seperti billing_db.set_package_features() (hapus semua baris lama,
    insert ulang yang baru, dalam satu fungsi supaya tidak ada baris usang
    tersisa kalau Owner mencabut sebuah izin)."""
    if get_role(role_id) is None:
        raise ValueError("Role tidak ditemukan.")
    now = _now()
    with get_conn() as conn:
        conn.execute("DELETE FROM user_role_permissions WHERE role_id = ?", (role_id,))
        for key in keys:
            conn.execute(
                "INSERT INTO user_role_permissions (role_id, izin_key, created_at) VALUES (?, ?, ?)",
                (role_id, key, now),
            )
