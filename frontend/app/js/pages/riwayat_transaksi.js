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

  // AUDIT (Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant --
  // perbaikan pasca-audit kesiapan): status YANG BELUM FINAL saja yang boleh
  // dicek ulang manual ke provider (POST .../cek-ulang) -- jalur ini KHUSUS
  // untuk transaksi yang macet karena webhook TIDAK PERNAH sampai sama
  // sekali, TIDAK PERNAH mengizinkan staff "mengklaim" status sendiri (lihat
  // routers/booking.py::cek_ulang_transaksi_gateway() -- server yang
  // memanggil ulang provider, bukan menerima input status dari sini).
  const STATUS_BOLEH_CEK_ULANG = new Set(["menunggu_pembayaran", "diproses"]);

  function bukaDetail(transaksi, { onSelesai } = {}) {
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

    let modal;
    if (STATUS_BOLEH_CEK_ULANG.has(transaksi.status_pembayaran)) {
      const btnCekUlang = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:16px;" },
        "Cek Ulang ke Provider");
      btnCekUlang.addEventListener("click", async () => {
        try {
          const updated = await MugenUI.withButtonLoading(btnCekUlang,
            () => MugenApi.post(`/api/booking/transactions/${transaksi.id}/cek-ulang`));
          modal.close();
          MugenUI.toast("Status berhasil diperbarui dari provider.", "success", { force: true });
          if (onSelesai) onSelesai();
          bukaDetail(updated, { onSelesai });
        } catch (e) {
          MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
        }
      });
      body.push(btnCekUlang);
      body.push(MugenUI.el("div", { class: "subtitle", style: "margin-top:6px;" },
        "Pakai ini HANYA kalau status di sini tidak kunjung berubah walau customer sudah membayar -- server akan menanyakan ulang status LANGSUNG ke provider."));
    }
    modal = MugenUI.infoModal({ title: `Detail Transaksi — ${transaksi.nomor_transaksi}`, body });
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

    // BUGFIX (audit, race condition): dulu tidak ada penjagaan urutan
    // request -- klik ganda "Terapkan Filter" bisa membuat dua fetch
    // tumpang tindih selesai TIDAK berurutan, hasil filter yang LEBIH
    // LAMA bisa menimpa hasil filter yang lebih baru.
    let urutanTerkini = 0;

    async function muatDaftar() {
      const urutanSaya = ++urutanTerkini;
      listBody.innerHTML = "";
      listBody.appendChild(MugenUI.skeleton("table", { cols: 6, rows: 4 }));
      try {
        const params = new URLSearchParams();
        if (inputMulai.value) params.set("tanggal_mulai", inputMulai.value);
        if (inputSelesai.value) params.set("tanggal_selesai", inputSelesai.value + "T23:59:59");
        if (selStatus.value) params.set("status_pembayaran", selStatus.value);
        const data = await MugenApi.get(`/api/booking/transactions?${params.toString()}`);
        if (urutanSaya !== urutanTerkini) return; // respons basi, biarkan panggilan terbaru yang merender
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
                    bukaDetail(detail, { onSelesai: muatDaftar });
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
        if (urutanSaya !== urutanTerkini) return; // respons basi, jangan timpa hasil yang lebih baru
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.errorState(e.message));
      }
    }

    btnFilter.addEventListener("click", muatDaftar);
    await muatDaftar();
  }

  return { render };
})();

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js
// (bukan <script> biasa lagi, lihat index.html/router.js) -- top-level
// "const" TIDAK menempel ke objek window di browser (beda dari "var"),
// jadi page_loader.js TIDAK BISA mendeteksi lewat window.PageRiwayatTransaksi begitu saja
// setelah script ini selesai dimuat. Baris di bawah ini SATU-SATUNYA
// perubahan di file ini untuk mendukung lazy-load -- expose eksplisit ke
// window supaya page_loader.js bisa memverifikasi modul benar-benar
// berhasil dimuat sebelum memanggil render()-nya.
window.PageRiwayatTransaksi = PageRiwayatTransaksi;
