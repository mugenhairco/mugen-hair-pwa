// pages/riwayat_transaksi.js — Implementasi Payment Gateway & Riwayat
// Transaksi Multi-Tenant: Riwayat Transaksi Payment Gateway booking milik
// TOKO INI SENDIRI (Owner/Admin/staff, lihat nav.js grup Keuangan).
// Backend (routers/booking.py::list_transaksi_gateway()) SELALU
// men-scope tenant_id dari akun login -- endpoint ini TIDAK PERNAH
// menerima tenant_id dari parameter apa pun, jadi toko lain tidak pernah
// bisa terlihat di sini apa pun yang dikirim dari sisi frontend.

const PageRiwayatTransaksi = (() => {
  const STATUS_LABEL = {
    menunggu_pembayaran: "Menunggu Pembayaran",
    diproses: "Sedang Diproses",
    berhasil: "Berhasil",
    gagal: "Gagal",
    kedaluwarsa: "Kedaluwarsa",
    dibatalkan: "Dibatalkan",
    refund: "Refund",
  };
  const STATUS_BADGE = {
    menunggu_pembayaran: "badge-libur",
    diproses: "badge-libur",
    berhasil: "badge-success",
    gagal: "badge-danger",
    kedaluwarsa: "badge-danger",
    dibatalkan: "badge-danger",
    refund: "badge-warning",
  };

  function statusBadge(status) {
    return MugenUI.el("span", { class: "badge" + (STATUS_BADGE[status] ? " " + STATUS_BADGE[status] : "") },
      STATUS_LABEL[status] || status);
  }

  function waktuLengkap(iso) {
    if (!iso) return "-";
    const [tanggal, jam] = iso.split("T");
    return `${MugenUI.formatTanggal(tanggal)} ${(jam || "").slice(0, 8)}`.trim();
  }

  function bukaDetail(transaksi) {
    const body = [
      MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-bottom:10px;" }, [
        MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Status"), statusBadge(transaksi.status_pembayaran)]),
        MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Nominal"), MugenUI.el("div", {}, MugenUI.formatRupiah(transaksi.nominal))]),
      ]),
      MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-bottom:10px;" }, [
        MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Metode"), MugenUI.el("div", {}, transaksi.metode_pembayaran || "-")]),
        MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Channel"), MugenUI.el("div", {}, transaksi.channel_pembayaran || "-")]),
      ]),
      MugenUI.el("div", { style: "margin-bottom:10px;" }, [
        MugenUI.el("div", { class: "subtitle" }, "Waktu Dibuat"), MugenUI.el("div", {}, waktuLengkap(transaksi.created_at)),
      ]),
      MugenUI.el("div", { style: "margin-bottom:10px;" }, [
        MugenUI.el("div", { class: "subtitle" }, "Waktu Dibayar"), MugenUI.el("div", {}, waktuLengkap(transaksi.paid_at)),
      ]),
      MugenUI.el("div", { style: "margin-bottom:10px;" }, [
        MugenUI.el("div", { class: "subtitle" }, "Waktu Webhook Terakhir Diterima"), MugenUI.el("div", {}, waktuLengkap(transaksi.updated_at)),
      ]),
      MugenUI.el("div", { style: "margin-bottom:10px;" }, [
        MugenUI.el("div", { class: "subtitle" }, "Transaction ID (Provider)"), MugenUI.el("div", {}, transaksi.transaction_id_provider || "-"),
      ]),
      MugenUI.el("div", { style: "margin-bottom:10px;" }, [
        MugenUI.el("div", { class: "subtitle" }, "Reference ID (Provider)"), MugenUI.el("div", {}, transaksi.reference_id_provider || "-"),
      ]),
      MugenUI.el("h3", { style: "margin-top:16px;" }, "Riwayat Perubahan Status"),
      MugenUI.buildTable(
        [
          { key: "waktu", label: "Waktu", format: waktuLengkap },
          { key: "status_lama", label: "Dari", format: (v) => STATUS_LABEL[v] || v || "-" },
          { key: "status_baru", label: "Ke", format: (v) => STATUS_LABEL[v] || v },
        ],
        transaksi.status_log || [],
        { emptyText: "Belum ada perubahan status." },
      ),
    ];
    MugenUI.infoModal({ title: `Detail Transaksi — ${transaksi.nomor_transaksi}`, body });
  }

  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Riwayat Transaksi"));
    root.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Riwayat transaksi Payment Gateway booking customer. Status pembayaran HANYA diperbarui otomatis begitu dikonfirmasi resmi oleh provider (webhook), tidak bisa diubah manual."));

    const filterCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    root.appendChild(filterCard);
    root.appendChild(listCard);

    const inputMulai = MugenUI.el("input", { type: "date" });
    const inputSelesai = MugenUI.el("input", { type: "date" });
    const selStatus = MugenUI.el("select");
    selStatus.appendChild(MugenUI.el("option", { value: "" }, "Semua Status"));
    for (const [k, label] of Object.entries(STATUS_LABEL)) selStatus.appendChild(MugenUI.el("option", { value: k }, label));
    const btnFilter = MugenUI.el("button", { class: "btn-primary" }, "Terapkan Filter");

    filterCard.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:8px;align-items:flex-end;" }, [
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Dari Tanggal"), inputMulai]),
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Sampai Tanggal"), inputSelesai]),
      MugenUI.el("div", {}, [MugenUI.el("label", {}, "Status"), selStatus]),
      btnFilter,
    ]));

    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    async function muatDaftar() {
      listBody.innerHTML = "";
      listBody.appendChild(MugenUI.skeleton("table", { cols: 6, rows: 4 }));
      try {
        const params = new URLSearchParams();
        if (inputMulai.value) params.set("tanggal_mulai", inputMulai.value);
        if (inputSelesai.value) params.set("tanggal_selesai", inputSelesai.value + "T23:59:59");
        if (selStatus.value) params.set("status_pembayaran", selStatus.value);
        const data = await MugenApi.get(`/api/booking/transactions?${params.toString()}`);
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.buildTable(
          [
            { key: "nomor_transaksi", label: "No. Transaksi" },
            { key: "created_at", label: "Tanggal", format: waktuLengkap },
            { key: "customer_nama", label: "Customer" },
            { key: "barber_nama", label: "Barber" },
            { key: "layanan", label: "Layanan" },
            { key: "nominal", label: "Nominal", format: MugenUI.formatRupiah },
            { key: "channel_pembayaran", label: "Channel", format: (v) => v || "-" },
            { key: "status_pembayaran", label: "Status", format: statusBadge },
            {
              key: "aksi", label: "Aksi", format: (_, t) => {
                const btn = MugenUI.el("button", {}, "Detail");
                btn.addEventListener("click", async () => {
                  try {
                    const detail = await MugenUI.withButtonLoading(btn, () => MugenApi.get(`/api/booking/transactions/${t.id}`));
                    bukaDetail(detail);
                  } catch (e) {
                    MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                  }
                });
                return btn;
              },
            },
          ],
          data,
          { emptyText: "Belum ada transaksi Payment Gateway." },
        ));
      } catch (e) {
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.errorState(e.message));
      }
    }

    btnFilter.addEventListener("click", muatDaftar);
    await muatDaftar();
  }

  return { render };
})();
