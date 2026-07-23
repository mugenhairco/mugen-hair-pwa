// pages/rekap.js

const PageRekap = (() => {
  async function render(root) {
    const user = MugenState.getUser();
    const isAdmin = user.role === "admin";
    const today = new Date();

    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Rekap"));

    const tabs = ["Transaksi", "Bulanan", ...(isAdmin ? ["Pengeluaran"] : [])];
    let activeTab = "Transaksi";

    const tabBar = MugenUI.el("div", { class: "tabs" });
    const body = MugenUI.el("div");
    root.appendChild(tabBar);
    root.appendChild(body);

    let barbers = [];
    if (isAdmin) {
      try {
        barbers = await MugenApi.get("/api/input-data/barbers", { useCache: true });
      } catch (e) { /* filter barber tetap opsional kalau gagal dimuat */ }
    }

    function renderTabs() {
      tabBar.innerHTML = "";
      for (const t of tabs) {
        const btn = MugenUI.el("button", { class: activeTab === t ? "active" : "" }, t);
        btn.addEventListener("click", () => { activeTab = t; renderTabs(); renderBody(); });
        tabBar.appendChild(btn);
      }
    }

    function filterBar({ withBarber = true } = {}) {
      const selBulan = MugenUI.el("select");
      for (let m = 1; m <= 12; m++) selBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
      selBulan.value = String(today.getMonth() + 1);
      const selTahun = MugenUI.el("select");
      for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) selTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
      selTahun.value = String(today.getFullYear());
      const selBarber = withBarber && isAdmin ? MugenUI.el("select") : null;
      if (selBarber) {
        selBarber.appendChild(MugenUI.el("option", { value: "" }, "Semua Barber"));
        for (const b of barbers) selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
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
      const { row, selBulan, selTahun, selBarber } = filterBar();
      const tableWrap = MugenUI.el("div");
      body.appendChild(row);
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
              { key: "nama_barber", label: "Barber" },
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
      selBulan.addEventListener("change", load);
      selTahun.addEventListener("change", load);
      if (selBarber) selBarber.addEventListener("change", load);
      load();
    }

    async function renderBulanan() {
      const { row, selBulan, selTahun, selBarber } = filterBar();
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
              { key: "bonus_kehadiran", label: "Bonus Hadir", format: MugenUI.formatRupiah },
              { key: "total_pendapatan", label: "Total", format: MugenUI.formatRupiah },
            ],
            rows,
          ));
        } catch (e) {
          tableWrap.innerHTML = "";
          tableWrap.appendChild(MugenUI.el("div", {}, e.message));
        }
      }
      selBulan.addEventListener("change", load);
      selTahun.addEventListener("change", load);
      if (selBarber) selBarber.addEventListener("change", load);
      load();
    }

    async function renderPengeluaran() {
      const { row, selBulan, selTahun } = filterBar({ withBarber: false });
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
              { key: "keterangan", label: "Keterangan" },
              { key: "jumlah", label: "Jumlah", format: MugenUI.formatRupiah },
            ],
            data.daftar,
          ));
        } catch (e) {
          tableWrap.innerHTML = "";
          tableWrap.appendChild(MugenUI.el("div", {}, e.message));
        }
      }
      selBulan.addEventListener("change", load);
      selTahun.addEventListener("change", load);
      load();
    }

    renderTabs();
    renderBody();
  }

  return { render };
})();
