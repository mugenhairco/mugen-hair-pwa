"""
subscription_migrasi.py — FONDASI Multi-Tenant Phase 3: Subscription & Tenant Lifecycle
=============================================================================
Migrasi backfill SEKALI SAJA (idempotent): pastikan SETIAP tenant yang sudah
ada (termasuk tenant produksi yang sudah live sebelum Phase 3 ini, mis.
"MUGEN Hair Co.") punya baris `tenant_subscriptions` -- lihat
subscription_db.create_default_subscription() untuk detail idempotensinya
(baris yang SUDAH ADA tidak pernah ditimpa).

PENTING -- TIDAK ADA status default yang di-hardcode permanen untuk tenant
mana pun (termasuk tenant produksi lama): default package/status BARU dibaca
dari environment variable SUBSCRIPTION_SEED_DEFAULT_PACKAGE/
SUBSCRIPTION_SEED_DEFAULT_STATUS (fallback 'free'/'active' kalau kosong,
supaya migrasi ini AMAN dijalankan tanpa konfigurasi tambahan -- tidak
pernah mengunci/memutus akses tenant yang sudah ada) -- Super Admin BEBAS
mengubah package/status/trial/grace tiap tenant kapan pun lewat Dashboard
Super Admin SETELAH baris ini dibuat, sama seperti tenant lain mana pun,
TIDAK ADA perlakuan khusus untuk tenant tertentu di kode ini."""

import os

import tenant_db
from subscription_db import create_default_subscription, init_subscription_db, PACKAGE_VALID, STATUS_VALID


def _default_package() -> str:
    nilai = os.environ.get("SUBSCRIPTION_SEED_DEFAULT_PACKAGE", "free").strip().lower()
    return nilai if nilai in PACKAGE_VALID else "free"


def _default_status() -> str:
    nilai = os.environ.get("SUBSCRIPTION_SEED_DEFAULT_STATUS", "active").strip().lower()
    return nilai if nilai in STATUS_VALID else "active"


def migrasi_subscription():
    """WAJIB dipanggil SETELAH migrasi_tenant() (butuh tabel `tenants` sudah
    ada & terisi) -- lihat urutan pemanggilan di main.py::on_startup()."""
    init_subscription_db()
    package = _default_package()
    status = _default_status()
    for tenant in tenant_db.list_tenants():
        create_default_subscription(tenant["id"], package=package, status=status)
