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

  // Tombol aksi generik dipakai kolom "Aksi" Rekap Transaksi (Owner) --
  // satu pola untuk hapus transaksi/reimburse dan batalkan pembayaran
  // kasbon, supaya konfirmasi/loading/toast/refresh-nya konsisten.
  // `onSelesai` (opsional) dipanggil setelah sukses menghapus/membatalkan,
  // dipakai renderTransaksi() untuk memuat ulang tabel.
  function tombolAksi({ label, title, confirmTitle, confirmMessage, hapusUrl, pesanSukses, onSelesai }) {
    const wrap = MugenUI.el("div", { class: "actions-cell" });
    const btn = MugenUI.el("button", { type: "button", class: "btn-danger", title }, label);
    btn.addEventListener("click", async () => {
      const ok = await MugenUI.confirmModal({
        title: confirmTitle,
        message: confirmMessage,
        confirmText: "Ya, Lanjutkan",
        cancelText: "Batal",
        danger: true,
      });
      if (!ok) return;
      try {
        await MugenUI.withLoading(() => MugenApi.del(hapusUrl), { message: "Memproses…" });
        MugenUI.toast(pesanSukses, "success", { force: true });
        if (onSelesai) onSelesai();
      } catch (e) {
        MugenUI.toast(e.message, "error");
      }
    });
    wrap.appendChild(btn);
    return wrap;
  }

  async function render(root) {
    const user = MugenState.getUser();
    const isAdmin = user.role === "admin" || user.role === "staff";
    // Fitur Hapus Rekap Transaksi: KHUSUS Owner (role "admin" di kode ini
    // -- lihat konvensi penamaan role di seluruh aplikasi, "staff" = Admin
    // di tampilan). Admin/Barber TIDAK melihat tombolnya sama sekali.
    const isOwner = user.role === "admin";
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
              // Ket.: baris "libur" MURNI tetap badge pil (persis seperti
              // sebelumnya, tidak berubah). Jenis lain (catatan Input Data,
              // Reimburse/Kasbon/Gaji Non-Barber) bisa berisi teks lebih
              // panjang -- ditampilkan polos (bukan dipaksa masuk pil kecil
              // yang didesain untuk label pendek seperti "Libur").
              {
                key: "keterangan", label: "Ket.", format: (v, r) => {
                  if (!v) return "-";
                  if (r.tipe === "libur") return MugenUI.el("span", { class: "badge badge-libur" }, v);
                  return v;
                },
              },
              // Kolom Hapus KHUSUS Owner (isOwner). Empat jenis baris punya
              // aksi berbeda: "transaksi" (hapus transaksi asli), "reimburse"
              // (hapus klaim yang sudah disetujui, dengan peringatan lebih
              // kuat karena ini uang yang sudah cair), "kasbon" (batalkan
              // SATU pembayaran manual saja -- pembayaran hasil potong
              // otomatis Slip Gaji, sumber="potong_gaji", sengaja TIDAK bisa
              // dihapus dari sini supaya tidak bentrok dengan status Slip
              // Gaji terkait, harus lewat pembatalan status Slip Gaji itu
              // sendiri), "non_barber" (hapus entri Gaji Non-Barber, Input
              // Data Non-Barber). Baris "libur" tidak punya "id" sama sekali
              // jadi otomatis dash.
              ...(isOwner ? [{
                key: "aksi", label: "Aksi", format: (_, r) => {
                  if (r.id == null) return "-";
                  if (r.tipe === "transaksi") {
                    return tombolAksi({
                      label: "🗑 Hapus", title: "Hapus Transaksi",
                      confirmTitle: "Hapus Transaksi",
                      confirmMessage: [
                        "Apakah Anda yakin ingin menghapus transaksi ini?",
                        "Data yang dihapus tidak dapat dikembalikan.",
                      ],
                      hapusUrl: `/api/input-data/transaksi/${r.id}`,
                      pesanSukses: "Transaksi berhasil dihapus.",
                      onSelesai: load,
                    });
                  }
                  if (r.tipe === "reimburse") {
                    return tombolAksi({
                      label: "🗑 Hapus", title: "Hapus Klaim Reimburse",
                      confirmTitle: "Hapus Klaim Reimburse",
                      confirmMessage: [
                        "Apakah Anda yakin ingin menghapus klaim reimburse yang sudah disetujui ini?",
                        "Klaim ini sudah cair/tercatat sebagai pendapatan -- menghapusnya akan mengurangi Total Pendapatan pada rekap ini.",
                        "Data yang dihapus tidak dapat dikembalikan.",
                      ],
                      hapusUrl: `/api/reimburse/${r.id}/rekap`,
                      pesanSukses: "Klaim reimburse berhasil dihapus.",
                      onSelesai: load,
                    });
                  }
                  if (r.tipe === "kasbon") {
                    if (r.sumber !== "manual") return "-"; // potong_gaji: lewat Slip Gaji
                    return tombolAksi({
                      label: "↩ Batalkan", title: "Batalkan Pembayaran Kasbon",
                      confirmTitle: "Batalkan Pembayaran Kasbon",
                      confirmMessage: [
                        "Apakah Anda yakin ingin membatalkan pembayaran kasbon ini?",
                        "Sisa kasbon karyawan ini akan dikembalikan sejumlah pembayaran yang dibatalkan.",
                        "Data yang dihapus tidak dapat dikembalikan.",
                      ],
                      hapusUrl: `/api/kasbon/pembayaran/${r.id}`,
                      pesanSukses: "Pembayaran kasbon berhasil dibatalkan.",
                      onSelesai: load,
                    });
                  }
                  if (r.tipe === "non_barber") {
                    return tombolAksi({
                      label: "🗑 Hapus", title: "Hapus Data Gaji Non-Barber",
                      confirmTitle: "Hapus Data Gaji Non-Barber",
                      confirmMessage: [
                        "Apakah Anda yakin ingin menghapus data gaji ini?",
                        "Data yang dihapus tidak dapat dikembalikan.",
                      ],
                      hapusUrl: `/api/data-non-barber/${r.id}`,
                      pesanSukses: "Data gaji Non-Barber berhasil dihapus.",
                      onSelesai: load,
                    });
                  }
                  return "-";
                },
              }] : []),
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
              { key: "reimburse", label: "Reimburse", format: MugenUI.formatRupiah },
              { key: "kasbon_dibayar", label: "Kasbon Dibayar", format: MugenUI.formatRupiah },
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
