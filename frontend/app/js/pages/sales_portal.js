// pages/sales_portal.js — Program Afiliasi Sales/Marketing (sales_db.py,
// routers/sales.py)
// =============================================================================
// Halaman BARU, khusus akun role 'sales' (tenant_id=NULL, pola identik
// superadmin.js -- dirender router.js untuk SEMUA hash begitu login sebagai
// sales, lihat router.js/nav.js). READ-ONLY total -- sales TIDAK bisa
// mengubah apa pun dari sini (persentase komisi/status bayar HANYA diatur
// Super Admin lewat tab "Sales & Referral" di superadmin.js).
//
// Tiga bagian: 1) info kode referral miliknya sendiri, 2) ringkasan +
// rincian komisi (belum/sudah dibayar), 3) daftar tenant yang terdaftar
// lewat kodenya.

const PageSalesPortal = (() => {
  function pesanError(e) {
    return (e && e.detail && e.detail.detail) ? e.detail.detail : (e.message || "Terjadi kesalahan.");
  }

  const LABEL_JENIS = { baru: "Pendaftaran Baru", repeat: "Perpanjangan", lifetime: "Lisensi Lifetime" };
  const LABEL_STATUS_SUB = {
    trial: "Trial", active: "Aktif", expired: "Kedaluwarsa",
    suspended: "Ditangguhkan", cancelled: "Dibatalkan", lifetime: "Lifetime",
  };
  const LABEL_PACKAGE = { free: "Free", basic: "Basic", pro: "Pro", enterprise: "Enterprise" };

  function infoItem(label, value) {
    return MugenUI.el("div", {}, [
      MugenUI.el("div", { class: "subtitle" }, label),
      MugenUI.el("div", { style: "font-weight:700;font-size:16px;" }, String(value)),
    ]);
  }

  function kartuKode(kode) {
    const card = MugenUI.el("div", { class: "card" });
    card.appendChild(MugenUI.el("h2", {}, "Kode Referral Saya"));
    const grid = MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:24px;margin-bottom:8px;" }, [
      infoItem("Kode", kode.kode),
      infoItem("Nama Sales", kode.nama_sales),
      infoItem("Status", kode.aktif ? "Aktif" : "Nonaktif"),
      infoItem("Komisi Pendaftaran Baru", `${kode.komisi_persen_baru}%`),
      infoItem("Komisi Perpanjangan", `${kode.komisi_persen_repeat}%`),
      infoItem("Komisi Lisensi Lifetime", `${kode.komisi_persen_lifetime}%`),
    ]);
    card.appendChild(grid);
    card.appendChild(MugenUI.el("p", { class: "subtitle", style: "margin-top:10px;" },
      "Bagikan kode ini ke calon tenant -- mereka cukup mengetikkannya di form Daftar, atau klik link pendaftaran yang sudah menyertakan kode ini secara otomatis."));
    return card;
  }

  function kartuRingkasanKomisi(data) {
    const card = MugenUI.el("div", { class: "card" });
    card.appendChild(MugenUI.el("h2", {}, "Ringkasan Komisi"));
    const grid = MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:24px;margin-bottom:8px;" }, [
      infoItem("Belum Dibayar", MugenUI.formatRupiah(data.total_belum_dibayar)),
      infoItem("Sudah Dibayar", MugenUI.formatRupiah(data.total_sudah_dibayar)),
    ]);
    card.appendChild(grid);
    card.appendChild(MugenUI.el("p", { class: "subtitle", style: "margin-top:10px;" },
      "Komisi dicairkan oleh Super Admin -- status di bawah ini akan berubah otomatis begitu pencairan ditandai selesai. Tidak perlu mengajukan klaim apa pun dari sini."));
    return card;
  }

  function badgeStatusKomisi(status) {
    const label = status === "sudah_dibayar" ? "Sudah Dibayar" : "Belum Dibayar";
    const cls = status === "sudah_dibayar" ? "badge-success" : "badge-warning";
    return MugenUI.el("span", { class: `badge ${cls}` }, label);
  }

  function kartuDaftarKomisi(komisiList) {
    const card = MugenUI.el("div", { class: "card" });
    card.appendChild(MugenUI.el("h2", {}, "Rincian Komisi"));
    const columns = [
      { key: "nama_tenant", label: "Tenant" },
      { key: "jenis", label: "Jenis", format: (v) => LABEL_JENIS[v] || v },
      { key: "nominal_dibayar", label: "Dibayar Tenant", format: (v) => MugenUI.formatRupiah(v) },
      { key: "persen_komisi", label: "Persen", format: (v) => `${v}%` },
      { key: "nominal_komisi", label: "Komisi Saya", format: (v) => MugenUI.formatRupiah(v) },
      { key: "status", label: "Status", format: (v) => badgeStatusKomisi(v) },
      { key: "dibuat_at", label: "Tanggal", format: (v) => MugenUI.formatTanggal((v || "").split("T")[0]) },
    ];
    card.appendChild(MugenUI.buildTable(columns, komisiList, { emptyText: "Belum ada komisi tercatat." }));
    return card;
  }

  function kartuDaftarTenant(tenants) {
    const card = MugenUI.el("div", { class: "card" });
    card.appendChild(MugenUI.el("h2", {}, "Tenant dari Kode Saya"));
    const columns = [
      { key: "nama_barbershop", label: "Nama Toko" },
      { key: "package", label: "Paket", format: (v) => LABEL_PACKAGE[v] || v || "-" },
      { key: "status", label: "Status Langganan", format: (v) => LABEL_STATUS_SUB[v] || v || "-" },
      { key: "created_at", label: "Terdaftar Sejak", format: (v) => MugenUI.formatTanggal((v || "").split("T")[0]) },
    ];
    card.appendChild(MugenUI.buildTable(columns, tenants, { emptyText: "Belum ada tenant yang terdaftar lewat kode ini." }));
    return card;
  }

  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Portal Sales"));

    const loadingCard = MugenUI.skeleton("card", { lines: 3 });
    root.appendChild(loadingCard);

    let kode, tenants, komisiData;
    try {
      [kode, tenants, komisiData] = await Promise.all([
        MugenApi.get("/api/sales/me"),
        MugenApi.get("/api/sales/me/tenants"),
        MugenApi.get("/api/sales/me/komisi"),
      ]);
    } catch (e) {
      loadingCard.innerHTML = "";
      loadingCard.appendChild(MugenUI.errorState(pesanError(e)));
      return;
    }
    loadingCard.remove();

    root.appendChild(kartuKode(kode));
    root.appendChild(kartuRingkasanKomisi(komisiData));
    root.appendChild(kartuDaftarTenant(tenants));
    root.appendChild(kartuDaftarKomisi(komisiData.komisi));
  }

  return { render };
})();

window.PageSalesPortal = PageSalesPortal;
