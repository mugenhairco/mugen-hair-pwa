// pages/slip_gaji.js — Modul Karyawan (Fase 1): Slip Gaji Otomatis.
// Satu halaman, dua sudut pandang (pola yang sama seperti pages/rekap.js):
// - Owner ('admin') selalu penuh; 'staff' (Admin) HANYA kalau diberi izin
//   izin_slip_gaji (Setting > Hak Akses Admin) -- lihat renderAdminView().
//   Backend (routers/slip_gaji.py) yang benar-benar menegakkan ini, frontend
//   di sini hanya menampilkan pesan error kalau ditolak server.
// - 'barber': hanya melihat riwayat Slip Gaji miliknya sendiri, read-only
//   (tidak ada tombol Generate/Status/Hapus) -- lihat renderBarberView().
//
// Slip Gaji = Gaji Pokok + Komisi + Tips + Uang Harian + Bonus Customer
// (SEMUA dihitung backend dari data yang sudah ada, TIDAK dihitung ulang di
// sini) dikurangi Potongan Kasbon + Potongan Lain (manual, diisi Owner/Admin
// saat generate). Satu slip per barber per bulan -- generate ulang sebelum
// berstatus Sudah Dibayar akan menghitung ulang komponen income-nya.

const PageSlipGaji = (() => {
  // Tahap 13: Periode rentang tanggal bebas untuk Kasir/OB/Kru (r.tanggal_mulai
  // terisi) -- BEDA dari Barber yang tetap satu bulan kalender penuh
  // (r.tanggal_mulai NULL, dari r.bulan/r.tahun seperti sebelumnya).
  function periodeText(r) {
    return r.tanggal_mulai
      ? `${MugenUI.formatTanggal(r.tanggal_mulai)} - ${MugenUI.formatTanggal(r.tanggal_selesai)}`
      : `${MugenUI.namaBulan(r.bulan)} ${r.tahun}`;
  }

  // Perbaikan Alur Cetak PDF: Preview PDF dulu (Zoom/Nomor Halaman/
  // Download/Print/Kembali), TIDAK langsung mengunduh -- lihat pdf_preview.js.
  function unduhPdf(id, namaBarber, tahun, bulan) {
    MugenPdfPreview.open({
      generate: () => MugenApi.fetchBlob(`/api/slip-gaji/${id}/pdf`),
      filename: MugenUI.namaFileAman(`Slip Gaji ${namaBarber} ${MugenUI.namaBulan(bulan)} ${tahun}.pdf`),
    });
  }

  function tombolDownloadPdfDaftar(getParams, computeFilename) {
    const btn = MugenUI.el("button", {}, "Cetak PDF Daftar");
    btn.addEventListener("click", () => {
      const qs = new URLSearchParams(getParams());
      const filename = computeFilename ? computeFilename() : "Daftar Slip Gaji.pdf";
      MugenPdfPreview.open({
        generate: () => MugenApi.fetchBlob(`/api/slip-gaji/pdf?${qs}`),
        filename: MugenUI.namaFileAman(filename),
      });
    });
    return btn;
  }

  async function loadListInto(listBody, params, isAdmin, onBerubah) {
    listBody.innerHTML = "Memuat...";
    try {
      const qs = new URLSearchParams(params);
      const data = await MugenApi.get(`/api/slip-gaji?${qs.toString()}`);
      listBody.innerHTML = "";
      const rows = Array.isArray(data) ? data : [];

      const kolom = [
        { key: "periode", label: "Periode", format: (_, r) => periodeText(r) },
      ];
      if (isAdmin) kolom.push({ key: "nama_barber", label: "Karyawan" });
      kolom.push(
        { key: "reimburse", label: "Reimburse", format: MugenUI.formatRupiah },
        { key: "total_diterima", label: "Total Diterima", format: MugenUI.formatRupiah },
        {
          key: "status", label: "Status",
          format: (v) => MugenUI.el("span", { class: "badge" + (v === "sudah_dibayar" ? "" : " badge-libur") },
            v === "sudah_dibayar" ? "Sudah Dibayar" : "Belum Dibayar"),
        },
        {
          key: "aksi", label: "Aksi", format: (_, r) => {
            const wrap = MugenUI.el("div", { class: "actions-cell" });
            const btnPdf = MugenUI.el("button", {}, "Cetak PDF");
            btnPdf.addEventListener("click", () => unduhPdf(r.id, r.nama_barber, r.tahun, r.bulan));
            wrap.appendChild(btnPdf);

            if (isAdmin) {
              const btnStatus = MugenUI.el("button", {},
                r.status === "sudah_dibayar" ? "Batalkan Status" : "Tandai Sudah Dibayar");
              btnStatus.addEventListener("click", async () => {
                const statusBaru = r.status === "sudah_dibayar" ? "belum_dibayar" : "sudah_dibayar";
                try {
                  await MugenUI.withLoading(() => MugenApi.put(`/api/slip-gaji/${r.id}/status`, { status: statusBaru }),
                    { message: "Menyimpan…" });
                  MugenUI.toast("Status Slip Gaji diperbarui.", "success");
                  onBerubah();
                } catch (e) {
                  MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                }
              });
              wrap.appendChild(btnStatus);

              if (r.status !== "sudah_dibayar") {
                const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btnHapus.addEventListener("click", async () => {
                  if (!confirm(`Hapus Slip Gaji ${r.nama_barber} periode ${periodeText(r)}?`)) return;
                  try {
                    await MugenUI.withLoading(() => MugenApi.del(`/api/slip-gaji/${r.id}`), { message: "Menghapus…" });
                    MugenUI.toast("Slip Gaji dihapus.", "success");
                    onBerubah();
                  } catch (e) {
                    MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                  }
                });
                wrap.appendChild(btnHapus);
              }
            }
            return wrap;
          },
        },
      );

      listBody.appendChild(MugenUI.buildTable(kolom, rows, { emptyText: "Belum ada Slip Gaji." }));
    } catch (e) {
      listBody.innerHTML = "";
      listBody.appendChild(MugenUI.el("div", {}, e.detail && e.detail.detail ? e.detail.detail : e.message));
    }
  }

  // ================= BARBER: riwayat milik sendiri, read-only =================
  async function renderBarberView(root) {
    root.appendChild(MugenUI.el("div", { class: "subtitle" }, "Riwayat Slip Gaji Anda."));
    const listCard = MugenUI.el("div", { class: "card" });
    root.appendChild(listCard);
    listCard.appendChild(MugenUI.el("h2", {}, "Riwayat"));
    listCard.appendChild(tombolDownloadPdfDaftar(() => ({}), () => "Daftar Slip Gaji Saya.pdf"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);
    const muat = () => loadListInto(listBody, {}, false, muat);
    muat();
  }

  // ================= OWNER/ADMIN: generate + kelola semua barber =================
  async function renderAdminView(root) {
    const today = new Date();
    let barbers = [];
    try {
      barbers = await MugenApi.get("/api/input-data/karyawan", { useCache: true });
    } catch (e) { /* opsional -- form Generate tetap tampil, dropdown Karyawan cuma kosong */ }

    const formCard = MugenUI.el("div", { class: "card" });
    const filterCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    root.appendChild(formCard);
    root.appendChild(filterCard);
    root.appendChild(listCard);

    // ---- Form Generate ----
    formCard.appendChild(MugenUI.el("h2", {}, "Generate Slip Gaji"));
    formCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Komisi/Tips/Uang Harian/Bonus Customer dihitung otomatis dari data yang sudah ada. Generate ulang sebelum " +
      "berstatus Sudah Dibayar akan menghitung ulang komponen ini (potongan tetap sesuai yang diisi terakhir)."));

    const selBarber = MugenUI.el("select");
    for (const b of barbers) selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    // Barber: periode SELALU satu bulan kalender (Bulan+Tahun, TIDAK
    // berubah). Kasir/OB/Kru: TIDAK dibayar bulanan -- periode rentang
    // tanggal bebas (wrapTanggalRentang di bawah), bisa >1 slip dalam
    // bulan kalender yang sama (Tahap 13). Field mana yang tampil
    // bergantung Jabatan karyawan yang dipilih, lihat terapkanTampilanJabatan().
    const wrapBulanTahun = MugenUI.el("div");
    const selBulan = MugenUI.el("select");
    for (let m = 1; m <= 12; m++) selBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    selBulan.value = String(today.getMonth() + 1);
    const selTahun = MugenUI.el("select");
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) selTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    selTahun.value = String(today.getFullYear());
    wrapBulanTahun.appendChild(MugenUI.el("label", {}, "Bulan"));
    wrapBulanTahun.appendChild(selBulan);
    wrapBulanTahun.appendChild(MugenUI.el("label", {}, "Tahun"));
    wrapBulanTahun.appendChild(selTahun);

    const wrapTanggalRentang = MugenUI.el("div");
    const inputTanggalMulai = MugenUI.el("input", { type: "date" });
    const inputTanggalSelesai = MugenUI.el("input", { type: "date" });
    inputTanggalMulai.value = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-01`;
    inputTanggalSelesai.value = today.toISOString().slice(0, 10);
    wrapTanggalRentang.appendChild(MugenUI.el("label", {}, "Tanggal Mulai"));
    wrapTanggalRentang.appendChild(inputTanggalMulai);
    wrapTanggalRentang.appendChild(MugenUI.el("label", {}, "Tanggal Selesai"));
    wrapTanggalRentang.appendChild(inputTanggalSelesai);
    // Karyawan Non-Barber (Kasir/OB/Kru): Gaji Pokok bulanan flat diganti
    // Jumlah Hari Masuk (dikalikan gaji_per_hari karyawan itu) -- field
    // mana yang tampil bergantung Jabatan karyawan yang sedang dipilih di
    // selBarber, lihat terapkanTampilanJabatan() di bawah.
    const wrapGajiPokok = MugenUI.el("div");
    const inputGajiPokok = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    wrapGajiPokok.appendChild(MugenUI.el("label", {}, "Gaji Pokok (Rp, opsional)"));
    wrapGajiPokok.appendChild(inputGajiPokok);

    const wrapHariMasuk = MugenUI.el("div");
    const inputJumlahHariMasuk = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const infoGajiPerHari = MugenUI.el("div", { class: "subtitle" }, "");
    wrapHariMasuk.appendChild(MugenUI.el("label", {}, "Jumlah Hari Masuk"));
    wrapHariMasuk.appendChild(inputJumlahHariMasuk);
    wrapHariMasuk.appendChild(infoGajiPerHari);

    const inputPotonganKasbon = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const inputPenyesuaianKomisi = MugenUI.el("input", { type: "number", value: "0" }); // boleh negatif -- tanpa atribut min
    const inputReimburse = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const inputBonusManual = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const inputPotonganLain = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const inputCatatanPotongan = MugenUI.el("input", { type: "text", placeholder: "Opsional, mis. keterlambatan" });
    const btnGenerate = MugenUI.el("button", { class: "btn-primary" }, "Generate Slip Gaji");
    const formError = MugenUI.el("div", { class: "login-error" });

    function jabatanTerpilih() {
      const b = barbers.find((x) => String(x.id) === selBarber.value);
      return (b && b.jabatan) || "barber";
    }
    function terapkanTampilanJabatan() {
      const barber = jabatanTerpilih() === "barber";
      wrapGajiPokok.style.display = barber ? "" : "none";
      wrapHariMasuk.style.display = barber ? "none" : "";
      wrapBulanTahun.style.display = barber ? "" : "none";
      wrapTanggalRentang.style.display = barber ? "none" : "";
    }

    // Belum ada tab tersendiri untuk atur Gaji Pokok per-barber (lihat
    // slip_gaji_db.py) -- form ini SEKALIAN jadi tempatnya, otomatis
    // terisi nilai yang tersimpan saat ini begitu Barber dipilih, dan
    // otomatis "nempel" (tersimpan permanen ke data barber) begitu di-Generate.
    // Karyawan Non-Barber: TIDAK ada nilai tersimpan untuk diisi ulang
    // (Jumlah Hari Masuk selalu diisi manual tiap generate), field ini
    // hanya menampilkan info Gaji per Hari karyawan itu sebagai referensi.
    function isiGajiPokokDariBarber() {
      const b = barbers.find((x) => String(x.id) === selBarber.value);
      inputGajiPokok.value = String((b && b.gaji_pokok) || 0);
      inputJumlahHariMasuk.value = "0";
      infoGajiPerHari.textContent = b ? `Gaji per Hari: ${MugenUI.formatRupiah(b.gaji_per_hari || 0)}` : "";
      terapkanTampilanJabatan();
    }
    // Modul Karyawan Fase 2 (Kasbon): Potongan Kasbon otomatis terisi dari
    // saldo kasbon belum lunas barber yang dipilih (GET /api/kasbon/saldo/
    // {barber_id}), TAPI tetap bebas diedit manual sebelum Generate -- nilai
    // ini HANYA saran awal, tidak disimpan ke mana pun sampai slip benar-
    // benar ditandai Sudah Dibayar (lihat slip_gaji_db.tandai_status()).
    async function isiPotonganKasbonDariBarber() {
      if (!selBarber.value) { inputPotonganKasbon.value = "0"; return; }
      try {
        const saldo = await MugenApi.get(`/api/kasbon/saldo/${selBarber.value}`);
        inputPotonganKasbon.value = String(saldo.saldo || 0);
      } catch (e) { /* opsional -- kalau gagal (mis. tidak ada izin), biarkan manual */ }
    }
    // Modul Karyawan Fase 3 (Komisi): Penyesuaian Komisi otomatis terisi dari
    // net bonus-potongan barber+PERIODE yang dipilih (GET /api/komisi/saldo/
    // {barber_id}?tahun=&bulan=) -- BEDA dari Potongan Kasbon yang cuma
    // bereaksi ke Barber (saldo berjalan, bukan per-periode), field ini
    // reaktif ke Barber DAN Bulan/Tahun sekaligus. Tetap bebas diedit manual
    // sebelum Generate, nilai ini HANYA saran awal.
    async function isiPenyesuaianKomisiDariPeriode() {
      // Komisi murni barber-only (Kasir/OB/Kru tidak pernah punya baris
      // penyesuaian komisi -- dropdown Komisi sudah /api/input-data/barbers,
      // lihat komisi_penyesuaian_db.py) -- tidak perlu fetch sama sekali.
      if (!selBarber.value || jabatanTerpilih() !== "barber") { inputPenyesuaianKomisi.value = "0"; return; }
      try {
        const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
        const saldo = await MugenApi.get(`/api/komisi/saldo/${selBarber.value}?${qs.toString()}`);
        inputPenyesuaianKomisi.value = String(saldo.saldo || 0);
      } catch (e) { /* opsional -- kalau gagal (mis. tidak ada izin), biarkan manual */ }
    }
    // Modul Karyawan Fase 4 (Reimburse): Reimburse otomatis terisi dari
    // total klaim BERSTATUS DISETUJUI barber+PERIODE yang dipilih. Barber
    // (periode bulan kalender): GET /api/reimburse/saldo/{barber_id}?
    // tahun=&bulan= (TIDAK berubah). Kasir/OB/Kru (Tahap 13: periode
    // rentang tanggal bebas): GET /api/reimburse/saldo-rentang/{barber_id}?
    // tanggal_mulai=&tanggal_selesai=. Nilai ini selalu >= 0 (murni
    // penambahan, tidak pernah negatif), HANYA saran awal, tetap bebas
    // diedit manual sebelum Generate.
    async function isiReimburseDariPeriode() {
      if (!selBarber.value) { inputReimburse.value = "0"; return; }
      try {
        let saldo;
        if (jabatanTerpilih() === "barber") {
          const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
          saldo = await MugenApi.get(`/api/reimburse/saldo/${selBarber.value}?${qs.toString()}`);
        } else {
          if (!inputTanggalMulai.value || !inputTanggalSelesai.value) { inputReimburse.value = "0"; return; }
          const qs = new URLSearchParams({ tanggal_mulai: inputTanggalMulai.value, tanggal_selesai: inputTanggalSelesai.value });
          saldo = await MugenApi.get(`/api/reimburse/saldo-rentang/${selBarber.value}?${qs.toString()}`);
        }
        inputReimburse.value = String(saldo.saldo || 0);
      } catch (e) { /* opsional -- kalau gagal (mis. tidak ada izin), biarkan manual */ }
    }
    selBarber.addEventListener("change", () => {
      isiGajiPokokDariBarber();
      isiPotonganKasbonDariBarber();
      isiPenyesuaianKomisiDariPeriode();
      isiReimburseDariPeriode();
    });
    selBulan.addEventListener("change", () => {
      isiPenyesuaianKomisiDariPeriode();
      isiReimburseDariPeriode();
    });
    selTahun.addEventListener("change", () => {
      isiPenyesuaianKomisiDariPeriode();
      isiReimburseDariPeriode();
    });
    inputTanggalMulai.addEventListener("change", isiReimburseDariPeriode);
    inputTanggalSelesai.addEventListener("change", isiReimburseDariPeriode);
    isiGajiPokokDariBarber();
    isiPotonganKasbonDariBarber();
    isiPenyesuaianKomisiDariPeriode();
    isiReimburseDariPeriode();

    formCard.appendChild(MugenUI.el("label", {}, "Karyawan"));
    formCard.appendChild(selBarber);
    formCard.appendChild(wrapBulanTahun);
    formCard.appendChild(wrapTanggalRentang);
    formCard.appendChild(wrapGajiPokok);
    formCard.appendChild(wrapHariMasuk);
    formCard.appendChild(MugenUI.el("label", {}, "Potongan Kasbon (Rp, opsional)"));
    formCard.appendChild(inputPotonganKasbon);
    formCard.appendChild(MugenUI.el("label", {}, "Penyesuaian Komisi (Rp, boleh negatif, opsional)"));
    formCard.appendChild(inputPenyesuaianKomisi);
    formCard.appendChild(MugenUI.el("label", {}, "Reimburse (Rp, opsional)"));
    formCard.appendChild(inputReimburse);
    formCard.appendChild(MugenUI.el("label", {}, "Bonus Manual (Rp, opsional)"));
    formCard.appendChild(inputBonusManual);
    formCard.appendChild(MugenUI.el("label", {}, "Potongan Lain (Rp, opsional)"));
    formCard.appendChild(inputPotonganLain);
    formCard.appendChild(MugenUI.el("label", {}, "Catatan Potongan (opsional)"));
    formCard.appendChild(inputCatatanPotongan);
    formCard.appendChild(formError);
    formCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnGenerate));

    btnGenerate.addEventListener("click", async () => {
      formError.textContent = "";
      if (!selBarber.value) { formError.textContent = "Pilih karyawan dulu."; return; }
      const barberMode = jabatanTerpilih() === "barber";
      if (!barberMode && (!inputJumlahHariMasuk.value || Number(inputJumlahHariMasuk.value) < 0)) {
        formError.textContent = "Jumlah Hari Masuk harus diisi (0 atau lebih)."; return;
      }
      if (!barberMode && (!inputTanggalMulai.value || !inputTanggalSelesai.value)) {
        formError.textContent = "Tanggal Mulai dan Tanggal Selesai wajib diisi."; return;
      }
      if (!barberMode && inputTanggalSelesai.value < inputTanggalMulai.value) {
        formError.textContent = "Tanggal Selesai tidak boleh sebelum Tanggal Mulai."; return;
      }
      btnGenerate.disabled = true;
      try {
        const body = {
          barber_id: Number(selBarber.value),
          potongan_kasbon: Number(inputPotonganKasbon.value) || 0, potongan_lain: Number(inputPotonganLain.value) || 0,
          penyesuaian_komisi: Number(inputPenyesuaianKomisi.value) || 0,
          reimburse: Number(inputReimburse.value) || 0,
          bonus_manual: Number(inputBonusManual.value) || 0,
          catatan_potongan: inputCatatanPotongan.value.trim(),
        };
        if (barberMode) {
          body.tahun = Number(selTahun.value);
          body.bulan = Number(selBulan.value);
          body.gaji_pokok = Number(inputGajiPokok.value) || 0;
        } else {
          body.tanggal_mulai = inputTanggalMulai.value;
          body.tanggal_selesai = inputTanggalSelesai.value;
          body.jumlah_hari_masuk = Number(inputJumlahHariMasuk.value) || 0;
        }
        await MugenUI.withLoading(() => MugenApi.post("/api/slip-gaji", body), { message: "Menghitung Slip Gaji…" });
        // Sinkronkan cache lokal supaya kalau karyawan yang sama dipilih lagi
        // tanpa reload halaman, Gaji Pokok yang tampil sudah yang terbaru.
        const b = barbers.find((x) => String(x.id) === selBarber.value);
        if (b && barberMode) b.gaji_pokok = Number(inputGajiPokok.value) || 0;
        MugenUI.toast("Slip Gaji berhasil dibuat.", "success");
        loadList();
      } catch (e) {
        formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      } finally {
        btnGenerate.disabled = false;
      }
    });

    // ---- Filter ----
    filterCard.appendChild(MugenUI.el("h2", {}, "Filter"));
    const filBarber = MugenUI.el("select");
    filBarber.appendChild(MugenUI.el("option", { value: "" }, "Semua Karyawan"));
    for (const b of barbers) filBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    const filBulan = MugenUI.el("select");
    filBulan.appendChild(MugenUI.el("option", { value: "" }, "Semua Bulan"));
    for (let m = 1; m <= 12; m++) filBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    const filTahun = MugenUI.el("select");
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) filTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    filTahun.value = String(today.getFullYear());
    filterCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;" }, [filBarber, filBulan, filTahun]));

    // ---- Daftar ----
    listCard.appendChild(MugenUI.el("h2", {}, "Daftar Slip Gaji"));

    function paramsFilterAktif() {
      const params = { tahun: filTahun.value };
      if (filBulan.value) params.bulan = filBulan.value;
      if (filBarber.value) params.barber_id = filBarber.value;
      return params;
    }
    listCard.appendChild(tombolDownloadPdfDaftar(paramsFilterAktif, () => {
      const karyawan = filBarber.value ? (barbers.find((b) => String(b.id) === filBarber.value) || {}).nama || "Karyawan" : "Semua Karyawan";
      const periode = filBulan.value ? `${MugenUI.namaBulan(Number(filBulan.value))} ${filTahun.value}` : filTahun.value;
      return `Daftar Slip Gaji ${karyawan} ${periode}.pdf`;
    }));

    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    function loadList() {
      loadListInto(listBody, paramsFilterAktif(), true, loadList);
    }

    filBarber.addEventListener("change", loadList);
    filBulan.addEventListener("change", loadList);
    filTahun.addEventListener("change", loadList);

    loadList();
  }

  async function render(root) {
    const user = MugenState.getUser();
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Slip Gaji"));

    if (user.role === "barber") {
      await renderBarberView(root);
    } else {
      await renderAdminView(root);
    }
  }

  return { render };
})();
