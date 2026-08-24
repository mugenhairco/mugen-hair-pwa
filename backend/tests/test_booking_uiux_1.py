"""
test_booking_uiux_1.py — BOOKING WEBSITE UI/UX REFINEMENT & BUG FIXES #1
=============================================================================
Cakupan (backend only -- perubahan UI murni book_public.js/style.css tidak
dites di sini, lihat laporan akhir untuk verifikasi manual/Playwright):
1. Bugfix pengurutan Karyawan: add_barber() sekarang mengisi `urutan`
   berurutan (persis pola add_service() di Maintenance #1), get_barbers()/
   get_karyawan() diurutkan oleh `urutan` (bukan alfabetis), migrasi
   normalisasi tabrakan urutan lama untuk barber.
2. Halaman Booking publik mengikuti urutan Settings > Karyawan (bukan
   ID/created_at/alfabet).
3. Tab "Identitas Barbershop" dihapus: POST /api/pengaturan/logo (dipakai
   tab Branding) sekarang digerbangi izin_setting_branding, bukan lagi
   izin_setting_identitas yang sudah tidak bisa diberikan lewat UI manapun.
"""

import database as db
import auth_db
import subscription_db


def test_add_barber_urutan_berurutan_otomatis(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    id1 = db.add_barber("MT Romen", tenant_id=tenant_id)
    id2 = db.add_barber("MT Putra", tenant_id=tenant_id)
    id3 = db.add_barber("MT Andi", tenant_id=tenant_id)

    karyawan = {b["id"]: b["urutan"] for b in db.get_karyawan(hanya_aktif=False, tenant_id=tenant_id)}
    assert karyawan[id1] == 0
    assert karyawan[id2] == 1
    assert karyawan[id3] == 2


def test_get_barbers_urut_berdasarkan_urutan_bukan_nama(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    db.add_barber("MT Zzz Terakhir Alfabet", tenant_id=tenant_id)  # urutan=0 (ditambah duluan)
    db.add_barber("MT Aaa Duluan Alfabet", tenant_id=tenant_id)    # urutan=1

    hasil = db.get_barbers(tenant_id=tenant_id)
    assert [b["nama"] for b in hasil] == ["MT Zzz Terakhir Alfabet", "MT Aaa Duluan Alfabet"]


def test_get_karyawan_urut_berdasarkan_urutan_bukan_nama(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    db.add_barber("MT Zzz Kasir", jabatan="kasir", tenant_id=tenant_id)
    db.add_barber("MT Aaa Kasir", jabatan="kasir", tenant_id=tenant_id)

    hasil = db.get_karyawan(tenant_id=tenant_id)
    assert [b["nama"] for b in hasil] == ["MT Zzz Kasir", "MT Aaa Kasir"]


def test_tombol_naik_turun_karyawan_bertukar_urutan_via_http(single_tenant):
    """Simulasikan tombol '↑' pada Karyawan B: tukar urutan A<->B, pola yang
    sama persis dipakai frontend (lihat pages/pengaturan.js renderBarber())."""
    client, headers, tenant_id = single_tenant["client"], single_tenant["headers"], single_tenant["tenant_id"]
    id_a = db.add_barber("MT Karyawan A", tenant_id=tenant_id)
    id_b = db.add_barber("MT Karyawan B", tenant_id=tenant_id)
    assert [b["nama"] for b in db.get_barbers(tenant_id=tenant_id)] == ["MT Karyawan A", "MT Karyawan B"]

    r1 = client.put(f"/api/booking/barber/{id_b}/urutan", headers=headers, json={"urutan": 0})
    r2 = client.put(f"/api/booking/barber/{id_a}/urutan", headers=headers, json={"urutan": 1})
    assert r1.status_code == 200 and r2.status_code == 200

    assert [b["nama"] for b in db.get_barbers(tenant_id=tenant_id)] == ["MT Karyawan B", "MT Karyawan A"]


def test_booking_publik_barbers_ikut_urutan_settings_karyawan(single_tenant):
    """Halaman Booking publik (/api/public/booking/barbers) HARUS mengikuti
    urutan yang sama seperti Settings > Karyawan, bukan alfabet/created_at."""
    client, headers, tenant_id = single_tenant["client"], single_tenant["headers"], single_tenant["tenant_id"]
    # AUDIT (enforcement paket/subscription): /api/public/booking/barbers
    # sekarang digerbang fitur "booking_online" (lihat routers/booking.py::
    # _pastikan_booking_online_aktif()) -- single_tenant TIDAK punya baris
    # subscription secara default (fail-CLOSED), isi eksplisit di sini
    # supaya test ini tetap menguji URUTAN barber, bukan malah 403 duluan.
    subscription_db.create_default_subscription(tenant_id)
    id_a = db.add_barber("MT Zzz Barber", tenant_id=tenant_id)
    id_b = db.add_barber("MT Aaa Barber", tenant_id=tenant_id)
    # Tukar urutan lewat tombol (persis seperti Owner memakai Settings > Karyawan).
    client.put(f"/api/booking/barber/{id_b}/urutan", headers=headers, json={"urutan": 0})
    client.put(f"/api/booking/barber/{id_a}/urutan", headers=headers, json={"urutan": 1})

    r = client.get(f"/api/public/booking/barbers?tenant={_slug(tenant_id)}")
    assert r.status_code == 200, r.text
    assert [b["nama"] for b in r.json()] == ["MT Aaa Barber", "MT Zzz Barber"]


def _slug(tenant_id):
    import tenant_db
    return tenant_db.get_tenant(tenant_id)["slug"]


def test_normalisasi_urutan_barber_kolisi_merapikan_tanpa_mengubah_urutan_relatif(single_tenant):
    import booking_form_migrasi
    tenant_id = single_tenant["tenant_id"]

    # Simulasikan data lama (sebelum bugfix) -- beberapa karyawan berbagi
    # urutan=0, ditambahkan lewat INSERT langsung (BUKAN add_barber() yang
    # sekarang sudah benar) supaya tabrakannya sungguhan.
    with db.get_conn() as conn:
        conn.execute("INSERT INTO barbers (nama, tenant_id, urutan) VALUES (?, ?, 0)", ("MT Beta", tenant_id))
        conn.execute("INSERT INTO barbers (nama, tenant_id, urutan) VALUES (?, ?, 0)", ("MT Alpha", tenant_id))
        conn.execute("INSERT INTO barbers (nama, tenant_id, urutan) VALUES (?, ?, 0)", ("MT Charlie", tenant_id))

    with db.get_conn() as conn:
        booking_form_migrasi._normalisasi_urutan_barber_kolisi(conn)

    hasil = db.get_karyawan(hanya_aktif=False, tenant_id=tenant_id)
    urutan_list = [b["urutan"] for b in hasil]
    assert urutan_list == sorted(urutan_list) == [0, 1, 2]
    assert [b["nama"] for b in hasil] == ["MT Alpha", "MT Beta", "MT Charlie"]


def test_normalisasi_urutan_barber_tidak_menyentuh_yang_sudah_unik(single_tenant):
    """No-op total kalau urutan sudah unik -- Owner yang sudah mengatur
    lewat tombol ↑/↓ tidak boleh melihat urutannya berubah."""
    import booking_form_migrasi
    tenant_id = single_tenant["tenant_id"]
    id_a = db.add_barber("MT Sudah Diatur A", tenant_id=tenant_id)
    id_b = db.add_barber("MT Sudah Diatur B", tenant_id=tenant_id)
    with db.get_conn() as conn:
        conn.execute("UPDATE barbers SET urutan = 5 WHERE id = ?", (id_a,))
        conn.execute("UPDATE barbers SET urutan = 2 WHERE id = ?", (id_b,))

    with db.get_conn() as conn:
        booking_form_migrasi._normalisasi_urutan_barber_kolisi(conn)

    hasil = {b["id"]: b["urutan"] for b in db.get_karyawan(hanya_aktif=False, tenant_id=tenant_id)}
    assert hasil[id_a] == 5
    assert hasil[id_b] == 2


# ---------------------------------------------------------------------------
# Tab "Identitas Barbershop" dihapus: POST /api/pengaturan/logo sekarang
# digerbangi izin_setting_branding (bukan izin_setting_identitas lagi).
# ---------------------------------------------------------------------------

def test_upload_logo_staff_tanpa_izin_branding_ditolak(single_tenant):
    client, tenant_id = single_tenant["client"], single_tenant["tenant_id"]
    auth_db.tambah_user("staffLogo1", "password123", role="staff", tenant_id=tenant_id)
    r = client.post("/api/auth/login", json={"username": "staffLogo1", "password": "password123"})
    headers_staff = {"Authorization": f"Bearer {r.json()['token']}"}

    r2 = client.post("/api/pengaturan/logo", headers=headers_staff,
                      files={"file": ("logo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20, "image/png")})
    assert r2.status_code == 403


def test_upload_logo_staff_dengan_izin_branding_diterima(single_tenant):
    client, headers, tenant_id = single_tenant["client"], single_tenant["headers"], single_tenant["tenant_id"]
    client.put("/api/pengaturan/hak-akses-admin", headers=headers,
               json={"izin": {"izin_setting_branding": True}})
    auth_db.tambah_user("staffLogo2", "password123", role="staff", tenant_id=tenant_id)
    r = client.post("/api/auth/login", json={"username": "staffLogo2", "password": "password123"})
    headers_staff = {"Authorization": f"Bearer {r.json()['token']}"}

    r2 = client.post("/api/pengaturan/logo", headers=headers_staff,
                      files={"file": ("logo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20, "image/png")})
    assert r2.status_code == 200, r2.text
