"""routers/superadmin.py — FONDASI Multi-Tenant Phase 2.1: Super Admin Dashboard
=============================================================================
Seluruh endpoint di sini KHUSUS akun `role='superadmin'` (require_superadmin,
lihat auth.py) -- mengelola SELURUH tenant dari satu tempat: daftar toko,
buat toko baru (+ akun Owner pertamanya), dan aktifkan/nonaktifkan toko.

TIDAK ADA endpoint di sini yang membaca/mengubah data BISNIS tenant mana pun
(transaksi, booking, dst) -- itu tetap murni urusan Owner/Admin masing-
masing toko lewat router lain, sesuai batas tanggung jawab Super Admin yang
sudah disepakati (identitas & lifecycle tenant, bukan operasional harian)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import auth_db
import subscription_db
import superadmin_audit_db
import tenant_db
from auth import require_superadmin

router = APIRouter(prefix="/api/superadmin", tags=["superadmin"])


def _tenant_dengan_ringkasan(t: dict) -> dict:
    """Tambahkan jumlah_user & jumlah_owner ke satu baris tenant -- cukup
    query ringan (get_user_list sudah dipakai luas di modul lain), supaya
    Dashboard Super Admin bisa menampilkan gambaran singkat tiap toko tanpa
    endpoint terpisah untuk kasus umum (lihat GET /tenants/{id} untuk daftar
    user LENGKAP kalau Super Admin perlu detail)."""
    hasil = dict(t)
    daftar_user = auth_db.get_user_list(tenant_id=t["id"])
    hasil["jumlah_user"] = len(daftar_user)
    hasil["jumlah_owner"] = sum(1 for u in daftar_user if u["role"] == "admin" and u["aktif"])
    return hasil


@router.get("/tenants")
def list_tenants(user: dict = Depends(require_superadmin)):
    return [_tenant_dengan_ringkasan(t) for t in tenant_db.list_tenants()]


@router.get("/tenants/{tenant_id}")
def detail_tenant(tenant_id: int, user: dict = Depends(require_superadmin)):
    t = tenant_db.get_tenant(tenant_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Tenant tidak ditemukan.")
    hasil = dict(t)
    daftar_user = auth_db.get_user_list(tenant_id=tenant_id)
    for u in daftar_user:
        u.pop("password_hash", None)
    hasil["users"] = daftar_user
    return hasil


class BuatTenantBody(BaseModel):
    slug: str
    nama_barbershop: str
    owner_username: str
    owner_password: str


@router.post("/tenants")
def buat_tenant(body: BuatTenantBody, user: dict = Depends(require_superadmin)):
    """Provisioning toko baru: baris `tenants` + SATU akun Owner ('admin')
    pertamanya sekaligus, supaya Super Admin tidak perlu langkah manual
    tambahan sebelum toko baru bisa dipakai (sama seperti
    main.py::_bootstrap_admin_pertama() untuk instalasi single-tenant lama,
    tapi dipicu lewat Dashboard alih-alih environment variable)."""
    try:
        tenant_id = tenant_db.buat_tenant(body.slug, body.nama_barbershop)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    try:
        auth_db.tambah_user(username=body.owner_username, password=body.owner_password,
                             role="admin", tenant_id=tenant_id)
    except ValueError as e:
        # Toko sudah terlanjur dibuat tapi akun Owner gagal (mis. password
        # < 4 karakter) -- tenant_id-nya tetap valid, Super Admin bisa buat
        # ulang akun Owner-nya lewat percobaan berikutnya (buat_tenant() di
        # atas akan menolak slug yang sama, jadi endpoint ini TIDAK dipanggil
        # ulang untuk toko yang sama; kasus ini cukup jarang untuk tidak
        # butuh rollback otomatis).
        raise HTTPException(status_code=422, detail=f"Toko dibuat, tapi akun Owner gagal: {e}")
    # FONDASI Multi-Tenant Phase 3: tenant baru langsung dapat baris
    # tenant_subscriptions default (sama seperti backfill migrasi untuk
    # tenant lama, lihat subscription_migrasi.py) -- supaya TIDAK ADA tenant
    # yang pernah "tidak dikenal" sistem subscription sejak awal dibuat.
    subscription_db.create_default_subscription(tenant_id)
    superadmin_audit_db.catat(user["username"], "buat_tenant", tenant_id=tenant_id, tenant_slug=body.slug,
                               detail=f"nama_barbershop={body.nama_barbershop!r}, owner_username={body.owner_username!r}")
    return _tenant_dengan_ringkasan(tenant_db.get_tenant(tenant_id))


class StatusTenantBody(BaseModel):
    status: str


@router.put("/tenants/{tenant_id}/status")
def ubah_status_tenant(tenant_id: int, body: StatusTenantBody, user: dict = Depends(require_superadmin)):
    try:
        tenant_db.set_status(tenant_id, body.status)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    t = tenant_db.get_tenant(tenant_id)
    aksi = "aktifkan_tenant" if body.status == "aktif" else "nonaktifkan_tenant"
    superadmin_audit_db.catat(user["username"], aksi, tenant_id=tenant_id, tenant_slug=t["slug"] if t else None)
    return _tenant_dengan_ringkasan(t)


@router.get("/audit-log")
def audit_log(user: dict = Depends(require_superadmin)):
    return superadmin_audit_db.list_log()
