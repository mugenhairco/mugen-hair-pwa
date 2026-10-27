// pages/superadmin.js — FONDASI Multi-Tenant Phase 2.1: Super Admin Dashboard
// Khusus akun role 'superadmin' (tenant_id=NULL, lihat auth_db.py/auth.py) --
// dirender router.js untuk SEMUA hash begitu login sebagai superadmin (lihat
// router.js), jadi halaman ini TIDAK mengikuti sistem menu/hash biasa.
//
// Dua bagian: 1) daftar seluruh tenant + tombol Aktifkan/Nonaktifkan,
// 2) form buat toko baru (+ akun Owner pertamanya sekaligus, lihat
// routers/superadmin.py::buat_tenant()).

const PageSuperadmin = (() => {
  let _permissionTreeCache = null;
  async function _muatPermissionTreeSuperadmin() {
    if (_permissionTreeCache) return _permissionTreeCache;
    _permissionTreeCache = await MugenApi.get("/api/superadmin/billing/permission-tree");
    return _permissionTreeCache;
  }

  // FITUR Package Permission Tree (Work #2, diminta Owner): pola dropdown/
  // expand SAMA PERSIS pages/pengaturan.js::buildPermissionTreeUI() (Role
  // Owner tenant) -- diduplikasi di sini (bukan diimpor lintas modul,
  // konsisten dengan konvensi file ini) karena dipakai menggerbang PAKET,
  // bukan Role. Lihat docstring lengkap di pengaturan.js untuk perilaku
  // dropdown/cascade-uncheck-nya.
  function buildPermissionTreeUI(container, tree, izinData) {
    const checkboxes = {};
    const childrenOf = {};
    for (const node of tree.nodes) {
      const p = node.parent;
      if (!childrenOf[p]) childrenOf[p] = [];
      childrenOf[p].push(node);
    }
    const crossCutting = new Set(tree.cross_cutting || []);

    function semuaKeturunan(key) {
      const hasil = [];
      for (const anak of (childrenOf[key] || [])) {
        hasil.push(anak.key);
        hasil.push(...semuaKeturunan(anak.key));
      }
      return hasil;
    }

    function buildNode(node, target) {
      const row = MugenUI.el("label", { class: "perm-tree-row" });
      const cb = MugenUI.el("input", { type: "checkbox", style: "width:auto;" });
      cb.checked = !!izinData[node.key];
      checkboxes[node.key] = cb;
      row.appendChild(cb);
      row.appendChild(MugenUI.el("span", {}, node.label));
      target.appendChild(row);

      const anakList = childrenOf[node.key] || [];
      if (!anakList.length) return;
      const anakBox = MugenUI.el("div", { class: "perm-tree-children",
        style: `margin-left:22px;${cb.checked ? "" : "display:none;"}` });
      target.appendChild(anakBox);
      for (const anak of anakList) buildNode(anak, anakBox);
      cb.addEventListener("change", () => {
        anakBox.style.display = cb.checked ? "" : "none";
        if (!cb.checked) {
          for (const keyKeturunan of semuaKeturunan(node.key)) {
            if (checkboxes[keyKeturunan]) checkboxes[keyKeturunan].checked = false;
          }
        }
      });
    }

    const roots = (childrenOf[null] || []).filter((n) => !crossCutting.has(n.key));
    for (const root of roots) buildNode(root, container);

    const sejajar = (childrenOf[null] || []).filter((n) => crossCutting.has(n.key));
    if (sejajar.length) {
      container.appendChild(MugenUI.el("h3", { style: "margin-top:20px;" }, "Lintas Menu"));
      for (const node of sejajar) buildNode(node, container);
    }
    return checkboxes;
  }

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
    // FITUR WA Bot (Input Data & Rekap via WhatsApp, Fonnte).
    ubah_config_whatsapp_bot: "Ubah Konfigurasi WA Bot",
    ubah_status_whatsapp_bot: "Ubah Status WA Bot",
    ubah_tampilkan_potongan_keterlambatan_whatsapp_bot: "Ubah Tampilan Potongan Keterlambatan WA Bot",
    hapus_config_whatsapp_bot: "Hapus Konfigurasi WA Bot",
    // FITUR Program Afiliasi Sales/Marketing (sales_db.py, routers/sales.py).
    buat_akun_sales: "Buat Akun Sales",
    ubah_password_sales: "Ubah Password Sales",
    ubah_kode_referral: "Ubah Kode Referral",
    tempel_referral_tenant: "Tempel Kode Referral ke Tenant",
    ubah_status_komisi: "Ubah Status Komisi",
    buat_transaksi_lifetime: "Buat Transaksi Lifetime",
    ubah_status_lifetime: "Ubah Status Lifetime",
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
    trial: "Trial", active: "Active",
    expired: "Expired", suspended: "Suspended", cancelled: "Cancelled",
  };
  const BADGE_STATUS_SUBS = {
    trial: "badge-libur", active: "badge-success",
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
    // "Riwayat Transaksi" -- pusat monitoring SELURUH transaksi platform
    // (booking customer + langganan SaaS), murni MEMBACA lewat
    // transaction_report_db.py (lihat modul itu), TIDAK menambah business
    // logic baru sama sekali.
    //
    // RESTRUKTURISASI (ledger audit trail, Agustus 2026): "Riwayat
    // Transaksi" jadi PARENT dengan 2 sub-tab yang TIDAK PERNAH tercampur
    // -- "Riwayat Langganan Tenant" (pembayaran tenant KE Rivoir, jenis=
    // langganan) dan "Riwayat Booking Tenant" (pembayaran customer KE
    // tenant, jenis=booking). Masing-masing MEMANGGIL endpoint yang sama
    // (/api/superadmin/transactions, sudah mendukung filter `jenis` sejak
    // awal, lihat transaction_report_db.py) tapi dengan `jenis` DIKUNCI
    // per sub-tab (bukan dropdown yang bisa diubah pengguna) -- supaya
    // dua daftar ini SECARA STRUKTUR tidak mungkin tercampur sama sekali,
    // bukan cuma kebetulan tidak dicampur di UI.
    const langgananSummaryCard = MugenUI.el("div", { class: "card" });
    const langgananCard = MugenUI.el("div", { class: "card" });
    const bookingSummaryCard = MugenUI.el("div", { class: "card" });
    const bookingCard = MugenUI.el("div", { class: "card" });
    // Settlement Faspay per Terminal (Tenant): monitoring closing SELURUH
    // tenant ("terminal" = tenant, keputusan eksplisit Owner) -- murni
    // MEMBACA lewat faspay_settlement_db.py (require_superadmin, lihat
    // routers/faspay_settlement_superadmin.py). SATU-SATUNYA aksi TULIS
    // Super Admin di sini: memicu rekonsiliasi H+1 (TIDAK PERNAH mengubah
    // data pengajuan awal terminal).
    const settlementCard = MugenUI.el("div", { class: "card" });
    // FITUR WA Bot (Input Data & Rekap via WhatsApp, provider Fonnte):
    // kelola nomor device + token + aktif/nonaktif + kuota per tenant --
    // SATU-SATUNYA tempat ini bisa diatur (Owner/Admin tenant TIDAK PUNYA
    // akses sama sekali, lihat routers/whatsapp_bot.py). waBotCard = daftar
    // tenant + status, waBotEditCard = form "Atur" yang dipopulasi saat
    // tombol di tabel diklik (pola SAMA seperti billingPackagesCard/
    // billingPackageEditCard di atas).
    const waBotCard = MugenUI.el("div", { class: "card" });
    const waBotEditCard = MugenUI.el("div", { class: "card" });
    // FITUR Program Afiliasi Sales/Marketing (sales_db.py, routers/sales.py):
    // tiga kartu -- rekrut akun sales + daftar kode referral (persentase
    // komisi fleksibel, diedit lewat prompt() pola sama seperti "Ubah Slug"
    // di atas), transaksi Lisensi Lifetime (dicatat manual, lihat
    // docstring sales_db.py), dan daftar komisi lintas sales (toggle
    // status bayar).
    const salesCard = MugenUI.el("div", { class: "card" });
    const salesLifetimeCard = MugenUI.el("div", { class: "card" });
    const salesKomisiCard = MugenUI.el("div", { class: "card" });

    const tabDashboard = MugenUI.el("div");
    const tabTenant = MugenUI.el("div", { style: "display:none;" });
    const tabPaket = MugenUI.el("div", { style: "display:none;" });
    const tabLanding = MugenUI.el("div", { style: "display:none;" });
    const tabPgw = MugenUI.el("div", { style: "display:none;" });
    const tabTransaksi = MugenUI.el("div", { style: "display:none;" });
    const tabSettlement = MugenUI.el("div", { style: "display:none;" });
    const tabWaBot = MugenUI.el("div", { style: "display:none;" });
    const tabSales = MugenUI.el("div", { style: "display:none;" });
    const panelByKey = { dashboard: tabDashboard, tenant: tabTenant, paket: tabPaket, landing: tabLanding, pgw: tabPgw, transaksi: tabTransaksi, settlement: tabSettlement, wabot: tabWaBot, sales: tabSales };
    const tabsCtl = MugenUI.tabs(
      [
        { key: "dashboard", label: "Dashboard" },
        { key: "tenant", label: "Tenant" },
        { key: "paket", label: "Paket" },
        { key: "landing", label: "Landing Page" },
        { key: "pgw", label: "Payment Gateway" },
        { key: "transaksi", label: "Riwayat Transaksi" },
        { key: "settlement", label: "Settlement Faspay" },
        { key: "wabot", label: "WA Bot" },
        { key: "sales", label: "Sales & Referral" },
      ],
      {
        onChange: (key) => {
          for (const k in panelByKey) panelByKey[k].style.display = k === key ? "" : "none";
          // Indikator sub-tab "Riwayat Transaksi" dihitung dari
          // offsetWidth/offsetLeft -- 0 kalau parent-nya masih
          // display:none saat pertama dirender (lihat MugenUI.tabs()),
          // jadi WAJIB dihitung ulang tepat saat panel ini baru terlihat.
          if (key === "transaksi") requestAnimationFrame(trxSubTabsCtl.moveIndicator);
        },
      },
    );
    root.appendChild(tabsCtl.bar);
    root.appendChild(tabDashboard);
    root.appendChild(tabTenant);
    root.appendChild(tabPaket);
    root.appendChild(tabLanding);
    root.appendChild(tabPgw);
    root.appendChild(tabTransaksi);
    root.appendChild(tabSettlement);
    root.appendChild(tabWaBot);
    root.appendChild(tabSales);
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

    const trxSubLangganan = MugenUI.el("div");
    const trxSubBooking = MugenUI.el("div", { style: "display:none;" });
    const trxSubPanelByKey = { langganan: trxSubLangganan, booking: trxSubBooking };
    const trxSubTabsCtl = MugenUI.tabs(
      [
        { key: "langganan", label: "Riwayat Langganan Tenant" },
        { key: "booking", label: "Riwayat Booking Tenant" },
      ],
      { onChange: (key) => { for (const k in trxSubPanelByKey) trxSubPanelByKey[k].style.display = k === key ? "" : "none"; } },
    );
    tabTransaksi.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:8px;" },
      "Dua ledger terpisah -- langganan SaaS tenant KE Rivoir, dan booking customer KE tenant. Keduanya TIDAK PERNAH digabung jadi satu daftar."));
    tabTransaksi.appendChild(trxSubTabsCtl.bar);
    tabTransaksi.appendChild(trxSubLangganan);
    tabTransaksi.appendChild(trxSubBooking);
    trxSubLangganan.appendChild(langgananSummaryCard);
    trxSubLangganan.appendChild(langgananCard);
    trxSubBooking.appendChild(bookingSummaryCard);
    trxSubBooking.appendChild(bookingCard);

    tabSettlement.appendChild(settlementCard);

    tabWaBot.appendChild(waBotCard);
    tabWaBot.appendChild(waBotEditCard);
    tabSales.appendChild(salesCard);
    tabSales.appendChild(salesLifetimeCard);
    tabSales.appendChild(salesKomisiCard);

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
      "Durasi default (hari) dipakai saat Trial BARU diatur ke tenant mana pun tanpa mengisi jumlah hari secara eksplisit."));
    const inputTrialHari = MugenUI.el("input", { type: "number", min: "1" });
    const btnSimpanConfig = MugenUI.el("button", { class: "btn-primary" }, "Simpan Konfigurasi");
    const configError = MugenUI.el("div", { class: "login-error" });
    subsConfigCard.appendChild(MugenUI.el("label", {}, "Durasi Trial Default (hari)"));
    subsConfigCard.appendChild(inputTrialHari);
    subsConfigCard.appendChild(configError);
    subsConfigCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanConfig));

    async function loadSubsConfig() {
      try {
        const cfg = await MugenApi.get("/api/superadmin/subscriptions/config");
        inputTrialHari.value = cfg.trial_hari;
      } catch (e) { configError.textContent = e.message; }
    }
    btnSimpanConfig.addEventListener("click", async () => {
      configError.textContent = "";
      try {
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        await MugenUI.withButtonLoading(btnSimpanConfig, () => MugenApi.put("/api/superadmin/subscriptions/config", {
          trial_hari: parseInt(inputTrialHari.value, 10) || null,
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

      // --- Reset Subscription (Perbaikan Billing/Subscription, requirement
      // Owner poin 3-6, 14, 15) --- koreksi package/periode/status SATU
      // tenant TANPA menyentuh invoice/pembayaran sama sekali (lihat
      // routers/subscription.py::reset_subscription()) -- TAMBAHAN di
      // samping kontrol Package/Status di atas, BUKAN pengganti.
      subsManagerBody.appendChild(MugenUI.el("div", { style: "margin-top:16px;padding-top:12px;border-top:1px solid var(--border);" }, [
        MugenUI.el("div", { class: "subtitle" }, `Paket Saat Ini: ${LABEL_PACKAGE_SUBS[sub.package] || sub.package}`),
        MugenUI.el("div", { class: "subtitle" },
          `Tanggal Aktif Sampai Saat Ini: ${sub.periode_selesai ? formatWaktu(sub.periode_selesai) : "-"}`),
      ]));
      const btnResetSubs = MugenUI.el("button", { type: "button", style: "margin-top:8px;" }, "↻ Reset Subscription");
      subsManagerBody.appendChild(btnResetSubs);
      btnResetSubs.addEventListener("click", () => bukaModalResetSubscription(tenant, sub));

      // --- Trial --- (REVISI, diminta Owner: Grace Period manual dihapus
      // total dari sini -- lihat subscription_db.py untuk penggantinya,
      // peringatan H-7 otomatis sebelum periode_selesai.)
      const infoTrial = sub.trial_start ? `${formatWaktu(sub.trial_start)} s/d ${formatWaktu(sub.trial_end)}` : "belum diatur";
      const inputTrialHariTenant = MugenUI.el("input", { type: "number", min: "1", placeholder: "hari" });
      const btnSetTrial = MugenUI.el("button", {}, "Set Trial (mulai sekarang)");
      const errTrial = MugenUI.el("div", { class: "login-error" });

      subsManagerBody.appendChild(MugenUI.el("div", { style: "margin-top:16px;" }, [
        MugenUI.el("div", { class: "subtitle" }, `Masa Trial saat ini: ${infoTrial}`),
        MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:8px;align-items:flex-end;margin-top:4px;" }, [inputTrialHariTenant, btnSetTrial]),
      ]));
      subsManagerBody.appendChild(errTrial);

      btnSetTrial.addEventListener("click", async () => {
        errTrial.textContent = "";
        try {
          await MugenUI.withButtonLoading(btnSetTrial, () => MugenApi.put(`/api/superadmin/subscriptions/${tenant.id}/trial`,
            { hari: inputTrialHariTenant.value ? parseInt(inputTrialHariTenant.value, 10) : null }));
          MugenUI.toast("Trial disimpan.", "success", { force: true });
          loadAuditLog(); renderSubscriptionManager(tenant);
        } catch (e) { errTrial.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
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

      // --- Payment Settings (PENGECUALIAN SENGAJA -- lihat komentar
      // "PENGECUALIAN SENGAJA" di routers/superadmin.py: SATU-SATUNYA
      // endpoint di modul Super Admin yang membaca/mengubah data bisnis
      // tenant, karena PERMINTAAN OWNER seluruh konfigurasi metode
      // pembayaran (termasuk upload foto QRIS) sekarang dikelola PENUH
      // oleh Super Admin per tenant, bukan lagi Owner sendiri.) ---
      subsManagerBody.appendChild(MugenUI.el("h3", { style: "margin-top:20px;" }, "Payment Settings"));
      const paymentSettingsBody = MugenUI.el("div");
      subsManagerBody.appendChild(paymentSettingsBody);

      const METODE_LABEL_PS = { qris: "QRIS (Foto Manual)", gateway: "Payment Gateway", cash: "Cash (Bayar di Toko)" };

      async function loadPaymentSettings() {
        paymentSettingsBody.innerHTML = "";
        paymentSettingsBody.appendChild(MugenUI.skeleton("card", { lines: 3 }));
        let ps;
        try {
          ps = await MugenApi.get(`/api/superadmin/tenants/${tenant.id}/payment-settings`);
        } catch (e) {
          paymentSettingsBody.innerHTML = "";
          paymentSettingsBody.appendChild(MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message));
          return;
        }
        paymentSettingsBody.innerHTML = "";

        const checkboxes = {};
        const metodeBox = MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;" });
        for (const m of Object.keys(METODE_LABEL_PS)) {
          const cb = MugenUI.el("input", { type: "checkbox" });
          cb.checked = ps.metode_aktif.includes(m);
          checkboxes[m] = cb;
          metodeBox.appendChild(MugenUI.el("label", { style: "display:flex;align-items:center;gap:6px;" }, [cb, METODE_LABEL_PS[m]]));
        }
        paymentSettingsBody.appendChild(MugenUI.el("div", {}, [MugenUI.el("label", {}, "Metode Aktif"), metodeBox]));

        const inputMerchantNama = MugenUI.el("input", { type: "text", value: ps.qris_merchant_nama || "", placeholder: "Nama merchant di QRIS" });
        paymentSettingsBody.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, [
          MugenUI.el("label", {}, "Nama Merchant QRIS"), inputMerchantNama,
        ]));

        const labelInputs = {}, instruksiInputs = {};
        for (const m of Object.keys(METODE_LABEL_PS)) {
          const inpLabel = MugenUI.el("input", { type: "text", value: ps.metode_nama[m] || "" });
          const inpInstruksi = MugenUI.el("textarea", { rows: "2" }, ps.metode_instruksi[m] || "");
          labelInputs[m] = inpLabel; instruksiInputs[m] = inpInstruksi;
          paymentSettingsBody.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, [
            MugenUI.el("label", {}, `Label "${METODE_LABEL_PS[m]}"`), inpLabel,
            MugenUI.el("label", { style: "margin-top:6px;" }, "Instruksi"), inpInstruksi,
          ]));
        }

        const errSimpanPs = MugenUI.el("div", { class: "login-error" });
        paymentSettingsBody.appendChild(errSimpanPs);
        const btnSimpanPs = MugenUI.el("button", { type: "button", class: "btn-primary", style: "margin-top:12px;" }, "Simpan Payment Settings");
        paymentSettingsBody.appendChild(btnSimpanPs);
        btnSimpanPs.addEventListener("click", async () => {
          errSimpanPs.textContent = "";
          try {
            await MugenUI.withButtonLoading(btnSimpanPs, () => MugenApi.put(`/api/superadmin/tenants/${tenant.id}/payment-settings`, {
              metode_aktif: Object.keys(checkboxes).filter((m) => checkboxes[m].checked),
              qris_merchant_nama: inputMerchantNama.value.trim(),
              metode_nama: Object.fromEntries(Object.keys(labelInputs).map((m) => [m, labelInputs[m].value])),
              metode_instruksi: Object.fromEntries(Object.keys(instruksiInputs).map((m) => [m, instruksiInputs[m].value])),
            }));
            MugenUI.toast("Payment Settings disimpan.", "success", { force: true });
            loadAuditLog(); loadPaymentSettings();
          } catch (e) { errSimpanPs.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
        });

        // --- Foto QRIS (slot tunggal per tenant, pola sama seperti logo) ---
        paymentSettingsBody.appendChild(MugenUI.el("div", { style: "margin-top:20px;padding-top:12px;border-top:1px solid var(--border);" }, [
          MugenUI.el("label", {}, "Foto QRIS"),
        ]));
        if (ps.qris_url) {
          paymentSettingsBody.appendChild(MugenUI.el("img", {
            src: MUGEN_API_BASE + ps.qris_url, style: "max-width:220px;display:block;margin-top:8px;border-radius:8px;",
          }));
          const btnHapusQris = MugenUI.el("button", { type: "button", style: "margin-top:8px;" }, "Hapus Foto QRIS");
          paymentSettingsBody.appendChild(btnHapusQris);
          btnHapusQris.addEventListener("click", async () => {
            if (!confirm("Hapus foto QRIS tenant ini?")) return;
            try {
              await MugenUI.withButtonLoading(btnHapusQris, () => MugenApi.del(`/api/superadmin/tenants/${tenant.id}/qris-foto`));
              MugenUI.toast("Foto QRIS dihapus.", "success");
              loadAuditLog(); loadPaymentSettings();
            } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
          });
        } else {
          paymentSettingsBody.appendChild(MugenUI.el("div", { class: "subtitle" }, "Belum ada foto QRIS untuk tenant ini."));
        }
        const inputFileQris = MugenUI.el("input", { type: "file", accept: "image/png,image/jpeg,image/webp", style: "margin-top:10px;display:block;" });
        const btnUploadQris = MugenUI.el("button", { type: "button", style: "margin-top:8px;" }, "Upload Foto QRIS");
        const errQris = MugenUI.el("div", { class: "login-error" });
        paymentSettingsBody.appendChild(inputFileQris);
        paymentSettingsBody.appendChild(btnUploadQris);
        paymentSettingsBody.appendChild(errQris);
        btnUploadQris.addEventListener("click", async () => {
          errQris.textContent = "";
          if (!inputFileQris.files[0]) { errQris.textContent = "Pilih file foto QRIS terlebih dahulu."; return; }
          try {
            await MugenUI.withButtonLoading(btnUploadQris,
              () => MugenApi.uploadFile(`/api/superadmin/tenants/${tenant.id}/qris-foto`, inputFileQris.files[0]));
            MugenUI.toast("Foto QRIS diunggah.", "success", { force: true });
            loadAuditLog(); loadPaymentSettings();
          } catch (e) { errQris.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
        });
      }

      await loadPaymentSettings();
    }

    // Perbaikan Billing/Subscription (requirement Owner poin 3-6, 15): modal
    // custom (pola SAMA PERSIS pages/billing.js::pilihChannelModal(), BUKAN
    // MugenUI.confirmModal() -- modal itu cuma satu tombol ya/tidak, di sini
    // butuh 4 field yang bisa diedit) untuk field Paket/Tanggal Mulai/
    // Tanggal Aktif Sampai/Status, LALU MugenUI.confirmModal() sebagai
    // langkah konfirmasi kedua yang menampilkan before->after (requirement
    // poin 4) sebelum benar-benar memanggil endpoint reset.
    function bukaModalResetSubscription(tenant, sub) {
      const overlay = MugenUI.el("div", { class: "modal-overlay" });
      const box = MugenUI.el("div", { class: "modal-box" });
      box.appendChild(MugenUI.el("h3", {}, "Reset Subscription"));
      box.appendChild(MugenUI.el("div", { class: "subtitle" }, tenant.nama_barbershop));

      const selPackage = MugenUI.el("select");
      for (const k of Object.keys(LABEL_PACKAGE_SUBS)) selPackage.appendChild(MugenUI.el("option", { value: k }, LABEL_PACKAGE_SUBS[k]));
      selPackage.value = sub.package;

      const inputMulai = MugenUI.el("input", { type: "date" });
      inputMulai.value = sub.periode_mulai ? sub.periode_mulai.split("T")[0] : "";
      const inputSelesai = MugenUI.el("input", { type: "date" });
      inputSelesai.value = sub.periode_selesai ? sub.periode_selesai.split("T")[0] : "";

      const selStatus = MugenUI.el("select");
      for (const k of Object.keys(LABEL_STATUS_SUBS)) selStatus.appendChild(MugenUI.el("option", { value: k }, LABEL_STATUS_SUBS[k]));
      selStatus.value = sub.status;

      box.appendChild(MugenUI.el("div", { style: "text-align:left;margin-top:12px;display:flex;flex-direction:column;gap:10px;" }, [
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Paket"), selPackage]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Tanggal Mulai"), inputMulai]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Tanggal Aktif Sampai"), inputSelesai]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Status"), selStatus]),
      ]));

      const errReset = MugenUI.el("div", { class: "login-error" });
      box.appendChild(errReset);

      const btnBatal = MugenUI.el("button", { type: "button" }, "Batal");
      const btnLanjut = MugenUI.el("button", { type: "button", class: "btn-primary" }, "Reset Subscription");
      box.appendChild(MugenUI.el("div", { class: "modal-actions", style: "margin-top:14px;" }, [btnBatal, btnLanjut]));
      overlay.appendChild(box);

      function tutup() {
        overlay.classList.add("closing");
        setTimeout(() => overlay.remove(), 120);
      }
      btnBatal.addEventListener("click", tutup);
      overlay.addEventListener("click", (e) => { if (e.target === overlay) tutup(); });

      btnLanjut.addEventListener("click", async () => {
        errReset.textContent = "";
        if (!inputMulai.value || !inputSelesai.value) {
          errReset.textContent = "Tanggal Mulai dan Tanggal Aktif Sampai wajib diisi.";
          return;
        }
        const labelSebelum = {
          package: LABEL_PACKAGE_SUBS[sub.package] || sub.package,
          periode: sub.periode_selesai ? formatWaktu(sub.periode_selesai) : "-",
          status: LABEL_STATUS_SUBS[sub.status] || sub.status,
        };
        const labelSesudah = {
          package: LABEL_PACKAGE_SUBS[selPackage.value] || selPackage.value,
          periode: formatWaktu(`${inputSelesai.value}T23:59:59`),
          status: LABEL_STATUS_SUBS[selStatus.value] || selStatus.value,
        };
        tutup();
        const ok = await MugenUI.confirmModal({
          title: "Konfirmasi Reset Subscription",
          message: [
            `Paket: ${labelSebelum.package} -> ${labelSesudah.package}`,
            `Tanggal Aktif Sampai: ${labelSebelum.periode} -> ${labelSesudah.periode}`,
            `Status: ${labelSebelum.status} -> ${labelSesudah.status}`,
            "Riwayat pembayaran & invoice TIDAK akan terhapus.",
          ],
          confirmText: "Reset Subscription",
          danger: true,
        });
        if (!ok) return;
        try {
          await MugenApi.put(`/api/superadmin/subscriptions/${tenant.id}/reset`, {
            package: selPackage.value,
            tanggal_mulai: inputMulai.value,
            tanggal_selesai: inputSelesai.value,
            status: selStatus.value,
          });
          MugenUI.toast("Subscription berhasil direset.", "success", { force: true });
          loadTenantList(); loadAuditLog(); renderSubscriptionManager(tenant);
        } catch (e) {
          MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
        }
      });

      document.body.appendChild(overlay);
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
      let fiturTertandai, permissionTree, paketPermissions;
      try {
        [_katalogFiturCache, fiturTertandai, permissionTree, paketPermissions] = await Promise.all([
          MugenApi.get("/api/superadmin/billing/features"),
          MugenApi.get(`/api/superadmin/billing/packages/${paket.id}/features`),
          _muatPermissionTreeSuperadmin(),
          MugenApi.get(`/api/superadmin/billing/packages/${paket.id}/permissions`),
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
      // FITUR Program Afiliasi Sales/Marketing -- Lisensi Lifetime (Beli
      // Putus): nominal katalog per paket, diisi otomatis ke form "Buat
      // Transaksi Lifetime" di tab Sales & Referral (lihat salesLifetimeCard
      // di bawah) -- kosongkan kalau paket ini tidak dijual Lifetime.
      const inputHargaLifetime = MugenUI.el("input", {
        type: "number", min: "0", placeholder: "tidak dijual Lifetime",
        value: paket.harga_lifetime !== null && paket.harga_lifetime !== undefined ? String(paket.harga_lifetime) : "",
      });

      billingPackageEditBody.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;" }, [
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Nama"), inputNama]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Harga (Rp)"), inputHarga]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Durasi (hari)"), inputDurasi]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Urutan"), inputUrutan]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Harga Lifetime (Rp)"), inputHargaLifetime]),
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

      // --- Package Permission Tree (Work #2, diminta Owner): POHON MENU
      // YANG SAMA PERSIS dipakai Role Owner tenant, menentukan menu/tab/
      // sub-item APA SAJA yang tersedia SAMA SEKALI untuk tenant paket ini
      // -- BATAS LUAR, di LUAR (sebelum) checklist Role di dalam tenant. ---
      billingPackageEditBody.appendChild(MugenUI.el("h3", { style: "margin-top:16px;" }, "Menu & Fitur (Package Permission Tree)"));
      billingPackageEditBody.appendChild(MugenUI.el("div", { class: "subtitle" },
        "Centang menu/tab/sub-item yang TERSEDIA untuk tenant paket ini -- Role staff di dalam satu tenant hanya bisa memakai apa yang sudah dicentang di sini."));
      const permTreeContainer = MugenUI.el("div", { class: "perm-tree" });
      billingPackageEditBody.appendChild(permTreeContainer);
      const permCheckboxes = buildPermissionTreeUI(permTreeContainer, permissionTree, paketPermissions);

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
          harga_lifetime: inputHargaLifetime.value === "" ? null : parseInt(inputHargaLifetime.value, 10),
        };
        for (const [key] of LIMIT_FIELDS) {
          const v = inputLimit[key].value;
          body[key] = v === "" ? null : parseInt(v, 10);
        }
        const featureIds = checkboxFitur.filter((cb) => cb.checked).map((cb) => parseInt(cb.dataset.featureId, 10));
        const izinPaket = {};
        for (const [key, cb] of Object.entries(permCheckboxes)) izinPaket[key] = cb.checked;
        try {
          await MugenUI.withButtonLoading(btnSimpan, async () => {
            await MugenApi.put(`/api/superadmin/billing/packages/${paket.id}`, body);
            await MugenApi.put(`/api/superadmin/billing/packages/${paket.id}/features`, { feature_ids: featureIds });
            await MugenApi.put(`/api/superadmin/billing/packages/${paket.id}/permissions`, { izin: izinPaket });
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
    // SNAP SEKARANG SUDAH di-wire lewat payment_provider_client.py (seam
    // dinamis) ke checkout booking (metode "gateway", channel VA/QRIS) DAN
    // billing SaaS -- mengisi/mengubah kredensial di sini LANGSUNG
    // memengaruhi checkout yang sedang berjalan (bukan lagi sekadar
    // persiapan), lihat routers/booking.py::public_buat_booking()/
    // routers/billing.py::checkout(). Xpress v4 TETAP ada, tidak dipanggil
    // lagi dari checkout mana pun, hanya untuk transaksi lama yang masih
    // berjalan lewatnya.
    // ---------------------------------------------------------------
    snapAdvanceCard.appendChild(MugenUI.el("h2", {}, "Faspay SNAP Advance"));
    snapAdvanceCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Provider AKTIF untuk checkout booking (metode Payment Gateway) & billing SaaS -- MENGGANTIKAN Payment Gateway (Xpress v4) di atas. VA & QRIS sudah diimplementasikan sesuai dokumen resmi Faspay & LANGSUNG dipakai customer/Owner begitu channel-nya dicentang aktif di bawah. Direct Debit & Registrasi/Account Binding-nya MASIH PENDING FASPAY -- belum bisa dipilih customer sama sekali sampai dikonfirmasi."));

    const inSnapEnv = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "sandbox" }, "Sandbox"),
      MugenUI.el("option", { value: "production" }, "Production"),
    ]);
    const inSnapSandboxUrl = MugenUI.el("input", { type: "text", placeholder: "mis. https://debit-sandbox.faspay.co.id" });
    const inSnapProductionUrl = MugenUI.el("input", { type: "text", placeholder: "PENDING FASPAY -- domain production belum dikonfirmasi" });
    const inSnapMerchantId = MugenUI.el("input", { type: "text" });
    const inSnapPartnerId = MugenUI.el("input", { type: "text" });
    const inSnapClientId = MugenUI.el("input", { type: "text" });
    // Kredensial di bawah SENGAJA terpisah sandbox/production (Faspay
    // menerbitkan keypair BERBEDA per environment) -- Merchant/Partner/
    // Channel ID di atas TETAP satu field (Faspay mengonfirmasi ID yang
    // sama dipakai kedua environment, cuma domain yang beda).
    const inSnapSandboxClientSecret = MugenUI.el("input", { type: "password", autocomplete: "off" });
    const inSnapSandboxPrivateKey = MugenUI.el("textarea", { rows: "4", placeholder: "-----BEGIN PRIVATE KEY-----" });
    const inSnapSandboxPublicKey = MugenUI.el("textarea", { rows: "4", placeholder: "-----BEGIN PUBLIC KEY----- (public key Faspay sandbox, untuk verifikasi webhook)" });
    const inSnapSandboxWebhookSecret = MugenUI.el("input", { type: "password", autocomplete: "off" });
    const inSnapProductionClientSecret = MugenUI.el("input", { type: "password", autocomplete: "off" });
    const inSnapProductionPrivateKey = MugenUI.el("textarea", { rows: "4", placeholder: "-----BEGIN PRIVATE KEY-----" });
    const inSnapProductionPublicKey = MugenUI.el("textarea", { rows: "4", placeholder: "-----BEGIN PUBLIC KEY----- (public key Faspay production, untuk verifikasi webhook)" });
    const inSnapProductionWebhookSecret = MugenUI.el("input", { type: "password", autocomplete: "off" });
    const inSnapChannelId = MugenUI.el("input", { type: "text", placeholder: "mis. 77001" });
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
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Client ID (opsional -- TIDAK dipakai signature Create VA/QRIS/Direct Debit, klarifikasi resmi Faspay)"));
    snapAdvanceCard.appendChild(inSnapClientId);
    snapAdvanceCard.appendChild(MugenUI.el("h3", { style: "margin-top:16px;" }, "Kredensial Sandbox"));
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Client Secret (opsional -- TIDAK dipakai signature Create VA/QRIS/Direct Debit, klarifikasi resmi Faspay)"));
    snapAdvanceCard.appendChild(inSnapSandboxClientSecret);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Private Key (RSA, milik merchant -- untuk menandatangani permintaan)"));
    snapAdvanceCard.appendChild(inSnapSandboxPrivateKey);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Public Key Faspay (untuk memverifikasi webhook masuk)"));
    snapAdvanceCard.appendChild(inSnapSandboxPublicKey);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Webhook Secret (kalau ada)"));
    snapAdvanceCard.appendChild(inSnapSandboxWebhookSecret);

    snapAdvanceCard.appendChild(MugenUI.el("h3", { style: "margin-top:16px;" }, "Kredensial Production"));
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Client Secret (opsional -- TIDAK dipakai signature Create VA/QRIS/Direct Debit, klarifikasi resmi Faspay)"));
    snapAdvanceCard.appendChild(inSnapProductionClientSecret);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Private Key (RSA, milik merchant -- untuk menandatangani permintaan)"));
    snapAdvanceCard.appendChild(inSnapProductionPrivateKey);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Public Key Faspay (untuk memverifikasi webhook masuk)"));
    snapAdvanceCard.appendChild(inSnapProductionPublicKey);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Webhook Secret (kalau ada)"));
    snapAdvanceCard.appendChild(inSnapProductionWebhookSecret);

    snapAdvanceCard.appendChild(MugenUI.el("label", { style: "margin-top:16px;" }, "CHANNEL-ID (identifier layanan API Faspay, BUKAN kode bank -- diberikan Faspay, mis. 77001)"));
    snapAdvanceCard.appendChild(inSnapChannelId);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Bank VA Aktif (customer memilih salah satu saat checkout)"));
    const snapVaBankList = MugenUI.el("div", { style: "display:flex;flex-direction:column;gap:6px;margin:8px 0;" });
    snapAdvanceCard.appendChild(snapVaBankList);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "E-Wallet QRIS Default (channelCode Generate QRIS)"));
    snapAdvanceCard.appendChild(inSnapQrisChannelCode);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Timeout (detik)"));
    snapAdvanceCard.appendChild(inSnapTimeout);
    snapAdvanceCard.appendChild(MugenUI.el("label", {}, "Retry Max"));
    snapAdvanceCard.appendChild(inSnapRetryMax);
    snapAdvanceCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:4px;" },
      `URL Payment Notification SNAP Advance (TIGA path terpisah, satu per produk -- sesuai klarifikasi resmi Faspay, BUKAN lagi satu URL gabungan): VA ${MUGEN_API_BASE}/v1.0/transfer-va/payment -- QRIS ${MUGEN_API_BASE}/v1.0/qr/qr-mpm-notify -- Direct Debit ${MUGEN_API_BASE}/v1.0/debit/notify`));

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

    // Fitur multi-bank VA: GANTI dropdown single-select "Bank VA Default"
    // lama -- customer sekarang bisa pilih bank APA PUN yang dicentang aktif
    // di sini (lihat payment_provider_client.py::va_bank_aktif()), bukan
    // cuma satu default platform-wide. Pola render SAMA PERSIS
    // renderSnapChannelList() di atas.
    let snapVaBankLabel = {};
    const snapVaBankCheckbox = {};

    function renderSnapVaBankList() {
      snapVaBankList.innerHTML = "";
      for (const key of Object.keys(snapVaBankLabel)) {
        const sudahAda = snapVaBankCheckbox[key];
        const cb = MugenUI.el("input", { type: "checkbox" });
        cb.checked = sudahAda ? sudahAda.checked : false;
        snapVaBankCheckbox[key] = cb;
        snapVaBankList.appendChild(MugenUI.el("div", { style: "display:flex;align-items:center;gap:10px;" }, [
          cb, MugenUI.bankLogoBadge(key, "sm"), MugenUI.el("span", {}, MugenUI.bankNamaLengkap(key, snapVaBankLabel[key])),
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
        inSnapSandboxClientSecret.value = "";
        inSnapSandboxClientSecret.placeholder = cfg.snap_sandbox_client_secret_terisi ? "(sudah diisi -- kosongkan supaya tidak berubah)" : "";
        inSnapSandboxPrivateKey.value = "";
        inSnapSandboxPrivateKey.placeholder = cfg.snap_sandbox_private_key_terisi
          ? "(sudah diisi -- kosongkan supaya tidak berubah)" : "-----BEGIN PRIVATE KEY-----";
        inSnapSandboxPublicKey.value = cfg.snap_sandbox_faspay_public_key || "";
        inSnapSandboxWebhookSecret.value = "";
        inSnapSandboxWebhookSecret.placeholder = cfg.snap_sandbox_webhook_secret_terisi ? "(sudah diisi -- kosongkan supaya tidak berubah)" : "";
        inSnapProductionClientSecret.value = "";
        inSnapProductionClientSecret.placeholder = cfg.snap_production_client_secret_terisi ? "(sudah diisi -- kosongkan supaya tidak berubah)" : "";
        inSnapProductionPrivateKey.value = "";
        inSnapProductionPrivateKey.placeholder = cfg.snap_production_private_key_terisi
          ? "(sudah diisi -- kosongkan supaya tidak berubah)" : "-----BEGIN PRIVATE KEY-----";
        inSnapProductionPublicKey.value = cfg.snap_production_faspay_public_key || "";
        inSnapProductionWebhookSecret.value = "";
        inSnapProductionWebhookSecret.placeholder = cfg.snap_production_webhook_secret_terisi ? "(sudah diisi -- kosongkan supaya tidak berubah)" : "";
        inSnapChannelId.value = cfg.snap_channel_id || "";
        inSnapTimeout.value = cfg.snap_timeout_detik || 30;
        inSnapRetryMax.value = cfg.snap_retry_max || 3;
        snapChannelLabel = cfg.channel_label || {};
        renderSnapChannelList();
        snapVaBankLabel = cfg.va_channel_code_label || {};
        renderSnapVaBankList();
        for (const key of (cfg.snap_va_bank_aktif || [])) if (snapVaBankCheckbox[key]) snapVaBankCheckbox[key].checked = true;
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
      const va_bank_aktif = Object.keys(snapVaBankCheckbox).filter((key) => snapVaBankCheckbox[key].checked);
      try {
        await MugenUI.withButtonLoading(btnSimpanSnap, () => MugenApi.put("/api/superadmin/snap-advance/config", {
          environment: inSnapEnv.value, sandbox_base_url: inSnapSandboxUrl.value,
          production_base_url: inSnapProductionUrl.value, merchant_id: inSnapMerchantId.value,
          partner_id: inSnapPartnerId.value, client_id: inSnapClientId.value,
          sandbox_client_secret: inSnapSandboxClientSecret.value, production_client_secret: inSnapProductionClientSecret.value,
          sandbox_private_key: inSnapSandboxPrivateKey.value, production_private_key: inSnapProductionPrivateKey.value,
          sandbox_faspay_public_key: inSnapSandboxPublicKey.value, production_faspay_public_key: inSnapProductionPublicKey.value,
          sandbox_webhook_secret: inSnapSandboxWebhookSecret.value, production_webhook_secret: inSnapProductionWebhookSecret.value,
          timeout_detik: Number(inSnapTimeout.value) || 30,
          retry_max: Number(inSnapRetryMax.value) || 0, channel_aktif,
          channel_id: inSnapChannelId.value, va_bank_aktif,
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
    // Transaksi Multi-Tenant, restrukturisasi ledger Agustus 2026) -- pusat
    // monitoring transaksi pembayaran platform, murni MEMBACA lewat
    // transaction_report_db.py (require_superadmin, lihat routers/
    // transaction_report.py). Status pembayaran yang tampil di sini TIDAK
    // PERNAH bisa diubah dari layar ini -- HANYA berubah lewat webhook
    // resmi provider (billing_webhook.py/booking_gateway_webhook.py).
    //
    // DUA LEDGER TERPISAH, `jenis` DIKUNCI per bagian (bukan dropdown) --
    // bikinBagianRiwayat() di bawah dipanggil DUA KALI dengan jenisTetap
    // berbeda, masing-masing punya filter/summary/tabel/export SENDIRI,
    // TIDAK PERNAH memanggil endpoint tanpa `jenis` (yang akan
    // menggabungkan keduanya).
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

    function trxStatusBadge(status) {
      return MugenUI.el("span", { class: "badge" + (TRX_STATUS_BADGE[status] ? " " + TRX_STATUS_BADGE[status] : "") },
        TRX_STATUS_LABEL[status] || status);
    }

    function trxWaktuLengkap(iso) {
      if (!iso) return "-";
      const [tanggal, jam] = iso.split("T");
      return `${MugenUI.formatTanggal(tanggal)} ${(jam || "").slice(0, 8)}`.trim();
    }

    function trxPeriodeLengkap(mulai, selesai) {
      // periode_mulai/periode_selesai tersimpan sebagai ISO datetime PENUH
      // (lihat billing_webhook.py) -- MugenUI.formatTanggal() cuma pecah
      // "-" (untuk "YYYY-MM-DD" polos), jadi WAJIB buang bagian jam dulu
      // (pola sama seperti formatWaktu() di atas), atau hasilnya kacau.
      if (!mulai && !selesai) return "-";
      const tglSaja = (iso) => (iso ? MugenUI.formatTanggal(iso.split("T")[0]) : "-");
      return `${tglSaja(mulai)} s/d ${tglSaja(selesai)}`;
    }

    async function trxLihatDetail(ringkas) {
      try {
        const detail = await MugenApi.get(`/api/superadmin/transactions/${ringkas.jenis}/${ringkas.id}`);
        const body = [
          MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-bottom:10px;" }, [
            MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Status"), trxStatusBadge(detail.status_unified)]),
            MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Jenis Transaksi"), MugenUI.el("div", {}, detail.jenis_transaksi || "-")]),
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
            MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Periode"), MugenUI.el("div", {}, trxPeriodeLengkap(detail.periode_mulai, detail.periode_selesai))]),
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

    // Factory dipanggil dua kali (langganan & booking) di bawah -- SATU
    // ledger per panggilan, `jenisTetap` SELALU dikirim ke endpoint,
    // TIDAK PERNAH lewat form/dropdown yang bisa diganti pengguna.
    function bikinBagianRiwayat({ jenisTetap, judul, deskripsi, summaryCard, listCard, kolomTabel, namaFileCsv, idKolomLabel }) {
      const summaryBody = MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-top:12px;" });
      summaryCard.appendChild(MugenUI.el("h2", {}, `${judul} -- Ringkasan`));
      summaryCard.appendChild(summaryBody);
      const perTenantBody = MugenUI.el("div", { style: "margin-top:16px;" });
      summaryCard.appendChild(perTenantBody);

      listCard.appendChild(MugenUI.el("h2", {}, judul));
      listCard.appendChild(MugenUI.el("div", { class: "subtitle" }, deskripsi));

      const selTenant = MugenUI.el("select");
      selTenant.appendChild(MugenUI.el("option", { value: "" }, "Semua Toko"));
      const inputMulai = MugenUI.el("input", { type: "date" });
      const inputSelesai = MugenUI.el("input", { type: "date" });
      const selStatus = MugenUI.el("select");
      selStatus.appendChild(MugenUI.el("option", { value: "" }, "Semua Status"));
      for (const [k, label] of Object.entries(TRX_STATUS_LABEL)) selStatus.appendChild(MugenUI.el("option", { value: k }, label));
      const inputMetode = MugenUI.el("input", { type: "text", placeholder: "mis. gateway, transfer, qris" });
      const inputCari = MugenUI.el("input", { type: "text", placeholder: `Cari ${idKolomLabel}/toko/nomor transaksi` });
      const btnFilter = MugenUI.el("button", { class: "btn-primary" }, "Terapkan Filter");
      const btnExport = MugenUI.el("button", {}, "Export CSV");

      listCard.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:8px;align-items:flex-end;" }, [
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Toko"), selTenant]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Dari Tanggal"), inputMulai]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Sampai Tanggal"), inputSelesai]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Status"), selStatus]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Metode Pembayaran"), inputMetode]),
        MugenUI.el("div", { style: "flex:1;min-width:240px;" }, [MugenUI.el("label", {}, "Cari"), inputCari]),
        btnFilter,
        btnExport,
      ]));

      const listBody = MugenUI.el("div", { style: "margin-top:12px;" });
      listCard.appendChild(listBody);

      function queryString() {
        const params = new URLSearchParams();
        params.set("jenis", jenisTetap);
        if (selTenant.value) params.set("tenant_id", selTenant.value);
        if (inputMulai.value) params.set("tanggal_mulai", inputMulai.value);
        if (inputSelesai.value) params.set("tanggal_selesai", inputSelesai.value + "T23:59:59");
        if (selStatus.value) params.set("status", selStatus.value);
        if (inputMetode.value.trim()) params.set("metode_pembayaran", inputMetode.value.trim());
        if (inputCari.value.trim()) params.set("cari", inputCari.value.trim());
        return params.toString();
      }

      async function load() {
        selTenant.innerHTML = "";
        selTenant.appendChild(MugenUI.el("option", { value: "" }, "Semua Toko"));
        for (const t of tenantList) selTenant.appendChild(MugenUI.el("option", { value: String(t.id) }, t.nama_barbershop));

        summaryBody.innerHTML = "";
        summaryBody.appendChild(MugenUI.skeleton("card", { lines: 2 }));
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.skeleton("table", { cols: 8, rows: 4 }));
        try {
          const hasil = await MugenApi.get(`/api/superadmin/transactions?${queryString()}`);
          const { transactions, summary } = hasil;

          summaryBody.innerHTML = "";
          summaryBody.appendChild(statTile("Total Transaksi", summary.total_transaksi));
          summaryBody.appendChild(statTile("Berhasil", summary.total_berhasil));
          summaryBody.appendChild(statTile("Pending", summary.total_pending));
          summaryBody.appendChild(statTile("Gagal", summary.total_gagal));
          summaryBody.appendChild(statTile("Dibatalkan", summary.total_dibatalkan));
          summaryBody.appendChild(statTile("Total Nominal (Berhasil)", MugenUI.formatRupiah(summary.total_nilai)));

          perTenantBody.innerHTML = "";
          perTenantBody.appendChild(MugenUI.el("h3", {}, "Per Toko (sesuai filter)"));
          perTenantBody.appendChild(MugenUI.buildTable(
            [
              { key: "tenant_nama", label: "Toko" },
              { key: "jumlah_transaksi", label: "Jumlah Transaksi" },
              { key: "omzet", label: "Total Nominal (Berhasil)", format: MugenUI.formatRupiah },
            ],
            summary.per_tenant || [],
            { emptyText: "Belum ada transaksi sesuai filter." },
          ));

          listBody.innerHTML = "";
          listBody.appendChild(MugenUI.buildTable(kolomTabel(trxLihatDetail), transactions,
            { emptyText: "Belum ada transaksi sesuai filter." }));
        } catch (e) {
          summaryBody.innerHTML = "";
          summaryBody.appendChild(MugenUI.errorState(e.message));
          listBody.innerHTML = "";
          listBody.appendChild(MugenUI.errorState(e.message));
        }
      }
      btnFilter.addEventListener("click", load);
      btnExport.addEventListener("click", async () => {
        try {
          await MugenUI.withButtonLoading(btnExport, () => MugenApi.downloadFile(`/api/superadmin/transactions/export?${queryString()}`, namaFileCsv));
        } catch (e) {
          MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
        }
      });
      return { load };
    }

    function kolomAksiDetail(lihatDetail) {
      return {
        key: "aksi", label: "Aksi", format: (_, r) => {
          const btn = MugenUI.el("button", {}, "Detail");
          btn.addEventListener("click", () => lihatDetail(r));
          return btn;
        },
      };
    }

    const bagianLangganan = bikinBagianRiwayat({
      jenisTetap: "langganan",
      judul: "Riwayat Langganan Tenant",
      deskripsi: "Pembayaran langganan SaaS tenant KE Rivoir (Langganan Baru/Perpanjangan/Upgrade Paket). TIDAK berisi transaksi booking customer sama sekali.",
      summaryCard: langgananSummaryCard,
      listCard: langgananCard,
      namaFileCsv: "riwayat-langganan-tenant.csv",
      idKolomLabel: "ID transaksi",
      kolomTabel: (lihatDetail) => [
        { key: "tanggal", label: "Tanggal & Waktu", format: trxWaktuLengkap },
        { key: "tenant_nama", label: "Tenant" },
        { key: "jenis_transaksi", label: "Jenis Transaksi", format: (v) => v || "-" },
        { key: "layanan", label: "Paket", format: (v) => (v || "").replace(/^Paket /, "") || "-" },
        { key: "periode_mulai", label: "Periode", format: (_, r) => trxPeriodeLengkap(r.periode_mulai, r.periode_selesai) },
        { key: "nominal", label: "Nominal", format: MugenUI.formatRupiah },
        { key: "metode_pembayaran", label: "Metode Pembayaran", format: (v) => v || "-" },
        { key: "status_unified", label: "Status", format: trxStatusBadge },
        { key: "nomor_transaksi", label: "ID Transaksi" },
        kolomAksiDetail(lihatDetail),
      ],
    });

    const bagianBooking = bikinBagianRiwayat({
      jenisTetap: "booking",
      judul: "Riwayat Booking Tenant",
      deskripsi: "Pembayaran booking customer KE tenant lewat Payment Gateway (Payment Booking/Refund Booking/Pembayaran Gagal/Expired). TIDAK berisi transaksi langganan SaaS sama sekali.",
      summaryCard: bookingSummaryCard,
      listCard: bookingCard,
      namaFileCsv: "riwayat-booking-tenant.csv",
      idKolomLabel: "Booking ID/Payment ID",
      kolomTabel: (lihatDetail) => [
        { key: "tanggal", label: "Tanggal & Waktu", format: trxWaktuLengkap },
        { key: "tenant_nama", label: "Tenant" },
        { key: "booking_id", label: "Booking ID", format: (v) => (v != null ? String(v) : "-") },
        { key: "customer_nama", label: "Customer", format: (v) => v || "-" },
        { key: "layanan", label: "Layanan", format: (v) => v || "-" },
        { key: "jenis_transaksi", label: "Jenis Transaksi", format: (v) => v || "-" },
        { key: "nominal", label: "Nominal", format: MugenUI.formatRupiah },
        { key: "metode_pembayaran", label: "Metode Pembayaran", format: (v) => v || "-" },
        { key: "status_unified", label: "Status", format: trxStatusBadge },
        { key: "transaction_id_provider", label: "Payment ID", format: (v) => v || "-" },
        kolomAksiDetail(lihatDetail),
      ],
    });

    async function loadTransaksi() {
      await Promise.all([bagianLangganan.load(), bagianBooking.load()]);
    }

    // ---------------------------------------------------------------
    // 13b. SETTLEMENT FASPAY per Terminal (Tenant) -- "terminal" = tenant
    // (keputusan eksplisit Owner), fokus HANYA transaksi Faspay SNAP
    // Advance. Murni MEMBACA (routers/faspay_settlement_superadmin.py) +
    // SATU aksi tulis: memicu rekonsiliasi H+1 (TIDAK PERNAH mengubah data
    // pengajuan awal terminal, lihat faspay_settlement_db.py).
    // ---------------------------------------------------------------
    const STL_STATUS_LABEL = { RECONCILED: "Reconciled", WARNING: "Warning", FINAL_MISMATCH: "Final Mismatch" };
    const STL_STATUS_BADGE = { RECONCILED: "badge-success", WARNING: "badge-warning", FINAL_MISMATCH: "badge-danger" };
    const STL_STATUS_ICON = { RECONCILED: "🟢", WARNING: "🟡", FINAL_MISMATCH: "🔴" };
    const STL_MATCH_LABEL = {
      match: "Match", pending_faspay: "Pending Faspay", final_match: "Match (Final)",
      missing_di_faspay: "Missing in Faspay", amount_mismatch: "Amount Mismatch",
      status_mismatch: "Status Mismatch", reference_mismatch: "Reference Mismatch",
      tidak_bisa_dicek: "Tidak Bisa Dicek",
    };

    function stlStatusBadge(status) {
      return MugenUI.el("span", { class: "badge" + (STL_STATUS_BADGE[status] ? " " + STL_STATUS_BADGE[status] : "") },
        `${STL_STATUS_ICON[status] || ""} ${STL_STATUS_LABEL[status] || status}`.trim());
    }

    settlementCard.appendChild(MugenUI.el("h2", {}, "Settlement Faspay"));
    settlementCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Closing harian transaksi Faspay SNAP Advance SELURUH tenant (\"terminal\" = tenant). Status real-time dihitung terminal sendiri saat submit -- rekonsiliasi H+1 (final, terhadap Inquiry API Faspay sungguhan) dipicu manual Super Admin di sini begitu data hari berikutnya tersedia."));

    const stlSelTenant = MugenUI.el("select");
    stlSelTenant.appendChild(MugenUI.el("option", { value: "" }, "Semua Toko"));
    const stlSelStatus = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "" }, "Semua Status"),
      ...Object.entries(STL_STATUS_LABEL).map(([k, label]) => MugenUI.el("option", { value: k }, label)),
    ]);
    const stlInputMulai = MugenUI.el("input", { type: "date" });
    const stlInputSelesai = MugenUI.el("input", { type: "date" });
    const stlBtnFilter = MugenUI.el("button", { class: "btn-primary" }, "Terapkan Filter");
    settlementCard.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:8px;align-items:flex-end;" }, [
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Toko"), stlSelTenant]),
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Status"), stlSelStatus]),
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Dari Tanggal"), stlInputMulai]),
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Sampai Tanggal"), stlInputSelesai]),
      stlBtnFilter,
    ]));

    const stlListBody = MugenUI.el("div", { style: "margin-top:12px;" });
    settlementCard.appendChild(stlListBody);

    async function stlBukaDetail(ringkas) {
      try {
        const s = await MugenApi.get(`/api/superadmin/settlement-faspay/${ringkas.id}`);
        renderStlDetailModal(s);
      } catch (e) {
        MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
      }
    }

    function renderStlDetailModal(s) {
      const body = [
        MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-bottom:10px;" }, [
          MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Status"), stlStatusBadge(s.status_rekonsiliasi)]),
          MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Toko (Terminal)"), MugenUI.el("div", {}, s.tenant_nama)]),
          MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Tanggal"), MugenUI.el("div", {}, MugenUI.formatTanggal(s.tanggal))]),
        ]),
        MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-bottom:10px;" }, [
          MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Diajukan Oleh"), MugenUI.el("div", {}, s.dibuat_oleh_nama)]),
          MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Jumlah Transaksi"), MugenUI.el("div", {}, String(s.jumlah_transaksi))]),
          MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Total Nominal"), MugenUI.el("div", {}, MugenUI.formatRupiah(s.total_nominal))]),
        ]),
        MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-bottom:10px;" }, [
          MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Match (real-time)"), MugenUI.el("div", {}, String(s.jumlah_match))]),
          MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Warning (real-time)"), MugenUI.el("div", {}, String(s.jumlah_warning))]),
          MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Final Mismatch (H+1)"),
            MugenUI.el("div", {}, s.jumlah_final_mismatch == null ? "Belum dijalankan" : String(s.jumlah_final_mismatch))]),
        ]),
      ];

      // WAJIB samakan PERSIS dengan guard backend (faspay_settlement_db.py::
      // _bisa_h1(): date.today() > tanggal SUBMITTED_AT, BUKAN tanggal
      // closing yang diajukan -- keduanya bisa beda kalau closing diajukan
      // belakangan untuk tanggal lampau). MugenUI.isoHariIniWib() dipakai
      // (bukan Date() browser) supaya patokan "hari ini" SAMA dengan
      // server (WIB), terlepas zona waktu perangkat Super Admin.
      const bisaH1 = MugenUI.isoHariIniWib() > s.submitted_at.split("T")[0];
      if (!s.h1_dijalankan_at) {
        const btnH1 = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin:8px 0 16px;" },
          "Jalankan Rekonsiliasi H+1");
        if (!bisaH1) {
          btnH1.disabled = true;
          body.push(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:8px;" },
            "Rekonsiliasi H+1 baru bisa dijalankan mulai hari setelah closing ini diajukan -- Settlement Report Faspay tidak dianggap tersedia secara real-time."));
        }
        btnH1.addEventListener("click", async () => {
          try {
            const updated = await MugenUI.withButtonLoading(btnH1,
              () => MugenApi.post(`/api/superadmin/settlement-faspay/${s.id}/rekonsiliasi-h1`));
            MugenUI.toast("Rekonsiliasi H+1 selesai.", "success", { force: true });
            modal.close();
            await muatSettlement();
            renderStlDetailModal(updated);
          } catch (e) {
            MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
          }
        });
        body.push(btnH1);
      } else {
        body.push(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:16px;" },
          `Rekonsiliasi H+1 sudah dijalankan ${trxWaktuLengkap(s.h1_dijalankan_at)} oleh ${s.h1_dijalankan_oleh}.`));
      }

      body.push(MugenUI.el("h3", {}, "Detail Transaksi"));
      body.push(MugenUI.buildTable(
        [
          { key: "order_id", label: "Order ID" },
          { key: "reference_id_provider", label: "Reference Faspay", format: (v) => v || "-" },
          { key: "payment_method", label: "Metode", format: (v) => (v || "-").toUpperCase() },
          { key: "nominal", label: "Nominal", format: MugenUI.formatRupiah },
          { key: "status_pembayaran", label: "Status" },
          { key: "match_status", label: "Real-time", format: (v) => STL_MATCH_LABEL[v] || v },
          {
            key: "h1_match_status", label: "Final (H+1)",
            format: (v, r) => (v ? `${STL_MATCH_LABEL[v] || v}${r.h1_match_detail ? ` -- ${r.h1_match_detail}` : ""}` : "-"),
          },
        ],
        s.items || [],
        { emptyText: "Tidak ada transaksi." },
      ));

      const modal = MugenUI.infoModal({ title: `Settlement Faspay -- ${s.tenant_nama} (${MugenUI.formatTanggal(s.tanggal)})`, body });
    }

    async function muatSettlement() {
      stlSelTenant.innerHTML = "";
      stlSelTenant.appendChild(MugenUI.el("option", { value: "" }, "Semua Toko"));
      for (const t of tenantList) stlSelTenant.appendChild(MugenUI.el("option", { value: String(t.id) }, t.nama_barbershop));

      stlListBody.innerHTML = "";
      stlListBody.appendChild(MugenUI.skeleton("table", { cols: 7, rows: 4 }));
      try {
        const params = new URLSearchParams();
        if (stlSelTenant.value) params.set("tenant_id", stlSelTenant.value);
        if (stlSelStatus.value) params.set("status", stlSelStatus.value);
        if (stlInputMulai.value) params.set("tanggal_mulai", stlInputMulai.value);
        if (stlInputSelesai.value) params.set("tanggal_selesai", stlInputSelesai.value);
        const data = await MugenApi.get(`/api/superadmin/settlement-faspay?${params.toString()}`);
        stlListBody.innerHTML = "";
        stlListBody.appendChild(MugenUI.buildTable(
          [
            { key: "tenant_nama", label: "Tenant (Terminal)" },
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            { key: "submitted_at", label: "Waktu Closing", format: trxWaktuLengkap },
            { key: "dibuat_oleh_nama", label: "User" },
            { key: "jumlah_transaksi", label: "Jumlah Transaksi" },
            { key: "total_nominal", label: "Total Nominal", format: MugenUI.formatRupiah },
            { key: "jumlah_match", label: "Match" },
            { key: "jumlah_warning", label: "Warning" },
            { key: "jumlah_final_mismatch", label: "Mismatch", format: (v) => (v == null ? "-" : String(v)) },
            { key: "status_rekonsiliasi", label: "Status", format: stlStatusBadge },
            {
              key: "aksi", label: "Aksi", format: (_, r) => {
                const btn = MugenUI.el("button", {}, "Detail");
                btn.addEventListener("click", () => stlBukaDetail(r));
                return btn;
              },
            },
          ],
          data,
          { emptyText: "Belum ada settlement diajukan tenant mana pun." },
        ));
      } catch (e) {
        stlListBody.innerHTML = "";
        stlListBody.appendChild(MugenUI.errorState(e.message));
      }
    }
    stlBtnFilter.addEventListener("click", muatSettlement);

    // ---------------------------------------------------------------
    // WA BOT (Input Data & Rekap via WhatsApp, provider Fonnte) -- kelola
    // nomor device + token + aktif/nonaktif + kuota per tenant, EKSKLUSIF
    // Superadmin (lihat whatsapp_bot_db.py/routers/whatsapp_bot.py). Pola
    // SAMA seperti Paket Billing di atas: tabel daftar tenant (waBotCard) +
    // tombol "Atur" yang mempopulasi form edit terpisah (waBotEditCard).
    // ---------------------------------------------------------------
    waBotCard.appendChild(MugenUI.el("h2", {}, "WA Bot -- Input Data & Rekap via WhatsApp"));
    waBotCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Nomor & token dari dashboard Fonnte (device -> token). Tenant baru SELALU mulai Nonaktif -- nyalakan manual lewat tombol \"Aktifkan\" setelah nomor benar-benar siap."));
    const waBotListBody = MugenUI.el("div");
    waBotCard.appendChild(waBotListBody);

    waBotEditCard.appendChild(MugenUI.el("h2", {}, "Atur Nomor WA Bot"));
    const waBotEditBody = MugenUI.el("div");
    waBotEditCard.appendChild(waBotEditBody);
    waBotEditBody.appendChild(MugenUI.el("div", { class: "subtitle" }, "Klik \"Atur\" pada salah satu toko di atas untuk mengisi/mengubah."));

    async function loadWaBotList() {
      waBotListBody.innerHTML = "";
      waBotListBody.appendChild(MugenUI.skeleton("table", { cols: 5, rows: 3 }));
      try {
        const baris = await MugenApi.get("/api/superadmin/whatsapp-bot");
        waBotListBody.innerHTML = "";
        waBotListBody.appendChild(MugenUI.buildTable(
          [
            { key: "nama_barbershop", label: "Toko" },
            {
              key: "nomor", label: "Nomor Device",
              format: (_, b) => b.config ? b.config.phone_number_id : MugenUI.el("span", { class: "subtitle" }, "belum diatur"),
            },
            {
              key: "kuota", label: "Kuota/Bulan",
              format: (_, b) => b.config ? String(b.config.kuota_pesan_bulanan) : "-",
            },
            {
              key: "status", label: "Status",
              format: (_, b) => {
                if (!b.config) return MugenUI.el("span", { class: "subtitle" }, "-");
                return MugenUI.el("span", { class: "badge" + (b.config.aktif ? " badge-success" : " badge-libur") },
                  b.config.aktif ? "Aktif" : "Nonaktif");
              },
            },
            {
              key: "aksi", label: "Aksi", format: (_, b) => {
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnAtur = MugenUI.el("button", {}, b.config ? "Edit" : "Atur");
                btnAtur.addEventListener("click", () => renderWaBotEdit(b));
                wrap.appendChild(btnAtur);
                if (b.config) {
                  const menujuAktif = !b.config.aktif;
                  const btnToggle = MugenUI.el("button", { class: menujuAktif ? "" : "btn-danger" },
                    menujuAktif ? "Aktifkan" : "Nonaktifkan");
                  btnToggle.addEventListener("click", async () => {
                    if (!confirm(`${menujuAktif ? "Aktifkan" : "Nonaktifkan"} WA Bot untuk "${b.nama_barbershop}"?`)) return;
                    try {
                      await MugenUI.withButtonLoading(btnToggle,
                        () => MugenApi.put(`/api/superadmin/whatsapp-bot/${b.tenant_id}/status`, { aktif: menujuAktif }));
                      MugenUI.toast("Status WA Bot diperbarui.", "success");
                      loadWaBotList();
                      loadAuditLog();
                    } catch (e) {
                      MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                    }
                  });
                  wrap.appendChild(btnToggle);
                  // FITUR WA Bot: toggle tampilan Uang Harian di pesan Rekap
                  // WA -- kalau dimatikan, potongan keterlambatan/limit habis
                  // diabaikan KHUSUS untuk tampilan WA (angka asli di
                  // Dashboard/Slip Gaji/Laporan PDF tidak berubah sama sekali,
                  // lihat whatsapp_bot_parser.py::_uang_harian_tampilan_hari()).
                  const menujuTampilkanPotongan = !b.config.tampilkan_potongan_keterlambatan;
                  const btnTogglePotongan = MugenUI.el("button", {},
                    menujuTampilkanPotongan ? "Tampilkan Potongan Telat" : "Sembunyikan Potongan Telat");
                  btnTogglePotongan.addEventListener("click", async () => {
                    if (!confirm(`${menujuTampilkanPotongan ? "Tampilkan" : "Sembunyikan"} potongan keterlambatan di Uang Harian pesan WA Bot untuk "${b.nama_barbershop}"?`)) return;
                    try {
                      await MugenUI.withButtonLoading(btnTogglePotongan,
                        () => MugenApi.put(`/api/superadmin/whatsapp-bot/${b.tenant_id}/tampilkan-potongan-keterlambatan`,
                          { aktif: menujuTampilkanPotongan }));
                      MugenUI.toast("Setting tampilan WA Bot diperbarui.", "success");
                      loadWaBotList();
                      loadAuditLog();
                    } catch (e) {
                      MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                    }
                  });
                  wrap.appendChild(btnTogglePotongan);
                  const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                  btnHapus.addEventListener("click", async () => {
                    if (!confirm(`Hapus konfigurasi WA Bot "${b.nama_barbershop}"? Nomor & token akan dilepas dari tenant ini.`)) return;
                    try {
                      await MugenUI.withButtonLoading(btnHapus,
                        () => MugenApi.del(`/api/superadmin/whatsapp-bot/${b.tenant_id}`));
                      MugenUI.toast("Konfigurasi WA Bot dihapus.", "success");
                      loadWaBotList();
                      loadAuditLog();
                      waBotEditBody.innerHTML = "";
                      waBotEditBody.appendChild(MugenUI.el("div", { class: "subtitle" }, "Klik \"Atur\" pada salah satu toko di atas untuk mengisi/mengubah."));
                    } catch (e) {
                      MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                    }
                  });
                  wrap.appendChild(btnHapus);
                }
                return wrap;
              },
            },
          ],
          baris,
          { emptyText: "Belum ada toko." },
        ));
      } catch (e) {
        waBotListBody.innerHTML = "";
        waBotListBody.appendChild(MugenUI.errorState(e.message));
      }
    }

    function renderWaBotEdit(b) {
      waBotEditBody.innerHTML = "";
      waBotEditBody.appendChild(MugenUI.el("h3", {}, `Atur WA Bot: ${b.nama_barbershop}`));
      const inputNomor = MugenUI.el("input", { type: "text", placeholder: "Nomor device Fonnte, mis. 628xxxxxxxxxx", value: b.config ? b.config.phone_number_id : "" });
      const inputToken = MugenUI.el("input", { type: "password", autocomplete: "off", placeholder: "Device Token (dashboard Fonnte -> device list)", value: b.config ? b.config.device_token || "" : "" });
      const inputNama = MugenUI.el("input", { type: "text", placeholder: "Label nomor (opsional)", value: b.config ? b.config.nama_nomor || "" : "" });
      const inputKuota = MugenUI.el("input", { type: "number", min: "0", placeholder: String(50), value: b.config ? String(b.config.kuota_pesan_bulanan) : "" });
      // FITUR WA Bot (Input Data & Rekap via WhatsApp): nomor yang setara
      // akses Owner PENUH lewat bot (input data siapa saja + rekap siapa
      // saja) -- OPSIONAL, beda dari Nomor Device Fonnte di atas (nomor
      // bot itu sendiri) dan dari nomor_whatsapp tiap barber (diatur di
      // Setting > Karyawan, akses terbatas ke data masing-masing).
      const inputNomorOwner = MugenUI.el("input", { type: "text", placeholder: "mis. 6281234567890 (opsional)",
        value: b.config ? b.config.nomor_owner_whatsapp || "" : "" });
      // PERMINTAAN OWNER: maksimal 2 nomor setara akses Owner PENUH lewat
      // bot per tenant (toko dengan 2 pemilik/pengelola) -- OPSIONAL,
      // kosongkan kalau cuma butuh 1 nomor Owner.
      const inputNomorOwner2 = MugenUI.el("input", { type: "text", placeholder: "mis. 6281234567891 (opsional, maks. 2)",
        value: b.config ? b.config.nomor_owner_whatsapp_2 || "" : "" });

      waBotEditBody.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;" }, [
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Nomor Device Fonnte"), inputNomor]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Device Token"), inputToken]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Label Nomor"), inputNama]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Kuota Pesan/Bulan"), inputKuota]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Nomor Owner 1 (WA) -- akses penuh lewat bot"), inputNomorOwner]),
        MugenUI.el("div", {}, [MugenUI.el("label", {}, "Nomor Owner 2 (WA) -- opsional"), inputNomorOwner2]),
      ]));

      const errEdit = MugenUI.el("div", { class: "login-error" });
      const btnSimpan = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
      waBotEditBody.appendChild(errEdit);
      waBotEditBody.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpan));

      btnSimpan.addEventListener("click", async () => {
        errEdit.textContent = "";
        const body = {
          phone_number_id: inputNomor.value.trim(),
          device_token: inputToken.value.trim(),
          nama_nomor: inputNama.value.trim() || null,
          kuota_pesan_bulanan: inputKuota.value === "" ? null : parseInt(inputKuota.value, 10),
          nomor_owner_whatsapp: inputNomorOwner.value.trim() || null,
          nomor_owner_whatsapp_2: inputNomorOwner2.value.trim() || null,
        };
        try {
          await MugenUI.withButtonLoading(btnSimpan,
            () => MugenApi.put(`/api/superadmin/whatsapp-bot/${b.tenant_id}`, body));
          MugenUI.toast("Konfigurasi WA Bot disimpan.", "success");
          loadAuditLog();
          await loadWaBotList();
          waBotEditBody.innerHTML = "";
          waBotEditBody.appendChild(MugenUI.el("div", { class: "subtitle" }, "Klik \"Atur\" pada salah satu toko di atas untuk mengisi/mengubah."));
        } catch (e) {
          errEdit.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        }
      });
    }

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

    // ---------------------------------------------------------------
    // FITUR Program Afiliasi Sales/Marketing (sales_db.py, routers/sales.py)
    // ---------------------------------------------------------------
    const LABEL_PACKAGE_SALES = { basic: "Basic", pro: "Pro", enterprise: "Enterprise" };
    const LABEL_JENIS_KOMISI = { baru: "Pendaftaran Baru", repeat: "Perpanjangan", lifetime: "Lisensi Lifetime" };

    salesCard.appendChild(MugenUI.el("h2", {}, "Rekrut Sales Baru"));
    salesCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Akun login (role Sales) + kode referral pertamanya dibuat sekaligus. Kasih username/password ini ke orangnya -- dia login lewat halaman login yang sama dipakai semua akun."));
    const fUsername = MugenUI.el("input", { type: "text", placeholder: "Username" });
    const fPassword = MugenUI.el("input", { type: "text", placeholder: "Password (min. 4 karakter)" });
    const fNamaSales = MugenUI.el("input", { type: "text", placeholder: "Nama Sales" });
    const fKode = MugenUI.el("input", { type: "text", placeholder: "Kode Referral, mis. BUDI10" });
    const fPersenBaru = MugenUI.el("input", { type: "number", value: "50", min: "0", max: "100" });
    const fPersenRepeat = MugenUI.el("input", { type: "number", value: "20", min: "0", max: "100" });
    const fPersenLifetime = MugenUI.el("input", { type: "number", value: "30", min: "0", max: "100" });
    salesCard.appendChild(MugenUI.el("label", {}, "Username"));
    salesCard.appendChild(fUsername);
    salesCard.appendChild(MugenUI.el("label", {}, "Password"));
    salesCard.appendChild(fPassword);
    salesCard.appendChild(MugenUI.el("label", {}, "Nama Sales"));
    salesCard.appendChild(fNamaSales);
    salesCard.appendChild(MugenUI.el("label", {}, "Kode Referral"));
    salesCard.appendChild(fKode);
    salesCard.appendChild(MugenUI.el("div", { class: "row", style: "margin-top:8px;" }, [
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Komisi Baru (%)"), fPersenBaru]),
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Komisi Repeat (%)"), fPersenRepeat]),
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Komisi Lifetime (%)"), fPersenLifetime]),
    ]));
    const btnBuatSales = MugenUI.el("button", {}, "Buat Akun Sales");
    salesCard.appendChild(btnBuatSales);
    btnBuatSales.addEventListener("click", async () => {
      try {
        await MugenUI.withButtonLoading(btnBuatSales, () => MugenApi.post("/api/superadmin/sales/akun", {
          username: fUsername.value.trim(), password: fPassword.value, nama_sales: fNamaSales.value.trim(),
          kode: fKode.value.trim(), komisi_persen_baru: Number(fPersenBaru.value),
          komisi_persen_repeat: Number(fPersenRepeat.value), komisi_persen_lifetime: Number(fPersenLifetime.value),
        }));
        MugenUI.toast("Akun sales dibuat.", "success");
        fUsername.value = ""; fPassword.value = ""; fNamaSales.value = ""; fKode.value = "";
        loadKodeReferral();
        loadAuditLog();
      } catch (e) {
        MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
      }
    });

    const kodeReferralBody = MugenUI.el("div");
    salesCard.appendChild(MugenUI.el("h3", { style: "margin-top:18px;" }, "Daftar Kode Referral"));
    salesCard.appendChild(kodeReferralBody);

    async function loadKodeReferral() {
      kodeReferralBody.innerHTML = "";
      kodeReferralBody.appendChild(MugenUI.skeleton("table", { cols: 6, rows: 3 }));
      try {
        const daftar = await MugenApi.get("/api/superadmin/sales/kode-referral");
        kodeReferralBody.innerHTML = "";
        kodeReferralBody.appendChild(MugenUI.buildTable(
          [
            { key: "kode", label: "Kode" },
            { key: "nama_sales", label: "Nama Sales" },
            { key: "username", label: "Username" },
            { key: "komisi_persen_baru", label: "Baru", format: (v) => `${v}%` },
            { key: "komisi_persen_repeat", label: "Repeat", format: (v) => `${v}%` },
            { key: "komisi_persen_lifetime", label: "Lifetime", format: (v) => `${v}%` },
            {
              key: "aktif", label: "Status",
              format: (v) => MugenUI.el("span", { class: "badge " + (v ? "badge-success" : "badge-libur") }, v ? "Aktif" : "Nonaktif"),
            },
            {
              key: "aksi", label: "Aksi", format: (_, k) => {
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnUbah = MugenUI.el("button", {}, "Ubah Komisi");
                btnUbah.addEventListener("click", async () => {
                  const baru = prompt("Persen komisi Pendaftaran Baru (0-100):", k.komisi_persen_baru);
                  if (baru === null) return;
                  const repeat = prompt("Persen komisi Perpanjangan (0-100):", k.komisi_persen_repeat);
                  if (repeat === null) return;
                  const lifetime = prompt("Persen komisi Lisensi Lifetime (0-100):", k.komisi_persen_lifetime);
                  if (lifetime === null) return;
                  try {
                    await MugenApi.put(`/api/superadmin/sales/kode-referral/${k.id}`, {
                      komisi_persen_baru: Number(baru), komisi_persen_repeat: Number(repeat),
                      komisi_persen_lifetime: Number(lifetime),
                    });
                    MugenUI.toast("Komisi diperbarui.", "success");
                    loadKodeReferral();
                    loadAuditLog();
                  } catch (e) {
                    MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                  }
                });
                wrap.appendChild(btnUbah);
                // REVISI (laporan Superadmin): password akun sales TIDAK
                // BISA dilihat (hash satu arah, sama seperti semua akun
                // lain) -- tombol ini satu-satunya cara Superadmin
                // mengubahnya kalau sales lupa/minta diganti.
                const btnGantiPassword = MugenUI.el("button", {}, "Ganti Password");
                btnGantiPassword.addEventListener("click", async () => {
                  const passwordBaru = prompt(`Password baru untuk akun "${k.username}" (minimal 4 karakter):`);
                  if (passwordBaru === null) return;
                  try {
                    await MugenApi.put(`/api/superadmin/sales/akun/${k.user_id}/password`, { password: passwordBaru });
                    MugenUI.toast("Password akun sales diperbarui.", "success");
                    loadAuditLog();
                  } catch (e) {
                    MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                  }
                });
                wrap.appendChild(btnGantiPassword);
                const menujuAktif = !k.aktif;
                const btnToggle = MugenUI.el("button", { class: menujuAktif ? "" : "btn-danger" },
                  menujuAktif ? "Aktifkan" : "Nonaktifkan");
                btnToggle.addEventListener("click", async () => {
                  if (!confirm(`${menujuAktif ? "Aktifkan" : "Nonaktifkan"} kode "${k.kode}"?`)) return;
                  try {
                    await MugenApi.put(`/api/superadmin/sales/kode-referral/${k.id}`, { aktif: menujuAktif });
                    MugenUI.toast("Status kode diperbarui.", "success");
                    loadKodeReferral();
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
          daftar,
          { emptyText: "Belum ada sales yang direkrut." },
        ));
      } catch (e) {
        kodeReferralBody.innerHTML = "";
        kodeReferralBody.appendChild(MugenUI.errorState(e.message));
      }
    }

    // --- Transaksi Lisensi Lifetime (Beli Putus) ---
    // REVISI (desain awal keliru -- Faspay tidak punya dashboard manusia
    // untuk membuat VA, VA hanya bisa dibuat lewat API): Super Admin
    // SEKARANG hanya memilih tenant + paket + metode pembayaran, nominal
    // & VA/QR dibuat OTOMATIS lewat gateway SNAP Advance yang SAMA dipakai
    // checkout langganan biasa (lihat routers/sales.py::buat_lifetime()).
    // Begitu tenant membayar (otomatis terdeteksi webhook, lihat
    // snap_webhook.py::_cascade_lifetime_license()), tenant otomatis
    // mendapat akses permanen (status 'Lifetime') di paket yang dipilih,
    // dan komisi (kalau kode referral dipasang) tercatat otomatis.
    salesLifetimeCard.appendChild(MugenUI.el("h2", {}, "Lisensi Lifetime (Beli Putus)"));
    salesLifetimeCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Pilih tenant & paket -- nominal dan Virtual Account/QRIS dibuat otomatis lewat Faspay SNAP Advance (gateway yang sama dipakai checkout langganan biasa). Begitu tenant membayar, status Lifetime aktif otomatis -- Super Admin tidak perlu menandai lunas manual."));
    // REVISI (bugfix UX, laporan Superadmin): SEBELUMNYA input angka "ID
    // Tenant" polos -- tabel daftar Tenant di tab sebelah TIDAK PERNAH
    // menampilkan ID mentahnya sama sekali, jadi tidak ada cara normal
    // untuk tahu angka yang harus diketik di sini. Diganti dropdown nama
    // toko (opsinya dimuat dari endpoint yang SAMA dipakai loadTenantList(),
    // lihat loadTenantOptionsLifetime() di bawah), Superadmin tinggal
    // pilih nama, tidak perlu tahu ID sama sekali. Tenant itu sendiri HARUS
    // SUDAH terdaftar lebih dulu (daftar mandiri lewat halaman Daftar, atau
    // Superadmin buat manual lewat tab Tenant) -- dropdown ini murni
    // memilih dari yang sudah ada, bukan alur pendaftaran baru.
    const ltTenantSelect = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "" }, "Memuat daftar tenant..."),
    ]);
    const ltPackage = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "" }, "Memuat daftar paket..."),
    ]);
    const ltAmount = MugenUI.el("input", { type: "number", placeholder: "Nominal (Rp) -- otomatis dari katalog" });
    const ltChannel = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "" }, "Memuat metode pembayaran..."),
    ]);
    const ltBankCode = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "" }, "-- pilih bank VA --"),
    ]);
    const ltBankCodeWrap = MugenUI.el("div", {}, [MugenUI.el("label", {}, "Bank VA"), ltBankCode]);
    const ltKodeReferral = MugenUI.el("input", { type: "text", placeholder: "Kode Referral (opsional)" });
    salesLifetimeCard.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;" }, [
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Tenant"), ltTenantSelect]),
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Paket"), ltPackage]),
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Nominal"), ltAmount]),
    ]));
    salesLifetimeCard.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-top:8px;" }, [
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Metode Pembayaran"), ltChannel]),
      ltBankCodeWrap,
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Kode Referral"), ltKodeReferral]),
    ]));

    async function loadTenantOptionsLifetime() {
      try {
        const tenants = await MugenApi.get("/api/superadmin/tenants");
        ltTenantSelect.innerHTML = "";
        ltTenantSelect.appendChild(MugenUI.el("option", { value: "" }, "Pilih Tenant..."));
        for (const t of tenants) {
          ltTenantSelect.appendChild(MugenUI.el("option", { value: String(t.id) }, `${t.nama_barbershop} (${t.slug})`));
        }
      } catch (e) {
        ltTenantSelect.innerHTML = "";
        ltTenantSelect.appendChild(MugenUI.el("option", { value: "" }, "Gagal memuat daftar tenant."));
      }
    }

    // {kode: harga_lifetime} -- diisi loadLifetimePaketOptions(), dipakai
    // auto-fill ltAmount begitu Superadmin mengganti pilihan paket.
    let _hargaLifetimePerPaket = {};
    async function loadLifetimePaketOptions() {
      try {
        const paket = await MugenApi.get("/api/superadmin/billing/packages");
        ltPackage.innerHTML = "";
        _hargaLifetimePerPaket = {};
        for (const p of paket) {
          _hargaLifetimePerPaket[p.kode] = p.harga_lifetime || null;
          const label = p.harga_lifetime ? `${p.nama} (${MugenUI.formatRupiah(p.harga_lifetime)})` : `${p.nama} (belum diatur)`;
          ltPackage.appendChild(MugenUI.el("option", { value: p.kode }, label));
        }
        if (ltPackage.options.length) ltAmount.value = _hargaLifetimePerPaket[ltPackage.value] || "";
      } catch (e) {
        ltPackage.innerHTML = "";
        ltPackage.appendChild(MugenUI.el("option", { value: "" }, "Gagal memuat daftar paket."));
      }
    }
    ltPackage.addEventListener("change", () => {
      const harga = _hargaLifetimePerPaket[ltPackage.value];
      if (harga) ltAmount.value = harga;
    });

    // Metode pembayaran & bank VA aktif -- SAMA PERSIS konfigurasi SNAP
    // Advance yang Super Admin atur di tab "Payment Gateway SNAP Advance"
    // (lihat loadSnapAdvanceConfig() di atas) -- form Lifetime di sini
    // TIDAK boleh menawarkan channel/bank yang belum/tidak diaktifkan.
    const LABEL_CHANNEL_LIFETIME = { va: "Virtual Account", qris: "QRIS" };
    async function loadLifetimeChannelOptions() {
      try {
        const cfg = await MugenApi.get("/api/superadmin/snap-advance/config");
        const channelAktif = cfg.snap_channel_aktif || [];
        ltChannel.innerHTML = "";
        if (!channelAktif.length) {
          ltChannel.appendChild(MugenUI.el("option", { value: "" }, "Belum ada metode pembayaran aktif."));
        }
        for (const kode of channelAktif) {
          ltChannel.appendChild(MugenUI.el("option", { value: kode }, LABEL_CHANNEL_LIFETIME[kode] || kode));
        }
        const vaBankLabel = cfg.va_channel_code_label || {};
        ltBankCode.innerHTML = "";
        for (const kode of (cfg.snap_va_bank_aktif || [])) {
          ltBankCode.appendChild(MugenUI.el("option", { value: kode }, MugenUI.bankNamaLengkap(kode, vaBankLabel[kode])));
        }
        ltBankCodeWrap.style.display = ltChannel.value === "va" ? "" : "none";
      } catch (e) {
        ltChannel.innerHTML = "";
        ltChannel.appendChild(MugenUI.el("option", { value: "" }, "Gagal memuat metode pembayaran."));
      }
    }
    ltChannel.addEventListener("change", () => {
      ltBankCodeWrap.style.display = ltChannel.value === "va" ? "" : "none";
    });

    const btnBuatLifetime = MugenUI.el("button", {}, "Buat Transaksi Lifetime");
    salesLifetimeCard.appendChild(MugenUI.el("div", { style: "margin-top:10px;" }, btnBuatLifetime));
    const lifetimeListBody = MugenUI.el("div");
    salesLifetimeCard.appendChild(MugenUI.el("h3", { style: "margin-top:18px;" }, "Riwayat Transaksi Lifetime"));
    salesLifetimeCard.appendChild(lifetimeListBody);

    btnBuatLifetime.addEventListener("click", async () => {
      if (!ltTenantSelect.value) {
        MugenUI.toast("Pilih tenant dulu -- kalau tenantnya belum ada di daftar, minta dia daftar sendiri lewat halaman Daftar, atau buat toko barunya lewat tab Tenant.", "error");
        return;
      }
      if (!ltChannel.value) {
        MugenUI.toast("Pilih metode pembayaran dulu.", "error");
        return;
      }
      if (ltChannel.value === "va" && !ltBankCode.value) {
        MugenUI.toast("Pilih bank VA dulu.", "error");
        return;
      }
      try {
        let referral_code_id = null;
        const kodeDiketik = ltKodeReferral.value.trim();
        if (kodeDiketik) {
          const semuaKode = await MugenApi.get("/api/superadmin/sales/kode-referral");
          const cocok = semuaKode.find((k) => k.kode.toUpperCase() === kodeDiketik.toUpperCase());
          if (!cocok) { MugenUI.toast(`Kode referral "${kodeDiketik}" tidak ditemukan.`, "error"); return; }
          referral_code_id = cocok.id;
        }
        await MugenUI.withButtonLoading(btnBuatLifetime, () => MugenApi.post("/api/superadmin/sales/lifetime", {
          tenant_id: Number(ltTenantSelect.value), package_kode: ltPackage.value,
          amount: ltAmount.value === "" ? null : Number(ltAmount.value),
          channel: ltChannel.value, bank_code: ltChannel.value === "va" ? ltBankCode.value : null,
          referral_code_id,
        }));
        MugenUI.toast("Transaksi Lifetime dibuat -- VA/QR siap ditagihkan ke tenant.", "success");
        ltTenantSelect.value = ""; ltKodeReferral.value = "";
        loadLifetimeList();
        loadAuditLog();
      } catch (e) {
        MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
      }
    });

    async function loadLifetimeList() {
      lifetimeListBody.innerHTML = "";
      lifetimeListBody.appendChild(MugenUI.skeleton("table", { cols: 7, rows: 3 }));
      try {
        const daftar = await MugenApi.get("/api/superadmin/sales/lifetime");
        lifetimeListBody.innerHTML = "";
        lifetimeListBody.appendChild(MugenUI.buildTable(
          [
            { key: "nama_tenant", label: "Tenant" },
            { key: "package_kode", label: "Paket", format: (v) => LABEL_PACKAGE_SALES[v] || v },
            { key: "amount", label: "Nominal", format: (v) => MugenUI.formatRupiah(v) },
            { key: "kode_referral", label: "Kode Referral", format: (v) => v || "-" },
            {
              key: "instrumen", label: "VA/QR", format: (_, p) => {
                if (p.channel === "va" && p.va_number) {
                  return MugenUI.el("div", {}, [
                    MugenUI.el("div", { class: "subtitle" }, MugenUI.bankNamaLengkap(p.channel_code, p.va_bank_label)),
                    MugenUI.el("div", { style: "font-weight:700;" }, p.va_number),
                  ]);
                }
                // PERBAIKAN BUG: akun Faspay SNAP Advance non-"direct merchant"
                // TIDAK PERNAH mengisi qrUrl (lihat snap_advance_client.py::
                // buat_transaksi_qris()) -- qrImageUrl (qr_content, link ke
                // halaman Faspay yang menampilkan QR) SELALU ada sebagai
                // gantinya, dulu TIDAK PERNAH dipakai sama sekali di sini.
                if (p.channel === "qris" && (p.qr_url || p.qr_content)) {
                  return MugenUI.el("a", { href: p.qr_url || p.qr_content, target: "_blank" }, "Lihat QRIS");
                }
                return "-";
              },
            },
            {
              key: "payment_status", label: "Status",
              format: (v) => {
                const cls = v === "paid" ? "badge-success" : v === "pending" ? "badge-warning" : "badge-danger";
                const label = { pending: "Menunggu", paid: "Lunas", expired: "Kedaluwarsa", failed: "Gagal", cancelled: "Dibatalkan" }[v] || v;
                return MugenUI.el("span", { class: `badge ${cls}` }, label);
              },
            },
            {
              key: "aksi", label: "Aksi", format: (_, p) => {
                if (p.payment_status !== "pending") return "-";
                const btnLunas = MugenUI.el("button", {}, "Tandai Lunas Manual");
                btnLunas.addEventListener("click", async () => {
                  if (!confirm(`Tandai transaksi Lifetime "${p.nama_tenant}" LUNAS secara manual? Normalnya ini otomatis begitu pembayaran dikonfirmasi gateway -- hanya pakai ini kalau tenant membayar lewat jalur lain di luar aplikasi. Tenant akan langsung mendapat akses permanen.`)) return;
                  try {
                    await MugenUI.withButtonLoading(btnLunas,
                      () => MugenApi.put(`/api/superadmin/sales/lifetime/${p.id}/status`, { payment_status: "paid" }));
                    MugenUI.toast("Transaksi Lifetime ditandai lunas, tenant sudah di-upgrade.", "success");
                    loadLifetimeList();
                    loadSalesKomisi();
                    loadAuditLog();
                  } catch (e) {
                    MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                  }
                });
                // FITUR: tombol Batalkan -- VA/QR yang sudah terlanjur
                // dibuat & tampil di halaman Billing tenant (lihat
                // routers/billing.py::lifetime_pending_saya()) perlu bisa
                // dihentikan kalau transaksinya batal (salah paket, test,
                // dll). Begitu dibatalkan, baris ini berhenti muncul di
                // Billing tenant -- TAPI TIDAK bisa membatalkan transfer
                // bank yang SUDAH terlanjur dilakukan (lihat peringatan
                // confirm() di bawah).
                const btnBatal = MugenUI.el("button", { class: "btn-danger" }, "Batalkan");
                btnBatal.addEventListener("click", async () => {
                  if (!confirm(`Batalkan transaksi Lifetime "${p.nama_tenant}"? VA/QR-nya akan berhenti ditampilkan di halaman Billing tenant. PERHATIAN: ini TIDAK membatalkan transfer bank yang mungkin SUDAH terlanjur dilakukan tenant ke VA tersebut -- pastikan dulu belum ada pembayaran masuk sebelum membatalkan.`)) return;
                  try {
                    await MugenUI.withButtonLoading(btnBatal,
                      () => MugenApi.put(`/api/superadmin/sales/lifetime/${p.id}/status`, { payment_status: "cancelled" }));
                    MugenUI.toast("Transaksi Lifetime dibatalkan.", "success");
                    loadLifetimeList();
                    loadAuditLog();
                  } catch (e) {
                    MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                  }
                });
                return MugenUI.el("div", { class: "actions-cell" }, [btnLunas, btnBatal]);
              },
            },
          ],
          daftar,
          { emptyText: "Belum ada transaksi Lifetime." },
        ));
      } catch (e) {
        lifetimeListBody.innerHTML = "";
        lifetimeListBody.appendChild(MugenUI.errorState(e.message));
      }
    }

    // --- Komisi lintas sales ---
    salesKomisiCard.appendChild(MugenUI.el("h2", {}, "Komisi Sales"));
    const salesKomisiBody = MugenUI.el("div");
    salesKomisiCard.appendChild(salesKomisiBody);

    async function loadSalesKomisi() {
      salesKomisiBody.innerHTML = "";
      salesKomisiBody.appendChild(MugenUI.skeleton("table", { cols: 7, rows: 3 }));
      try {
        const daftar = await MugenApi.get("/api/superadmin/sales/komisi");
        salesKomisiBody.innerHTML = "";
        salesKomisiBody.appendChild(MugenUI.buildTable(
          [
            { key: "nama_sales", label: "Sales" },
            { key: "nama_tenant", label: "Tenant" },
            { key: "jenis", label: "Jenis", format: (v) => LABEL_JENIS_KOMISI[v] || v },
            { key: "nominal_dibayar", label: "Dibayar Tenant", format: (v) => MugenUI.formatRupiah(v) },
            { key: "nominal_komisi", label: "Komisi", format: (v) => MugenUI.formatRupiah(v) },
            {
              key: "status", label: "Status",
              format: (v) => MugenUI.el("span", { class: "badge " + (v === "sudah_dibayar" ? "badge-success" : "badge-warning") },
                v === "sudah_dibayar" ? "Sudah Dibayar" : "Belum Dibayar"),
            },
            {
              key: "aksi", label: "Aksi", format: (_, k) => {
                const menujuStatus = k.status === "sudah_dibayar" ? "belum_dibayar" : "sudah_dibayar";
                const btn = MugenUI.el("button", {}, menujuStatus === "sudah_dibayar" ? "Tandai Sudah Dibayar" : "Tandai Belum Dibayar");
                btn.addEventListener("click", async () => {
                  try {
                    await MugenUI.withButtonLoading(btn,
                      () => MugenApi.put(`/api/superadmin/sales/komisi/${k.id}/status`, { status: menujuStatus }));
                    MugenUI.toast("Status komisi diperbarui.", "success");
                    loadSalesKomisi();
                    loadAuditLog();
                  } catch (e) {
                    MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                  }
                });
                return btn;
              },
            },
          ],
          daftar,
          { emptyText: "Belum ada komisi tercatat." },
        ));
      } catch (e) {
        salesKomisiBody.innerHTML = "";
        salesKomisiBody.appendChild(MugenUI.errorState(e.message));
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
    await muatSettlement();
    await loadWaBotList();
    await loadKodeReferral();
    await loadTenantOptionsLifetime();
    await loadLifetimePaketOptions();
    await loadLifetimeChannelOptions();
    await loadLifetimeList();
    await loadSalesKomisi();
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
