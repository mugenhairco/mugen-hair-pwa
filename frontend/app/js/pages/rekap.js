// pages/rekap.js

const PageRekap = (() => {
  // Perbaikan Alur Cetak PDF: tombol "Cetak PDF" TIDAK lagi langsung
  // mengunduh -- PDF dibuat lalu ditampilkan dulu lewat MugenPdfPreview
  // (Preview PDF di dalam aplikasi, dengan Zoom/Nomor Halaman/Download
  // PDF/Print/Kembali), unduhan sungguhan hanya terjadi kalau tombol
  // "Download PDF" DI DALAM preview itu yang ditekan. `computeOptions`
  // dipanggil ULANG setiap kali tombol diklik (bukan sekali di awal),
  // supaya filter yang aktif SAAT diklik yang dipakai -- return
  // { generate: () => Promise<Blob>, filename: string }.
  function tombolCetakPdf(computeOptions) {
    const btn = MugenUI.el("button", {}, "Cetak PDF");
    btn.addEventListener("click", () => {
      const { generate, filename } = computeOptions();
      MugenPdfPreview.open({ generate, filename });
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
      // Jenis Laporan (Perbaikan Alur Cetak PDF): "Rekap Detail" = format
      // lama (satu baris per transaksi/hari, TIDAK berubah), "Rekap
      // Periode (Ringkasan)" = BARU, satu baris per karyawan untuk seluruh
      // periode -- lihat laporan_pdf.buat_pdf_rekap_transaksi_ringkasan().
      const selJenisLaporan = MugenUI.el("select", {}, [
        MugenUI.el("option", { value: "detail" }, "Rekap Detail"),
        MugenUI.el("option", { value: "ringkasan" }, "Rekap Periode (Ringkasan)"),
      ]);
      const pdfRow = MugenUI.el("div", { class: "row", style: "flex:none;margin-bottom:14px;align-items:center;flex-wrap:wrap;" }, [
        MugenUI.el("span", { class: "subtitle", style: "margin:0;" }, "Periode PDF (opsional):"),
        inputDariTanggal, inputSampaiTanggal,
        MugenUI.el("span", { class: "subtitle", style: "margin:0;" }, "Jenis Laporan:"),
        selJenisLaporan,
      ]);

      // Periode efektif yang dipakai NAMA FILE (murni tampilan nama file --
      // parameter yang DIKIRIM ke server tetap lewat qs di bawah, TIDAK
      // berubah): kalau Periode PDF custom diisi, pakai apa adanya; kalau
      // tidak, diturunkan dari Bulan+Tahun yang aktif (tanggal 1 s.d. hari
      // terakhir bulan itu).
      function periodeUntukNamaFile() {
        if (inputDariTanggal.value && inputSampaiTanggal.value) {
          return { mulai: inputDariTanggal.value, selesai: inputSampaiTanggal.value };
        }
        const tahun = Number(selTahun.value), bulan = Number(selBulan.value);
        const hariTerakhir = new Date(tahun, bulan, 0).getDate();
        const dua = (n) => String(n).padStart(2, "0");
        return {
          mulai: `${tahun}-${dua(bulan)}-01`,
          selesai: `${tahun}-${dua(bulan)}-${dua(hariTerakhir)}`,
        };
      }

      function namaFilePdf() {
        const jenisLabel = selJenisLaporan.value === "ringkasan" ? "Rekap Periode" : "Rekap Harian";
        const karyawan = selBarber && selBarber.value
          ? (karyawanAll.find((k) => String(k.id) === selBarber.value) || {}).nama || "Karyawan"
          : "Semua Karyawan";
        const { mulai, selesai } = periodeUntukNamaFile();
        const tanggalLabel = mulai === selesai
          ? MugenUI.namaTanggalIndo(mulai)
          : `${MugenUI.namaTanggalIndo(mulai)} - ${MugenUI.namaTanggalIndo(selesai)}`;
        return MugenUI.namaFileAman(`${jenisLabel} ${karyawan} ${tanggalLabel}.pdf`);
      }

      pdfRow.appendChild(tombolCetakPdf(() => {
        const qs = new URLSearchParams();
        if (inputDariTanggal.value && inputSampaiTanggal.value) {
          qs.set("tanggal_mulai", inputDariTanggal.value);
          qs.set("tanggal_selesai", inputSampaiTanggal.value);
        } else {
          qs.set("tahun", selTahun.value);
          qs.set("bulan", selBulan.value);
        }
        if (selBarber && selBarber.value) qs.set("barber_id", selBarber.value);
        qs.set("jenis", selJenisLaporan.value);
        return {
          generate: () => MugenApi.fetchBlob(`/api/rekap/transaksi/pdf?${qs}`),
          filename: namaFilePdf(),
        };
      }));

      const tableWrap = MugenUI.el("div");
      body.appendChild(row);
      body.appendChild(pdfRow);
      body.appendChild(tableWrap);

      // Rekap Barber: kolom Komisi/Kasbon/Reimburse/Total KHUSUS akun
      // ber-role Barber (tampilan Owner/Admin di bawah TIDAK berubah sama
      // sekali, tetap kolom "Pendapatan" gabungan seperti sebelumnya).
      // Kasbon/Reimburse SUDAH ADA sebagai BARIS TERSENDIRI di data yang
      // sama (tipe="kasbon"/"reimburse", lihat kasbon_db.py/reimburse_db.py
      // gabung_ke_rekap_transaksi()) dengan nilainya sudah ada di field
      // "pendapatan" (kasbon NEGATIF, reimburse POSITIF) -- fungsi ini
      // TIDAK menghitung ulang satu angka pun, murni memecah field yang
      // sudah ada ke kolom masing-masing berdasar tipe baris supaya lebih
      // mudah dibaca daripada bercampur jadi satu kolom "Pendapatan".
      // Kolom "Total" = field "pendapatan" apa adanya (sudah bertanda
      // benar untuk tiap tipe baris), TIDAK PERNAH kosong. Kolom Kasbon/
      // Reimburse hanya ditampilkan kalau ADA minimal satu baris tipe itu
      // pada hasil periode yang sedang dilihat (kalau tidak ada sama
      // sekali, kolomnya dihilangkan, bukan ditampilkan kosong).
      function kolomTransaksiBarber(rowsBarber) {
        const adaKasbon = rowsBarber.some((r) => r.tipe === "kasbon");
        const adaReimburse = rowsBarber.some((r) => r.tipe === "reimburse");
        return [
          { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
          { key: "nama_barber", label: "Nama" },
          { key: "daftar_service", label: "Service", format: MugenUI.serviceCell },
          { key: "jumlah_service", label: "Jml Service" },
          { key: "uang_harian", label: "Uang Harian", format: MugenUI.formatRupiah },
          { key: "tips", label: "Tips", format: MugenUI.formatRupiah },
          { key: "pendapatan", label: "Komisi", format: (v, r) => (r.tipe === "transaksi" ? MugenUI.formatRupiah(v) : "-") },
          ...(adaKasbon ? [{ key: "pendapatan", label: "Kasbon", format: (v, r) => (r.tipe === "kasbon" ? MugenUI.formatRupiah(Math.abs(v)) : "-") }] : []),
          ...(adaReimburse ? [{ key: "pendapatan", label: "Reimburse", format: (v, r) => (r.tipe === "reimburse" ? MugenUI.formatRupiah(v) : "-") }] : []),
          { key: "pendapatan", label: "Total", format: MugenUI.formatRupiah },
          {
            key: "keterangan", label: "Ket.", format: (v, r) => {
              if (!v) return "-";
              if (r.tipe === "libur") return MugenUI.el("span", { class: "badge badge-libur" }, v);
              return MugenUI.keteranganCell(v);
            },
          },
        ];
      }

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
            isAdmin ? [
              { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
              { key: "nama_barber", label: "Nama" },
              { key: "daftar_service", label: "Service", format: MugenUI.serviceCell },
              { key: "jumlah_service", label: "Jml Service" },
              { key: "uang_harian", label: "Uang Harian", format: MugenUI.formatRupiah },
              { key: "tips", label: "Tips", format: MugenUI.formatRupiah },
              { key: "pendapatan", label: "Pendapatan", format: MugenUI.formatRupiah },
              // Ket.: baris "libur" MURNI tetap badge pil (persis seperti
              // sebelumnya, tidak berubah). Jenis lain (catatan Input Data,
              // Reimburse/Kasbon/Gaji Non-Barber) bisa berisi lebih dari
              // satu informasi sekaligus (dipisah "; ") -- ditampilkan satu
              // baris per informasi (MugenUI.keteranganCell()), bukan
              // digabung jadi satu baris.
              {
                key: "keterangan", label: "Ket.", format: (v, r) => {
                  if (!v) return "-";
                  if (r.tipe === "libur") return MugenUI.el("span", { class: "badge badge-libur" }, v);
                  return MugenUI.keteranganCell(v);
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
            ] : kolomTransaksiBarber(rows),
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
      row.appendChild(tombolCetakPdf(() => {
        const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
        if (selBarber && selBarber.value) qs.set("barber_id", selBarber.value);
        const barberNama = selBarber && selBarber.value
          ? (barbersOnly.find((b) => String(b.id) === selBarber.value) || {}).nama || "Barber"
          : "Semua Barber";
        return {
          generate: () => MugenApi.fetchBlob(`/api/rekap/bulanan/pdf?${qs}`),
          filename: MugenUI.namaFileAman(`Rekap Bulanan ${barberNama} ${MugenUI.namaBulan(Number(selBulan.value))} ${selTahun.value}.pdf`),
        };
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
      row.appendChild(tombolCetakPdf(() => {
        const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
        return {
          generate: () => MugenApi.fetchBlob(`/api/rekap/pengeluaran/pdf?${qs}`),
          filename: MugenUI.namaFileAman(`Rekap Pengeluaran ${MugenUI.namaBulan(Number(selBulan.value))} ${selTahun.value}.pdf`),
        };
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
