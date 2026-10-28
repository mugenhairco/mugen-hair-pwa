"""test_pos_cash_terpisah_dari_booking.py -- Cash POS TERPISAH dari Cash Booking
=============================================================================
PERMINTAAN Owner: "apakah bisa mengaktifkan metode cash hanya untuk pos
ini, jika diaktifkan yang cash untuk booking tidak otomatis aktif?" --
`pos_cash_aktif` (pos_db.py) adalah setting TERPISAH dari `booking_
metode_aktif` (booking_db.py) -- mengaktifkan salah satu TIDAK PERNAH
otomatis mengaktifkan yang lain, dan label untuk Cash di POS cukup
"Cash" (bukan "Cash (Bayar di Toko)" seperti Booking)."""

import auth_db
import booking_db
import pos_db


def _buat_superadmin_dan_login(client, username="superadmin_cash", password="rahasia123"):
    auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_cash_pos_dan_cash_booking_saling_independen(single_tenant):
    client = single_tenant["client"]
    headers = single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    sa_headers = _buat_superadmin_dan_login(client)

    # Default: keduanya nonaktif.
    assert pos_db.get_pos_cash_aktif(tenant_id) is False
    r0 = client.get("/api/pos/pengaturan", headers=headers)
    assert r0.status_code == 200, r0.text
    assert "cash" not in r0.json()["metode_aktif"]

    # Aktifkan Cash untuk BOOKING saja -- POS TIDAK ikut berubah.
    r1 = client.put(f"/api/superadmin/tenants/{tenant_id}/payment-settings", headers=sa_headers, json={
        "metode_aktif": ["qris", "cash"],
    })
    assert r1.status_code == 200, r1.text
    assert r1.json()["pos_cash_aktif"] is False
    assert "cash" in r1.json()["metode_aktif"]

    r1b = client.get("/api/pos/pengaturan", headers=headers)
    assert "cash" not in r1b.json()["metode_aktif"]

    # Aktifkan Cash untuk POS saja (toggle terpisah) -- metode_aktif Booking tidak tersentuh.
    r2 = client.put(f"/api/superadmin/tenants/{tenant_id}/payment-settings", headers=sa_headers, json={
        "pos_cash_aktif": True,
    })
    assert r2.status_code == 200, r2.text
    assert r2.json()["pos_cash_aktif"] is True
    assert "cash" in r2.json()["metode_aktif"]  # masih dari langkah sebelumnya, tidak berubah

    r2b = client.get("/api/pos/pengaturan", headers=headers)
    assert "cash" in r2b.json()["metode_aktif"]
    assert r2b.json()["metode_nama"]["cash"] == "Cash"  # label POS polos, BUKAN "Cash (Bayar di Toko)"

    # Label Booking TETAP "Cash (Bayar di Toko)" -- tidak ikut berubah oleh label POS.
    bps = booking_db.get_payment_settings(tenant_id=tenant_id)
    assert bps["metode_nama"]["cash"] == "Cash (Bayar di Toko)"

    # Matikan Cash BOOKING -- Cash POS TETAP aktif (independen satu sama lain).
    r3 = client.put(f"/api/superadmin/tenants/{tenant_id}/payment-settings", headers=sa_headers, json={
        "metode_aktif": ["qris"],
    })
    assert r3.status_code == 200, r3.text
    assert "cash" not in r3.json()["metode_aktif"]
    assert r3.json()["pos_cash_aktif"] is True

    r3b = client.get("/api/pos/pengaturan", headers=headers)
    assert "cash" in r3b.json()["metode_aktif"]
