// pages/billing.js — FONDASI Multi-Tenant Phase 4: Billing & Payment (Midtrans)
// =============================================================================
// Halaman BARU, KHUSUS Owner (require_admin, sama seperti Setting > Subscription
// Phase 3 -- staff TIDAK ikut melihat, lihat nav.js) -- TERPISAH TOTAL dari tab
// "Subscription" read-only di pages/pengaturan.js (Phase 3, TIDAK diubah sama
// sekali di sini): paket aktif + periode + status, katalog paket untuk upgrade/
// downgrade/perpanjang, checkout Midtrans Snap, riwayat invoice/pembayaran.
//
// Snap.js Midtrans dimuat DINAMIS (bukan <script> tetap di index.html) --
// proyek ini sengaja tanpa bundler/CDN tetap apa pun (lihat README), dan
// Snap.js HANYA dibutuhkan tepat saat Owner menekan tombol checkout, jadi
// tidak ada gunanya dimuat di awal (apalagi kalau Midtrans belum
// dikonfigurasi Super Admin sama sekali -- lihat GET /api/billing/config).

const PageBilling = (() => {
  const LABEL_PACKAGE = { free: "Free", basic: "Basic", pro: "Pro", enterprise: "Enterprise" };
  const LABEL_STATUS_SUB = {
    trial: "Trial", active: "Aktif", grace_period: "Grace Period",
    expired: "Kedaluwarsa", suspended: "Ditangguhkan", cancelled: "Dibatalkan",
  };
  const BADGE_STATUS_SUB = {
    trial: "badge-libur", active: "badge-success", grace_period: "badge-warning",
    expired: "badge-danger", suspended: "badge-danger", cancelled: "badge-danger",
  };
  const LABEL_STATUS_INVOICE = {
    pending: "Menunggu Pembayaran", paid: "Berhasil", denied: "Ditolak",
    cancelled: "Dibatalkan", expired: "Kedaluwarsa",
  };
  const BADGE_STATUS_INVOICE = {
    pending: "badge-warning", paid: "badge-success", denied: "badge-danger",
    cancelled: "badge-danger", expired: "badge-danger",
  };

  function formatWaktu(iso) {
    if (!iso) return "-";
    const [tanggal, jam] = iso.split("T");
    return `${MugenUI.formatTanggal(tanggal)} ${jam || ""}`.trim();
  }

  // Invoice PAID paling baru yang periode_selesai-nya masih di masa depan
  // -- SATU-SATUNYA sumber "periode aktif sekarang" di frontend (backend
  // TIDAK menyimpan tanggal ini di tenant_subscriptions sama sekali, lihat
  // catatan panjang di billing_webhook.py soal alasannya).
  function invoicePeriodeAktif(invoices) {
    const now = new Date().toISOString();
    const kandidat = (invoices || []).filter((inv) => inv.status === "paid" && inv.periode_selesai && inv.periode_selesai > now);
    if (!kandidat.length) return null;
    return kandidat.reduce((a, b) => (a.periode_selesai > b.periode_selesai ? a : b));
  }

  let _snapLoadPromise = null;
  function muatSnapJs(src, clientKey) {
    if (window.snap) return Promise.resolve();
    if (_snapLoadPromise) return _snapLoadPromise;
    _snapLoadPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.setAttribute("data-client-key", clientKey);
      script.onload = () => resolve();
      script.onerror = () => {
        _snapLoadPromise = null;
        reject(new Error("Gagal memuat modul pembayaran Midtrans. Periksa koneksi internet Anda."));
      };
      document.head.appendChild(script);
    });
    return _snapLoadPromise;
  }

  function pesanError(e) {
    return (e && e.detail && e.detail.detail) ? e.detail.detail : (e.message || "Terjadi kesalahan.");
  }

  function renderStatusCard(root, sub, invoices, packages, config) {
    const card = MugenUI.el("div", { class: "card" });
    root.appendChild(card);
    card.appendChild(MugenUI.el("h2", {}, "Paket & Status Langganan"));

    if (sub.akses_diblokir) {
      card.appendChild(MugenUI.el("div", { class: "login-error", style: "margin-bottom:12px;" },
        `Akses toko ini sedang dibatasi karena status subscription "${LABEL_STATUS_SUB[sub.status] || sub.status}". ` +
        "Selesaikan pembayaran di bawah untuk mengaktifkan kembali."));
    }
    if (!config.enabled) {
      card.appendChild(MugenUI.el("div", { class: "login-error", style: "margin-bottom:12px;" },
        "Pembayaran online belum aktif untuk toko ini -- hubungi penyedia layanan."));
    }

    const periodeAktif = invoicePeriodeAktif(invoices);
    const ringkasan = MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:24px;margin-bottom:8px;" }, [
      MugenUI.el("div", {}, [
        MugenUI.el("div", { class: "subtitle" }, "Paket"),
        MugenUI.el("div", { style: "font-weight:700;font-size:16px;" }, LABEL_PACKAGE[sub.package] || sub.package),
      ]),
      MugenUI.el("div", {}, [
        MugenUI.el("div", { class: "subtitle" }, "Status"),
        MugenUI.el("span", { class: "badge " + (BADGE_STATUS_SUB[sub.status] || "") },
          LABEL_STATUS_SUB[sub.status] || sub.status),
      ]),
      MugenUI.el("div", {}, [
        MugenUI.el("div", { class: "subtitle" }, "Periode Aktif Berakhir"),
        MugenUI.el("div", { style: "font-weight:700;" }, periodeAktif ? formatWaktu(periodeAktif.periode_selesai) : "-"),
      ]),
    ]);
    card.appendChild(ringkasan);
  }

  async function mulaiCheckout(packageId, config, onSelesai) {
    let invoice;
    try {
      invoice = await MugenUI.withLoading(
        () => MugenApi.post("/api/billing/checkout", { package_id: packageId }),
        { message: "Menyiapkan pembayaran…" },
      );
    } catch (e) {
      MugenUI.toast(pesanError(e), "error");
      return;
    }

    try {
      await muatSnapJs(config.snap_js_url, config.client_key);
    } catch (e) {
      MugenUI.toast(e.message, "error");
      return;
    }

    window.snap.pay(invoice.snap_token, {
      onSuccess: () => {
        MugenUI.toast("Pembayaran berhasil, memperbarui status langganan…", "info", { force: true });
        setTimeout(onSelesai, 2000);
      },
      onPending: () => {
        MugenUI.toast("Pembayaran sedang diproses -- paket akan aktif otomatis setelah dikonfirmasi.", "info", { force: true });
        onSelesai();
      },
      onError: () => {
        MugenUI.toast("Pembayaran gagal. Silakan coba lagi.", "error");
        onSelesai();
      },
      onClose: onSelesai,
    });
  }

  async function mulaiDowngrade(paket, onSelesai) {
    const ok = await MugenUI.confirmModal({
      title: "Downgrade Paket",
      message: `Pindah ke paket "${paket.nama}" sekarang? Perubahan berlaku langsung tanpa pembayaran.`,
      confirmText: "Ya, Downgrade",
    });
    if (!ok) return;
    try {
      await MugenUI.withLoading(() => MugenApi.post("/api/billing/downgrade", { package_id: paket.id }),
        { message: "Memproses downgrade…" });
    } catch (e) {
      MugenUI.toast(pesanError(e), "error");
      return;
    }
    onSelesai();
  }

  function kartuFitur(fitur) {
    if (!fitur || !fitur.length) return MugenUI.el("div", { class: "subtitle" }, "Tidak ada fitur tercatat.");
    const wrap = MugenUI.el("div", { style: "display:flex;flex-wrap:wrap;gap:6px;margin:10px 0;" });
    for (const f of fitur) wrap.appendChild(MugenUI.el("span", { class: "badge badge-libur" }, f.nama));
    return wrap;
  }

  function renderPaketCard(root, sub, config, packages, onSelesai) {
    const card = MugenUI.el("div", { class: "card" });
    root.appendChild(card);
    card.appendChild(MugenUI.el("h2", {}, "Pilih Paket"));
    card.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Upgrade langsung dibayar lewat Midtrans (VA/QRIS/kartu). Downgrade & Perpanjang paket yang sama TIDAK memerlukan pembayaran baru di sini kecuali memang paket berbayar."));

    const current = packages.find((p) => p.kode === sub.package) || null;
    const grid = MugenUI.el("div", { class: "grid-cards" });
    card.appendChild(grid);

    for (const paket of packages) {
      const isCurrent = paket.kode === sub.package;
      const box = MugenUI.el("div", { class: "card", style: "margin-bottom:0;" + (isCurrent ? "border-color:var(--accent);" : "") });
      box.appendChild(MugenUI.el("h2", {}, paket.nama));
      box.appendChild(MugenUI.el("div", { style: "font-size:20px;font-weight:700;" }, MugenUI.formatRupiah(paket.harga)));
      box.appendChild(MugenUI.el("div", { class: "subtitle" }, `per ${paket.durasi_hari} hari`));
      if (paket.deskripsi) box.appendChild(MugenUI.el("div", { style: "margin-top:8px;" }, paket.deskripsi));
      box.appendChild(kartuFitur(paket.fitur));

      let btn;
      if (isCurrent) {
        box.appendChild(MugenUI.el("span", { class: "badge badge-success", style: "margin-bottom:10px;display:inline-block;" }, "Paket Aktif"));
        if (paket.harga > 0) {
          btn = MugenUI.el("button", { class: "btn-primary" }, "Perpanjang");
          btn.addEventListener("click", () => mulaiCheckout(paket.id, config, onSelesai));
        }
      } else if (current && paket.urutan > current.urutan) {
        btn = MugenUI.el("button", { class: "btn-primary" }, "Upgrade");
        btn.addEventListener("click", () => mulaiCheckout(paket.id, config, onSelesai));
      } else if (current && paket.urutan < current.urutan) {
        btn = MugenUI.el("button", {}, "Downgrade");
        btn.addEventListener("click", () => mulaiDowngrade(paket, onSelesai));
      } else {
        btn = MugenUI.el("button", { class: "btn-primary" }, "Pilih Paket");
        btn.addEventListener("click", () => mulaiCheckout(paket.id, config, onSelesai));
      }
      if (btn) box.appendChild(MugenUI.el("div", {}, btn));
      grid.appendChild(box);
    }
  }

  function renderInvoiceCard(root, invoices) {
    const card = MugenUI.el("div", { class: "card" });
    root.appendChild(card);
    card.appendChild(MugenUI.el("h2", {}, "Riwayat Pembayaran"));

    const kolom = [
      { key: "nomor_invoice", label: "No. Invoice" },
      { key: "package_nama", label: "Paket" },
      { key: "jumlah", label: "Jumlah", format: (v) => MugenUI.formatRupiah(v) },
      { key: "metode_pembayaran", label: "Metode", format: (v) => v || "-" },
      { key: "status", label: "Status", format: (v) => MugenUI.el("span", { class: "badge " + (BADGE_STATUS_INVOICE[v] || "") }, LABEL_STATUS_INVOICE[v] || v) },
      { key: "created_at", label: "Tanggal", format: (v) => formatWaktu(v) },
    ];
    card.appendChild(MugenUI.buildTable(kolom, invoices, { emptyText: "Belum ada riwayat pembayaran." }));
  }

  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Billing & Pembayaran"));

    const loadingCard = MugenUI.el("div", { class: "card" }, "Memuat data billing…");
    root.appendChild(loadingCard);

    let sub, config, packages, invoices;
    try {
      [sub, config, packages, invoices] = await Promise.all([
        MugenApi.get("/api/subscription/me"),
        MugenApi.get("/api/billing/config"),
        MugenApi.get("/api/billing/packages"),
        MugenApi.get("/api/billing/invoices"),
      ]);
    } catch (e) {
      loadingCard.textContent = pesanError(e);
      return;
    }
    loadingCard.remove();

    renderStatusCard(root, sub, invoices, packages, config);
    renderPaketCard(root, sub, config, packages, () => render(root));
    renderInvoiceCard(root, invoices);
  }

  return { render };
})();
