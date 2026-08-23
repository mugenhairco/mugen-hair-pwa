"""test_faspay_settlement.py — Settlement Faspay per Terminal (Tenant)
=============================================================================
Cakupan: "terminal" = tenant (real-time match dari data lokal snap_payment_
transactions, submit mengunci settlement/tidak bisa diubah/tidak bisa
dobel per tanggal, isolasi Tenant->Terminal->Periode, rekonsiliasi H+1
lewat Inquiry API SNAP Advance yang di-mock (TIDAK PERNAH memanggil Faspay
sungguhan), dan akses Super Admin. Transaksi SNAP dibuat LANGSUNG lewat
snap_payment_db.py (pola sama seperti test_snap_advance.py) -- TIDAK
memanggil provider sungguhan sama sekali."""

from datetime import datetime, timedelta

import faspay_settlement_db
import snap_payment_db
from database import get_conn


def _buat_superadmin_dan_login(client, username="superadmin-settlement", password="rahasia123"):
    import auth_db
    auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _buat_transaksi_snap(tenant_id, *, status="PAID", channel="va", amount=100000,
                          booking_id=1, tanggal_created=None):
    trx = snap_payment_db.buat_transaksi(
        snap_payment_db.TRANSACTION_TYPE_BOOKING, tenant_id, amount, booking_id=booking_id, channel=channel,
    )
    snap_payment_db.catat_hasil_create_transaction(
        trx["id"], provider_transaction_id=f"PROV-{trx['id']}",
        va_number=f"88808{trx['id']:05d}" if channel == "va" else None,
    )
    if status != "CREATED":
        snap_payment_db.update_status(trx["id"], status, sumber="test")
    if tanggal_created is not None:
        with get_conn() as conn:
            conn.execute("UPDATE snap_payment_transactions SET created_at = ? WHERE id = ?",
                         (f"{tanggal_created}T10:00:00", trx["id"]))
    return snap_payment_db.get_transaksi(trx["id"])


def _mundurkan_submitted_at(settlement_id, hari=1):
    """Backdate submitted_at supaya _bisa_h1() lolos TANPA mock date.today()."""
    baru = (datetime.now() - timedelta(days=hari)).isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute("UPDATE faspay_settlements SET submitted_at = ? WHERE id = ?", (baru, settlement_id))


# ============================= Preview (real-time, murni lokal) =============================

def test_preview_semua_paid_reconciled(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    _buat_transaksi_snap(tenant_id, status="PAID", tanggal_created="2026-08-23")
    _buat_transaksi_snap(tenant_id, status="PAID", tanggal_created="2026-08-23")

    r = single_tenant["client"].get("/api/settlement-faspay/preview", params={"tanggal": "2026-08-23"},
                                     headers=single_tenant["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["jumlah_transaksi"] == 2
    assert body["jumlah_match"] == 2
    assert body["jumlah_warning"] == 0
    assert body["status_rekonsiliasi"] == "RECONCILED"


def test_preview_ada_pending_warning(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    _buat_transaksi_snap(tenant_id, status="PAID", tanggal_created="2026-08-23")
    _buat_transaksi_snap(tenant_id, status="CREATED", tanggal_created="2026-08-23")

    r = single_tenant["client"].get("/api/settlement-faspay/preview", params={"tanggal": "2026-08-23"},
                                     headers=single_tenant["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["jumlah_match"] == 1
    assert body["jumlah_warning"] == 1
    assert body["status_rekonsiliasi"] == "WARNING"
    pending_item = next(i for i in body["items"] if i["match_status"] == "pending_faspay")
    assert pending_item["status_pembayaran"] == "CREATED"


def test_preview_tidak_ikutkan_tanggal_lain(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    _buat_transaksi_snap(tenant_id, status="PAID", tanggal_created="2026-08-22")
    _buat_transaksi_snap(tenant_id, status="PAID", tanggal_created="2026-08-23")

    r = single_tenant["client"].get("/api/settlement-faspay/preview", params={"tanggal": "2026-08-23"},
                                     headers=single_tenant["headers"])
    assert r.json()["jumlah_transaksi"] == 1


def test_preview_tidak_menulis_apa_pun(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    _buat_transaksi_snap(tenant_id, status="PAID", tanggal_created="2026-08-23")
    single_tenant["client"].get("/api/settlement-faspay/preview", params={"tanggal": "2026-08-23"},
                                 headers=single_tenant["headers"])
    assert faspay_settlement_db.list_settlements(tenant_id=tenant_id) == []


# ============================= Submit Settlement =============================

def test_submit_settlement_berhasil(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    _buat_transaksi_snap(tenant_id, status="PAID", amount=150000, tanggal_created="2026-08-23")
    _buat_transaksi_snap(tenant_id, status="PAID", amount=75000, tanggal_created="2026-08-23")

    r = single_tenant["client"].post("/api/settlement-faspay", params={"tanggal": "2026-08-23"},
                                      headers=single_tenant["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["jumlah_transaksi"] == 2
    assert body["total_nominal"] == 225000
    assert body["status_rekonsiliasi"] == "RECONCILED"
    assert body["dibuat_oleh_nama"] == "owner1"
    assert len(body["items"]) == 2


def test_submit_settlement_dobel_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    _buat_transaksi_snap(tenant_id, status="PAID", tanggal_created="2026-08-23")
    client, headers = single_tenant["client"], single_tenant["headers"]
    r1 = client.post("/api/settlement-faspay", params={"tanggal": "2026-08-23"}, headers=headers)
    assert r1.status_code == 200, r1.text
    r2 = client.post("/api/settlement-faspay", params={"tanggal": "2026-08-23"}, headers=headers)
    assert r2.status_code == 409


def test_submit_settlement_kosong_tetap_reconciled(single_tenant):
    r = single_tenant["client"].post("/api/settlement-faspay", params={"tanggal": "2026-08-23"},
                                      headers=single_tenant["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["jumlah_transaksi"] == 0
    assert r.json()["status_rekonsiliasi"] == "RECONCILED"


def test_tidak_ada_endpoint_update_atau_hapus_settlement(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    _buat_transaksi_snap(tenant_id, status="PAID", tanggal_created="2026-08-23")
    client, headers = single_tenant["client"], single_tenant["headers"]
    settlement = client.post("/api/settlement-faspay", params={"tanggal": "2026-08-23"}, headers=headers).json()
    r_put = client.put(f"/api/settlement-faspay/{settlement['id']}", headers=headers)
    r_delete = client.delete(f"/api/settlement-faspay/{settlement['id']}", headers=headers)
    assert r_put.status_code == 405
    assert r_delete.status_code == 405


# ============================= Isolasi Tenant -> Terminal -> Periode =============================

def test_isolasi_settlement_tenant_lain_tidak_terlihat(two_tenants):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    client = two_tenants["client"]
    _buat_transaksi_snap(tenant_a, status="PAID", tanggal_created="2026-08-23")
    settlement_a = client.post("/api/settlement-faspay", params={"tanggal": "2026-08-23"},
                                headers=two_tenants["headers_a"]).json()

    r = client.get(f"/api/settlement-faspay/{settlement_a['id']}", headers=two_tenants["headers_b"])
    assert r.status_code == 404


def test_list_settlement_tenant_hanya_milik_sendiri(two_tenants):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    client = two_tenants["client"]
    _buat_transaksi_snap(tenant_a, status="PAID", tanggal_created="2026-08-23")
    _buat_transaksi_snap(tenant_b, status="PAID", tanggal_created="2026-08-23")
    client.post("/api/settlement-faspay", params={"tanggal": "2026-08-23"}, headers=two_tenants["headers_a"])
    client.post("/api/settlement-faspay", params={"tanggal": "2026-08-23"}, headers=two_tenants["headers_b"])

    r = client.get("/api/settlement-faspay", headers=two_tenants["headers_a"])
    body = r.json()
    assert len(body) == 1
    assert body[0]["tenant_id"] == tenant_a


def test_submit_dobel_tidak_saling_ganggu_beda_tenant(two_tenants):
    """Satu tenant sudah submit tanggal X TIDAK menghalangi tenant lain
    submit tanggal SAMA (unique index per tenant+tanggal, bukan global)."""
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    client = two_tenants["client"]
    _buat_transaksi_snap(tenant_a, status="PAID", tanggal_created="2026-08-23")
    _buat_transaksi_snap(tenant_b, status="PAID", tanggal_created="2026-08-23")
    r1 = client.post("/api/settlement-faspay", params={"tanggal": "2026-08-23"}, headers=two_tenants["headers_a"])
    r2 = client.post("/api/settlement-faspay", params={"tanggal": "2026-08-23"}, headers=two_tenants["headers_b"])
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text


# ============================= Rekonsiliasi H+1 =============================

def test_h1_ditolak_kalau_belum_h_plus_1(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    _buat_transaksi_snap(tenant_id, status="PAID", tanggal_created="2026-08-23")
    client = single_tenant["client"]
    settlement = client.post("/api/settlement-faspay", params={"tanggal": "2026-08-23"},
                              headers=single_tenant["headers"]).json()
    headers_super = _buat_superadmin_dan_login(client)

    r = client.post(f"/api/superadmin/settlement-faspay/{settlement['id']}/rekonsiliasi-h1", headers=headers_super)
    assert r.status_code == 422
    assert "H+1" in r.json()["detail"]


def test_h1_final_match_semua_cocok(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _buat_transaksi_snap(tenant_id, status="PAID", channel="va", amount=100000, tanggal_created="2026-08-23")
    client = single_tenant["client"]
    settlement = client.post("/api/settlement-faspay", params={"tanggal": "2026-08-23"},
                              headers=single_tenant["headers"]).json()
    _mundurkan_submitted_at(settlement["id"])
    headers_super = _buat_superadmin_dan_login(client)

    import snap_advance_client
    monkeypatch.setattr(snap_advance_client, "inquiry_status_va", lambda ref, va: {
        "latestTransactionStatus": "00", "paidAmount": {"value": "100000.00"}, "trxId": f"PROV-1",
    })

    r = client.post(f"/api/superadmin/settlement-faspay/{settlement['id']}/rekonsiliasi-h1", headers=headers_super)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status_rekonsiliasi"] == "RECONCILED"
    assert body["jumlah_final_mismatch"] == 0
    assert body["items"][0]["h1_match_status"] == "final_match"


def test_h1_amount_mismatch(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _buat_transaksi_snap(tenant_id, status="PAID", channel="va", amount=100000, tanggal_created="2026-08-23")
    client = single_tenant["client"]
    settlement = client.post("/api/settlement-faspay", params={"tanggal": "2026-08-23"},
                              headers=single_tenant["headers"]).json()
    _mundurkan_submitted_at(settlement["id"])
    headers_super = _buat_superadmin_dan_login(client)

    import snap_advance_client
    monkeypatch.setattr(snap_advance_client, "inquiry_status_va", lambda ref, va: {
        "latestTransactionStatus": "00", "paidAmount": {"value": "95000.00"}, "trxId": "PROV-1",
    })

    r = client.post(f"/api/superadmin/settlement-faspay/{settlement['id']}/rekonsiliasi-h1", headers=headers_super)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status_rekonsiliasi"] == "FINAL_MISMATCH"
    assert body["jumlah_final_mismatch"] == 1
    assert body["items"][0]["h1_match_status"] == "amount_mismatch"


def test_h1_status_mismatch(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _buat_transaksi_snap(tenant_id, status="PAID", channel="va", amount=100000, tanggal_created="2026-08-23")
    client = single_tenant["client"]
    settlement = client.post("/api/settlement-faspay", params={"tanggal": "2026-08-23"},
                              headers=single_tenant["headers"]).json()
    _mundurkan_submitted_at(settlement["id"])
    headers_super = _buat_superadmin_dan_login(client)

    import snap_advance_client
    monkeypatch.setattr(snap_advance_client, "inquiry_status_va", lambda ref, va: {
        "latestTransactionStatus": "06", "paidAmount": {"value": "100000.00"}, "trxId": "PROV-1",
    })

    r = client.post(f"/api/superadmin/settlement-faspay/{settlement['id']}/rekonsiliasi-h1", headers=headers_super)
    body = r.json()
    assert body["status_rekonsiliasi"] == "FINAL_MISMATCH"
    assert body["items"][0]["h1_match_status"] == "status_mismatch"


def test_h1_reference_mismatch(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _buat_transaksi_snap(tenant_id, status="PAID", channel="va", amount=100000, tanggal_created="2026-08-23")
    client = single_tenant["client"]
    settlement = client.post("/api/settlement-faspay", params={"tanggal": "2026-08-23"},
                              headers=single_tenant["headers"]).json()
    _mundurkan_submitted_at(settlement["id"])
    headers_super = _buat_superadmin_dan_login(client)

    import snap_advance_client
    monkeypatch.setattr(snap_advance_client, "inquiry_status_va", lambda ref, va: {
        "latestTransactionStatus": "00", "paidAmount": {"value": "100000.00"}, "trxId": "PROV-BEDA-SEKALI",
    })

    r = client.post(f"/api/superadmin/settlement-faspay/{settlement['id']}/rekonsiliasi-h1", headers=headers_super)
    body = r.json()
    assert body["items"][0]["h1_match_status"] == "reference_mismatch"


def test_h1_direct_debit_tidak_bisa_dicek_bukan_ditebak(single_tenant, monkeypatch):
    """channel_code spesifik Direct Debit tidak tersimpan per-transaksi --
    modul ini JUJUR menandai tidak_bisa_dicek, TIDAK menebak."""
    tenant_id = single_tenant["tenant_id"]
    _buat_transaksi_snap(tenant_id, status="PAID", channel="direct_debit", amount=100000, tanggal_created="2026-08-23")
    client = single_tenant["client"]
    settlement = client.post("/api/settlement-faspay", params={"tanggal": "2026-08-23"},
                              headers=single_tenant["headers"]).json()
    _mundurkan_submitted_at(settlement["id"])
    headers_super = _buat_superadmin_dan_login(client)

    r = client.post(f"/api/superadmin/settlement-faspay/{settlement['id']}/rekonsiliasi-h1", headers=headers_super)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["items"][0]["h1_match_status"] == "tidak_bisa_dicek"
    assert body["status_rekonsiliasi"] == "FINAL_MISMATCH"


def test_h1_bisa_diulang_hasil_tertimpa_bukan_menumpuk(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _buat_transaksi_snap(tenant_id, status="PAID", channel="va", amount=100000, tanggal_created="2026-08-23")
    client = single_tenant["client"]
    settlement = client.post("/api/settlement-faspay", params={"tanggal": "2026-08-23"},
                              headers=single_tenant["headers"]).json()
    _mundurkan_submitted_at(settlement["id"])
    headers_super = _buat_superadmin_dan_login(client)

    import snap_advance_client
    monkeypatch.setattr(snap_advance_client, "inquiry_status_va", lambda ref, va: {
        "latestTransactionStatus": "06", "paidAmount": {"value": "100000.00"}, "trxId": "PROV-1",
    })
    r1 = client.post(f"/api/superadmin/settlement-faspay/{settlement['id']}/rekonsiliasi-h1", headers=headers_super)
    assert r1.json()["status_rekonsiliasi"] == "FINAL_MISMATCH"

    monkeypatch.setattr(snap_advance_client, "inquiry_status_va", lambda ref, va: {
        "latestTransactionStatus": "00", "paidAmount": {"value": "100000.00"}, "trxId": "PROV-1",
    })
    r2 = client.post(f"/api/superadmin/settlement-faspay/{settlement['id']}/rekonsiliasi-h1", headers=headers_super)
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["status_rekonsiliasi"] == "RECONCILED"
    assert len(body2["items"]) == 1  # tertimpa, bukan menumpuk jadi 2


# ============================= Akses =============================

def test_endpoint_superadmin_ditolak_untuk_tenant_biasa(single_tenant):
    r = single_tenant["client"].get("/api/superadmin/settlement-faspay", headers=single_tenant["headers"])
    assert r.status_code == 403


def test_endpoint_tenant_ditolak_tanpa_login(app_client):
    r = app_client.get("/api/settlement-faspay/preview", params={"tanggal": "2026-08-23"})
    assert r.status_code == 401


def test_h1_settlement_tidak_ditemukan_404(single_tenant):
    client = single_tenant["client"]
    headers_super = _buat_superadmin_dan_login(client)
    r = client.post("/api/superadmin/settlement-faspay/999999/rekonsiliasi-h1", headers=headers_super)
    assert r.status_code == 404


def test_superadmin_bisa_lihat_settlement_semua_tenant(two_tenants):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    client = two_tenants["client"]
    _buat_transaksi_snap(tenant_a, status="PAID", tanggal_created="2026-08-23")
    _buat_transaksi_snap(tenant_b, status="PAID", tanggal_created="2026-08-23")
    client.post("/api/settlement-faspay", params={"tanggal": "2026-08-23"}, headers=two_tenants["headers_a"])
    client.post("/api/settlement-faspay", params={"tanggal": "2026-08-23"}, headers=two_tenants["headers_b"])
    headers_super = _buat_superadmin_dan_login(client)

    r = client.get("/api/superadmin/settlement-faspay", headers=headers_super)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 2
