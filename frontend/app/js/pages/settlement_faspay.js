// pages/settlement_faspay.js — Settlement Faspay per Terminal (Tenant)
// "Terminal" = toko/tenant ini sendiri (keputusan eksplisit Owner). Fokus
// HANYA transaksi Faspay SNAP Advance -- backend (routers/faspay_settlement.py)
// SELALU men-scope tenant_id dari akun login, TIDAK PERNAH menerima
// tenant_id dari parameter apa pun di sini.

const PageSettlementFaspay = (() => {
  const STATUS_LABEL = { RECONCILED: "Reconciled", WARNING: "Warning", FINAL_MISMATCH: "Final Mismatch" };
  const STATUS_BADGE = { RECONCILED: "badge-success", WARNING: "badge-warning", FINAL_MISMATCH: "badge-danger" };
  const STATUS_ICON = { RECONCILED: "🟢", WARNING: "🟡", FINAL_MISMATCH: "🔴" };

  function statusBadge(status) {
    return MugenUI.el("span", { class: "badge" + (STATUS_BADGE[status] ? " " + STATUS_BADGE[status] : "") },
      `${STATUS_ICON[status] || ""} ${STATUS_LABEL[status] || status}`.trim());
  }

  const MATCH_LABEL = {
    match: "Match", pending_faspay: "Pending Faspay", final_match: "Match (Final)",
    missing_di_faspay: "Missing in Faspay", amount_mismatch: "Amount Mismatch",
    status_mismatch: "Status Mismatch", reference_mismatch: "Reference Mismatch",
    tidak_bisa_dicek: "Tidak Bisa Dicek",
  };

  function waktuLengkap(iso) {
    if (!iso) return "-";
    const [tanggal, jam] = iso.split("T");
    return `${MugenUI.formatTanggal(tanggal)} ${(jam || "").slice(0, 8)}`.trim();
  }

  function kolomItem() {
    return [
      { key: "order_id", label: "Order ID" },
      { key: "reference_id_provider", label: "Reference Faspay", format: (v) => v || "-" },
      { key: "payment_method", label: "Metode", format: (v) => (v || "-").toUpperCase() },
      { key: "nominal", label: "Nominal", format: MugenUI.formatRupiah },
      { key: "status_pembayaran", label: "Status" },
      { key: "timestamp_transaksi", label: "Waktu", format: waktuLengkap },
      { key: "match_status", label: "Real-time", format: (v) => MATCH_LABEL[v] || v },
      { key: "h1_match_status", label: "Final (H+1)", format: (v) => (v ? MATCH_LABEL[v] || v : "Belum dijalankan") },
    ];
  }

  function bukaDetailSettlement(settlement) {
    const body = [
      MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-bottom:10px;" }, [
        MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Status"), statusBadge(settlement.status_rekonsiliasi)]),
        MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Tanggal"), MugenUI.el("div", {}, MugenUI.formatTanggal(settlement.tanggal))]),
        MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Diajukan Oleh"), MugenUI.el("div", {}, settlement.dibuat_oleh_nama)]),
      ]),
      MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-bottom:10px;" }, [
        MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Jumlah Transaksi"), MugenUI.el("div", {}, String(settlement.jumlah_transaksi))]),
        MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Total Nominal"), MugenUI.el("div", {}, MugenUI.formatRupiah(settlement.total_nominal))]),
        MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Match / Warning"), MugenUI.el("div", {}, `${settlement.jumlah_match} / ${settlement.jumlah_warning}`)]),
      ]),
      settlement.h1_dijalankan_at
        ? MugenUI.el("div", { style: "margin-bottom:10px;" }, [
            MugenUI.el("div", { class: "subtitle" }, "Rekonsiliasi H+1"),
            MugenUI.el("div", {}, `${waktuLengkap(settlement.h1_dijalankan_at)} oleh ${settlement.h1_dijalankan_oleh} -- ${settlement.jumlah_final_mismatch} bermasalah`),
          ])
        : MugenUI.el("div", { class: "subtitle", style: "margin-bottom:10px;" }, "Rekonsiliasi H+1 belum dijalankan Super Admin."),
      MugenUI.el("h3", { style: "margin-top:16px;" }, "Detail Transaksi"),
      MugenUI.buildTable(kolomItem(), settlement.items || [], { emptyText: "Tidak ada transaksi." }),
    ];
    MugenUI.infoModal({ title: `Settlement Faspay -- ${MugenUI.formatTanggal(settlement.tanggal)}`, body });
  }

  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Settlement Faspay"));
    root.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Closing harian transaksi Faspay toko ini. Setelah disubmit, settlement dikunci dan tidak bisa diubah -- rekonsiliasi final (H+1) dijalankan Super Admin begitu data hari berikutnya tersedia."));

    const level = await MugenMenuAccess.get("settlement_faspay");
    if (level === "none") {
      root.appendChild(MugenUI.emptyState("Anda tidak memiliki akses ke menu ini."));
      return;
    }
    const bolehSubmit = level === "write";

    const closingCard = MugenUI.el("div", { class: "card" });
    const historyCard = MugenUI.el("div", { class: "card" });
    root.appendChild(closingCard);
    root.appendChild(historyCard);

    closingCard.appendChild(MugenUI.el("h2", {}, "Closing Faspay"));
    const inputTanggal = MugenUI.el("input", { type: "date", value: MugenUI.isoHariIniWib() });
    const btnMuat = MugenUI.el("button", { class: "btn-primary" }, "Muat Transaksi");
    closingCard.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:8px;align-items:flex-end;" }, [
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Tanggal"), inputTanggal]),
      btnMuat,
    ]));

    const previewBody = MugenUI.el("div", { style: "margin-top:14px;" });
    closingCard.appendChild(previewBody);

    async function muatPreview() {
      const tanggal = inputTanggal.value;
      if (!tanggal) return;
      previewBody.innerHTML = "";
      previewBody.appendChild(MugenUI.skeleton("table", { cols: 6, rows: 3 }));
      try {
        const sudahAda = (await MugenApi.get(`/api/settlement-faspay?tanggal_mulai=${tanggal}&tanggal_selesai=${tanggal}`))
          .some((s) => s.tanggal === tanggal);
        const ringkas = await MugenApi.get(`/api/settlement-faspay/preview?tanggal=${tanggal}`);
        previewBody.innerHTML = "";

        const ringkasanRow = MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-bottom:12px;" }, [
          MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Jumlah Transaksi"), MugenUI.el("div", { style: "font-weight:700;" }, String(ringkas.jumlah_transaksi))]),
          MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Total Nominal"), MugenUI.el("div", { style: "font-weight:700;" }, MugenUI.formatRupiah(ringkas.total_nominal))]),
          MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Match"), MugenUI.el("div", { style: "font-weight:700;" }, String(ringkas.jumlah_match))]),
          MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Warning"), MugenUI.el("div", { style: "font-weight:700;" }, String(ringkas.jumlah_warning))]),
          MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Status"), statusBadge(ringkas.status_rekonsiliasi)]),
        ]);
        previewBody.appendChild(ringkasanRow);
        previewBody.appendChild(MugenUI.buildTable(
          [
            { key: "order_id", label: "Order ID" },
            { key: "payment_method", label: "Metode", format: (v) => (v || "-").toUpperCase() },
            { key: "nominal", label: "Nominal", format: MugenUI.formatRupiah },
            { key: "status_pembayaran", label: "Status" },
            { key: "timestamp_transaksi", label: "Waktu", format: waktuLengkap },
            { key: "match_status", label: "Real-time", format: (v) => MATCH_LABEL[v] || v },
          ],
          ringkas.items,
          { emptyText: "Belum ada transaksi Faspay pada tanggal ini." },
        ));

        if (!bolehSubmit) return;
        if (sudahAda) {
          previewBody.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:12px;" },
            "Settlement untuk tanggal ini sudah pernah diajukan -- lihat Riwayat Settlement di bawah."));
          return;
        }
        const btnSubmit = MugenUI.el("button", { class: "btn-primary", style: "margin-top:12px;" }, "Submit Settlement");
        btnSubmit.addEventListener("click", async () => {
          const ok = await MugenUI.confirmModal({
            title: "Submit Settlement Faspay",
            message: `Kirim closing ${ringkas.jumlah_transaksi} transaksi (${MugenUI.formatRupiah(ringkas.total_nominal)}) untuk tanggal ${MugenUI.formatTanggal(tanggal)}? Setelah disubmit, settlement TIDAK BISA diubah lagi.`,
            confirmText: "Ya, Submit",
          });
          if (!ok) return;
          try {
            await MugenUI.withButtonLoading(btnSubmit, () => MugenApi.post(`/api/settlement-faspay?tanggal=${tanggal}`));
            MugenUI.toast("Settlement Faspay berhasil disubmit.", "success", { force: true });
            await muatPreview();
            await muatRiwayat();
          } catch (e) {
            MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
          }
        });
        previewBody.appendChild(btnSubmit);
      } catch (e) {
        previewBody.innerHTML = "";
        previewBody.appendChild(MugenUI.errorState(e.message));
      }
    }
    btnMuat.addEventListener("click", muatPreview);

    historyCard.appendChild(MugenUI.el("h2", {}, "Riwayat Settlement"));
    const historyBody = MugenUI.el("div");
    historyCard.appendChild(historyBody);

    async function muatRiwayat() {
      historyBody.innerHTML = "";
      historyBody.appendChild(MugenUI.skeleton("table", { cols: 6, rows: 3 }));
      try {
        const data = await MugenApi.get("/api/settlement-faspay");
        historyBody.innerHTML = "";
        historyBody.appendChild(MugenUI.buildTable(
          [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            { key: "dibuat_oleh_nama", label: "Diajukan Oleh" },
            { key: "jumlah_transaksi", label: "Jumlah Transaksi" },
            { key: "total_nominal", label: "Total Nominal", format: MugenUI.formatRupiah },
            { key: "status_rekonsiliasi", label: "Status", format: statusBadge },
            {
              key: "aksi", label: "Aksi", format: (_, s) => {
                const btn = MugenUI.el("button", {}, "Detail");
                btn.addEventListener("click", async () => {
                  try {
                    const detail = await MugenUI.withButtonLoading(btn, () => MugenApi.get(`/api/settlement-faspay/${s.id}`));
                    bukaDetailSettlement(detail);
                  } catch (e) {
                    MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                  }
                });
                return btn;
              },
            },
          ],
          data,
          { emptyText: "Belum ada settlement diajukan." },
        ));
      } catch (e) {
        historyBody.innerHTML = "";
        historyBody.appendChild(MugenUI.errorState(e.message));
      }
    }

    await muatPreview();
    await muatRiwayat();
  }

  return { render };
})();

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js (lihat
// catatan identik di pages/riwayat_transaksi.js) -- expose eksplisit ke
// window supaya page_loader.js bisa memverifikasi modul berhasil dimuat.
window.PageSettlementFaspay = PageSettlementFaspay;
