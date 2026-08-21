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
    hapus_tenant: "Hapus Toko",
    ubah_slug_tenant: "Ubah Slug Toko",
    // FONDASI Multi-Tenant Phase 3 (Subscription & Tenant Lifecycle).
    ubah_package_subscription: "Ubah Package Subscription",
    ubah_status_subscription: "Ubah Status Subscription",
    ubah_trial_subscription: "Ubah Trial Subscription",
    ubah_grace_subscription: "Ubah Grace Period Subscription",
    ubah_config_subscription: "Ubah Konfigurasi Subscription",
    buat_pembayaran_subscription: "Catat Pembayaran Subscription",
    ubah_status_pembayaran_subscription: "Ubah Status Pembayaran Subscription",
    // FONDASI Multi-Tenant Phase 4 (Billing & Payment Gateway).
    ubah_paket_billing: "Ubah Paket Billing",
    ubah_fitur_billing: "Ubah Fitur Billing",
    hapus_fitur_billing: "Hapus Fitur Billing",
    ubah_fitur_paket_billing: "Ubah Fitur Paket Billing",
    // Payment Gateway (booking publik, platform-wide).
    ubah_config_payment_gateway: "Ubah Konfigurasi Payment Gateway",
    // Payment Gateway Billing SaaS (platform-wide, TERPISAH dari Payment
    // Gateway booking di atas -- lihat catatan arsitektur di gateway_client_base.py).
    ubah_config_billing_gateway: "Ubah Konfigurasi Payment Gateway Billing SaaS",
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
    root.appendChild(MugenUI.el("h1", {}, "Super Admin"));

    let tenantList = [];

    // REVISI Restrukturisasi Super Admin: SEBELUMNYA seluruh kartu di bawah
    // ditumpuk lurus dalam satu halaman panjang (sulit dikelola) -- sekarang
    // dipisah 5 tab (Dashboard/Tenant/Paket/Landing Page/Payment Gateway)
    // pakai MugenUI.tabs() (pola sama seperti pages/pengaturan.js). BEDA
    // dari pengaturan.js: di sini SELURUH kartu tetap dibangun & dimuat
    // SEKALI di akhir render() ini seperti sebelumnya (bukan lazy per-tab)
    // -- tab HANYA mengatur kartu mana yang terlihat (toggle display),
    // supaya urutan/logika loadXxx() yang sudah ada di bawah TIDAK perlu
    // disusun ulang sama sekali, murni pengelompokan tampilan.
    const dashboardSummaryCard = MugenUI.el("div", { class: "card" });
    const formCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    const subsConfigCard = MugenUI.el("div", { class: "card" });
    const subsManagerCard = MugenUI.el("div", { class: "card" });
    // FONDASI Multi-Tenant Phase 4: tiga kartu baru, TIDAK mengubah kartu
    // Phase 3 di atas sama sekali -- lihat billing_db.py/routers/billing.py.
    const billingPackagesCard = MugenUI.el("div", { class: "card" });
    const billingFeaturesCard = MugenUI.el("div", { class: "card" });
    const billingInvoicesCard = MugenUI.el("div", { class: "card" });
    // Payment Gateway Billing SaaS (platform-wide) -- TERPISAH TOTAL dari
    // kartu "Payment Gateway" (booking customer) di bawah: kredensial di
    // sini untuk Owner tenant membayar LANGGANAN platform, BUKAN untuk
    // customer membayar booking -- lihat billing_gateway_db.py.
    const billingGatewayCard = MugenUI.el("div", { class: "card" });
    // FONDASI Multi-Tenant Phase 5 (Landing Page SaaS) -- REVISI
    // Restrukturisasi Super Admin & Landing Page: fitur Testimonial DIHAPUS
    // TOTAL (lihat riwayat commit), landingFooterCard BARU (tagline footer).
    const landingFaqCard = MugenUI.el("div", { class: "card" });
    const landingContactCard = MugenUI.el("div", { class: "card" });
    const landingFooterCard = MugenUI.el("div", { class: "card" });
    // Payment Gateway (booking publik, platform-wide) -- TIDAK mengubah
    // kartu Billing SaaS (subsConfigCard/billing*Card) di atas sama sekali,
    // integrasi terpisah total (lihat payment_gateway_db.py).
    const paymentGatewayCard = MugenUI.el("div", { class: "card" });
    // Migrasi Faspay SNAP Advance: provider BARU, TERPISAH TOTAL dari kartu
    // "Payment Gateway" (Xpress v4) di atas -- lihat snap_advance_db.py.
    // Xpress v4 TETAP berjalan penuh selama masa transisi (kartu di atas
    // TIDAK disentuh), kartu ini murni TAMBAHAN untuk mengisi kredensial
    // SNAP Advance begitu tersedia dari Faspay.
    const snapAdvanceCard = MugenUI.el("div", { class: "card" });
    const auditCard = MugenUI.el("div", { class: "card" });
    // Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant: tab
    // baru "Riwayat Transaksi" -- pusat monitoring SELURUH transaksi
    // platform (booking customer + langganan SaaS), murni MEMBACA lewat
    // transaction_report_db.py (lihat modul itu), TIDAK menambah business
    // logic baru sama sekali.
    const transaksiSummaryCard = MugenUI.el("div", { class: "card" });
    const transaksiCard = MugenUI.el("div", { class: "card" });

    const tabDashboard = MugenUI.el("div");
    const tabTenant = MugenUI.el("div", { style: "display:none;" });
    const tabPaket = MugenUI.el("div", { style: "display:none;" });
    const tabLanding = MugenUI.el("div", { style: "display:none;" });
    const tabPgw = MugenUI.el("div", { style: "display:none;" });
    const tabTransaksi = MugenUI.el("div", { style: "display:none;" });
    const panelByKey = { dashboard: tabDashboard, tenant: tabTenant, paket: tabPaket, landing: tabLanding, pgw: tabPgw, transaksi: tabTransaksi };
    const tabsCtl = MugenUI.tabs(
      [
        { key: "dashboard", label: "Dashboard" },
        { key: "tenant", label: "Tenant" },
        { key: "paket", label: "Paket" },
        { key: "landing", label: "Landing Page" },
        { key: "pgw", label: "Payment Gateway" },
        { key: "transaksi", label: "Riwayat Transaksi" },
      ],
      { onChange: (key) => { for (const k in panelByKey) panelByKey[k].style.display = k === key ? "" : "none"; } },
    );
    root.appendChild(tabsCtl.bar);
    root.appendChild(tabDashboard);
    root.appendChild(tabTenant);
    root.appendChild(tabPaket);
    root.appendChild(tabLanding);
    root.appendChild(tabPgw);
    root.appendChild(tabTransaksi);
    requestAnimationFrame(tabsCtl.moveIndicator);

    tabDashboard.appendChild(dashboardSummaryCard);
    tabDashboard.appendChild(auditCard);
    tabTenant.appendChild(listCard);
    tabTenant.appendChild(formCard);
    tabTenant.appendChild(subsConfigCard);
    tabTenant.appendChild(subsManagerCard);
    tabPaket.appendChild(billingPackagesCard);
    tabPaket.appendChild(billingFeaturesCard);
    tabPaket.appendChild(billingInvoicesCard);
    tabLanding.appendChild(landingFaqCard);
    tabLanding.appendChild(landingContactCard);
    tabLanding.appendChild(landingFooterCard);
    tabPgw.appendChild(billingGatewayCard);
    tabPgw.appendChild(paymentGatewayCard);
    tabPgw.appendChild(snapAdvanceCard);
    tabTransaksi.appendChild(transaksiSummaryCard);
    tabTransaksi.appendChild(transaksiCard);

    // ---------------------------------------------------------------
    // 0. DASHBOARD -- Ringkasan Sistem (murni dihitung dari data yang SUDAH
    // dimuat tab Tenant di bawah/loadTenantList() -- TIDAK ada endpoint
    // baru sama sekali, lihat catatan restrukturisasi di atas).
    // ---------------------------------------------------------------
    dashboardSummaryCard.appendChild(MugenUI.el("h2", {}, "Ringkasan Sistem"));
    const dashboardSummaryBody = MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-top:12px;" });
    dashboardSummaryCard.appendChild(dashboardSummaryBody);

    function statTile(label, value) {
      return MugenUI.el("div", { class: "card", style: "flex:1;min-width:160px;text-align:center;padding:16px;" }, [
        MugenUI.el("div", { style: "font-size:1.6rem;font-weight:700;" }, String(value)),
        MugenUI.el("div", { class: "subtitle" }, label),
      ]);
    }

    function renderDashboardSummary() {
      dashboardSummaryBody.innerHTML = "";
      const totalToko = tenantList.length;
      const tokoAktif = tenantList.filter((t) => t.status === "aktif").length;
      const totalOwner = tenantList.reduce((n, t) => n + (t.jumlah_owner || 0), 0);
      const totalUser = tenantList.reduce((n, t) => n + (t.jumlah_user || 0), 0);
      dashboardSummaryBody.appendChild(statTile("Total Toko", totalToko));
      dashboardSummaryBody.appendChild(statTile("Toko Aktif", tokoAktif));
      dashboardSummaryBody.appendChild(statTile("Total Owner", totalOwner));
      dashboardSummaryBody.appendChild(statTile("Total User", totalUser));
    }

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
        renderDashboardSummary();
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.buildTable(
          [
            { key: "nama_barbershop", label: "Nama Barbershop" },
            { key: "slug", label: "Slug" },
            // FITUR Username Tenant di Super Admin: owner_username dikirim
            // backend (routers/superadmin.py::_tenant_dengan_ringkasan())
            // -- username akun Owner aktif toko itu, dipakai tenant untuk
            // login (lihat FITUR Username Registrasi Mandiri di register.js/
            // tenant_registration.py). "-" kalau toko belum punya Owner
            // aktif (mis. baru dibuat lalu akunnya dinonaktifkan).
            {
              key: "owner_username", label: "Username",
              format: (v) => v || MugenUI.el("span", { class: "subtitle" }, "-"),
            },
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
            // FITUR URL Booking Publik per Tenant (item 8 spesifikasi):
            // booking_url dikirim backend (routers/superadmin.py::
            // _tenant_dengan_ringkasan(), lewat tenant_db.get_booking_url()
            // -- subdomain dari booking_slug TERKINI + path "/app/#/book")
            // -- pola KOLOM SAMA PERSIS dengan Alamat Website di atas
            // (link + tombol Salin + tombol Buka Booking), TERPISAH karena
            // booking_slug bisa berbeda dari slug/custom_domain tenant.
            {
              key: "booking_url", label: "Booking URL",
              format: (v) => {
                if (!v) return MugenUI.el("span", { class: "subtitle" }, "Belum dibuat");
                const link = MugenUI.el("a", { href: v, target: "_blank", rel: "noopener noreferrer" }, v);
                const btnSalin = MugenUI.el("button", { type: "button", title: "Salin URL" }, "📋 Salin");
                btnSalin.addEventListener("click", async () => {
                  try {
                    await navigator.clipboard.writeText(v);
                    MugenUI.toast("Booking URL disalin.", "success");
                  } catch (e) {
                    MugenUI.toast("Gagal menyalin otomatis -- salin manual dari link di atas.", "error");
                  }
                });
                const btnBuka = MugenUI.el(
                  "a",
                  { href: v, target: "_blank", rel: "noopener noreferrer", class: "btn-primary", title: "Buka Booking" },
                  "↗ Buka Booking",
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
                // FITUR Migrasi Subdomain: ganti slug (subdomain dashboard/
                // login/booking utama, {slug}.rivoirsett.com) tenant yang
                // sudah ada -- backend (tenant_db.set_slug()) memvalidasi
                // format+keunikan, SENGAJA tidak memblokir tenant utama
                // (justru dipakai untuk migrasi "mugen-hair-co" -> "mugen").
                // Perubahan subdomain langsung berdampak (URL lama berhenti
                // berfungsi), jadi tetap minta konfirmasi jelas.
                const btnUbahSlug = MugenUI.el("button", {}, "Ubah Slug");
                btnUbahSlug.addEventListener("click", async () => {
                  const slugBaru = prompt(
                    `Ganti subdomain toko "${t.nama_barbershop}" -- URL lama (${t.slug}.rivoirsett.com) akan BERHENTI berfungsi begitu disimpan. Masukkan slug baru:`,
                    t.slug,
                  );
                  if (slugBaru === null) return;
                  if (!slugBaru.trim() || slugBaru.trim().toLowerCase() === t.slug.trim().toLowerCase()) return;
                  try {
                    await MugenUI.withButtonLoading(btnUbahSlug,
                      () => MugenApi.put(`/api/superadmin/tenants/${t.id}/slug`, { slug: slugBaru.trim() }));
                    MugenUI.toast("Slug toko diperbarui.", "success", { force: true });
                    loadTenantList();
                    loadAuditLog();
                  } catch (e) {
                    MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error", { force: true });
                  }
                });
                wrap.appendChild(btnUbahSlug);
                const btnKelolaSubs = MugenUI.el("button", {}, "Kelola Subscription");
                btnKelolaSubs.addEventListener("click", () => renderSubscriptionManager(t));
                wrap.appendChild(btnKelolaSubs);
                // FITUR Hapus Tenant: khusus tenant testing/development --
                // backend (tenant_db.hapus_tenant()) menolak keras tenant
                // "mugen-hair-co" & tenant terakhir yang tersisa, apa pun
                // yang terjadi di sisi tombol ini. Konfirmasi DUA LAPIS di
                // sisi UI (harus mengetik ULANG slug persis, bukan sekadar
                // klik "OK") supaya klik keliru pada aksi PERMANEN/tidak
                // bisa dibatalkan ini sangat kecil kemungkinannya.
                const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btnHapus.addEventListener("click", async () => {
                  const ketik = prompt(
                    `PERMANEN, TIDAK BISA DIBATALKAN. Ini akan menghapus toko "${t.nama_barbershop}" beserta SELURUH datanya (user, barber, booking, transaksi, dst).\n\nKetik ulang slug toko ini untuk konfirmasi: ${t.slug}`,
                  );
                  if (ketik === null) return;
                  if (ketik.trim().toLowerCase() !== t.slug.trim().toLowerCase()) {
                    MugenUI.toast("Slug tidak cocok -- penghapusan dibatalkan.", "error", { force: true });
                    return;
                  }
                  try {
                    await MugenUI.withButtonLoading(btnHapus,
                      () => MugenApi.del(`/api/superadmin/tenants/${t.id}`, { konfirmasi_slug: ketik.trim() }));
                    MugenUI.toast(`Toko "${t.nama_barbershop}" dihapus permanen.`, "success", { force: true });
                    loadTenantList();
                    loadAuditLog();
                  } catch (e) {
                    MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error", { force: true });
                  }
                });
                wrap.appendChild(btnHapus);
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
    // 6. KATALOG FITUR (FONDASI Multi-Tenant Phase 4) -- REVISI (audit
    // "fitur hardcode di Superadmin"): daftar SEKARANG TETAP (hanya kode
    // yang sungguhan menggerbang sesuatu, lihat billing_db.py), Super Admin
    // hanya bisa mencentang/hapus-centang penugasan ke paket + aktifkan/
    // nonaktifkan/hapus dari katalog -- TIDAK BISA lagi menambah fitur baru
    // sembarang nama (tombol "Tambah Fitur Baru" & endpoint POST /features
    // dihapus total).
    // ---------------------------------------------------------------
    billingFeaturesCard.appendChild(MugenUI.el("h2", {}, "Katalog Fitur"));
    billingFeaturesCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Fitur yang benar-benar punya fungsi nyata di aplikasi -- centang penugasannya ke paket lewat \"Edit\" paket di atas."));
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
    // 8. PAYMENT GATEWAY BILLING SAAS (platform-wide, provider-agnostic --
    // Owner tenant membayar LANGGANAN platform lewat menu Billing >
    // Perpanjang Paket, TERPISAH TOTAL dari kartu "Payment Gateway" booking
    // customer di bawah, lihat billing_gateway_db.py/routers/billing.py).
    // Kredensial di sini sebelumnya HANYA lewat environment variable
    // MIDTRANS_* -- sekarang tersimpan di database, berlaku langsung tanpa
    // deploy ulang. Field SENGAJA generik (BUKAN spesifik satu provider --
    // TIDAK ADA dropdown Provider) supaya form yang sama tetap terpakai
    // kalau kelak platform pindah provider PGW; TIDAK semua field wajib
    // diisi, tiap provider butuh kombinasi kredensial berbeda.
    // ---------------------------------------------------------------
    billingGatewayCard.appendChild(MugenUI.el("h2", {}, "Billing SaaS – Payment Gateway"));
    billingGatewayCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Kredensial Payment Gateway milik PLATFORM (Rivoir) -- dipakai SELURUH tenant saat Owner membayar/memperpanjang paket langganan lewat menu Billing. Terpisah total dari Payment Gateway booking customer di bawah. Isi hanya field yang dibutuhkan provider yang dipakai."));

    const inBillingEnv = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "sandbox" }, "Sandbox"),
      MugenUI.el("option", { value: "production" }, "Production"),
    ]);
    const inBillingApiKey = MugenUI.el("input", { type: "password", autocomplete: "off" });
    const inBillingServerKey = MugenUI.el("input", { type: "password", autocomplete: "off" });
    const inBillingClientKey = MugenUI.el("input", { type: "text", autocomplete: "off" });
    const inBillingMerchantId = MugenUI.el("input", { type: "text" });
    const inBillingSecretKey = MugenUI.el("input", { type: "password", autocomplete: "off" });
    const inBillingWebhookUrl = MugenUI.el("input", { type: "text", placeholder: "https://api.rivoirsett.com/api/..." });

    billingGatewayCard.appendChild(MugenUI.el("label", {}, "Environment"));
    billingGatewayCard.appendChild(inBillingEnv);
    billingGatewayCard.appendChild(MugenUI.el("label", {}, "API Key (tidak dipakai Faspay)"));
    billingGatewayCard.appendChild(inBillingApiKey);
    billingGatewayCard.appendChild(MugenUI.el("label", {}, "Server Key (Faspay: User ID)"));
    billingGatewayCard.appendChild(inBillingServerKey);
    billingGatewayCard.appendChild(MugenUI.el("label", {}, "Client Key (tidak dipakai Faspay)"));
    billingGatewayCard.appendChild(inBillingClientKey);
    billingGatewayCard.appendChild(MugenUI.el("label", {}, "Merchant ID (Faspay: Merchant ID)"));
    billingGatewayCard.appendChild(inBillingMerchantId);
    billingGatewayCard.appendChild(MugenUI.el("label", {}, "Secret Key (Faspay: Password)"));
    billingGatewayCard.appendChild(inBillingSecretKey);
    billingGatewayCard.appendChild(MugenUI.el("label", {}, "Webhook / Callback URL"));
    billingGatewayCard.appendChild(inBillingWebhookUrl);
    // URL webhook SUNGGUHAN endpoint ini (SENGAJA TIDAK diganti namanya --
    // lihat routers/billing_webhook.py -- risiko operasional memutus
    // webhook yang mungkin sudah terdaftar di dashboard provider produksi)
    // -- daftarkan URL ini PERSIS di dashboard provider, field di atas
    // murni catatan Super Admin sendiri.
    billingGatewayCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:4px;" },
      `URL webhook aktif: ${MUGEN_API_BASE}/api/public/billing/midtrans-webhook`));
    // Provider RESMI: Faspay Xpress v4 -- satu akun Faspay HANYA bisa
    // mendaftarkan SATU Payment Notification URL & SATU Return URL untuk
    // KEDUA modul (Billing SaaS ini & Payment Gateway booking di bawah),
    // lihat gateway_notification_dispatch.py -- URL di atas TETAP aktif
    // (dipanggil secara internal), tapi yang benar-benar didaftarkan ke
    // Faspay adalah dispatcher tunggal di bawah ini.
    billingGatewayCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:4px;" },
      `Faspay Xpress v4: URL Payment Notification & Return URL yang SUNGGUHAN didaftarkan ke Faspay untuk SATU akun ini (dipakai bersama Payment Gateway booking di bawah) -- Payment Notification: ${MUGEN_API_BASE}/api/public/gateway/faspay-notification, Return URL: ${MUGEN_API_BASE}/api/public/gateway/faspay-return`));

    const errorBillingGateway = MugenUI.el("div", { class: "login-error" });
    const btnSimpanBillingGateway = MugenUI.el("button", { class: "btn-primary" }, "Simpan Payment Gateway Billing SaaS");
    billingGatewayCard.appendChild(errorBillingGateway);
    billingGatewayCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanBillingGateway));

    async function loadBillingGatewayConfig() {
      try {
        const cfg = await MugenApi.get("/api/superadmin/billing/gateway-config");
        inBillingEnv.value = cfg.environment || "sandbox";
        inBillingApiKey.value = cfg.api_key || "";
        inBillingServerKey.value = cfg.server_key || "";
        inBillingClientKey.value = cfg.client_key || "";
        inBillingMerchantId.value = cfg.merchant_id || "";
        inBillingSecretKey.value = cfg.secret_key || "";
        inBillingWebhookUrl.value = cfg.webhook_url || "";
      } catch (e) { errorBillingGateway.textContent = e.message; }
    }
    btnSimpanBillingGateway.addEventListener("click", async () => {
      errorBillingGateway.textContent = "";
      try {
        await MugenUI.withButtonLoading(btnSimpanBillingGateway, () => MugenApi.put("/api/superadmin/billing/gateway-config", {
          environment: inBillingEnv.value, api_key: inBillingApiKey.value, server_key: inBillingServerKey.value,
          client_key: inBillingClientKey.value, merchant_id: inBillingMerchantId.value,
          secret_key: inBillingSecretKey.value, webhook_url: inBillingWebhookUrl.value,
        }));
        MugenUI.toast("Konfigurasi Payment Gateway Billing SaaS disimpan.", "success");
        loadAuditLog();
      } catch (e) {
        errorBillingGateway.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });

    // ---------------------------------------------------------------
    // 9. LANDING PAGE -- FAQ (FONDASI Multi-Tenant Phase 5)
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
    // 10. LANDING PAGE -- KONTAK
    // ---------------------------------------------------------------
    // REVISI Hubungi Kami Dinamis: HANYA Email & WhatsApp -- masing-masing
    // dirender publik sebagai link mailto:/wa.me (lihat landing.js), field
    // yang kosong tidak ditampilkan. Alamat/Maps/Social media (dulu ada di
    // sini tapi TIDAK PERNAH dipakai frontend) dihapus sebagai pembersihan
    // kode mati -- lihat landing_db.py::_CONTACT_KEYS.
    landingContactCard.appendChild(MugenUI.el("h2", {}, "Landing Page -- Kontak"));
    landingContactCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Email & WhatsApp yang tampil di section \"Hubungi Kami\" Landing Page -- masing-masing bisa langsung diklik (mailto:/WhatsApp). Kosongkan salah satu untuk menyembunyikannya dari halaman publik."));

    const inputContactEmail = MugenUI.el("input", { type: "text", placeholder: "Email (mis. cs@rivoirsett.com)" });
    const inputContactWhatsapp = MugenUI.el("input", { type: "text", placeholder: "WhatsApp (mis. 081234567890)" });
    const btnSimpanContact = MugenUI.el("button", { class: "btn-primary" }, "Simpan Kontak");
    const errContact = MugenUI.el("div", { class: "login-error" });

    landingContactCard.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:8px;align-items:flex-end;" }, [
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Email"), inputContactEmail]),
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "WhatsApp"), inputContactWhatsapp]),
      btnSimpanContact,
    ]));
    landingContactCard.appendChild(errContact);

    async function loadLandingContact() {
      try {
        const contact = await MugenApi.get("/api/superadmin/landing/contact");
        inputContactEmail.value = contact.platform_contact_email || "";
        inputContactWhatsapp.value = contact.platform_contact_whatsapp || "";
      } catch (e) {
        errContact.textContent = e.message;
      }
    }

    btnSimpanContact.addEventListener("click", async () => {
      errContact.textContent = "";
      try {
        await MugenUI.withButtonLoading(btnSimpanContact, () => MugenApi.put("/api/superadmin/landing/contact", {
          platform_contact_email: inputContactEmail.value.trim(),
          platform_contact_whatsapp: inputContactWhatsapp.value.trim(),
        }));
        MugenUI.toast("Kontak disimpan.", "success");
      } catch (e) {
        errContact.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });

    // ---------------------------------------------------------------
    // 11. LANDING PAGE -- FOOTER
    // ---------------------------------------------------------------
    // HANYA tagline singkat yang dinamis -- kolom link navigasi & teks
    // copyright footer TETAP hardcode di index.html (lihat landing_db.py::
    // _FOOTER_KEYS).
    landingFooterCard.appendChild(MugenUI.el("h2", {}, "Landing Page -- Footer"));
    landingFooterCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Tagline singkat yang tampil di footer Landing Page. Kosongkan untuk memakai teks bawaan."));

    const inputFooterTagline = MugenUI.el("textarea", { rows: "2" });
    const btnSimpanFooter = MugenUI.el("button", { class: "btn-primary" }, "Simpan Footer");
    const errFooter = MugenUI.el("div", { class: "login-error" });

    landingFooterCard.appendChild(MugenUI.el("label", {}, "Tagline"));
    landingFooterCard.appendChild(inputFooterTagline);
    landingFooterCard.appendChild(errFooter);
    landingFooterCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanFooter));

    async function loadLandingFooter() {
      try {
        const footer = await MugenApi.get("/api/superadmin/landing/footer");
        inputFooterTagline.value = footer.platform_footer_tagline || "";
      } catch (e) {
        errFooter.textContent = e.message;
      }
    }

    btnSimpanFooter.addEventListener("click", async () => {
      errFooter.textContent = "";
      try {
        await MugenUI.withButtonLoading(btnSimpanFooter, () => MugenApi.put("/api/superadmin/landing/footer", {
          platform_footer_tagline: inputFooterTagline.value.trim(),
        }));
        MugenUI.toast("Footer disimpan.", "success");
      } catch (e) {
        errFooter.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });

    // ---------------------------------------------------------------
    // 12. PAYMENT GATEWAY (booking publik, platform-wide -- SATU merchant
    // account dipakai bersama SELURUH tenant, lihat payment_gateway_db.py.
    // Kredensial di sini TERPISAH TOTAL dari "Konfigurasi Subscription"/
    // "Paket Billing"/"Billing SaaS – Payment Gateway" di atas -- itu untuk
    // Owner membayar LANGGANAN platform ini, ini untuk CUSTOMER membayar
    // booking.)
    // ---------------------------------------------------------------
    paymentGatewayCard.appendChild(MugenUI.el("h2", {}, "Payment Gateway"));
    paymentGatewayCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Kredensial provider PGW (dipakai SELURUH toko lewat metode \"Payment Gateway\" di halaman booking publik) + channel pembayaran yang aktif & urutan tampilnya. Tersimpan di database, berlaku langsung tanpa perlu deploy ulang."));

    const inPgwProvider = MugenUI.el("input", { type: "text", placeholder: "Nama provider Payment Gateway" });
    const selPgwEnv = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "sandbox" }, "Sandbox"),
      MugenUI.el("option", { value: "production" }, "Production"),
    ]);
    const inPgwApiKey = MugenUI.el("input", { type: "password", autocomplete: "off" });
    const inPgwServerKey = MugenUI.el("input", { type: "password", autocomplete: "off" });
    const inPgwClientKey = MugenUI.el("input", { type: "password", autocomplete: "off" });
    const inPgwMerchantId = MugenUI.el("input", { type: "text" });
    const inPgwSecretKey = MugenUI.el("input", { type: "password", autocomplete: "off" });
    const inPgwWebhookUrl = MugenUI.el("input", { type: "text", placeholder: "https://api.rivoirsett.com/api/..." });

    paymentGatewayCard.appendChild(MugenUI.el("label", {}, "Provider"));
    paymentGatewayCard.appendChild(inPgwProvider);
    paymentGatewayCard.appendChild(MugenUI.el("label", {}, "Environment"));
    paymentGatewayCard.appendChild(selPgwEnv);
    paymentGatewayCard.appendChild(MugenUI.el("label", {}, "API Key (tidak dipakai Faspay)"));
    paymentGatewayCard.appendChild(inPgwApiKey);
    paymentGatewayCard.appendChild(MugenUI.el("label", {}, "Server Key (Faspay: User ID)"));
    paymentGatewayCard.appendChild(inPgwServerKey);
    paymentGatewayCard.appendChild(MugenUI.el("label", {}, "Client Key (tidak dipakai Faspay)"));
    paymentGatewayCard.appendChild(inPgwClientKey);
    paymentGatewayCard.appendChild(MugenUI.el("label", {}, "Merchant ID (Faspay: Merchant ID)"));
    paymentGatewayCard.appendChild(inPgwMerchantId);
    paymentGatewayCard.appendChild(MugenUI.el("label", {}, "Secret Key (Faspay: Password)"));
    paymentGatewayCard.appendChild(inPgwSecretKey);
    paymentGatewayCard.appendChild(MugenUI.el("label", {}, "Webhook / Callback URL"));
    paymentGatewayCard.appendChild(inPgwWebhookUrl);
    // URL webhook SUNGGUHAN endpoint ini (booking_gateway_webhook.py) --
    // daftarkan URL ini PERSIS di dashboard provider, field di atas murni
    // catatan Super Admin sendiri.
    paymentGatewayCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:4px;" },
      `URL webhook aktif: ${MUGEN_API_BASE}/api/public/booking/gateway-webhook`));
    // Provider RESMI: Faspay Xpress v4 -- lihat catatan identik di kartu
    // "Billing SaaS – Payment Gateway" di atas (satu akun Faspay dipakai
    // bersama, HANYA satu Payment Notification URL & satu Return URL yang
    // bisa didaftarkan).
    paymentGatewayCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:4px;" },
      `Faspay Xpress v4: URL Payment Notification & Return URL yang SUNGGUHAN didaftarkan ke Faspay untuk SATU akun ini (dipakai bersama Billing SaaS di atas) -- Payment Notification: ${MUGEN_API_BASE}/api/public/gateway/faspay-notification, Return URL: ${MUGEN_API_BASE}/api/public/gateway/faspay-return`));

    paymentGatewayCard.appendChild(MugenUI.el("label", { style: "margin-top:8px;" }, "Channel Pembayaran (aktif & urutan tampil)"));
    // AUDIT (pre-merge): SESUAI keputusan eksplisit soal payment_channel --
    // daftar/urutan di bawah ini BELUM benar-benar mengontrol apa pun untuk
    // Faspay saat ini (payment_gateway_client.py SENGAJA TIDAK mengirim
    // payment_channel di buat_transaksi() -- Faspay menampilkan SEMUA
    // channel aktif di Merchant ID apa adanya, terlepas pengaturan ini).
    // Tersimpan supaya siap dipakai begitu Faspay menyediakan daftar kode
    // channel resmi -- TIDAK dihapus dari UI, hanya belum berefek.
    paymentGatewayCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:2px;margin-bottom:6px;" },
      "Belum berefek ke halaman pembayaran Faspay saat ini -- Faspay menampilkan semua channel aktif di Merchant ID apa adanya. Pengaturan ini tersimpan untuk diaktifkan begitu Faspay menyediakan daftar kode channel resmi."));
    const pgwChannelList = MugenUI.el("div", { style: "display:flex;flex-direction:column;gap:6px;margin:8px 0;" });
    paymentGatewayCard.appendChild(pgwChannelList);

    const errorPgw = MugenUI.el("div", { class: "login-error" });
    const btnSimpanPgw = MugenUI.el("button", { class: "btn-primary" }, "Simpan Payment Gateway");
    paymentGatewayCard.appendChild(errorPgw);
    paymentGatewayCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanPgw));

    // channelOrder: SEMUA channel yang didukung (lihat channel_label dari
    // backend), disusun [aktif dulu sesuai urutan tersimpan] lalu [sisanya
    // yang belum aktif] -- checkbox menentukan aktif/tidak, tombol ↑/↓
    // menggeser posisi (URUTAN array = urutan tampil di wizard booking
    // publik begitu disimpan), pola SAMA seperti reorder Gallery di
    // pages/booking.js (drag dianggap kurang andal di layar sentuh, ↑/↓
    // lebih pasti).
    let channelOrder = [];
    let channelLabel = {};
    const channelCheckbox = {};

    function renderPgwChannelList() {
      pgwChannelList.innerHTML = "";
      channelOrder.forEach((key, idx) => {
        const sudahAda = channelCheckbox[key]; // preserve toggle state milik key ini lintas re-render (reorder)
        const cb = MugenUI.el("input", { type: "checkbox" });
        cb.checked = sudahAda ? sudahAda.checked : false;
        channelCheckbox[key] = cb;
        const btnNaik = MugenUI.el("button", { type: "button", title: "Naikkan urutan" }, "↑");
        btnNaik.disabled = idx === 0;
        btnNaik.addEventListener("click", () => {
          [channelOrder[idx - 1], channelOrder[idx]] = [channelOrder[idx], channelOrder[idx - 1]];
          renderPgwChannelList();
        });
        const btnTurun = MugenUI.el("button", { type: "button", title: "Turunkan urutan" }, "↓");
        btnTurun.disabled = idx === channelOrder.length - 1;
        btnTurun.addEventListener("click", () => {
          [channelOrder[idx], channelOrder[idx + 1]] = [channelOrder[idx + 1], channelOrder[idx]];
          renderPgwChannelList();
        });
        pgwChannelList.appendChild(MugenUI.el("div", { style: "display:flex;align-items:center;gap:8px;" }, [
          cb, MugenUI.el("span", { style: "flex:1;" }, channelLabel[key] || key), btnNaik, btnTurun,
        ]));
      });
    }

    async function loadPaymentGatewayConfig() {
      try {
        const cfg = await MugenApi.get("/api/superadmin/payment-gateway/config");
        inPgwProvider.value = cfg.pgw_provider || "";
        selPgwEnv.value = cfg.pgw_environment || "sandbox";
        inPgwApiKey.value = cfg.pgw_api_key || "";
        inPgwServerKey.value = cfg.pgw_server_key || "";
        inPgwClientKey.value = cfg.pgw_client_key || "";
        inPgwMerchantId.value = cfg.pgw_merchant_id || "";
        inPgwSecretKey.value = cfg.pgw_secret_key || "";
        inPgwWebhookUrl.value = cfg.pgw_webhook_url || "";
        channelLabel = cfg.channel_label || {};
        const aktif = cfg.metode_aktif || [];
        const belumAktif = Object.keys(channelLabel).filter((k) => !aktif.includes(k));
        channelOrder = [...aktif, ...belumAktif];
        renderPgwChannelList();
        for (const key of aktif) if (channelCheckbox[key]) channelCheckbox[key].checked = true;
      } catch (e) { errorPgw.textContent = e.message; }
    }
    btnSimpanPgw.addEventListener("click", async () => {
      errorPgw.textContent = "";
      const metode_aktif = channelOrder.filter((key) => channelCheckbox[key] && channelCheckbox[key].checked);
      try {
        await MugenUI.withButtonLoading(btnSimpanPgw, () => MugenApi.put("/api/superadmin/payment-gateway/config", {
          provider: inPgwProvider.value, environment: selPgwEnv.value, api_key: inPgwApiKey.value,
          server_key: inPgwServerKey.value, client_key: inPgwClientKey.value, merchant_id: inPgwMerchantId.value,
          secret_key: inPgwSecretKey.value, webhook_url: inPgwWebhookUrl.value, metode_aktif,
        }));
        MugenUI.toast("Konfigurasi Payment Gateway disimpan.", "success");
        loadAuditLog();
      } catch (e) {
        errorPgw.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });

    // ---------------------------------------------------------------
    // Migrasi Faspay SNAP Advance -- kartu konfigurasi TERPISAH dari kartu
    // "Payment Gateway" (Xpress v4) di atas, lihat snap_advance_db.py.
    // Xpress v4 TETAP jadi provider aktif untuk booking/billing sampai SNAP
    // Advance tervalidasi produksi -- mengisi kredensial di sini TIDAK
    // memindahkan lalu lintas pembayaran apa pun secara otomatis.
    // ---------------------------------------------------------------
    snapAdvanceCard.appendChild(MugenUI.el("h2", {}, "Faspay SNAP Advance (Migrasi)"));
    snapAdvanceCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Provider BARU yang MENGGANTIKAN Payment Gateway (Xpress v4) di atas -- Owner sudah memutuskan Xpress v4 tidak lagi dipakai, satu-satunya Payment Notification URL Merchant ID Faspay sekarang mengarah ke SNAP. VA & Direct Debit sudah diimplementasikan sesuai dokumen resmi Faspay -- QRIS & Registrasi/Account Binding Direct Debit MASIH PENDING FASPAY. Mengisi form ini menyiapkan kredensial -- SNAP BELUM di-wire ke flow checkout booking/billing production, menunggu uji Faspay Simulator & verifikasi ASPI/BI lebih dulu."));

    const inSnapEnv = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "sandbox" }, "Sandbox"),
      MugenUI.el("option", { value: "production" }, "Production"),
    ]);
    const inSnapSandboxUrl = MugenUI.el("input", { type: "text", placeholder: "mis. https://debit-sandbox.faspay.co.id" });
    const inSnapProductionUrl = MugenUI.el("input", { type: "text", placeholder: "PENDING FASPAY -- domain production belum dikonfirmasi" });
    const inSnapMerchantId = MugenUI.el("input", { type: "text" });
    const inSnapPartnerId = MugenUI.el("input", { type: "text" });
    const inSnapClientId = MugenUI.el("input", { type: "text" });
    const inSnapClientSecret = MugenUI.el("input", { type: "password", autocomplete: "off" });
    const inSnapPrivateKey = MugenUI.el("textarea", { rows: "4", placeholder: "-----BEGIN PRIVATE KEY-----" });
    const inSnapPublicKey = MugenUI.el("textarea", { rows: "4", placeholder: "-----BEGIN PUBLIC KEY----- (public key Faspay, untuk verifikasi webhook)" });
    const inSnapWebhookSecret = MugenUI.el("input", { type: "password", autocomplete: "off" });
    const inSnapChannelId = MugenUI.el("input", { type: "text", placeholder: "mis. 77001" });
    const inSnapVaChannelCode = MugenUI.el("select", {}, [MugenUI.el("option", { value: "" }, "-- pilih bank VA --")]);
    const inSnapQrisChannelCode = MugenUI.el("select", {}, [MugenUI.el("option", { value: "" }, "-- pilih e-wallet QRIS --")]);
    const inSnapTimeout = MugenUI.el("input", { type: "number", min: "1" });
    const inSnapRetryMax = MugenUI.el("input", { type: "number", min: "0" });

    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Environment"));
    snapAdvanceCard.appendChild(inSnapEnv);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Sandbox Base URL"));
    snapAdvanceCard.appendChild(inSnapSandboxUrl);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Production Base URL"));
    snapAdvanceCard.appendChild(inSnapProductionUrl);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Merchant ID"));
    snapAdvanceCard.appendChild(inSnapMerchantId);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Partner ID"));
    snapAdvanceCard.appendChild(inSnapPartnerId);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Client ID"));
    snapAdvanceCard.appendChild(inSnapClientId);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Client Secret"));
    snapAdvanceCard.appendChild(inSnapClientSecret);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Private Key (RSA, milik merchant -- untuk menandatangani permintaan)"));
    snapAdvanceCard.appendChild(inSnapPrivateKey);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Public Key Faspay (untuk memverifikasi webhook masuk)"));
    snapAdvanceCard.appendChild(inSnapPublicKey);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Webhook Secret (kalau ada)"));
    snapAdvanceCard.appendChild(inSnapWebhookSecret);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "CHANNEL-ID (identifier layanan API Faspay, BUKAN kode bank -- diberikan Faspay, mis. 77001)"));
    snapAdvanceCard.appendChild(inSnapChannelId);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Bank VA Default (channelCode Create VA)"));
    snapAdvanceCard.appendChild(inSnapVaChannelCode);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "E-Wallet QRIS Default (channelCode Generate QRIS)"));
    snapAdvanceCard.appendChild(inSnapQrisChannelCode);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Timeout (detik)"));
    snapAdvanceCard.appendChild(inSnapTimeout);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Retry Max"));
    snapAdvanceCard.appendChild(inSnapRetryMax);
    snapAdvanceCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:4px;" },
      `URL webhook SNAP Advance (SATU endpoint untuk Booking + SaaS Billing): ${MUGEN_API_BASE}/api/public/gateway/snap-notification`));

    snapAdvanceCard.appendChild(MugenUI.el("label", { style: "margin-top:8px;" }, "Channel Aktif"));
    snapAdvanceCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:2px;margin-bottom:6px;" },
      "QRIS sekarang sudah diimplementasikan sesuai dokumen resmi Faspay -- centang untuk mengaktifkan (jangan lupa isi \"E-Wallet QRIS Default\" di atas). Dynamic E-Wallet (di luar QRIS) BELUM tersedia -- dokumen resmi belum diberikan, sengaja tidak ditebak. Direct Debit BELUM bisa diaktifkan lewat checkbox ini -- prasyarat Registrasi/Account Binding-nya masih PENDING FASPAY (dokumen Payment menunjukkan token binding hanya wajib untuk channel BRI Direct Debit, channel lain belum terkonfirmasi caranya)."));
    const snapChannelList = MugenUI.el("div", { style: "display:flex;flex-direction:column;gap:6px;margin:8px 0;" });
    snapAdvanceCard.appendChild(snapChannelList);

    const errorSnap = MugenUI.el("div", { class: "login-error" });
    const btnSimpanSnap = MugenUI.el("button", { class: "btn-primary" }, "Simpan SNAP Advance");
    snapAdvanceCard.appendChild(errorSnap);
    snapAdvanceCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanSnap));

    let snapChannelLabel = {};
    const snapChannelCheckbox = {};

    function renderSnapChannelList() {
      snapChannelList.innerHTML = "";
      for (const key of Object.keys(snapChannelLabel)) {
        const sudahAda = snapChannelCheckbox[key];
        const cb = MugenUI.el("input", { type: "checkbox" });
        cb.checked = sudahAda ? sudahAda.checked : false;
        snapChannelCheckbox[key] = cb;
        snapChannelList.appendChild(MugenUI.el("div", { style: "display:flex;align-items:center;gap:8px;" }, [
          cb, MugenUI.el("span", {}, snapChannelLabel[key] || key),
        ]));
      }
    }

    async function loadSnapAdvanceConfig() {
      try {
        const cfg = await MugenApi.get("/api/superadmin/snap-advance/config");
        inSnapEnv.value = cfg.snap_environment || "sandbox";
        inSnapSandboxUrl.value = cfg.snap_sandbox_base_url || "";
        inSnapProductionUrl.value = cfg.snap_production_base_url || "";
        inSnapMerchantId.value = cfg.snap_merchant_id || "";
        inSnapPartnerId.value = cfg.snap_partner_id || "";
        inSnapClientId.value = cfg.snap_client_id || "";
        // BUGFIX keamanan: get_config() TIDAK PERNAH lagi mengirim nilai asli
        // untuk field rahasia (private key/client secret/webhook secret) --
        // lihat snap_advance_db.py::get_config(). Input dikosongkan (BUKAN
        // diisi ulang) dan diberi placeholder dari penanda `_terisi`, supaya
        // private key RSA tidak lagi ikut mendarat di browser tiap halaman
        // dibuka. Mengirim field ini KOSONG saat Simpan berarti "tidak
        // diubah" (lihat snap_advance_db.py::update_config()) -- isi ulang
        // HANYA kalau memang mau mengganti nilainya.
        inSnapClientSecret.value = "";
        inSnapClientSecret.placeholder = cfg.snap_client_secret_terisi ? "(sudah diisi -- kosongkan supaya tidak berubah)" : "";
        inSnapPrivateKey.value = "";
        inSnapPrivateKey.placeholder = cfg.snap_private_key_terisi
          ? "(sudah diisi -- kosongkan supaya tidak berubah)" : "-----BEGIN PRIVATE KEY-----";
        inSnapPublicKey.value = cfg.snap_faspay_public_key || "";
        inSnapWebhookSecret.value = "";
        inSnapWebhookSecret.placeholder = cfg.snap_webhook_secret_terisi ? "(sudah diisi -- kosongkan supaya tidak berubah)" : "";
        inSnapChannelId.value = cfg.snap_channel_id || "";
        inSnapTimeout.value = cfg.snap_timeout_detik || 30;
        inSnapRetryMax.value = cfg.snap_retry_max || 3;
        snapChannelLabel = cfg.channel_label || {};
        renderSnapChannelList();
        const vaChannelLabel = cfg.va_channel_code_label || {};
        inSnapVaChannelCode.innerHTML = "";
        inSnapVaChannelCode.appendChild(MugenUI.el("option", { value: "" }, "-- pilih bank VA --"));
        for (const [kode, label] of Object.entries(vaChannelLabel)) {
          inSnapVaChannelCode.appendChild(MugenUI.el("option", { value: kode }, `${kode} -- ${label}`));
        }
        inSnapVaChannelCode.value = cfg.snap_va_channel_code || "";
        const qrisChannelLabel = cfg.qris_channel_code_label || {};
        inSnapQrisChannelCode.innerHTML = "";
        inSnapQrisChannelCode.appendChild(MugenUI.el("option", { value: "" }, "-- pilih e-wallet QRIS --"));
        for (const [kode, label] of Object.entries(qrisChannelLabel)) {
          inSnapQrisChannelCode.appendChild(MugenUI.el("option", { value: kode }, `${kode} -- ${label}`));
        }
        inSnapQrisChannelCode.value = cfg.snap_qris_channel_code || "";
        for (const key of (cfg.snap_channel_aktif || [])) if (snapChannelCheckbox[key]) snapChannelCheckbox[key].checked = true;
      } catch (e) { errorSnap.textContent = e.message; }
    }
    btnSimpanSnap.addEventListener("click", async () => {
      errorSnap.textContent = "";
      const channel_aktif = Object.keys(snapChannelCheckbox).filter((key) => snapChannelCheckbox[key].checked);
      try {
        await MugenUI.withButtonLoading(btnSimpanSnap, () => MugenApi.put("/api/superadmin/snap-advance/config", {
          environment: inSnapEnv.value, sandbox_base_url: inSnapSandboxUrl.value,
          production_base_url: inSnapProductionUrl.value, merchant_id: inSnapMerchantId.value,
          partner_id: inSnapPartnerId.value, client_id: inSnapClientId.value, client_secret: inSnapClientSecret.value,
          private_key: inSnapPrivateKey.value, faspay_public_key: inSnapPublicKey.value,
          webhook_secret: inSnapWebhookSecret.value, timeout_detik: Number(inSnapTimeout.value) || 30,
          retry_max: Number(inSnapRetryMax.value) || 0, channel_aktif,
          channel_id: inSnapChannelId.value, va_channel_code: inSnapVaChannelCode.value,
          qris_channel_code: inSnapQrisChannelCode.value,
        }));
        MugenUI.toast("Konfigurasi SNAP Advance disimpan.", "success");
        loadAuditLog();
      } catch (e) {
        errorSnap.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });

    // ---------------------------------------------------------------
    // 13. RIWAYAT TRANSAKSI (Implementasi Payment Gateway & Riwayat
    // Transaksi Multi-Tenant) -- pusat monitoring SELURUH transaksi
    // pembayaran platform (booking customer + langganan SaaS Owner), murni
    // MEMBACA lewat transaction_report_db.py (require_superadmin, lihat
    // routers/transaction_report.py). Status pembayaran yang tampil di sini
    // TIDAK PERNAH bisa diubah dari layar ini -- HANYA berubah lewat
    // webhook resmi provider (billing_webhook.py/booking_gateway_webhook.py).
    // ---------------------------------------------------------------
    const TRX_STATUS_LABEL = {
      menunggu_pembayaran: "Menunggu Pembayaran",
      diproses: "Sedang Diproses",
      berhasil: "Berhasil",
      gagal: "Gagal",
      kedaluwarsa: "Kedaluwarsa",
      dibatalkan: "Dibatalkan",
      refund: "Refund",
    };
    const TRX_STATUS_BADGE = {
      menunggu_pembayaran: "badge-libur",
      diproses: "badge-libur",
      berhasil: "badge-success",
      gagal: "badge-danger",
      kedaluwarsa: "badge-danger",
      dibatalkan: "badge-danger",
      refund: "badge-warning",
    };
    const TRX_JENIS_LABEL = { booking: "Booking", langganan: "Langganan SaaS" };

    function trxStatusBadge(status) {
      return MugenUI.el("span", { class: "badge" + (TRX_STATUS_BADGE[status] ? " " + TRX_STATUS_BADGE[status] : "") },
        TRX_STATUS_LABEL[status] || status);
    }

    transaksiSummaryCard.appendChild(MugenUI.el("h2", {}, "Riwayat Transaksi -- Ringkasan"));
    const transaksiSummaryBody = MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-top:12px;" });
    transaksiSummaryCard.appendChild(transaksiSummaryBody);
    const transaksiPerTenantBody = MugenUI.el("div", { style: "margin-top:16px;" });
    transaksiSummaryCard.appendChild(transaksiPerTenantBody);

    transaksiCard.appendChild(MugenUI.el("h2", {}, "Riwayat Transaksi"));
    transaksiCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Seluruh transaksi pembayaran platform (booking customer + langganan SaaS Owner). Status HANYA berubah otomatis lewat notifikasi resmi provider (webhook), tidak pernah dari layar ini."));

    const trxSelTenant = MugenUI.el("select");
    trxSelTenant.appendChild(MugenUI.el("option", { value: "" }, "Semua Toko"));
    const trxInputMulai = MugenUI.el("input", { type: "date" });
    const trxInputSelesai = MugenUI.el("input", { type: "date" });
    const trxSelJenis = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "" }, "Semua Jenis"),
      MugenUI.el("option", { value: "booking" }, "Booking"),
      MugenUI.el("option", { value: "langganan" }, "Langganan SaaS"),
    ]);
    const trxSelStatus = MugenUI.el("select");
    trxSelStatus.appendChild(MugenUI.el("option", { value: "" }, "Semua Status"));
    for (const [k, label] of Object.entries(TRX_STATUS_LABEL)) trxSelStatus.appendChild(MugenUI.el("option", { value: k }, label));
    const trxInputMetode = MugenUI.el("input", { type: "text", placeholder: "mis. gateway, transfer, qris" });
    const trxInputChannel = MugenUI.el("input", { type: "text", placeholder: "mis. qris, bank_transfer" });
    const trxInputCari = MugenUI.el("input", { type: "text", placeholder: "No. transaksi/toko/customer/Booking ID/Transaction ID/Reference ID" });
    const trxBtnFilter = MugenUI.el("button", { class: "btn-primary" }, "Terapkan Filter");
    const trxBtnExport = MugenUI.el("button", {}, "Export CSV");

    transaksiCard.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:8px;align-items:flex-end;" }, [
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Toko"), trxSelTenant]),
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Dari Tanggal"), trxInputMulai]),
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Sampai Tanggal"), trxInputSelesai]),
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Jenis"), trxSelJenis]),
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Status"), trxSelStatus]),
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Metode"), trxInputMetode]),
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Channel"), trxInputChannel]),
      MugenUI.el("div", { style: "flex:1;min-width:240px;" }, [MugenUI.el("label", {}, "Cari"), trxInputCari]),
      trxBtnFilter,
      trxBtnExport,
    ]));

    const trxListBody = MugenUI.el("div", { style: "margin-top:12px;" });
    transaksiCard.appendChild(trxListBody);

    function trxWaktuLengkap(iso) {
      if (!iso) return "-";
      const [tanggal, jam] = iso.split("T");
      return `${MugenUI.formatTanggal(tanggal)} ${(jam || "").slice(0, 8)}`.trim();
    }

    function trxQueryString() {
      const params = new URLSearchParams();
      if (trxSelTenant.value) params.set("tenant_id", trxSelTenant.value);
      if (trxInputMulai.value) params.set("tanggal_mulai", trxInputMulai.value);
      if (trxInputSelesai.value) params.set("tanggal_selesai", trxInputSelesai.value + "T23:59:59");
      if (trxSelJenis.value) params.set("jenis", trxSelJenis.value);
      if (trxSelStatus.value) params.set("status", trxSelStatus.value);
      if (trxInputMetode.value.trim()) params.set("metode_pembayaran", trxInputMetode.value.trim());
      if (trxInputChannel.value.trim()) params.set("channel_pembayaran", trxInputChannel.value.trim());
      if (trxInputCari.value.trim()) params.set("cari", trxInputCari.value.trim());
      return params.toString();
    }

    async function trxLihatDetail(ringkas) {
      try {
        const detail = await MugenApi.get(`/api/superadmin/transactions/${ringkas.jenis}/${ringkas.id}`);
        const body = [
          MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-bottom:10px;" }, [
            MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Status"), trxStatusBadge(detail.status_unified)]),
            MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Jenis"), MugenUI.el("div", {}, TRX_JENIS_LABEL[detail.jenis] || detail.jenis)]),
            MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Nominal"), MugenUI.el("div", {}, MugenUI.formatRupiah(detail.nominal))]),
          ]),
          MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-bottom:10px;" }, [
            MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Toko"), MugenUI.el("div", {}, detail.tenant_nama || "-")]),
            MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Customer"), MugenUI.el("div", {}, detail.customer_nama || "-")]),
            MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Booking ID"), MugenUI.el("div", {}, detail.booking_id != null ? String(detail.booking_id) : "-")]),
          ]),
          MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-bottom:10px;" }, [
            MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Barber"), MugenUI.el("div", {}, detail.barber_nama || "-")]),
            MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Layanan/Paket"), MugenUI.el("div", {}, detail.layanan || "-")]),
          ]),
          MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-bottom:10px;" }, [
            MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Metode"), MugenUI.el("div", {}, detail.metode_pembayaran || "-")]),
            MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Channel"), MugenUI.el("div", {}, detail.channel_pembayaran || "-")]),
          ]),
          MugenUI.el("div", { style: "margin-bottom:10px;" }, [
            MugenUI.el("div", { class: "subtitle" }, "Dibuat"), MugenUI.el("div", {}, trxWaktuLengkap(detail.created_at)),
          ]),
          MugenUI.el("div", { style: "margin-bottom:10px;" }, [
            MugenUI.el("div", { class: "subtitle" }, "Dibayar"), MugenUI.el("div", {}, trxWaktuLengkap(detail.paid_at)),
          ]),
          MugenUI.el("div", { style: "margin-bottom:10px;" }, [
            MugenUI.el("div", { class: "subtitle" }, "Webhook Terakhir Diterima"), MugenUI.el("div", {}, trxWaktuLengkap(detail.updated_at)),
          ]),
          MugenUI.el("div", { style: "margin-bottom:10px;" }, [
            MugenUI.el("div", { class: "subtitle" }, "Transaction ID (Provider)"), MugenUI.el("div", {}, detail.transaction_id_provider || "-"),
          ]),
          MugenUI.el("div", { style: "margin-bottom:10px;" }, [
            MugenUI.el("div", { class: "subtitle" }, "Reference ID (Provider)"), MugenUI.el("div", {}, detail.reference_id_provider || "-"),
          ]),
          MugenUI.el("h3", { style: "margin-top:16px;" }, "Riwayat Perubahan Status"),
          MugenUI.buildTable(
            [
              { key: "waktu", label: "Waktu", format: trxWaktuLengkap },
              { key: "status_lama", label: "Dari", format: (v) => TRX_STATUS_LABEL[v] || v || "-" },
              { key: "status_baru", label: "Ke", format: (v) => TRX_STATUS_LABEL[v] || v },
            ],
            detail.status_log || [],
            { emptyText: "Belum ada perubahan status." },
          ),
          MugenUI.el("h3", { style: "margin-top:16px;" }, "Raw Webhook Payload (Troubleshooting)"),
          MugenUI.el("pre", { style: "white-space:pre-wrap;word-break:break-all;font-size:12px;background:var(--card-alt,#0000000d);padding:8px;border-radius:6px;" },
            detail.raw_notification || "Belum ada notifikasi webhook diterima."),
        ];
        MugenUI.infoModal({ title: `Detail Transaksi -- ${detail.nomor_transaksi}`, body });
      } catch (e) {
        MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
      }
    }

    async function loadTransaksi() {
      trxSelTenant.innerHTML = "";
      trxSelTenant.appendChild(MugenUI.el("option", { value: "" }, "Semua Toko"));
      for (const t of tenantList) trxSelTenant.appendChild(MugenUI.el("option", { value: String(t.id) }, t.nama_barbershop));

      transaksiSummaryBody.innerHTML = "";
      transaksiSummaryBody.appendChild(MugenUI.skeleton("card", { lines: 2 }));
      trxListBody.innerHTML = "";
      trxListBody.appendChild(MugenUI.skeleton("table", { cols: 8, rows: 4 }));
      try {
        const hasil = await MugenApi.get(`/api/superadmin/transactions?${trxQueryString()}`);
        const { transactions, summary } = hasil;

        transaksiSummaryBody.innerHTML = "";
        transaksiSummaryBody.appendChild(statTile("Total Transaksi", summary.total_transaksi));
        transaksiSummaryBody.appendChild(statTile("Booking", summary.total_booking));
        transaksiSummaryBody.appendChild(statTile("Langganan SaaS", summary.total_langganan));
        transaksiSummaryBody.appendChild(statTile("Berhasil", summary.total_berhasil));
        transaksiSummaryBody.appendChild(statTile("Pending", summary.total_pending));
        transaksiSummaryBody.appendChild(statTile("Gagal", summary.total_gagal));
        transaksiSummaryBody.appendChild(statTile("Dibatalkan", summary.total_dibatalkan));
        transaksiSummaryBody.appendChild(statTile("Total Nilai (Berhasil)", MugenUI.formatRupiah(summary.total_nilai)));

        transaksiPerTenantBody.innerHTML = "";
        transaksiPerTenantBody.appendChild(MugenUI.el("h3", {}, "Per Toko (sesuai filter)"));
        transaksiPerTenantBody.appendChild(MugenUI.buildTable(
          [
            { key: "tenant_nama", label: "Toko" },
            { key: "jumlah_transaksi", label: "Jumlah Transaksi" },
            { key: "omzet", label: "Omzet (Berhasil)", format: MugenUI.formatRupiah },
          ],
          summary.per_tenant || [],
          { emptyText: "Belum ada transaksi sesuai filter." },
        ));

        trxListBody.innerHTML = "";
        trxListBody.appendChild(MugenUI.buildTable(
          [
            { key: "nomor_transaksi", label: "No. Transaksi" },
            { key: "tanggal", label: "Tanggal", format: trxWaktuLengkap },
            { key: "jenis", label: "Jenis", format: (v) => TRX_JENIS_LABEL[v] || v },
            { key: "tenant_nama", label: "Toko" },
            { key: "customer_nama", label: "Customer", format: (v) => v || "-" },
            { key: "booking_id", label: "Booking ID", format: (v) => (v != null ? String(v) : "-") },
            { key: "barber_nama", label: "Barber", format: (v) => v || "-" },
            { key: "layanan", label: "Layanan/Paket" },
            { key: "nominal", label: "Nominal", format: MugenUI.formatRupiah },
            { key: "metode_pembayaran", label: "Metode" },
            { key: "channel_pembayaran", label: "Channel", format: (v) => v || "-" },
            { key: "status_unified", label: "Status", format: trxStatusBadge },
            { key: "transaction_id_provider", label: "Transaction ID", format: (v) => v || "-" },
            { key: "reference_id_provider", label: "Reference ID", format: (v) => v || "-" },
            {
              key: "aksi", label: "Aksi", format: (_, r) => {
                const btn = MugenUI.el("button", {}, "Detail");
                btn.addEventListener("click", () => trxLihatDetail(r));
                return btn;
              },
            },
          ],
          transactions,
          { emptyText: "Belum ada transaksi sesuai filter." },
        ));
      } catch (e) {
        transaksiSummaryBody.innerHTML = "";
        transaksiSummaryBody.appendChild(MugenUI.errorState(e.message));
        trxListBody.innerHTML = "";
        trxListBody.appendChild(MugenUI.errorState(e.message));
      }
    }
    trxBtnFilter.addEventListener("click", loadTransaksi);
    trxBtnExport.addEventListener("click", async () => {
      try {
        await MugenUI.withButtonLoading(trxBtnExport, () => MugenApi.downloadFile(`/api/superadmin/transactions/export?${trxQueryString()}`, "riwayat-transaksi.csv"));
      } catch (e) {
        MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
      }
    });

    // ---------------------------------------------------------------
    // 14. RIWAYAT AKSI (Audit Log)
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
    await loadBillingGatewayConfig();
    await loadLandingFaq();
    await loadLandingContact();
    await loadLandingFooter();
    await loadPaymentGatewayConfig();
    await loadSnapAdvanceConfig();
    await loadTransaksi();
    await loadAuditLog();
  }

  return { render };
})();

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js
// (bukan <script> biasa lagi, lihat index.html/router.js) -- top-level
// "const" TIDAK menempel ke objek window di browser (beda dari "var"),
// jadi page_loader.js TIDAK BISA mendeteksi lewat window.PageSuperadmin begitu saja
// setelah script ini selesai dimuat. Baris di bawah ini SATU-SATUNYA
// perubahan di file ini untuk mendukung lazy-load -- expose eksplisit ke
// window supaya page_loader.js bisa memverifikasi modul benar-benar
// berhasil dimuat sebelum memanggil render()-nya.
window.PageSuperadmin = PageSuperadmin;
