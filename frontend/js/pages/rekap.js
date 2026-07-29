// pages/rekap.js

const PageRekap = (() => {
  function tombolDownloadPdf(onClick) {
    const btn = MugenUI.el("button", {}, "Download PDF");
    btn.addEventListener("click", async () => {
      try {
        await MugenUI.withLoading(onClick, { message: "Menyiapkan PDF…" });
      } catch (e) {
        MugenUI.toast(e.message, "error");
      }
    });
    return btn;
  }

  async function render(root) {
    const user = MugenState.getUser();
    const isAdmin = user.role === "admin" || user.role === "staff";
    const today = new Date();

    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Rekap"));

    const tabs = ["Transaksi", "Bulanan", ...(isAdmin ? ["Pengeluaran"] : [])];
    let activeTab = "Transaksi";

    const tabBar = MugenUI.el("div", { class: "tabs" });
    const body = MugenUI.el("div");
    root.appendChild(tabBar);
    root.appendChild(body);

    // Rekap Bulanan murni perhitungan komisi/tips/uang harian jasa potong
    // rambut -- TETAP khusus Barber (barbersOnly). Rekap Transaksi
    // menampilkan/memfilter SELURUH karyawan (barbersOnly + Kasir/OB/Kru,
    // lewat karyawanAll) sesuai permintaan revisi Karyawan Non-Barber --
    // barber non-barber otomatis tidak akan pernah punya baris transaksi
    // (Input Data tidak pernah membiarkan itu dibuat untuk non-barber),
    // jadi filter itu valid, hanya hasilnya kosong.
    let barbersOnly = [];
    let karyawanAll = [];
    if (isAdmin) {
      try {
        [barbersOnly, karyawanAll] = await Promise.all([
          MugenApi.get("/api/input-data/barbers", { useCache: true }),
          MugenApi.get("/api/input-data/karyawan", { useCache: true }),
        ]);
      } catch (e) { /* filter tetap opsional kalau gagal dimuat */ }
    }

    function renderTabs() {
      tabBar.innerHTML = "";
      for (const t of tabs) {
        const btn = MugenUI.el("button", { class: activeTab === t ? "active" : "" }, t);
        btn.addEventListener("click", () => { activeTab = t; renderTabs(); renderBody(); });
        tabBar.appendChild(btn);
      }
    }

    function filterBar({ withBarber = true, daftarKaryawan = barbersOnly, labelSemua = "Semua Barber" } = {}) {
      const selBulan = MugenUI.el("select");
      for (let m = 1; m <= 12; m++) selBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
      selBulan.value = String(today.getMonth() + 1);
      const selTahun = MugenUI.el("select");
      for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) selTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
      selTahun.value = String(today.getFullYear());
      const selBarber = withBarber && isAdmin ? MugenUI.el("select") : null;
      if (selBarber) {
        selBarber.appendChild(MugenUI.el("option", { value: "" }, labelSemua));
        for (const b of daftarKaryawan) selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
      }
      const row = MugenUI.el("div", { class: "row", style: "flex:none;margin-bottom:14px;" },
        [selBulan, selTahun, ...(selBarber ? [selBarber] : [])]);
      return { row, selBulan, selTahun, selBarber };
    }

    async function renderBody() {
      body.innerHTML = "";
      if (activeTab === "Transaksi") await renderTransaksi();
      else if (activeTab === "Bulanan") await renderBulanan();
      else await renderPengeluaran();
    }

    async function renderTransaksi() {
      const { row, selBulan, selTahun, selBarber } = filterBar({ daftarKaryawan: karyawanAll, labelSemua: "Semua Karyawan" });

      // Periode tanggal TAMBAHAN khusus untuk cetak PDF (filter Bulan+Tahun
      // di atas untuk tampilan layar TIDAK berubah) -- kalau diisi,
      // menggantikan Bulan+Tahun sebagai periode PDF supaya bisa cetak
      // rentang custom (mis. per 2 minggu), default kosong (pakai Bulan+
      // Tahun seperti biasa).
      const inputDariTanggal = MugenUI.el("input", { type: "date" });
      const inputSampaiTanggal = MugenUI.el("input", { type: "date" });
      const pdfRow = MugenUI.el("div", { class: "row", style: "flex:none;margin-bottom:14px;align-items:center;" }, [
        MugenUI.el("span", { class: "subtitle", style: "margin:0;" }, "Periode PDF (opsional):"),
        inputDariTanggal, inputSampaiTanggal,
      ]);
      pdfRow.appendChild(tombolDownloadPdf(() => {
        const qs = new URLSearchParams();
        if (inputDariTanggal.value && inputSampaiTanggal.value) {
          qs.set("tanggal_mulai", inputDariTanggal.value);
          qs.set("tanggal_selesai", inputSampaiTanggal.value);
        } else {
          qs.set("tahun", selTahun.value);
          qs.set("bulan", selBulan.value);
        }
        if (selBarber && selBarber.value) qs.set("barber_id", selBarber.value);
        return MugenApi.downloadFile(`/api/rekap/transaksi/pdf?${qs}`, `rekap_transaksi_${selTahun.value}-${selBulan.value}.pdf`);
      }));

      const tableWrap = MugenUI.el("div");
      body.appendChild(row);
      body.appendChild(pdfRow);
      body.appendChild(tableWrap);

      async function load() {
        tableWrap.innerHTML = "Memuat...";
        try {
          const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
          if (selBarber && selBarber.value) qs.set("barber_id", selBarber.value);
          const data = await MugenApi.get(`/api/rekap/transaksi?${qs}`, { useCache: true });
          tableWrap.innerHTML = "";
          if (data.__offline) tableWrap.appendChild(MugenUI.offlineBanner(data.__cachedAt));
          const rows = Array.isArray(data) ? data : [];
          tableWrap.appendChild(MugenUI.buildTable(
            [
              { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
              { key: "nama_barber", label: "Nama" },
              { key: "daftar_service", label: "Service" },
              { key: "jumlah_service", label: "Jml Service" },
              { key: "uang_harian", label: "Uang Harian", format: MugenUI.formatRupiah },
              { key: "tips", label: "Tips", format: MugenUI.formatRupiah },
              { key: "pendapatan", label: "Pendapatan", format: MugenUI.formatRupiah },
              { key: "keterangan", label: "Ket.", format: (v) => v ? MugenUI.el("span", { class: "badge badge-libur" }, v) : "-" },
            ],
            rows,
          ));
        } catch (e) {
          tableWrap.innerHTML = "";
          tableWrap.appendChild(MugenUI.el("div", {}, e.message));
        }
      }
      selBulan.addEventListener("change", () => MugenUI.withLoading(load));
      selTahun.addEventListener("change", () => MugenUI.withLoading(load));
      if (selBarber) selBarber.addEventListener("change", () => MugenUI.withLoading(load));
      load();
    }

    async function renderBulanan() {
      const { row, selBulan, selTahun, selBarber } = filterBar();
      row.appendChild(tombolDownloadPdf(() => {
        const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
        if (selBarber && selBarber.value) qs.set("barber_id", selBarber.value);
        return MugenApi.downloadFile(`/api/rekap/bulanan/pdf?${qs}`, `rekap_bulanan_${selTahun.value}-${selBulan.value}.pdf`);
      }));
      const tableWrap = MugenUI.el("div");
      body.appendChild(row);
      body.appendChild(tableWrap);

      async function load() {
        tableWrap.innerHTML = "Memuat...";
        try {
          const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
          if (selBarber && selBarber.value) qs.set("barber_id", selBarber.value);
          const data = await MugenApi.get(`/api/rekap/bulanan?${qs}`, { useCache: true });
          tableWrap.innerHTML = "";
          if (data.__offline) tableWrap.appendChild(MugenUI.offlineBanner(data.__cachedAt));
          const rows = Array.isArray(data) ? data : [];
          tableWrap.appendChild(MugenUI.buildTable(
            [
              { key: "nama_barber", label: "Barber" },
              { key: "jumlah_service", label: "Jml Service" },
              { key: "total_komisi", label: "Komisi", format: MugenUI.formatRupiah },
              { key: "tips", label: "Tips", format: MugenUI.formatRupiah },
              { key: "uang_harian", label: "Uang Harian", format: MugenUI.formatRupiah },
              { key: "hari_libur", label: "Hari Libur" },
              { key: "target_tercapai", label: "Target Bonus", format: (v) => v ? "Tercapai" : "Belum" },
              { key: "bonus_customer", label: "Bonus Cust.", format: MugenUI.formatRupiah },
              { key: "total_pendapatan", label: "Total", format: MugenUI.formatRupiah },
            ],
            rows,
          ));
        } catch (e) {
          tableWrap.innerHTML = "";
          tableWrap.appendChild(MugenUI.el("div", {}, e.message));
        }
      }
      selBulan.addEventListener("change", () => MugenUI.withLoading(load));
      selTahun.addEventListener("change", () => MugenUI.withLoading(load));
      if (selBarber) selBarber.addEventListener("change", () => MugenUI.withLoading(load));
      load();
    }

    async function renderPengeluaran() {
      const { row, selBulan, selTahun } = filterBar({ withBarber: false });
      row.appendChild(tombolDownloadPdf(() => {
        const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
        return MugenApi.downloadFile(`/api/rekap/pengeluaran/pdf?${qs}`, `rekap_pengeluaran_${selTahun.value}-${selBulan.value}.pdf`);
      }));
      const totalBox = MugenUI.el("div", { class: "card" });
      const tableWrap = MugenUI.el("div");
      body.appendChild(row);
      body.appendChild(totalBox);
      body.appendChild(tableWrap);

      async function load() {
        tableWrap.innerHTML = "Memuat...";
        try {
          const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
          const data = await MugenApi.get(`/api/rekap/pengeluaran?${qs}`, { useCache: true });
          tableWrap.innerHTML = "";
          totalBox.innerHTML = "";
          if (data.__offline) tableWrap.appendChild(MugenUI.offlineBanner(data.__cachedAt));
          totalBox.appendChild(MugenUI.el("h2", {}, "Total Pengeluaran Bulan Ini"));
          totalBox.appendChild(MugenUI.el("div", { class: "big-number" }, MugenUI.formatRupiah(data.total)));
          tableWrap.appendChild(MugenUI.buildTable(
            [
              { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
              { key: "kategori", label: "Kategori", format: (v) => v || "-" },
              { key: "keterangan", label: "Keterangan" },
              { key: "nama_barber", label: "Barber", format: (v) => v || "-" },
              { key: "jumlah", label: "Jumlah", format: MugenUI.formatRupiah },
            ],
            data.daftar,
          ));
        } catch (e) {
          tableWrap.innerHTML = "";
          tableWrap.appendChild(MugenUI.el("div", {}, e.message));
        }
      }
      selBulan.addEventListener("change", () => MugenUI.withLoading(load));
      selTahun.addEventListener("change", () => MugenUI.withLoading(load));
      load();
    }

    renderTabs();
    renderBody();
  }

  return { render };
})();
