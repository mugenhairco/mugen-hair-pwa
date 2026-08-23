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
    // Feature Gating "export_pdf": tanpa fitur ini di paket, tombolnya
    // diganti blok upgrade -- SATU titik keputusan untuk seluruh 3 pemanggil
    // tombolCetakPdf() di file ini (Rekap Detail/Ringkasan, Rekap Pengeluaran).
    if (typeof MugenFeature !== "undefined" && !MugenFeature.has("export_pdf")) {
      return MugenFeature.upgradeBlock("Export PDF");
    }
    const btn = MugenUI.el("button", {}, "Cetak PDF");
    btn.addEventListener("click", () => {
      const { generate, filename } = computeOptions();
      MugenPdfPreview.open({ generate, filename });
    });
    return btn;
  }

  // Tombol aksi generik dipakai kolom "Aksi" Rekap Transaksi (Owner) --
  // satu pola untuk hapus transaksi/reimburse/Keterangan Libur dan
  // batalkan pembayaran kasbon, supaya konfirmasi/loading/toast/refresh-nya
  // konsisten. `onSelesai` (opsional) dipanggil setelah sukses menghapus/
  // membatalkan, dipakai renderTransaksi() untuk memuat ulang tabel.
  // `hapusBody` (opsional): baris "libur" TIDAK punya `id` (dihapus lewat
  // kombinasi barber_id+tanggal di body, bukan lewat path param seperti
  // transaksi/reimburse/kasbon/non_barber -- lihat DELETE /api/input-data/libur,
  // pola SAMA seperti tombol "Batalkan Libur" yang sudah ada di Input Data).
  function tombolAksi({ label, title, confirmTitle, confirmMessage, hapusUrl, hapusBody, pesanSukses, onSelesai }) {
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
        // REVISI UI/UX Premium: spinner inline di tombol sendiri, bukan overlay layar penuh
        await MugenUI.withButtonLoading(btn, () => MugenApi.del(hapusUrl, hapusBody));
        MugenUI.toast(pesanSukses, "success", { force: true });
        if (onSelesai) onSelesai();
      } catch (e) {
        MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
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

    // AUDIT Hak Akses Menu (permintaan Owner): "Tidak Ada Akses" -- HANYA
    // pesan kosong, tanpa tab/data apa pun (MugenMenuAccess.get() selalu
    // balas "write" untuk Owner & Barber, jadi gate ini efektifnya HANYA
    // berlaku untuk 'staff').
    if ((await MugenMenuAccess.get("rekap")) === "none") {
      root.appendChild(MugenUI.emptyState("Anda tidak memiliki akses ke menu ini."));
      return;
    }

    // REVISI UI/UX Premium: MugenUI.tabs() (indikator geser halus otomatis)
    // menggantikan tabBar/renderTabs manual.
    const tabItems = [
      { key: "Transaksi", label: "Transaksi" },
      { key: "Bulanan", label: "Bulanan" },
      ...(isAdmin ? [{ key: "Pengeluaran", label: "Pengeluaran" }] : []),
    ];
    const body = MugenUI.el("div");
    const tabsCtl = MugenUI.tabs(tabItems, { onChange: renderBody });
    root.appendChild(tabsCtl.bar);
    root.appendChild(body);
    requestAnimationFrame(tabsCtl.moveIndicator);

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
      if (tabsCtl.active === "Transaksi") await renderTransaksi();
      else if (tabsCtl.active === "Bulanan") await renderBulanan();
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

      async function load() {
        // REVISI UI/UX Premium: skeleton (bentuk tabel) menggantikan teks "Memuat..."
        tableWrap.innerHTML = "";
        tableWrap.appendChild(MugenUI.skeleton("table", { cols: isOwner ? 9 : (isAdmin ? 8 : 11), rows: 4 }));
        try {
          const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
          if (selBarber && selBarber.value) qs.set("barber_id", selBarber.value);
          const data = await MugenApi.get(`/api/rekap/transaksi?${qs}`, { useCache: true });
          tableWrap.innerHTML = "";
          if (data.__offline) tableWrap.appendChild(MugenUI.offlineBanner(data.__cachedAt));
          const rows = Array.isArray(data) ? data : [];
          // Ket.: baris "libur" MURNI tetap badge pil (persis seperti
          // sebelumnya, tidak berubah). Jenis lain (catatan Input Data,
          // Reimburse/Kasbon/Gaji Non-Barber) bisa berisi lebih dari satu
          // informasi sekaligus (dipisah "; ") -- ditampilkan satu baris per
          // informasi (MugenUI.keteranganCell()), bukan digabung jadi satu
          // baris. Dipakai KEDUA susunan kolom (Owner/Admin & Barber) di
          // bawah, jadi diekstrak supaya tidak dobel.
          const kolomKet = {
            key: "keterangan", label: "Ket.", format: (v, r) => {
              if (!v) return "-";
              if (r.tipe === "libur") return MugenUI.el("span", { class: "badge badge-libur" }, v);
              return MugenUI.keteranganCell(v);
            },
          };
          // REVISI Rekap Transaksi (KHUSUS Barber, lihat !isAdmin di bawah):
          // susunan kolom Owner/Admin (isAdmin true, termasuk Staff)
          // DIBIARKAN PERSIS seperti sebelumnya, TIDAK disentuh sama sekali
          // -- permintaan eksplisit supaya perbaikan ini hanya berlaku untuk
          // akun ber-role Barber, bukan Tenant (Owner/Admin).
          const kolomAdmin = [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            { key: "nama_barber", label: "Nama" },
            { key: "daftar_service", label: "Service", format: MugenUI.serviceCell },
            { key: "jumlah_service", label: "Jml Service" },
            { key: "uang_harian", label: "Uang Harian", format: MugenUI.formatRupiah },
            { key: "tips", label: "Tips", format: MugenUI.formatRupiah },
            { key: "pendapatan", label: "Pendapatan", format: MugenUI.formatRupiah },
            kolomKet,
          ];
          // Susunan BARU khusus Barber (BUG FIX): (1) kolom Komisi yang
          // sebelumnya tidak ada sama sekali (field "komisi" sudah dikirim
          // backend, lihat database.py::get_rekap_transaksi_list(), tinggal
          // ditampilkan); (2) Reimburse/Kasbon Dibayar jadi kolom sendiri
          // (sebelumnya nilainya "tersembunyi" di dalam Pendapatan tanpa
          // label jelas) -- "-" untuk baris yang bukan tipe itu; (3)
          // Pendapatan sekarang benar-benar TOTAL baris itu (Komisi + Uang
          // Harian + Tips untuk baris transaksi -- SEBELUMNYA Uang Harian
          // tidak ikut dihitung; baris Reimburse/Kasbon/Libur nilainya apa
          // adanya dari backend, sudah benar sejak awal, tidak perlu
          // dihitung ulang di sini).
          const kolomBarber = [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            { key: "nama_barber", label: "Nama" },
            { key: "daftar_service", label: "Service", format: MugenUI.serviceCell },
            { key: "jumlah_service", label: "Jml Service" },
            { key: "komisi", label: "Komisi", format: (v, r) => r.tipe === "transaksi" ? MugenUI.formatRupiah(v || 0) : "-" },
            { key: "uang_harian", label: "Uang Harian", format: MugenUI.formatRupiah },
            { key: "tips", label: "Tips", format: MugenUI.formatRupiah },
            { key: "pendapatan", label: "Reimburse", format: (v, r) => r.tipe === "reimburse" ? MugenUI.formatRupiah(v) : "-" },
            { key: "pendapatan", label: "Kasbon Dibayar", format: (v, r) => r.tipe === "kasbon" ? MugenUI.formatRupiah(-v) : "-" },
            {
              key: "pendapatan", label: "Pendapatan", format: (v, r) => MugenUI.formatRupiah(
                r.tipe === "transaksi" ? (r.komisi || 0) + (r.uang_harian || 0) + (r.tips || 0) : v
              ),
            },
            kolomKet,
          ];
          tableWrap.appendChild(MugenUI.buildTable(
            [
              ...(isAdmin ? kolomAdmin : kolomBarber),
              // Kolom Hapus KHUSUS Owner (isOwner). Lima jenis baris punya
              // aksi berbeda: "transaksi" (hapus transaksi asli), "reimburse"
              // (hapus klaim yang sudah disetujui, dengan peringatan lebih
              // kuat karena ini uang yang sudah cair), "kasbon" (batalkan
              // SATU pembayaran manual saja -- pembayaran hasil potong
              // otomatis Slip Gaji, sumber="potong_gaji", sengaja TIDAK bisa
              // dihapus dari sini supaya tidak bentrok dengan status Slip
              // Gaji terkait, harus lewat pembatalan status Slip Gaji itu
              // sendiri), "non_barber" (hapus entri Gaji Non-Barber, Input
              // Data Non-Barber), "libur" (hapus Keterangan Libur -- REVISI:
              // sebelumnya SELALU dash karena baris ini tidak punya "id" sama
              // sekali, dicek TERPISAH dari baris lain SEBELUM gerbang
              // `r.id == null` di bawah supaya tidak ikut ke-skip; dihapus
              // lewat kombinasi barber_id+tanggal, bukan id, lihat
              // tombolAksi()/DELETE /api/input-data/libur).
              ...(isOwner ? [{
                key: "aksi", label: "Aksi", format: (_, r) => {
                  if (r.tipe === "libur") {
                    return tombolAksi({
                      label: "🗑 Hapus", title: "Hapus Keterangan Libur",
                      confirmTitle: "Hapus Keterangan Libur",
                      confirmMessage: [
                        `Apakah Anda yakin ingin menghapus keterangan libur ${r.nama_barber} pada ${MugenUI.formatTanggal(r.tanggal)}?`,
                        "Barber ini akan dianggap masuk kerja seperti biasa pada tanggal tersebut setelah dihapus.",
                      ],
                      hapusUrl: "/api/input-data/libur",
                      hapusBody: { barber_id: r.barber_id, tanggal: r.tanggal },
                      pesanSukses: "Keterangan libur berhasil dihapus.",
                      onSelesai: load,
                    });
                  }
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
          tableWrap.appendChild(MugenUI.errorState(e.message));
        }
      }
      // REVISI UI/UX Premium (Contextual Loading): tanpa overlay layar penuh
      // -- skeleton di dalam tableWrap sendiri (di atas) sudah jadi feedback yang cukup.
      selBulan.addEventListener("change", load);
      selTahun.addEventListener("change", load);
      if (selBarber) selBarber.addEventListener("change", load);
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
        // REVISI UI/UX Premium: skeleton (bentuk tabel) menggantikan teks "Memuat..."
        tableWrap.innerHTML = "";
        tableWrap.appendChild(MugenUI.skeleton("table", { cols: 11, rows: 4 }));
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
          tableWrap.appendChild(MugenUI.errorState(e.message));
        }
      }
      // REVISI UI/UX Premium (Contextual Loading): tanpa overlay layar penuh
      // -- skeleton di dalam tableWrap sendiri (di atas) sudah jadi feedback yang cukup.
      selBulan.addEventListener("change", load);
      selTahun.addEventListener("change", load);
      if (selBarber) selBarber.addEventListener("change", load);
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
        // REVISI UI/UX Premium: skeleton (bentuk tabel) menggantikan teks "Memuat..."
        tableWrap.innerHTML = "";
        tableWrap.appendChild(MugenUI.skeleton("table", { cols: 5, rows: 4 }));
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
          tableWrap.appendChild(MugenUI.errorState(e.message));
        }
      }
      // REVISI UI/UX Premium (Contextual Loading): tanpa overlay layar penuh
      // -- skeleton di dalam tableWrap sendiri (di atas) sudah jadi feedback yang cukup.
      selBulan.addEventListener("change", load);
      selTahun.addEventListener("change", load);
      load();
    }

    renderBody();
  }

  return { render };
})();

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js
// (bukan <script> biasa lagi, lihat index.html/router.js) -- top-level
// "const" TIDAK menempel ke objek window di browser (beda dari "var"),
// jadi page_loader.js TIDAK BISA mendeteksi lewat window.PageRekap begitu saja
// setelah script ini selesai dimuat. Baris di bawah ini SATU-SATUNYA
// perubahan di file ini untuk mendukung lazy-load -- expose eksplisit ke
// window supaya page_loader.js bisa memverifikasi modul benar-benar
// berhasil dimuat sebelum memanggil render()-nya.
window.PageRekap = PageRekap;
