// pages/komisi.js — Modul Karyawan (Fase 3): Komisi (Audit & Penyesuaian).
// Satu halaman, dua sudut pandang (pola yang sama seperti pages/kasbon.js):
// - Owner ('admin') selalu penuh; 'staff' (Admin) HANYA kalau diberi izin
//   izin_komisi (Setting > Hak Akses Admin) -- lihat renderAdminView().
//   Backend (routers/komisi.py) yang benar-benar menegakkan ini, frontend
//   di sini hanya menampilkan pesan error kalau ditolak server.
// - 'barber': hanya melihat riwayat penyesuaian miliknya sendiri, read-only
//   (tidak ada tombol Tambah/Edit/Hapus) -- lihat renderBarberView().
//
// "Riwayat Komisi" (angka komisi dasar per barber/periode) memakai ULANG
// GET /api/rekap/bulanan yang sudah ada apa adanya -- halaman ini TIDAK
// menghitung ulang komisi dasar sendiri, hanya menampilkan lapisan
// penyesuaian manual (bonus/potongan) di atasnya. Penyesuaian TERKUNCI
// (tidak bisa dibuat/diedit/dihapus) begitu Slip Gaji periode itu berstatus
// Sudah Dibayar -- lihat field `terkunci` yang dikembalikan API.

const PageKomisi = (() => {
  function badgeJenis(jenis) {
    return MugenUI.el("span", { class: "badge" + (jenis === "bonus" ? "" : " badge-libur") },
      jenis === "bonus" ? "Bonus" : "Potongan");
  }

  // Perbaikan Alur Cetak PDF: lihat catatan sama di pages/kasbon.js.
  function tombolDownloadPdf(getParams, computeFilename) {
    // Feature Gating "export_pdf": lihat catatan sama di pages/rekap.js.
    if (typeof MugenFeature !== "undefined" && !MugenFeature.has("export_pdf")) {
      return MugenFeature.upgradeBlock("Export PDF");
    }
    const btn = MugenUI.el("button", {}, "Cetak PDF");
    btn.addEventListener("click", () => {
      const qs = new URLSearchParams(getParams());
      const filename = computeFilename ? computeFilename() : "Laporan Komisi.pdf";
      MugenPdfPreview.open({
        generate: () => MugenApi.fetchBlob(`/api/komisi/pdf?${qs}`),
        filename: MugenUI.namaFileAman(filename),
      });
    });
    return btn;
  }

  // REVISI UI/UX Premium: refreshInto() (skeleton tabel + crossfade)
  // menggantikan pola innerHTML="Memuat..." manual -- lihat catatan di ui.js.
  async function tampilkanRiwayatKomisi(riwayatBody, barberId, tahun, bulan) {
    await MugenUI.refreshInto(riwayatBody, async () => {
      try {
        const qs = new URLSearchParams({ tahun: String(tahun), bulan: String(bulan) });
        if (barberId) qs.set("barber_id", String(barberId));
        const data = await MugenApi.get(`/api/rekap/bulanan?${qs.toString()}`);
        const rows = Array.isArray(data) ? data : [];
        return MugenUI.buildTable(
          [
            { key: "nama_barber", label: "Barber" },
            { key: "jumlah_service", label: "Jumlah Service" },
            { key: "total_komisi", label: "Komisi Dasar", format: MugenUI.formatRupiah },
            { key: "tips", label: "Tips", format: MugenUI.formatRupiah },
            { key: "uang_harian", label: "Uang Harian", format: MugenUI.formatRupiah },
            { key: "bonus_customer", label: "Bonus Customer", format: MugenUI.formatRupiah },
            { key: "total_pendapatan", label: "Total Pendapatan", format: MugenUI.formatRupiah },
          ],
          rows,
          { emptyText: "Tidak ada data untuk periode ini." },
        );
      } catch (e) {
        return MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message);
      }
    }, { skeleton: { kind: "table", cols: 7, rows: 4 } });
  }

  // ================= BARBER: riwayat penyesuaian milik sendiri, read-only =================
  async function renderBarberView(root) {
    const today = new Date();
    root.appendChild(MugenUI.el("div", { class: "subtitle" }, "Riwayat komisi & penyesuaian Anda."));

    const filterCard = MugenUI.el("div", { class: "card" });
    const riwayatCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    root.appendChild(filterCard);
    root.appendChild(riwayatCard);
    root.appendChild(listCard);

    filterCard.appendChild(MugenUI.el("h2", {}, "Periode"));
    const selBulan = MugenUI.el("select");
    for (let m = 1; m <= 12; m++) selBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    selBulan.value = String(today.getMonth() + 1);
    const selTahun = MugenUI.el("select");
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) selTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    selTahun.value = String(today.getFullYear());
    filterCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;" }, [selBulan, selTahun]));
    filterCard.appendChild(tombolDownloadPdf(
      () => ({ tahun: selTahun.value, bulan: selBulan.value }),
      () => `Laporan Komisi Saya ${MugenUI.namaBulan(Number(selBulan.value))} ${selTahun.value}.pdf`,
    ));

    riwayatCard.appendChild(MugenUI.el("h2", {}, "Riwayat Komisi (Dasar)"));
    const riwayatBody = MugenUI.el("div");
    riwayatCard.appendChild(riwayatBody);

    listCard.appendChild(MugenUI.el("h2", {}, "Penyesuaian Komisi"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    const user = MugenState.getUser();

    async function muat() {
      tampilkanRiwayatKomisi(riwayatBody, user.barber_id, selTahun.value, selBulan.value);
      // REVISI UI/UX Premium: refreshInto() (skeleton tabel + crossfade)
      // menggantikan pola innerHTML="Memuat..." manual -- lihat catatan di ui.js.
      await MugenUI.refreshInto(listBody, async () => {
        try {
          const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
          const data = await MugenApi.get(`/api/komisi/penyesuaian?${qs.toString()}`);
          const rows = Array.isArray(data) ? data : [];
          return MugenUI.buildTable(
            [
              { key: "jenis", label: "Jenis", format: badgeJenis },
              { key: "jumlah", label: "Jumlah", format: MugenUI.formatRupiah },
              { key: "keterangan", label: "Keterangan" },
            ],
            rows,
            { emptyText: "Tidak ada penyesuaian komisi untuk periode ini." },
          );
        } catch (e) {
          return MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message);
        }
      }, { skeleton: { kind: "table", cols: 3, rows: 4 } });
    }

    selBulan.addEventListener("change", muat);
    selTahun.addEventListener("change", muat);
    muat();
  }

  // ================= OWNER/ADMIN: kelola penyesuaian komisi =================
  async function renderAdminView(root) {
    const today = new Date();
    let editingId = null;
    let barbers = [];
    try {
      barbers = await MugenApi.get("/api/input-data/barbers", { useCache: true });
    } catch (e) { /* opsional -- form tetap tampil, dropdown Barber cuma kosong */ }

    const formCard = MugenUI.el("div", { class: "card" });
    const filterCard = MugenUI.el("div", { class: "card" });
    const riwayatCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    root.appendChild(formCard);
    root.appendChild(filterCard);
    root.appendChild(riwayatCard);
    root.appendChild(listCard);

    // ---- Form Tambah / Edit Penyesuaian ----
    const formTitle = MugenUI.el("h2", {}, "Tambah Penyesuaian Komisi");
    const selBarber = MugenUI.el("select");
    for (const b of barbers) selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    const selBulan = MugenUI.el("select");
    for (let m = 1; m <= 12; m++) selBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    selBulan.value = String(today.getMonth() + 1);
    const selTahun = MugenUI.el("select");
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) selTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    selTahun.value = String(today.getFullYear());
    const selJenis = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "bonus" }, "Bonus Tambahan"),
      MugenUI.el("option", { value: "potongan" }, "Potongan Komisi"),
    ]);
    const inputJumlah = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const inputKeterangan = MugenUI.el("input", { type: "text", placeholder: "Wajib diisi -- alasan penyesuaian" });
    const lockedNote = MugenUI.el("div", { class: "subtitle", style: "display:none;" },
      "Slip Gaji periode ini sudah Sudah Dibayar dan terkunci -- batalkan statusnya dulu di halaman Slip Gaji kalau perlu mengubah ini.");
    const btnSubmit = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
    const btnBatal = MugenUI.el("button", { style: "display:none;" }, "Batal Edit");
    const formError = MugenUI.el("div", { class: "login-error" });

    formCard.appendChild(formTitle);
    formCard.appendChild(MugenUI.el("label", {}, "Barber"));
    formCard.appendChild(selBarber);
    formCard.appendChild(MugenUI.el("label", {}, "Bulan"));
    formCard.appendChild(selBulan);
    formCard.appendChild(MugenUI.el("label", {}, "Tahun"));
    formCard.appendChild(selTahun);
    formCard.appendChild(MugenUI.el("label", {}, "Jenis"));
    formCard.appendChild(selJenis);
    formCard.appendChild(MugenUI.el("label", {}, "Jumlah (Rp)"));
    formCard.appendChild(inputJumlah);
    formCard.appendChild(MugenUI.el("label", {}, "Keterangan"));
    formCard.appendChild(inputKeterangan);
    formCard.appendChild(lockedNote);
    formCard.appendChild(formError);
    formCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnSubmit, btnBatal]));

    function resetForm() {
      editingId = null;
      formTitle.textContent = "Tambah Penyesuaian Komisi";
      btnSubmit.textContent = "Simpan";
      btnBatal.style.display = "none";
      selBarber.disabled = false;
      selBulan.disabled = false;
      selTahun.disabled = false;
      inputJumlah.value = "0";
      selJenis.value = "bonus";
      inputKeterangan.value = "";
      lockedNote.style.display = "none";
      formError.textContent = "";
    }

    function isiFormUntukEdit(p) {
      editingId = p.id;
      formTitle.textContent = `Edit Penyesuaian #${p.id}`;
      btnSubmit.textContent = "Simpan Perubahan";
      btnBatal.style.display = "";
      selBarber.value = String(p.barber_id);
      selBarber.disabled = true;
      selBulan.value = String(p.bulan);
      selBulan.disabled = true;
      selTahun.value = String(p.tahun);
      selTahun.disabled = true;
      selJenis.value = p.jenis;
      inputJumlah.value = String(p.jumlah);
      inputKeterangan.value = p.keterangan || "";
      lockedNote.style.display = "none";
      formError.textContent = "";
      formCard.scrollIntoView({ behavior: "smooth" });
    }

    btnBatal.addEventListener("click", resetForm);

    btnSubmit.addEventListener("click", async () => {
      formError.textContent = "";
      if (!selBarber.value) { formError.textContent = "Pilih barber dulu."; return; }
      if (!inputJumlah.value || Number(inputJumlah.value) <= 0) { formError.textContent = "Jumlah harus lebih dari 0."; return; }
      if (!inputKeterangan.value.trim()) { formError.textContent = "Keterangan wajib diisi."; return; }
      try {
        // REVISI UI/UX Premium: withButtonLoading() (spinner inline di
        // tombol) menggantikan withLoading() (overlay layar penuh) untuk
        // aksi CRUD rutin -- lihat catatan di ui.js.
        if (editingId) {
          await MugenUI.withButtonLoading(btnSubmit, () => MugenApi.put(`/api/komisi/penyesuaian/${editingId}`, {
            jenis: selJenis.value, jumlah: Number(inputJumlah.value) || 0,
            keterangan: inputKeterangan.value.trim(),
          }));
          MugenUI.toast("Penyesuaian komisi diperbarui.", "success");
        } else {
          await MugenUI.withButtonLoading(btnSubmit, () => MugenApi.post("/api/komisi/penyesuaian", {
            barber_id: Number(selBarber.value), tahun: Number(selTahun.value), bulan: Number(selBulan.value),
            jenis: selJenis.value, jumlah: Number(inputJumlah.value) || 0,
            keterangan: inputKeterangan.value.trim(),
          }));
          MugenUI.toast("Penyesuaian komisi disimpan.", "success");
        }
        resetForm();
        loadList();
      } catch (e) {
        formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });

    // ---- Filter ----
    filterCard.appendChild(MugenUI.el("h2", {}, "Filter"));
    const filBarber = MugenUI.el("select");
    filBarber.appendChild(MugenUI.el("option", { value: "" }, "Semua Barber"));
    for (const b of barbers) filBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    const filJenis = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "" }, "Semua Jenis"),
      MugenUI.el("option", { value: "bonus" }, "Bonus"),
      MugenUI.el("option", { value: "potongan" }, "Potongan"),
    ]);
    const filBulan = MugenUI.el("select");
    for (let m = 1; m <= 12; m++) filBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    filBulan.value = String(today.getMonth() + 1);
    const filTahun = MugenUI.el("select");
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) filTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    filTahun.value = String(today.getFullYear());
    filterCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;" }, [filBarber, filJenis, filBulan, filTahun]));
    filterCard.appendChild(tombolDownloadPdf(() => {
      const params = { tahun: filTahun.value, bulan: filBulan.value };
      if (filBarber.value) params.barber_id = filBarber.value;
      if (filJenis.value) params.jenis = filJenis.value;
      return params;
    }, () => {
      const karyawan = filBarber.value ? (barbers.find((b) => String(b.id) === filBarber.value) || {}).nama || "Karyawan" : "Semua Barber";
      const jenis = filJenis.value === "bonus" ? "Bonus" : filJenis.value === "potongan" ? "Potongan" : "";
      return ["Laporan Komisi", karyawan, jenis, MugenUI.namaBulan(Number(filBulan.value)), filTahun.value].filter(Boolean).join(" ") + ".pdf";
    }));

    // ---- Riwayat Komisi (dasar, reuse Rekap Bulanan) ----
    riwayatCard.appendChild(MugenUI.el("h2", {}, "Riwayat Komisi (Dasar)"));
    riwayatCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Angka komisi dasar (belum termasuk penyesuaian manual di bawah), sesuai filter Bulan/Tahun/Barber di atas."));
    const riwayatBody = MugenUI.el("div");
    riwayatCard.appendChild(riwayatBody);

    // ---- Daftar Penyesuaian ----
    listCard.appendChild(MugenUI.el("h2", {}, "Daftar Penyesuaian Komisi"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    async function loadList() {
      tampilkanRiwayatKomisi(riwayatBody, filBarber.value || null, filTahun.value, filBulan.value);

      listBody.innerHTML = "";
      listBody.appendChild(MugenUI.skeleton("table", { cols: 5, rows: 3 }));
      try {
        const qs = new URLSearchParams({ tahun: filTahun.value, bulan: filBulan.value });
        if (filBarber.value) qs.set("barber_id", filBarber.value);
        if (filJenis.value) qs.set("jenis", filJenis.value);
        const data = await MugenApi.get(`/api/komisi/penyesuaian?${qs.toString()}`);
        const rows = Array.isArray(data) ? data : [];
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.buildTable(
          [
            { key: "nama_barber", label: "Barber" },
            { key: "jenis", label: "Jenis", format: badgeJenis },
            { key: "jumlah", label: "Jumlah", format: MugenUI.formatRupiah },
            { key: "keterangan", label: "Keterangan" },
            {
              key: "aksi", label: "Aksi", format: (_, r) => {
                if (r.terkunci) return MugenUI.el("span", { class: "subtitle" }, "Terkunci (Slip Sudah Dibayar)");
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnEdit = MugenUI.el("button", {}, "Edit");
                btnEdit.addEventListener("click", () => isiFormUntukEdit(r));
                const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btnHapus.addEventListener("click", async () => {
                  if (!confirm(`Hapus penyesuaian ${r.jenis} untuk ${r.nama_barber}?`)) return;
                  try {
                    await MugenUI.withButtonLoading(btnHapus, () => MugenApi.del(`/api/komisi/penyesuaian/${r.id}`));
                    MugenUI.toast("Penyesuaian komisi dihapus.", "success");
                    loadList();
                  } catch (e) {
                    MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                  }
                });
                wrap.appendChild(btnEdit);
                wrap.appendChild(btnHapus);
                return wrap;
              },
            },
          ],
          rows,
          { emptyText: "Belum ada penyesuaian komisi untuk filter ini." },
        ));
      } catch (e) {
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message));
      }
    }

    filBarber.addEventListener("change", loadList);
    filJenis.addEventListener("change", loadList);
    filBulan.addEventListener("change", loadList);
    filTahun.addEventListener("change", loadList);

    resetForm();
    loadList();
  }

  async function render(root) {
    const user = MugenState.getUser();
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Komisi"));

    if (user.role === "barber") {
      await renderBarberView(root);
    } else {
      await renderAdminView(root);
    }
  }

  return { render };
})();
