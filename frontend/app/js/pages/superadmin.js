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
    // FONDASI Multi-Tenant Phase 3 (Subscription & Tenant Lifecycle).
    ubah_package_subscription: "Ubah Package Subscription",
    ubah_status_subscription: "Ubah Status Subscription",
    ubah_trial_subscription: "Ubah Trial Subscription",
    ubah_grace_subscription: "Ubah Grace Period Subscription",
    ubah_config_subscription: "Ubah Konfigurasi Subscription",
    buat_pembayaran_subscription: "Catat Pembayaran Subscription",
    ubah_status_pembayaran_subscription: "Ubah Status Pembayaran Subscription",
    // FONDASI Multi-Tenant Phase 4 (Billing & Payment Midtrans).
    ubah_paket_billing: "Ubah Paket Billing",
    tambah_fitur_billing: "Tambah Fitur Billing",
    ubah_fitur_billing: "Ubah Fitur Billing",
    hapus_fitur_billing: "Hapus Fitur Billing",
    ubah_fitur_paket_billing: "Ubah Fitur Paket Billing",
  };

  const LABEL_STATUS_INVOICE = {
    pending: "Menunggu Pembayaran", paid: "Berhasil", denied: "Ditolak",
    cancelled: "Dibatalkan", expired: "Kedaluwarsa",
  };
  const BADGE_STATUS_INVOICE = {
    pending: "badge-warning", paid: "badge-success", denied: "badge-danger",
    cancelled: "badge-danger", expired: "badge-danger",
  };

  const LABEL_PACKAGE_SUBS = { free: "Free", basic: "Basic", pro: "Pro", enterprise: "Enterprise" };
  const LABEL_STATUS_SUBS = {
    trial: "Trial", active: "Active", grace_period: "Grace Period",
    expired: "Expired", suspended: "Suspended", cancelled: "Cancelled",
  };
  const BADGE_STATUS_SUBS = {
    trial: "badge-libur", active: "badge-success", grace_period: "badge-warning",
    expired: "badge-danger", suspended: "badge-danger", cancelled: "badge-danger",
  };
  const LABEL_PAYMENT_STATUS = { pending: "Pending", paid: "Lunas", expired: "Kedaluwarsa", failed: "Gagal" };

  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Kelola Tenant (Super Admin)"));

    let tenantList = [];

    const formCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    const subsConfigCard = MugenUI.el("div", { class: "card" });
    const subsManagerCard = MugenUI.el("div", { class: "card" });
    // FONDASI Multi-Tenant Phase 4: tiga kartu baru, TIDAK mengubah kartu
    // Phase 3 di atas sama sekali -- lihat billing_db.py/routers/billing.py.
    const billingPackagesCard = MugenUI.el("div", { class: "card" });
    const billingFeaturesCard = MugenUI.el("div", { class: "card" });
    const billingInvoicesCard = MugenUI.el("div", { class: "card" });
    // FONDASI Multi-Tenant Phase 5 (Landing Page SaaS): tiga kartu baru,
    // TIDAK mengubah kartu Phase 3/4 di atas sama sekali -- lihat
    // landing_db.py/routers/landing.py.
    const landingFaqCard = MugenUI.el("div", { class: "card" });
    const landingTestimonialsCard = MugenUI.el("div", { class: "card" });
    const landingContactCard = MugenUI.el("div", { class: "card" });
    const auditCard = MugenUI.el("div", { class: "card" });
    root.appendChild(listCard);
    root.appendChild(formCard);
    root.appendChild(subsConfigCard);
    root.appendChild(subsManagerCard);
    root.appendChild(billingPackagesCard);
    root.appendChild(billingFeaturesCard);
    root.appendChild(billingInvoicesCard);
    root.appendChild(landingFaqCard);
    root.appendChild(landingTestimonialsCard);
    root.appendChild(landingContactCard);
    root.appendChild(auditCard);

    // ---------------------------------------------------------------
    // 1. DAFTAR TENANT
    // ---------------------------------------------------------------
    listCard.appendChild(MugenUI.el("h2", {}, "Daftar Toko"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    // REVISI UI/UX Premium: skeleton menggantikan teks "Memuat...".
    async function loadTenantList() {
      listBody.innerHTML = "";
      listBody.appendChild(MugenUI.skeleton("table", { cols: 7, rows: 4 }));
      try {
        const [tenants, subs] = await Promise.all([
          MugenApi.get("/api/superadmin/tenants"),
          MugenApi.get("/api/superadmin/subscriptions"),
        ]);
        const subsByTenantId = {};
        for (const s of subs) subsByTenantId[s.tenant_id] = s;
        tenantList = tenants.map((t) => ({ ...t, subscription: subsByTenantId[t.id] || null }));
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.buildTable(
          [
            { key: "nama_barbershop", label: "Nama Barbershop" },
            { key: "slug", label: "Slug" },
            // FITUR Alamat Website Tenant: website_url dikirim backend
            // (routers/superadmin.py::_tenant_dengan_ringkasan(), lewat
            // tenant_db.get_website_url() -- custom_domain kalau tenant
            // sudah pindah domain sendiri, else subdomain dari slug) --
            // link bisa langsung diklik (buka tab baru) PLUS tombol Salin/
            // Buka terpisah untuk kenyamanan, supaya Super Admin tidak
            // perlu cek manual ke Render/Cloudflare/database.
            {
              key: "website_url", label: "Alamat Website",
              format: (v) => {
                if (!v) return MugenUI.el("span", { class: "subtitle" }, "Belum dibuat");
                const link = MugenUI.el("a", { href: v, target: "_blank", rel: "noopener noreferrer" }, v);
                const btnSalin = MugenUI.el("button", { type: "button", title: "Salin URL" }, "📋 Salin");
                btnSalin.addEventListener("click", async () => {
                  try {
                    await navigator.clipboard.writeText(v);
                    MugenUI.toast("Alamat website disalin.", "success");
                  } catch (e) {
                    MugenUI.toast("Gagal menyalin otomatis -- salin manual dari link di atas.", "error");
                  }
                });
                const btnBuka = MugenUI.el(
                  "a",
                  { href: v, target: "_blank", rel: "noopener noreferrer", class: "btn-primary", title: "Buka Website" },
                  "↗ Buka",
                );
                return MugenUI.el("div", { class: "actions-cell", style: "flex-wrap:wrap;align-items:center;gap:6px;" },
                  [link, btnSalin, btnBuka]);
              },
            },
            {
              key: "status", label: "Status",
              format: (v) => MugenUI.el("span", {
                class: "badge" + (v === "aktif" ? "" : " badge-libur"),
              }, v === "aktif" ? "Aktif" : "Nonaktif"),
            },
            {
              key: "subscription", label: "Subscription",
              format: (v) => v
                ? MugenUI.el("span", { class: "badge " + (BADGE_STATUS_SUBS[v.status] || "") },
                    `${LABEL_PACKAGE_SUBS[v.package] || v.package} / ${LABEL_STATUS_SUBS[v.status] || v.status}`)
                : MugenUI.el("span", { class: "subtitle" }, "belum ada"),
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
                    // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
                    await MugenUI.withButtonLoading(btnToggle,
                      () => MugenApi.put(`/api/superadmin/tenants/${t.id}/status`, { status: statusBaru }));
                    MugenUI.toast("Status toko diperbarui.", "success");
                    loadTenantList();
                    loadAuditLog();
                  } catch (e) {
                    MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                  }
                });
                wrap.appendChild(btnToggle);
                const btnKelolaSubs = MugenUI.el("button", {}, "Kelola Subscription");
                btnKelolaSubs.addEventListener("click", () => renderSubscriptionManager(t));
                wrap.appendChild(btnKelolaSubs);
                return wrap;
              },
            },
          ],
          tenantList,
          { emptyText: "Belum ada toko." },
        ));
      } catch (e) {
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.errorState(e.message));
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
      try {
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        await MugenUI.withButtonLoading(btnBuatTenant, () => MugenApi.post("/api/superadmin/tenants", {
          slug, nama_barbershop: nama,
          owner_username: ownerUsername, owner_password: ownerPassword,
        }));
        // Aksi besar/konfirmasi penting (pembuatan tenant baru) -- toast
        // sukses SENGAJA ditampilkan (force:true), lihat whitelist di ui.js.
        MugenUI.toast("Toko baru dibuat.", "success", { force: true });
        inputSlug.value = "";
        inputNama.value = "";
        inputOwnerUsername.value = "";
        inputOwnerPassword.value = "";
        loadTenantList();
        loadAuditLog();
      } catch (e) {
        formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });

    // ---------------------------------------------------------------
    // 3. KONFIGURASI SUBSCRIPTION (platform-wide, FONDASI Multi-Tenant Phase 3)
    // ---------------------------------------------------------------
    subsConfigCard.appendChild(MugenUI.el("h2", {}, "Konfigurasi Subscription"));
    subsConfigCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Durasi default (hari) dipakai saat Trial/Grace Period BARU diatur ke tenant mana pun tanpa mengisi jumlah hari secara eksplisit."));
    const inputTrialHari = MugenUI.el("input", { type: "number", min: "1" });
    const inputGraceHari = MugenUI.el("input", { type: "number", min: "1" });
    const btnSimpanConfig = MugenUI.el("button", { class: "btn-primary" }, "Simpan Konfigurasi");
    const configError = MugenUI.el("div", { class: "login-error" });
    subsConfigCard.appendChild(MugenUI.el("label", {}, "Durasi Trial Default (hari)"));
    subsConfigCard.appendChild(inputTrialHari);
    subsConfigCard.appendChild(MugenUI.el("label", {}, "Durasi Grace Period Default (hari)"));
    subsConfigCard.appendChild(inputGraceHari);
    subsConfigCard.appendChild(configError);
    subsConfigCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanConfig));

    async function loadSubsConfig() {
      try {
        const cfg = await MugenApi.get("/api/superadmin/subscriptions/config");
        inputTrialHari.value = cfg.trial_hari;
        inputGraceHari.value = cfg.grace_hari;
      } catch (e) { configError.textContent = e.message; }
    }
    btnSimpanConfig.addEventListener("click", async () => {
      configError.textContent = "";
      try {
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        await MugenUI.withButtonLoading(btnSimpanConfig, () => MugenApi.put("/api/superadmin/subscriptions/config", {
          trial_hari: parseInt(inputTrialHari.value, 10) || null,
          grace_hari: parseInt(inputGraceHari.value, 10) || null,
        }));
        MugenUI.toast("Konfigurasi Subscription disimpan.", "success");
        loadAuditLog();
      } catch (e) {
        configError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });

    // ---------------------------------------------------------------
    // 4. KELOLA SUBSCRIPTION PER TOKO (FONDASI Multi-Tenant Phase 3)
    // ---------------------------------------------------------------
    subsManagerCard.appendChild(MugenUI.el("h2", {}, "Kelola Subscription Toko"));
    const subsManagerBody = MugenUI.el("div", {}, "Klik \"Kelola Subscription\" pada salah satu toko di Daftar Toko di atas.");
    subsManagerCard.appendChild(subsManagerBody);

    // REVISI UI/UX Premium: skeleton menggantikan teks "Memuat...".
    async function renderSubscriptionManager(tenant) {
      subsManagerBody.innerHTML = "";
      subsManagerBody.appendChild(MugenUI.skeleton("card", { lines: 3 }));
      let sub;
      try {
        sub = await MugenApi.get(`/api/superadmin/subscriptions/${tenant.id}`);
      } catch (e) {
        subsManagerBody.innerHTML = "";
        subsManagerBody.appendChild(MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message));
        return;
      }
      subsManagerBody.innerHTML = "";
      subsManagerBody.appendChild(MugenUI.el("h3", {}, tenant.nama_barbershop));

      // --- Package & Status ---
      const selPackage = MugenUI.el("select");
      for (const k of Object.keys(LABEL_PACKAGE_SUBS)) selPackage.appendChild(MugenUI.el("option", { value: k }, LABEL_PACKAGE_SUBS[k]));
      selPackage.value = sub.package;
      const btnSimpanPackage = MugenUI.el("button", {}, "Simpan Package");
      const selStatus = MugenUI.el("select");
      for (const k of Object.keys(LABEL_STATUS_SUBS)) selStatus.appendChild(MugenUI.el("option", { value: k }, LABEL_STATUS_SUBS[k]));
      selStatus.value = sub.status;
      const btnSimpanStatus = MugenUI.el("button", {}, "Simpan Status");
      const errPackageStatus = MugenUI.el("div", { class: "login-error" });

      subsManagerBody.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;align-items:flex-end;margin-top:8px;" }, [
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Package"), selPackage]),
        btnSimpanPackage,
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Status"), selStatus]),
        btnSimpanStatus,
      ]));
      subsManagerBody.appendChild(errPackageStatus);

      // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading();
      // aksi besar/konfirmasi penting (perubahan package/status subscription
      // TENANT) -- toast sukses SENGAJA force:true, lihat whitelist di ui.js.
      btnSimpanPackage.addEventListener("click", async () => {
        errPackageStatus.textContent = "";
        try {
          await MugenUI.withButtonLoading(btnSimpanPackage, () => MugenApi.put(`/api/superadmin/subscriptions/${tenant.id}/package`,
            { package: selPackage.value }));
          MugenUI.toast("Package disimpan.", "success", { force: true });
          loadTenantList(); loadAuditLog(); renderSubscriptionManager(tenant);
        } catch (e) { errPackageStatus.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
      });
      btnSimpanStatus.addEventListener("click", async () => {
        errPackageStatus.textContent = "";
        try {
          await MugenUI.withButtonLoading(btnSimpanStatus, () => MugenApi.put(`/api/superadmin/subscriptions/${tenant.id}/status`,
            { status: selStatus.value }));
          MugenUI.toast("Status disimpan.", "success", { force: true });
          loadTenantList(); loadAuditLog(); renderSubscriptionManager(tenant);
        } catch (e) { errPackageStatus.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
      });

      // --- Trial & Grace ---
      const infoTrial = sub.trial_start ? `${formatWaktu(sub.trial_start)} s/d ${formatWaktu(sub.trial_end)}` : "belum diatur";
      const infoGrace = sub.grace_start ? `${formatWaktu(sub.grace_start)} s/d ${formatWaktu(sub.grace_end)}` : "belum diatur";
      const inputTrialHariTenant = MugenUI.el("input", { type: "number", min: "1", placeholder: "hari" });
      const btnSetTrial = MugenUI.el("button", {}, "Set Trial (mulai sekarang)");
      const inputGraceHariTenant = MugenUI.el("input", { type: "number", min: "1", placeholder: "hari" });
      const btnSetGrace = MugenUI.el("button", {}, "Set Grace Period (mulai sekarang)");
      const errTrialGrace = MugenUI.el("div", { class: "login-error" });

      subsManagerBody.appendChild(MugenUI.el("div", { style: "margin-top:16px;" }, [
        MugenUI.el("div", { class: "subtitle" }, `Masa Trial saat ini: ${infoTrial}`),
        MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:8px;align-items:flex-end;margin-top:4px;" }, [inputTrialHariTenant, btnSetTrial]),
      ]));
      subsManagerBody.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, [
        MugenUI.el("div", { class: "subtitle" }, `Grace Period saat ini: ${infoGrace}`),
        MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:8px;align-items:flex-end;margin-top:4px;" }, [inputGraceHariTenant, btnSetGrace]),
      ]));
      subsManagerBody.appendChild(errTrialGrace);

      btnSetTrial.addEventListener("click", async () => {
        errTrialGrace.textContent = "";
        try {
          await MugenUI.withButtonLoading(btnSetTrial, () => MugenApi.put(`/api/superadmin/subscriptions/${tenant.id}/trial`,
            { hari: inputTrialHariTenant.value ? parseInt(inputTrialHariTenant.value, 10) : null }));
          MugenUI.toast("Trial disimpan.", "success", { force: true });
          loadAuditLog(); renderSubscriptionManager(tenant);
        } catch (e) { errTrialGrace.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
      });
      btnSetGrace.addEventListener("click", async () => {
        errTrialGrace.textContent = "";
        try {
          await MugenUI.withButtonLoading(btnSetGrace, () => MugenApi.put(`/api/superadmin/subscriptions/${tenant.id}/grace`,
            { hari: inputGraceHariTenant.value ? parseInt(inputGraceHariTenant.value, 10) : null }));
          MugenUI.toast("Grace Period disimpan.", "success", { force: true });
          loadAuditLog(); renderSubscriptionManager(tenant);
        } catch (e) { errTrialGrace.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
      });

      // --- Pembayaran (VA) -- struktur saja, TANPA payment gateway ---
      subsManagerBody.appendChild(MugenUI.el("h3", { style: "margin-top:20px;" }, "Pembayaran (Virtual Account)"));
      const paymentListBody = MugenUI.el("div");
      subsManagerBody.appendChild(paymentListBody);

      async function loadPayments() {
        paymentListBody.innerHTML = "";
        paymentListBody.appendChild(MugenUI.skeleton("table", { cols: 5, rows: 3 }));
        try {
          const payments = await MugenApi.get(`/api/superadmin/subscriptions/${tenant.id}/payments`);
          paymentListBody.innerHTML = "";
          paymentListBody.appendChild(MugenUI.buildTable(
            [
              { key: "provider", label: "Provider" },
              { key: "virtual_account_number", label: "No. VA" },
              { key: "amount", label: "Jumlah", format: (v) => MugenUI.formatRupiah(v) },
              { key: "payment_status", label: "Status", format: (v) => LABEL_PAYMENT_STATUS[v] || v },
              { key: "paid_at", label: "Dibayar", format: formatWaktu },
              {
                key: "aksi", label: "Aksi", format: (_, p) => {
                  if (p.payment_status !== "pending") return "";
                  const btn = MugenUI.el("button", {}, "Tandai Lunas");
                  btn.addEventListener("click", async () => {
                    if (!confirm("Tandai pembayaran ini sebagai Lunas?")) return;
                    try {
                      await MugenUI.withButtonLoading(btn, () => MugenApi.put(`/api/superadmin/subscriptions/payments/${p.id}/status`,
                        { payment_status: "paid" }));
                      MugenUI.toast("Pembayaran ditandai Lunas.", "success");
                      loadAuditLog(); loadPayments();
                    } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                  });
                  return btn;
                },
              },
            ],
            payments,
            { emptyText: "Belum ada catatan pembayaran." },
          ));
        } catch (e) {
          paymentListBody.innerHTML = "";
          paymentListBody.appendChild(MugenUI.errorState(e.message));
        }
      }

      const inputProvider = MugenUI.el("input", { type: "text", placeholder: "Provider (mis. BCA, Mandiri)" });
      const inputVaNumber = MugenUI.el("input", { type: "text", placeholder: "Nomor Virtual Account" });
      const inputAmount = MugenUI.el("input", { type: "number", min: "1", placeholder: "Jumlah (Rp)" });
      const btnCatatPembayaran = MugenUI.el("button", {}, "Catat Pembayaran Baru");
      const errPembayaran = MugenUI.el("div", { class: "login-error" });
      subsManagerBody.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:8px;align-items:flex-end;margin-top:12px;" }, [
        inputProvider, inputVaNumber, inputAmount, btnCatatPembayaran,
      ]));
      subsManagerBody.appendChild(errPembayaran);

      btnCatatPembayaran.addEventListener("click", async () => {
        errPembayaran.textContent = "";
        try {
          await MugenUI.withButtonLoading(btnCatatPembayaran, () => MugenApi.post(`/api/superadmin/subscriptions/${tenant.id}/payments`, {
            provider: inputProvider.value.trim(),
            virtual_account_number: inputVaNumber.value.trim(),
            amount: parseInt(inputAmount.value, 10) || 0,
          }));
          MugenUI.toast("Pembayaran dicatat.", "success");
          inputProvider.value = ""; inputVaNumber.value = ""; inputAmount.value = "";
          loadAuditLog(); loadPayments();
        } catch (e) { errPembayaran.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
      });

      await loadPayments();
    }

    // ---------------------------------------------------------------
    // 5. PAKET BILLING (FONDASI Multi-Tenant Phase 4) -- konfigurasi
    // nama/harga/durasi/status/urutan/deskripsi/limit pemakaian + fitur
    // checkbox untuk EMPAT kode paket yang SAMA dengan Kelola Subscription
    // Toko di atas (free/basic/pro/enterprise, lihat billing_db.py) --
    // BUKAN sistem paket baru.
    // ---------------------------------------------------------------
    billingPackagesCard.appendChild(MugenUI.el("h2", {}, "Paket Billing (Harga, Limit, Fitur)"));
    billingPackagesCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Atribut EMPAT paket subscription yang sama dipakai Kelola Subscription Toko di atas -- kosongkan limit untuk tidak dibatasi."));
    const billingPackagesListBody = MugenUI.el("div");
    const billingPackageEditBody = MugenUI.el("div", { style: "margin-top:16px;" },
      MugenUI.el("div", { class: "subtitle" }, "Klik \"Edit\" pada salah satu paket di atas untuk mengubah."));
    billingPackagesCard.appendChild(billingPackagesListBody);
    billingPackagesCard.appendChild(billingPackageEditBody);

    let _katalogFiturCache = [];

    async function loadBillingPackages() {
      billingPackagesListBody.innerHTML = "";
      billingPackagesListBody.appendChild(MugenUI.skeleton("table", { cols: 6, rows: 3 }));
      try {
        const paket = await MugenApi.get("/api/superadmin/billing/packages");
        billingPackagesListBody.innerHTML = "";
        billingPackagesListBody.appendChild(MugenUI.buildTable(
          [
            { key: "nama", label: "Nama" },
            { key: "kode", label: "Kode" },
            { key: "harga", label: "Harga", format: (v) => MugenUI.formatRupiah(v) },
            { key: "durasi_hari", label: "Durasi (hari)" },
            { key: "urutan", label: "Urutan" },
            { key: "aktif", label: "Status", format: (v) => MugenUI.el("span", { class: "badge" + (v ? " badge-success" : " badge-danger") }, v ? "Aktif" : "Nonaktif") },
            {
              key: "aksi", label: "Aksi", format: (_, p) => {
                const btn = MugenUI.el("button", {}, "Edit");
                btn.addEventListener("click", () => renderBillingPackageEdit(p));
                return btn;
              },
            },
          ],
          paket,
          { emptyText: "Belum ada paket." },
        ));
      } catch (e) {
        billingPackagesListBody.innerHTML = "";
        billingPackagesListBody.appendChild(MugenUI.errorState(e.message));
      }
    }

    async function renderBillingPackageEdit(paket) {
      billingPackageEditBody.innerHTML = "";
      billingPackageEditBody.appendChild(MugenUI.skeleton("card", { lines: 3 }));
      let fiturTertandai;
      try {
        [_katalogFiturCache, fiturTertandai] = await Promise.all([
          MugenApi.get("/api/superadmin/billing/features"),
          MugenApi.get(`/api/superadmin/billing/packages/${paket.id}/features`),
        ]);
      } catch (e) {
        billingPackageEditBody.innerHTML = "";
        billingPackageEditBody.appendChild(MugenUI.errorState(e.message));
        return;
      }
      const idFiturTertandai = new Set(fiturTertandai.map((f) => f.id));

      billingPackageEditBody.innerHTML = "";
      billingPackageEditBody.appendChild(MugenUI.el("h3", {}, `Edit Paket: ${paket.nama} (${paket.kode})`));

      const inputNama = MugenUI.el("input", { type: "text", value: paket.nama });
      const inputHarga = MugenUI.el("input", { type: "number", min: "0", value: String(paket.harga) });
      const inputDurasi = MugenUI.el("input", { type: "number", min: "1", value: String(paket.durasi_hari) });
      const inputUrutan = MugenUI.el("input", { type: "number", min: "0", value: String(paket.urutan) });
      const inputAktif = MugenUI.el("input", { type: "checkbox" });
      inputAktif.checked = !!paket.aktif;
      const inputDeskripsi = MugenUI.el("textarea", { rows: "2" }, paket.deskripsi || "");

      billingPackageEditBody.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;" }, [
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Nama"), inputNama]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Harga (Rp)"), inputHarga]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Durasi (hari)"), inputDurasi]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Urutan"), inputUrutan]),
      ]));
      billingPackageEditBody.appendChild(MugenUI.el("label", { style: "margin-top:10px;display:flex;align-items:center;gap:6px;" }, [inputAktif, "Aktif (tampil di katalog Owner)"]));
      billingPackageEditBody.appendChild(MugenUI.el("label", {}, "Deskripsi"));
      billingPackageEditBody.appendChild(inputDeskripsi);

      // --- Limit pemakaian ---
      billingPackageEditBody.appendChild(MugenUI.el("h3", { style: "margin-top:16px;" }, "Limit Pemakaian (kosongkan = tidak dibatasi)"));
      const LIMIT_FIELDS = [
        ["max_barber", "Maks. Barber"], ["max_user", "Maks. User"], ["max_layanan", "Maks. Layanan"],
        ["max_booking", "Maks. Booking/bulan"], ["max_cabang", "Maks. Cabang"],
      ];
      const inputLimit = {};
      const limitRow = MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;" });
      for (const [key, label] of LIMIT_FIELDS) {
        const input = MugenUI.el("input", { type: "number", min: "0", placeholder: "tidak dibatasi" });
        if (paket[key] !== null && paket[key] !== undefined) input.value = String(paket[key]);
        inputLimit[key] = input;
        limitRow.appendChild(MugenUI.el("div", {}, [MugenUI.el("label", {}, label), input]));
      }
      billingPackageEditBody.appendChild(limitRow);

      // --- Fitur checkbox ---
      billingPackageEditBody.appendChild(MugenUI.el("h3", { style: "margin-top:16px;" }, "Fitur Paket Ini"));
      const fiturWrap = MugenUI.el("div", { style: "display:flex;flex-wrap:wrap;gap:12px;margin-bottom:8px;" });
      const checkboxFitur = [];
      if (!_katalogFiturCache.length) {
        fiturWrap.appendChild(MugenUI.el("div", { class: "subtitle" }, "Belum ada fitur di katalog -- tambah dulu di bagian Katalog Fitur di bawah."));
      }
      for (const f of _katalogFiturCache) {
        const cb = MugenUI.el("input", { type: "checkbox" });
        cb.checked = idFiturTertandai.has(f.id);
        cb.dataset.featureId = String(f.id);
        checkboxFitur.push(cb);
        fiturWrap.appendChild(MugenUI.el("label", { style: "display:flex;align-items:center;gap:6px;" }, [cb, f.nama]));
      }
      billingPackageEditBody.appendChild(fiturWrap);

      const errEdit = MugenUI.el("div", { class: "login-error" });
      const btnSimpan = MugenUI.el("button", { class: "btn-primary" }, "Simpan Paket");
      billingPackageEditBody.appendChild(errEdit);
      billingPackageEditBody.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpan));

      btnSimpan.addEventListener("click", async () => {
        errEdit.textContent = "";
        const body = {
          nama: inputNama.value.trim(),
          harga: parseInt(inputHarga.value, 10) || 0,
          durasi_hari: parseInt(inputDurasi.value, 10) || 1,
          urutan: parseInt(inputUrutan.value, 10) || 0,
          aktif: inputAktif.checked,
          deskripsi: inputDeskripsi.value,
        };
        for (const [key] of LIMIT_FIELDS) {
          const v = inputLimit[key].value;
          body[key] = v === "" ? null : parseInt(v, 10);
        }
        const featureIds = checkboxFitur.filter((cb) => cb.checked).map((cb) => parseInt(cb.dataset.featureId, 10));
        try {
          await MugenUI.withButtonLoading(btnSimpan, async () => {
            await MugenApi.put(`/api/superadmin/billing/packages/${paket.id}`, body);
            await MugenApi.put(`/api/superadmin/billing/packages/${paket.id}/features`, { feature_ids: featureIds });
          });
          MugenUI.toast("Paket billing disimpan.", "success");
          loadAuditLog();
          await loadBillingPackages();
          billingPackageEditBody.innerHTML = "";
          billingPackageEditBody.appendChild(MugenUI.el("div", { class: "subtitle" }, "Klik \"Edit\" pada salah satu paket di atas untuk mengubah."));
        } catch (e) {
          errEdit.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        }
      });
    }

    // ---------------------------------------------------------------
    // 6. KATALOG FITUR (FONDASI Multi-Tenant Phase 4) -- murni katalog/
    // toggle, TIDAK menggerbang fungsi kode apa pun (lihat billing_db.py).
    // ---------------------------------------------------------------
    billingFeaturesCard.appendChild(MugenUI.el("h2", {}, "Katalog Fitur"));
    billingFeaturesCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Tambah/ubah/nonaktifkan/hapus fitur bebas -- centang penugasannya ke paket lewat \"Edit\" paket di atas."));
    const billingFeaturesListBody = MugenUI.el("div");
    billingFeaturesCard.appendChild(billingFeaturesListBody);

    async function loadBillingFeatures() {
      billingFeaturesListBody.innerHTML = "";
      billingFeaturesListBody.appendChild(MugenUI.skeleton("table", { cols: 4, rows: 3 }));
      try {
        const fitur = await MugenApi.get("/api/superadmin/billing/features");
        billingFeaturesListBody.innerHTML = "";
        billingFeaturesListBody.appendChild(MugenUI.buildTable(
          [
            { key: "nama", label: "Nama" },
            { key: "kode", label: "Kode" },
            { key: "deskripsi", label: "Deskripsi", format: (v) => v || "-" },
            { key: "aktif", label: "Status", format: (v) => MugenUI.el("span", { class: "badge" + (v ? " badge-success" : " badge-danger") }, v ? "Aktif" : "Nonaktif") },
            {
              key: "aksi", label: "Aksi", format: (_, f) => {
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnToggle = MugenUI.el("button", {}, f.aktif ? "Nonaktifkan" : "Aktifkan");
                btnToggle.addEventListener("click", async () => {
                  try {
                    await MugenUI.withButtonLoading(btnToggle, () => MugenApi.put(`/api/superadmin/billing/features/${f.id}`,
                      { aktif: !f.aktif }));
                    MugenUI.toast("Fitur diperbarui.", "success");
                    loadAuditLog(); loadBillingFeatures();
                  } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                });
                wrap.appendChild(btnToggle);
                const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btnHapus.addEventListener("click", async () => {
                  if (!confirm(`Hapus fitur "${f.nama}" dari katalog? Fitur ini otomatis lepas dari SEMUA paket yang sudah mencentangnya.`)) return;
                  try {
                    await MugenUI.withButtonLoading(btnHapus, () => MugenApi.del(`/api/superadmin/billing/features/${f.id}`));
                    MugenUI.toast("Fitur dihapus.", "success");
                    loadAuditLog(); loadBillingFeatures();
                  } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                });
                wrap.appendChild(btnHapus);
                return wrap;
              },
            },
          ],
          fitur,
          { emptyText: "Belum ada fitur di katalog." },
        ));
      } catch (e) {
        billingFeaturesListBody.innerHTML = "";
        billingFeaturesListBody.appendChild(MugenUI.errorState(e.message));
      }
    }

    const inputFiturKode = MugenUI.el("input", { type: "text", placeholder: "kode_fitur (mis. whatsapp_reminder)" });
    const inputFiturNama = MugenUI.el("input", { type: "text", placeholder: "Nama Fitur (mis. WhatsApp Reminder)" });
    const inputFiturDeskripsi = MugenUI.el("input", { type: "text", placeholder: "Deskripsi (opsional)" });
    const btnTambahFitur = MugenUI.el("button", { class: "btn-primary" }, "Tambah Fitur");
    const errFitur = MugenUI.el("div", { class: "login-error" });
    billingFeaturesCard.appendChild(MugenUI.el("h3", { style: "margin-top:16px;" }, "Tambah Fitur Baru"));
    billingFeaturesCard.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:8px;align-items:flex-end;" }, [
      inputFiturKode, inputFiturNama, inputFiturDeskripsi, btnTambahFitur,
    ]));
    billingFeaturesCard.appendChild(errFitur);

    btnTambahFitur.addEventListener("click", async () => {
      errFitur.textContent = "";
      try {
        await MugenUI.withButtonLoading(btnTambahFitur, () => MugenApi.post("/api/superadmin/billing/features", {
          kode: inputFiturKode.value.trim(), nama: inputFiturNama.value.trim(), deskripsi: inputFiturDeskripsi.value.trim(),
        }));
        MugenUI.toast("Fitur ditambahkan.", "success");
        inputFiturKode.value = ""; inputFiturNama.value = ""; inputFiturDeskripsi.value = "";
        loadAuditLog(); loadBillingFeatures();
      } catch (e) {
        errFitur.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });

    // ---------------------------------------------------------------
    // 7. MONITORING PEMBAYARAN SEMUA TOKO (FONDASI Multi-Tenant Phase 4)
    // ---------------------------------------------------------------
    billingInvoicesCard.appendChild(MugenUI.el("h2", {}, "Monitoring Pembayaran (Semua Toko)"));
    const billingInvoicesBody = MugenUI.el("div");
    billingInvoicesCard.appendChild(billingInvoicesBody);

    async function loadBillingInvoices() {
      billingInvoicesBody.innerHTML = "";
      billingInvoicesBody.appendChild(MugenUI.skeleton("table", { cols: 7, rows: 4 }));
      try {
        const invoices = await MugenApi.get("/api/superadmin/billing/invoices");
        billingInvoicesBody.innerHTML = "";
        billingInvoicesBody.appendChild(MugenUI.buildTable(
          [
            { key: "nomor_invoice", label: "No. Invoice" },
            { key: "nama_barbershop", label: "Toko", format: (v, i) => v || i.tenant_slug || "-" },
            { key: "package_nama", label: "Paket" },
            { key: "jumlah", label: "Jumlah", format: (v) => MugenUI.formatRupiah(v) },
            { key: "metode_pembayaran", label: "Metode", format: (v) => v || "-" },
            { key: "status", label: "Status", format: (v) => MugenUI.el("span", { class: "badge " + (BADGE_STATUS_INVOICE[v] || "") }, LABEL_STATUS_INVOICE[v] || v) },
            { key: "created_at", label: "Tanggal", format: formatWaktu },
          ],
          invoices,
          { emptyText: "Belum ada invoice." },
        ));
      } catch (e) {
        billingInvoicesBody.innerHTML = "";
        billingInvoicesBody.appendChild(MugenUI.errorState(e.message));
      }
    }

    // ---------------------------------------------------------------
    // 8. LANDING PAGE -- FAQ (FONDASI Multi-Tenant Phase 5)
    // ---------------------------------------------------------------
    landingFaqCard.appendChild(MugenUI.el("h2", {}, "Landing Page -- FAQ"));
    landingFaqCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Tambah/ubah/nonaktifkan/hapus FAQ yang tampil di halaman publik -- hanya yang Aktif yang tampil."));
    const landingFaqListBody = MugenUI.el("div");
    landingFaqCard.appendChild(landingFaqListBody);

    async function loadLandingFaq() {
      landingFaqListBody.innerHTML = "";
      landingFaqListBody.appendChild(MugenUI.skeleton("table", { cols: 3, rows: 3 }));
      try {
        const list = await MugenApi.get("/api/superadmin/landing/faq");
        landingFaqListBody.innerHTML = "";
        landingFaqListBody.appendChild(MugenUI.buildTable(
          [
            { key: "pertanyaan", label: "Pertanyaan" },
            { key: "jawaban", label: "Jawaban" },
            { key: "aktif", label: "Status", format: (v) => MugenUI.el("span", { class: "badge" + (v ? " badge-success" : " badge-danger") }, v ? "Aktif" : "Nonaktif") },
            {
              key: "aksi", label: "Aksi", format: (_, f) => {
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnToggle = MugenUI.el("button", {}, f.aktif ? "Nonaktifkan" : "Aktifkan");
                btnToggle.addEventListener("click", async () => {
                  try {
                    await MugenUI.withButtonLoading(btnToggle, () => MugenApi.put(`/api/superadmin/landing/faq/${f.id}`, { aktif: !f.aktif }));
                    MugenUI.toast("FAQ diperbarui.", "success");
                    loadLandingFaq();
                  } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                });
                wrap.appendChild(btnToggle);
                const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btnHapus.addEventListener("click", async () => {
                  if (!confirm("Hapus FAQ ini?")) return;
                  try {
                    await MugenUI.withButtonLoading(btnHapus, () => MugenApi.del(`/api/superadmin/landing/faq/${f.id}`));
                    MugenUI.toast("FAQ dihapus.", "success");
                    loadLandingFaq();
                  } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                });
                wrap.appendChild(btnHapus);
                return wrap;
              },
            },
          ],
          list,
          { emptyText: "Belum ada FAQ." },
        ));
      } catch (e) {
        landingFaqListBody.innerHTML = "";
        landingFaqListBody.appendChild(MugenUI.errorState(e.message));
      }
    }

    const inputFaqPertanyaan = MugenUI.el("input", { type: "text", placeholder: "Pertanyaan" });
    const inputFaqJawaban = MugenUI.el("input", { type: "text", placeholder: "Jawaban" });
    const btnTambahFaq = MugenUI.el("button", { class: "btn-primary" }, "Tambah FAQ");
    const errFaq = MugenUI.el("div", { class: "login-error" });
    landingFaqCard.appendChild(MugenUI.el("h3", { style: "margin-top:16px;" }, "Tambah FAQ Baru"));
    landingFaqCard.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:8px;align-items:flex-end;" }, [
      inputFaqPertanyaan, inputFaqJawaban, btnTambahFaq,
    ]));
    landingFaqCard.appendChild(errFaq);

    btnTambahFaq.addEventListener("click", async () => {
      errFaq.textContent = "";
      try {
        await MugenUI.withButtonLoading(btnTambahFaq, () => MugenApi.post("/api/superadmin/landing/faq", {
          pertanyaan: inputFaqPertanyaan.value.trim(), jawaban: inputFaqJawaban.value.trim(),
        }));
        MugenUI.toast("FAQ ditambahkan.", "success");
        inputFaqPertanyaan.value = ""; inputFaqJawaban.value = "";
        loadLandingFaq();
      } catch (e) {
        errFaq.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });

    // ---------------------------------------------------------------
    // 9. LANDING PAGE -- TESTIMONIAL
    // ---------------------------------------------------------------
    landingTestimonialsCard.appendChild(MugenUI.el("h2", {}, "Landing Page -- Testimonial"));
    const landingTestimonialsListBody = MugenUI.el("div");
    landingTestimonialsCard.appendChild(landingTestimonialsListBody);

    async function loadLandingTestimonials() {
      landingTestimonialsListBody.innerHTML = "";
      landingTestimonialsListBody.appendChild(MugenUI.skeleton("table", { cols: 5, rows: 3 }));
      try {
        const list = await MugenApi.get("/api/superadmin/landing/testimonials");
        landingTestimonialsListBody.innerHTML = "";
        landingTestimonialsListBody.appendChild(MugenUI.buildTable(
          [
            { key: "nama", label: "Nama" },
            { key: "jabatan_toko", label: "Toko/Jabatan", format: (v) => v || "-" },
            { key: "isi", label: "Isi" },
            { key: "rating", label: "Rating" },
            { key: "aktif", label: "Status", format: (v) => MugenUI.el("span", { class: "badge" + (v ? " badge-success" : " badge-danger") }, v ? "Aktif" : "Nonaktif") },
            {
              key: "aksi", label: "Aksi", format: (_, t) => {
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnToggle = MugenUI.el("button", {}, t.aktif ? "Nonaktifkan" : "Aktifkan");
                btnToggle.addEventListener("click", async () => {
                  try {
                    await MugenUI.withButtonLoading(btnToggle, () => MugenApi.put(`/api/superadmin/landing/testimonials/${t.id}`, { aktif: !t.aktif }));
                    MugenUI.toast("Testimonial diperbarui.", "success");
                    loadLandingTestimonials();
                  } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                });
                wrap.appendChild(btnToggle);
                const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btnHapus.addEventListener("click", async () => {
                  if (!confirm(`Hapus testimonial dari "${t.nama}"?`)) return;
                  try {
                    await MugenUI.withButtonLoading(btnHapus, () => MugenApi.del(`/api/superadmin/landing/testimonials/${t.id}`));
                    MugenUI.toast("Testimonial dihapus.", "success");
                    loadLandingTestimonials();
                  } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                });
                wrap.appendChild(btnHapus);
                return wrap;
              },
            },
          ],
          list,
          { emptyText: "Belum ada testimonial." },
        ));
      } catch (e) {
        landingTestimonialsListBody.innerHTML = "";
        landingTestimonialsListBody.appendChild(MugenUI.errorState(e.message));
      }
    }

    const inputTestiNama = MugenUI.el("input", { type: "text", placeholder: "Nama" });
    const inputTestiJabatan = MugenUI.el("input", { type: "text", placeholder: "Toko/Jabatan (opsional)" });
    const inputTestiIsi = MugenUI.el("input", { type: "text", placeholder: "Isi testimonial" });
    const inputTestiRating = MugenUI.el("input", { type: "number", min: "1", max: "5", value: "5", style: "width:70px;" });
    const btnTambahTesti = MugenUI.el("button", { class: "btn-primary" }, "Tambah Testimonial");
    const errTesti = MugenUI.el("div", { class: "login-error" });
    landingTestimonialsCard.appendChild(MugenUI.el("h3", { style: "margin-top:16px;" }, "Tambah Testimonial Baru"));
    landingTestimonialsCard.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:8px;align-items:flex-end;" }, [
      inputTestiNama, inputTestiJabatan, inputTestiIsi, inputTestiRating, btnTambahTesti,
    ]));
    landingTestimonialsCard.appendChild(errTesti);

    btnTambahTesti.addEventListener("click", async () => {
      errTesti.textContent = "";
      try {
        await MugenUI.withButtonLoading(btnTambahTesti, () => MugenApi.post("/api/superadmin/landing/testimonials", {
          nama: inputTestiNama.value.trim(), jabatan_toko: inputTestiJabatan.value.trim(),
          isi: inputTestiIsi.value.trim(), rating: Number(inputTestiRating.value) || 5,
        }));
        MugenUI.toast("Testimonial ditambahkan.", "success");
        inputTestiNama.value = ""; inputTestiJabatan.value = ""; inputTestiIsi.value = ""; inputTestiRating.value = "5";
        loadLandingTestimonials();
      } catch (e) {
        errTesti.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });

    // ---------------------------------------------------------------
    // 10. LANDING PAGE -- KONTAK & STATISTIK
    // ---------------------------------------------------------------
    landingContactCard.appendChild(MugenUI.el("h2", {}, "Landing Page -- Kontak & Statistik"));
    landingContactCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Active Tenants & Total Bookings dihitung otomatis dari data asli (tidak bisa diedit di sini)."));

    const inputContactWhatsapp = MugenUI.el("input", { type: "text", placeholder: "WhatsApp" });
    const inputContactEmail = MugenUI.el("input", { type: "text", placeholder: "Email" });
    const inputContactAlamat = MugenUI.el("input", { type: "text", placeholder: "Alamat" });
    const inputContactMaps = MugenUI.el("input", { type: "text", placeholder: "Link Google Maps (opsional)" });
    const inputStatHappy = MugenUI.el("input", { type: "text", placeholder: "Happy Customers (mis. 500+)" });
    const inputStatUptime = MugenUI.el("input", { type: "text", placeholder: "Uptime (mis. 99.9%)" });
    const btnSimpanContact = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
    const errContact = MugenUI.el("div", { class: "login-error" });

    landingContactCard.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:8px;" }, [
      inputContactWhatsapp, inputContactEmail, inputContactAlamat, inputContactMaps,
    ]));
    landingContactCard.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:8px;margin-top:8px;" }, [
      inputStatHappy, inputStatUptime, btnSimpanContact,
    ]));
    landingContactCard.appendChild(errContact);

    async function loadLandingContact() {
      try {
        const [contact, stats] = await Promise.all([
          MugenApi.get("/api/superadmin/landing/contact"),
          MugenApi.get("/api/superadmin/landing/stats"),
        ]);
        inputContactWhatsapp.value = contact.platform_contact_whatsapp || "";
        inputContactEmail.value = contact.platform_contact_email || "";
        inputContactAlamat.value = contact.platform_contact_alamat || "";
        inputContactMaps.value = contact.platform_contact_maps_url || "";
        inputStatHappy.value = stats.platform_stat_happy_customers || "";
        inputStatUptime.value = stats.platform_stat_uptime || "";
      } catch (e) {
        errContact.textContent = e.message;
      }
    }

    btnSimpanContact.addEventListener("click", async () => {
      errContact.textContent = "";
      try {
        await MugenUI.withButtonLoading(btnSimpanContact, () => Promise.all([
          MugenApi.put("/api/superadmin/landing/contact", {
            platform_contact_whatsapp: inputContactWhatsapp.value.trim(),
            platform_contact_email: inputContactEmail.value.trim(),
            platform_contact_alamat: inputContactAlamat.value.trim(),
            platform_contact_maps_url: inputContactMaps.value.trim(),
          }),
          MugenApi.put("/api/superadmin/landing/stats", {
            platform_stat_happy_customers: inputStatHappy.value.trim(),
            platform_stat_uptime: inputStatUptime.value.trim(),
          }),
        ]));
        MugenUI.toast("Kontak & statistik disimpan.", "success");
      } catch (e) {
        errContact.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });

    // ---------------------------------------------------------------
    // 11. RIWAYAT AKSI (Audit Log)
    // ---------------------------------------------------------------
    auditCard.appendChild(MugenUI.el("h2", {}, "Riwayat Aksi"));
    const auditBody = MugenUI.el("div");
    auditCard.appendChild(auditBody);

    async function loadAuditLog() {
      auditBody.innerHTML = "";
      auditBody.appendChild(MugenUI.skeleton("table", { cols: 5, rows: 4 }));
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
        auditBody.appendChild(MugenUI.errorState(e.message));
      }
    }

    await loadTenantList();
    await loadSubsConfig();
    await loadBillingPackages();
    await loadBillingFeatures();
    await loadBillingInvoices();
    await loadLandingFaq();
    await loadLandingTestimonials();
    await loadLandingContact();
    await loadAuditLog();
  }

  return { render };
})();
