"""feature_access.py — Penegakan Fitur per Paket Langganan (Feature Gating)
=============================================================================
`subscription_packages`/`subscription_features`/`subscription_package_features`
(billing_db.py, FONDASI Multi-Tenant Phase 4) SUDAH ADA lengkap dengan CRUD
Superadmin (routers/billing.py::superadmin_router, superadmin.js) -- tapi
sebelumnya MURNI katalog/display (badge fitur di halaman harga), TIDAK
pernah menggerbang satu endpoint pun. File ini menambahkan penegakan
sungguhan: `tenant_has_feature()` dipanggil dari auth.py::require_feature()
(dependency FastAPI, dipasang per endpoint sama seperti require_permission()).

Dipanggil dari LAPISAN ROUTER, sama seperti billing_limits.py/permissions.py
(business logic murni CRUD tetap tidak tahu apa-apa soal billing).

BEDA SENGAJA dari billing_limits.py (fail-OPEN untuk limit numerik -- tenant
tanpa baris tenant_subscriptions/subscription_packages dianggap TIDAK
DIBATASI, karena NULL pada kolom limit sudah py berarti "unlimited" secara
sah): untuk FITUR, tenant tanpa baris subscription/paket dianggap TIDAK
PUNYA fitur apa pun (fail-CLOSED) -- "tidak ada data paket" tidak boleh
diam-diam disamakan dengan "paket ter-lengkap", beda konteks dari limit
angka yang memang punya makna "unlimited" bawaan.

Cakupan fitur yang SUNGGUHAN ditegakkan (lihat README/plan implementasi):
hanya `booking_online`, `qris`, `export_pdf` -- SATU-SATUNYA kode fitur di
katalog (`billing_db._FITUR_DEFAULT`) yang punya padanan fungsi nyata di
aplikasi ini. Kode fitur lain (google_calendar/api/priority_support/
multi_cabang/whatsapp_reminder/export_excel) TETAP bisa dibuat/di-toggle
Superadmin lewat Katalog Fitur (tidak dihapus/disembunyikan), tapi memang
belum ada titik penegakan untuk itu SAMPAI fungsinya sungguhan dibangun --
`tenant_has_feature()` di bawah generik untuk kode APA PUN, jadi menambah
penegakan fitur baru nanti cukup satu baris `Depends(require_feature("kode_baru"))`
di endpoint terkait, tanpa mengubah file ini."""

import billing_db
import subscription_db


def tenant_has_feature(tenant_id: int, kode: str) -> bool:
    """True kalau paket AKTIF tenant ini menyertakan kode fitur `kode`.
    Selalu query database langsung (tidak ada cache di lapisan ini) --
    upgrade/downgrade paket (routers/superadmin.py, billing_webhook.py)
    jadi otomatis berlaku di request BERIKUTNYA tanpa restart/deploy ulang."""
    sub = subscription_db.get_subscription(tenant_id)
    if sub is None:
        return False
    paket = billing_db.get_package_by_kode(sub["package"])
    if paket is None:
        return False
    return any(f["kode"] == kode for f in billing_db.get_package_features(paket["id"]))
