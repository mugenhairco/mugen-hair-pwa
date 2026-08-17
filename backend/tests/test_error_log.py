"""test_error_log.py — DIY error monitoring (bukan Sentry, lihat
error_log_db.py). Cakupan: error_log_db.py (catat_error/get_error_log_list/
pemangkasan baris lama), routers/error_log.py (POST publik TANPA login,
GET khusus Owner), dan main.py::_tangani_exception_global() (auto-capture
crash tak terduga, dites langsung terhadap fungsi handler-nya -- BUKAN lewat
route asli, supaya tidak perlu menyuntik route yang sengaja crash ke app
produksi)."""

import asyncio

import error_log_db


# ---------------------------------------------------------------------------
# error_log_db.py
# ---------------------------------------------------------------------------

def test_catat_dan_ambil_error(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    error_log_db.catat_error(sumber="frontend", pesan="TypeError: x is not a function",
                              detail="at foo.js:12", url="https://x/app/#/booking",
                              user_agent="Mozilla/5.0", tenant_id=tenant_id)
    logs = error_log_db.get_error_log_list(tenant_id=tenant_id)
    assert len(logs) == 1
    assert logs[0]["pesan"] == "TypeError: x is not a function"
    assert logs[0]["sumber"] == "frontend"
    assert logs[0]["url"] == "https://x/app/#/booking"


def test_get_error_log_list_hanya_tenant_sendiri(two_tenants):
    error_log_db.catat_error(sumber="frontend", pesan="Error A", tenant_id=two_tenants["tenant_a"])
    error_log_db.catat_error(sumber="frontend", pesan="Error B", tenant_id=two_tenants["tenant_b"])
    logs_a = error_log_db.get_error_log_list(tenant_id=two_tenants["tenant_a"])
    assert len(logs_a) == 1
    assert logs_a[0]["pesan"] == "Error A"


def test_get_error_log_list_filter_sumber(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    error_log_db.catat_error(sumber="frontend", pesan="Error FE", tenant_id=tenant_id)
    error_log_db.catat_error(sumber="backend", pesan="Error BE", tenant_id=tenant_id)
    logs = error_log_db.get_error_log_list(tenant_id=tenant_id, sumber="backend")
    assert len(logs) == 1
    assert logs[0]["pesan"] == "Error BE"


def test_error_tenant_id_none_tidak_muncul_di_tenant_manapun(single_tenant):
    error_log_db.catat_error(sumber="backend", pesan="Crash sebelum tenant diketahui", tenant_id=None)
    assert error_log_db.get_error_log_list(tenant_id=single_tenant["tenant_id"]) == []


def test_pesan_dan_detail_dipangkas_panjang_maksimal(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    error_log_db.catat_error(sumber="frontend", pesan="x" * 5000, detail="y" * 20000, tenant_id=tenant_id)
    log = error_log_db.get_error_log_list(tenant_id=tenant_id)[0]
    assert len(log["pesan"]) == 2000
    assert len(log["detail"]) == 8000


def test_baris_terlama_dipangkas_lewat_batas(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    monkeypatch.setattr(error_log_db, "BATAS_BARIS", 3)
    for i in range(5):
        error_log_db.catat_error(sumber="frontend", pesan=f"Error #{i}", tenant_id=tenant_id)
    logs = error_log_db.get_error_log_list(tenant_id=tenant_id, limit=100)
    assert len(logs) == 3
    # Baris yang TERSISA harus yang PALING BARU (#2, #3, #4) -- baris #0/#1
    # (paling lama) yang dihapus duluan.
    pesan_tersisa = {l["pesan"] for l in logs}
    assert pesan_tersisa == {"Error #2", "Error #3", "Error #4"}


# ---------------------------------------------------------------------------
# routers/error_log.py -- POST publik (tanpa login), GET khusus Owner
# ---------------------------------------------------------------------------

def test_post_log_error_tanpa_login_pakai_slug_query(single_tenant):
    client = single_tenant["client"]
    tenant_slug = "test-toko"
    r = client.post(f"/api/log-error?tenant={tenant_slug}", json={
        "pesan": "Gagal render halaman Login", "sumber": "frontend",
        "url": "https://x/app/#/login", "user_agent": "TestAgent/1.0",
    })
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    logs = error_log_db.get_error_log_list(tenant_id=single_tenant["tenant_id"])
    assert len(logs) == 1
    assert logs[0]["pesan"] == "Gagal render halaman Login"


def test_post_log_error_tanpa_login_tanpa_slug_tetap_ok_tenant_none(app_client):
    """Tidak ada sesi, tidak ada slug -- endpoint TIDAK BOLEH 404 (beda dari
    resolve_tenant_publik yang tegas menolak) -- tenant_id disimpan None,
    tetap tercatat (lihat catatan di error_log_db.get_error_log_list soal
    baris tenant_id NULL tidak muncul di tampilan tenant manapun)."""
    r = app_client.post("/api/log-error", json={"pesan": "Error tanpa tenant sama sekali"})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}


def test_post_log_error_dengan_sesi_login_pakai_tenant_sesi(single_tenant):
    client = single_tenant["client"]
    headers = single_tenant["headers"]
    r = client.post("/api/log-error", json={"pesan": "Error saat sudah login", "sumber": "frontend"},
                     headers=headers)
    assert r.status_code == 200, r.text
    logs = error_log_db.get_error_log_list(tenant_id=single_tenant["tenant_id"])
    assert len(logs) == 1
    assert logs[0]["pesan"] == "Error saat sudah login"


def test_post_log_error_sumber_tidak_valid_jatuh_ke_frontend(single_tenant):
    client = single_tenant["client"]
    headers = single_tenant["headers"]
    client.post("/api/log-error", json={"pesan": "x", "sumber": "sumber-aneh"}, headers=headers)
    logs = error_log_db.get_error_log_list(tenant_id=single_tenant["tenant_id"])
    assert logs[0]["sumber"] == "frontend"


def test_get_log_error_khusus_owner(single_tenant):
    client = single_tenant["client"]
    headers = single_tenant["headers"]
    error_log_db.catat_error(sumber="frontend", pesan="Error lama", tenant_id=single_tenant["tenant_id"])

    r = client.get("/api/log-error", headers=headers)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1
    assert r.json()[0]["pesan"] == "Error lama"


def test_get_log_error_barber_ditolak(single_tenant):
    client = single_tenant["client"]
    tenant_id = single_tenant["tenant_id"]
    import database as db
    import auth_db
    barber_id = db.add_barber("Barber Test", tenant_id=tenant_id)
    auth_db.tambah_user("barbertest", "passwordX123", role="barber", barber_id=barber_id, tenant_id=tenant_id)
    r = client.post("/api/auth/login", json={"username": "barbertest", "password": "passwordX123"})
    token = r.json()["token"]

    r = client.get("/api/log-error", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_get_log_error_tanpa_login_ditolak(app_client):
    r = app_client.get("/api/log-error")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# main.py::_tangani_exception_global() -- auto-capture crash backend
# ---------------------------------------------------------------------------

def test_exception_handler_global_mencatat_ke_error_logs_dan_balas_500(single_tenant):
    import database
    import main
    from starlette.requests import Request

    scope = {
        "type": "http", "method": "GET", "path": "/api/rusak-sengaja",
        "headers": [], "query_string": b"", "scheme": "http",
        "server": ("testserver", 80), "client": ("testclient", 123),
    }
    request = Request(scope)

    # traceback.format_exc() (dipanggil di dalam handler) HANYA mengembalikan
    # isi sungguhan kalau ada exception AKTIF di call stack saat itu (sama
    # seperti kondisi asli-nya: ExceptionMiddleware FastAPI selalu memanggil
    # exception handler dari dalam blok except) -- exception dibuat lewat
    # raise/except beneran di sini, BUKAN sekadar ValueError(...) yang belum
    # pernah di-raise (itu akan membuat traceback.format_exc() melihat
    # "NoneType: None", bukan traceback ValueError sungguhan).
    try:
        raise ValueError("boom -- error sengaja untuk tes")
    except ValueError as exc:
        response = asyncio.run(main._tangani_exception_global(request, exc))
    assert response.status_code == 500

    logs = error_log_db.get_error_log_list(tenant_id=single_tenant["tenant_id"])
    # tenant_id SELALU None dari exception handler global (lihat docstring-nya)
    # -- TIDAK PERNAH muncul di tampilan tenant manapun, verifikasi lewat
    # query langsung ke tabel tanpa filter tenant.
    assert logs == []
    with database.get_conn() as conn:
        rows = conn.execute("SELECT * FROM error_logs WHERE sumber = 'backend'").fetchall()
    assert len(rows) == 1
    assert "boom -- error sengaja untuk tes" in rows[0]["pesan"]
    assert "ValueError" in rows[0]["detail"]
    assert rows[0]["url"].endswith("/api/rusak-sengaja")
