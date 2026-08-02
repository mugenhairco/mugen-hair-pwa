// pages/superadmin.js — FONDASI Multi-Tenant Phase 2.1: Super Admin Dashboard
// Khusus akun role 'superadmin' (tenant_id=NULL, lihat auth_db.py/auth.py) --
// dirender router.js untuk SEMUA hash begitu login sebagai superadmin (lihat
// router.js), jadi halaman ini TIDAK mengikuti sistem menu/hash biasa.
//
// Dua bagian: 1) daftar seluruh tenant + tombol Aktifkan/Nonaktifkan,
// 2) form buat toko baru (+ akun Owner pertamanya sekaligus, lihat
// routers/superadmin.py::buat_tenant()).

const PageSuperadmin = (() => {
  // waktu audit log disimpan sebagai ISO "YYYY-MM-DDTHH:MM:SS" (lihat
  // superadmin_audit_db.py) -- formatTanggal() di ui.js hanya untuk tanggal
  // tanpa jam (split "-" saja), jadi dipakai formatter lokal kecil di sini.
  function formatWaktu(iso) {
    if (!iso) return "-";
    const [tanggal, jam] = iso.split("T");
    return `${MugenUI.formatTanggal(tanggal)} ${jam || ""}`.trim();
  }

  const AKSI_LABEL = {
    buat_tenant: "Buat Toko",
    aktifkan_tenant: "Aktifkan Toko",
    nonaktifkan_tenant: "Nonaktifkan Toko",
  };

  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Kelola Tenant (Super Admin)"));

    let tenantList = [];

    const formCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    const auditCard = MugenUI.el("div", { class: "card" });
    root.appendChild(listCard);
    root.appendChild(formCard);
    root.appendChild(auditCard);

    // ---------------------------------------------------------------
    // 1. DAFTAR TENANT
    // ---------------------------------------------------------------
    listCard.appendChild(MugenUI.el("h2", {}, "Daftar Toko"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    async function loadTenantList() {
      listBody.innerHTML = "Memuat...";
      try {
        tenantList = await MugenApi.get("/api/superadmin/tenants");
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.buildTable(
          [
            { key: "nama_barbershop", label: "Nama Barbershop" },
            { key: "slug", label: "Slug" },
            {
              key: "status", label: "Status",
              format: (v) => MugenUI.el("span", {
                class: "badge" + (v === "aktif" ? "" : " badge-libur"),
              }, v === "aktif" ? "Aktif" : "Nonaktif"),
            },
            { key: "jumlah_owner", label: "Jumlah Owner" },
            { key: "jumlah_user", label: "Jumlah User" },
            {
              key: "aksi", label: "Aksi", format: (_, t) => {
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const menujuAktif = t.status !== "aktif";
                const btnToggle = MugenUI.el(
                  "button",
                  { class: menujuAktif ? "" : "btn-danger" },
                  menujuAktif ? "Aktifkan" : "Nonaktifkan",
                );
                btnToggle.addEventListener("click", async () => {
                  const statusBaru = menujuAktif ? "aktif" : "nonaktif";
                  if (!confirm(`${menujuAktif ? "Aktifkan" : "Nonaktifkan"} toko "${t.nama_barbershop}"?`)) return;
                  try {
                    await MugenUI.withLoading(
                      () => MugenApi.put(`/api/superadmin/tenants/${t.id}/status`, { status: statusBaru }),
                      { message: "Menyimpan…" },
                    );
                    MugenUI.toast("Status toko diperbarui.", "success");
                    loadTenantList();
                    loadAuditLog();
                  } catch (e) {
                    MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                  }
                });
                wrap.appendChild(btnToggle);
                return wrap;
              },
            },
          ],
          tenantList,
          { emptyText: "Belum ada toko." },
        ));
      } catch (e) {
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.el("div", {}, e.message));
      }
    }

    // ---------------------------------------------------------------
    // 2. BUAT TOKO BARU (+ akun Owner pertamanya)
    // ---------------------------------------------------------------
    formCard.appendChild(MugenUI.el("h2", {}, "Buat Toko Baru"));
    const inputSlug = MugenUI.el("input", { type: "text", placeholder: "slug-toko (huruf kecil, tanpa spasi)" });
    const inputNama = MugenUI.el("input", { type: "text", placeholder: "Nama Barbershop" });
    const inputOwnerUsername = MugenUI.el("input", { type: "text", placeholder: "Username Owner", autocomplete: "off" });
    const inputOwnerPassword = MugenUI.el("input", { type: "password", placeholder: "Password Owner (min. 4 karakter)", autocomplete: "new-password" });
    const btnBuatTenant = MugenUI.el("button", { class: "btn-primary" }, "Buat Toko");
    const formError = MugenUI.el("div", { class: "login-error" });

    formCard.appendChild(MugenUI.el("label", {}, "Slug"));
    formCard.appendChild(inputSlug);
    formCard.appendChild(MugenUI.el("label", {}, "Nama Barbershop"));
    formCard.appendChild(inputNama);
    formCard.appendChild(MugenUI.el("label", {}, "Username Owner"));
    formCard.appendChild(inputOwnerUsername);
    formCard.appendChild(MugenUI.el("label", {}, "Password Owner"));
    formCard.appendChild(inputOwnerPassword);
    formCard.appendChild(formError);
    formCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnBuatTenant]));

    btnBuatTenant.addEventListener("click", async () => {
      formError.textContent = "";
      const slug = inputSlug.value.trim().toLowerCase();
      const nama = inputNama.value.trim();
      const ownerUsername = inputOwnerUsername.value.trim();
      const ownerPassword = inputOwnerPassword.value;
      if (!slug || !nama || !ownerUsername || !ownerPassword) {
        formError.textContent = "Semua field wajib diisi.";
        return;
      }
      btnBuatTenant.disabled = true;
      try {
        await MugenUI.withLoading(() => MugenApi.post("/api/superadmin/tenants", {
          slug, nama_barbershop: nama,
          owner_username: ownerUsername, owner_password: ownerPassword,
        }), { message: "Membuat toko…" });
        MugenUI.toast("Toko baru dibuat.", "success");
        inputSlug.value = "";
        inputNama.value = "";
        inputOwnerUsername.value = "";
        inputOwnerPassword.value = "";
        loadTenantList();
        loadAuditLog();
      } catch (e) {
        formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      } finally {
        btnBuatTenant.disabled = false;
      }
    });

    // ---------------------------------------------------------------
    // 3. RIWAYAT AKSI (Audit Log)
    // ---------------------------------------------------------------
    auditCard.appendChild(MugenUI.el("h2", {}, "Riwayat Aksi"));
    const auditBody = MugenUI.el("div");
    auditCard.appendChild(auditBody);

    async function loadAuditLog() {
      auditBody.innerHTML = "Memuat...";
      try {
        const log = await MugenApi.get("/api/superadmin/audit-log");
        auditBody.innerHTML = "";
        auditBody.appendChild(MugenUI.buildTable(
          [
            { key: "waktu", label: "Waktu", format: formatWaktu },
            { key: "superadmin_username", label: "Super Admin" },
            { key: "aksi", label: "Aksi", format: (v) => AKSI_LABEL[v] || v },
            { key: "tenant_slug", label: "Toko" },
            { key: "detail", label: "Detail" },
          ],
          log,
          { emptyText: "Belum ada aksi tercatat." },
        ));
      } catch (e) {
        auditBody.innerHTML = "";
        auditBody.appendChild(MugenUI.el("div", {}, e.message));
      }
    }

    await loadTenantList();
    await loadAuditLog();
  }

  return { render };
})();
