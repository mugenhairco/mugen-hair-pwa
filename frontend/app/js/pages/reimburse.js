// pages/reimburse.js — Modul Karyawan (Fase 4): Reimburse.
// BEDA dari kasbon.js/komisi.js: klaim DIAJUKAN SENDIRI oleh Barber
// (self-service) -- barber boleh Tambah/Edit/Hapus/Upload Bukti untuk
// klaim MILIKNYA SENDIRI selama masih berstatus Pending, tanpa perlu
// izin_reimburse (itu HANYA berlaku untuk staff mengelola klaim SEMUA
// barber + aksi Setujui/Tolak, lihat routers/reimburse.py). Backend yang
// benar-benar menegakkan ini, frontend di sini hanya menampilkan pesan
// error kalau ditolak server.

const PageReimburse = (() => {
  function todayIso() {
    return new Date().toISOString().slice(0, 10);
  }

  function badgeStatus(status) {
    const label = status === "disetujui" ? "Disetujui" : status === "ditolak" ? "Ditolak" : "Pending";
    return MugenUI.el("span", { class: "badge" + (status === "disetujui" ? "" : " badge-libur") }, label);
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
      const filename = computeFilename ? computeFilename() : "Laporan Reimburse.pdf";
      MugenPdfPreview.open({
        generate: () => MugenApi.fetchBlob(`/api/reimburse/pdf?${qs}`),
        filename: MugenUI.namaFileAman(filename),
      });
    });
    return btn;
  }

  function kolomBukti(r) {
    if (!r.bukti_filename) return MugenUI.el("span", { class: "subtitle" }, "-");
    const a = MugenUI.el("a", { href: `${MUGEN_API_BASE}/api/reimburse/${r.id}/bukti`, target: "_blank" }, "Lihat Bukti");
    return a;
  }

  async function unggahBukti(id, file, onSelesai) {
    try {
      await MugenUI.withLoading(() => MugenApi.uploadFile(`/api/reimburse/${id}/bukti`, file), { message: "Mengunggah bukti…" });
      MugenUI.toast("Bukti berhasil diunggah.", "success");
      onSelesai();
    } catch (e) {
      MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
    }
  }

  function buatTombolUploadBukti(r, onSelesai) {
    const inputFile = MugenUI.el("input", { type: "file", accept: "image/jpeg,image/png,image/webp,application/pdf", style: "display:none;" });
    const btn = MugenUI.el("button", {}, r.bukti_filename ? "Ganti Bukti" : "Upload Bukti");
    btn.addEventListener("click", () => inputFile.click());
    inputFile.addEventListener("change", () => {
      if (inputFile.files[0]) unggahBukti(r.id, inputFile.files[0], onSelesai);
    });
    return MugenUI.el("span", {}, [btn, inputFile]);
  }

  // ================= BARBER: pengajuan milik sendiri =================
  async function renderBarberView(root) {
    const user = MugenState.getUser();
    let kategoriOptions = [];
    try {
      kategoriOptions = await MugenApi.get("/api/reimburse/kategori", { useCache: true });
    } catch (e) { /* opsional -- form tetap tampil */ }

    const formCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    root.appendChild(formCard);
    root.appendChild(listCard);

    const kategoriListId = "reimburse-kategori-list";
    const datalist = MugenUI.el("datalist", { id: kategoriListId });
    for (const k of kategoriOptions) datalist.appendChild(MugenUI.el("option", { value: k }));
    root.appendChild(datalist);

    let editingId = null;
    const formTitle = MugenUI.el("h2", {}, "Ajukan Reimburse");
    const inputTanggal = MugenUI.el("input", { type: "date", value: todayIso(), max: todayIso() });
    const inputKategori = MugenUI.el("input", { type: "text", list: kategoriListId, placeholder: "mis. Transportasi" });
    const inputNominal = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const inputKeterangan = MugenUI.el("input", { type: "text", placeholder: "Opsional" });
    const btnSubmit = MugenUI.el("button", { class: "btn-primary" }, "Ajukan");
    const btnBatal = MugenUI.el("button", { style: "display:none;" }, "Batal Edit");
    const formError = MugenUI.el("div", { class: "login-error" });

    formCard.appendChild(formTitle);
    formCard.appendChild(MugenUI.el("label", {}, "Tanggal"));
    formCard.appendChild(inputTanggal);
    formCard.appendChild(MugenUI.el("label", {}, "Kategori"));
    formCard.appendChild(inputKategori);
    formCard.appendChild(MugenUI.el("label", {}, "Nominal (Rp)"));
    formCard.appendChild(inputNominal);
    formCard.appendChild(MugenUI.el("label", {}, "Keterangan"));
    formCard.appendChild(inputKeterangan);
    formCard.appendChild(formError);
    formCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnSubmit, btnBatal]));

    function resetForm() {
      editingId = null;
      formTitle.textContent = "Ajukan Reimburse";
      btnSubmit.textContent = "Ajukan";
      btnBatal.style.display = "none";
      inputTanggal.value = todayIso();
      inputKategori.value = "";
      inputNominal.value = "0";
      inputKeterangan.value = "";
      formError.textContent = "";
    }

    function isiFormUntukEdit(r) {
      editingId = r.id;
      formTitle.textContent = `Edit Klaim #${r.id}`;
      btnSubmit.textContent = "Simpan Perubahan";
      btnBatal.style.display = "";
      inputTanggal.value = r.tanggal;
      inputKategori.value = r.kategori;
      inputNominal.value = String(r.nominal);
      inputKeterangan.value = r.keterangan || "";
      formError.textContent = "";
      formCard.scrollIntoView({ behavior: "smooth" });
    }

    btnBatal.addEventListener("click", resetForm);
    btnSubmit.addEventListener("click", async () => {
      formError.textContent = "";
      if (!inputKategori.value.trim()) { formError.textContent = "Kategori tidak boleh kosong."; return; }
      if (!inputNominal.value || Number(inputNominal.value) <= 0) { formError.textContent = "Nominal harus lebih dari 0."; return; }
      btnSubmit.disabled = true;
      try {
        const body = {
          tanggal: inputTanggal.value, kategori: inputKategori.value.trim(),
          nominal: Number(inputNominal.value) || 0, keterangan: inputKeterangan.value.trim(),
        };
        if (editingId) {
          await MugenUI.withLoading(() => MugenApi.put(`/api/reimburse/${editingId}`, body), { message: "Menyimpan…" });
          MugenUI.toast("Klaim reimburse diperbarui.", "success");
        } else {
          await MugenUI.withLoading(() => MugenApi.post("/api/reimburse", body), { message: "Mengajukan…" });
          MugenUI.toast("Klaim reimburse diajukan.", "success");
        }
        resetForm();
        loadList();
      } catch (e) {
        formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      } finally {
        btnSubmit.disabled = false;
      }
    });

    listCard.appendChild(MugenUI.el("h2", {}, "Riwayat Klaim Saya"));
    listCard.appendChild(tombolDownloadPdf(() => ({}), () => "Laporan Reimburse Saya.pdf"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    async function loadList() {
      listBody.innerHTML = "Memuat...";
      try {
        const data = await MugenApi.get("/api/reimburse");
        const rows = Array.isArray(data) ? data : [];
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.buildTable(
          [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            { key: "kategori", label: "Kategori" },
            { key: "nominal", label: "Nominal", format: MugenUI.formatRupiah },
            { key: "status", label: "Status", format: badgeStatus },
            { key: "catatan_approval", label: "Catatan", format: (v) => v || "-" },
            { key: "bukti", label: "Bukti", format: (_, r) => kolomBukti(r) },
            {
              key: "aksi", label: "Aksi", format: (_, r) => {
                if (r.status !== "pending") return MugenUI.el("span", { class: "subtitle" }, "-");
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                wrap.appendChild(buatTombolUploadBukti(r, loadList));
                const btnEdit = MugenUI.el("button", {}, "Edit");
                btnEdit.addEventListener("click", () => isiFormUntukEdit(r));
                wrap.appendChild(btnEdit);
                const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btnHapus.addEventListener("click", async () => {
                  if (!confirm(`Hapus klaim reimburse tanggal ${r.tanggal}?`)) return;
                  try {
                    await MugenApi.del(`/api/reimburse/${r.id}`);
                    MugenUI.toast("Klaim reimburse dihapus.", "success");
                    loadList();
                  } catch (e) {
                    MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                  }
                });
                wrap.appendChild(btnHapus);
                return wrap;
              },
            },
          ],
          rows,
          { emptyText: "Belum ada klaim reimburse." },
        ));
      } catch (e) {
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.el("div", {}, e.detail && e.detail.detail ? e.detail.detail : e.message));
      }
    }

    resetForm();
    loadList();
  }

  // ================= OWNER/ADMIN: kelola & approve semua klaim =================
  async function renderAdminView(root) {
    const today = new Date();
    let editingId = null;
    let barbers = [];
    let kategoriOptions = [];
    try {
      [barbers, kategoriOptions] = await Promise.all([
        MugenApi.get("/api/input-data/karyawan", { useCache: true }),
        MugenApi.get("/api/reimburse/kategori", { useCache: true }),
      ]);
    } catch (e) { /* opsional */ }

    const formCard = MugenUI.el("div", { class: "card" });
    const filterCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    root.appendChild(formCard);
    root.appendChild(filterCard);
    root.appendChild(listCard);

    const kategoriListId = "reimburse-kategori-list";
    const datalist = MugenUI.el("datalist", { id: kategoriListId });
    for (const k of kategoriOptions) datalist.appendChild(MugenUI.el("option", { value: k }));
    root.appendChild(datalist);

    // ---- Form Tambah / Edit (Owner bisa mengajukan atas nama barber) ----
    const formTitle = MugenUI.el("h2", {}, "Tambah Klaim Reimburse");
    const selBarber = MugenUI.el("select");
    for (const b of barbers) selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    const inputTanggal = MugenUI.el("input", { type: "date", value: todayIso(), max: todayIso() });
    const inputKategori = MugenUI.el("input", { type: "text", list: kategoriListId, placeholder: "mis. Transportasi" });
    const inputNominal = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const inputKeterangan = MugenUI.el("input", { type: "text", placeholder: "Opsional" });
    const btnSubmit = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
    const btnBatal = MugenUI.el("button", { style: "display:none;" }, "Batal Edit");
    const formError = MugenUI.el("div", { class: "login-error" });

    formCard.appendChild(formTitle);
    formCard.appendChild(MugenUI.el("label", {}, "Karyawan"));
    formCard.appendChild(selBarber);
    formCard.appendChild(MugenUI.el("label", {}, "Tanggal"));
    formCard.appendChild(inputTanggal);
    formCard.appendChild(MugenUI.el("label", {}, "Kategori"));
    formCard.appendChild(inputKategori);
    formCard.appendChild(MugenUI.el("label", {}, "Nominal (Rp)"));
    formCard.appendChild(inputNominal);
    formCard.appendChild(MugenUI.el("label", {}, "Keterangan"));
    formCard.appendChild(inputKeterangan);
    formCard.appendChild(formError);
    formCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnSubmit, btnBatal]));

    function resetForm() {
      editingId = null;
      formTitle.textContent = "Tambah Klaim Reimburse";
      btnSubmit.textContent = "Simpan";
      btnBatal.style.display = "none";
      selBarber.disabled = false;
      inputTanggal.value = todayIso();
      inputKategori.value = "";
      inputNominal.value = "0";
      inputKeterangan.value = "";
      formError.textContent = "";
    }

    function isiFormUntukEdit(r) {
      editingId = r.id;
      formTitle.textContent = `Edit Klaim #${r.id}`;
      btnSubmit.textContent = "Simpan Perubahan";
      btnBatal.style.display = "";
      selBarber.value = String(r.barber_id);
      selBarber.disabled = true;
      inputTanggal.value = r.tanggal;
      inputKategori.value = r.kategori;
      inputNominal.value = String(r.nominal);
      inputKeterangan.value = r.keterangan || "";
      formError.textContent = "";
      formCard.scrollIntoView({ behavior: "smooth" });
    }

    btnBatal.addEventListener("click", resetForm);
    btnSubmit.addEventListener("click", async () => {
      formError.textContent = "";
      if (!selBarber.value) { formError.textContent = "Pilih karyawan dulu."; return; }
      if (!inputKategori.value.trim()) { formError.textContent = "Kategori tidak boleh kosong."; return; }
      if (!inputNominal.value || Number(inputNominal.value) <= 0) { formError.textContent = "Nominal harus lebih dari 0."; return; }
      btnSubmit.disabled = true;
      try {
        if (editingId) {
          await MugenUI.withLoading(() => MugenApi.put(`/api/reimburse/${editingId}`, {
            tanggal: inputTanggal.value, kategori: inputKategori.value.trim(),
            nominal: Number(inputNominal.value) || 0, keterangan: inputKeterangan.value.trim(),
          }), { message: "Menyimpan…" });
          MugenUI.toast("Klaim reimburse diperbarui.", "success");
        } else {
          await MugenUI.withLoading(() => MugenApi.post("/api/reimburse", {
            barber_id: Number(selBarber.value), tanggal: inputTanggal.value, kategori: inputKategori.value.trim(),
            nominal: Number(inputNominal.value) || 0, keterangan: inputKeterangan.value.trim(),
          }), { message: "Menyimpan…" });
          MugenUI.toast("Klaim reimburse disimpan.", "success");
        }
        resetForm();
        loadList();
      } catch (e) {
        formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      } finally {
        btnSubmit.disabled = false;
      }
    });

    // ---- Filter ----
    filterCard.appendChild(MugenUI.el("h2", {}, "Filter"));
    const filBarber = MugenUI.el("select");
    filBarber.appendChild(MugenUI.el("option", { value: "" }, "Semua Karyawan"));
    for (const b of barbers) filBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    const filStatus = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "" }, "Semua Status"),
      MugenUI.el("option", { value: "pending" }, "Pending"),
      MugenUI.el("option", { value: "disetujui" }, "Disetujui"),
      MugenUI.el("option", { value: "ditolak" }, "Ditolak"),
    ]);
    const filBulan = MugenUI.el("select");
    filBulan.appendChild(MugenUI.el("option", { value: "" }, "Semua Bulan"));
    for (let m = 1; m <= 12; m++) filBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    const filTahun = MugenUI.el("select");
    filTahun.appendChild(MugenUI.el("option", { value: "" }, "Semua Tahun"));
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) filTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    filterCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;" }, [filBarber, filStatus, filBulan, filTahun]));
    filterCard.appendChild(tombolDownloadPdf(() => {
      const params = {};
      if (filBarber.value) params.barber_id = filBarber.value;
      if (filStatus.value) params.status = filStatus.value;
      if (filBulan.value) params.bulan = filBulan.value;
      if (filTahun.value) params.tahun = filTahun.value;
      return params;
    }, () => {
      const karyawan = filBarber.value ? (barbers.find((b) => String(b.id) === filBarber.value) || {}).nama || "Karyawan" : "Semua Karyawan";
      const label = { pending: "Pending", disetujui: "Disetujui", ditolak: "Ditolak" };
      const status = label[filStatus.value] || "";
      const periode = filBulan.value && filTahun.value ? `${MugenUI.namaBulan(Number(filBulan.value))} ${filTahun.value}` : filTahun.value || "";
      return ["Laporan Reimburse", karyawan, status, periode].filter(Boolean).join(" ") + ".pdf";
    }));

    // ---- Daftar ----
    listCard.appendChild(MugenUI.el("h2", {}, "Daftar Klaim Reimburse"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    async function ubahStatus(id, status) {
      let catatan = "";
      if (status === "ditolak") {
        catatan = prompt("Alasan penolakan (opsional):") || "";
      } else {
        catatan = prompt("Catatan approval (opsional):") || "";
      }
      try {
        await MugenUI.withLoading(() => MugenApi.put(`/api/reimburse/${id}/status`, { status, catatan_approval: catatan }),
          { message: "Menyimpan…" });
        MugenUI.toast(`Klaim reimburse ${status === "disetujui" ? "disetujui" : "ditolak"}.`, "success");
        loadList();
      } catch (e) {
        MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
      }
    }

    async function loadList() {
      listBody.innerHTML = "Memuat...";
      try {
        const qs = new URLSearchParams();
        if (filBarber.value) qs.set("barber_id", filBarber.value);
        if (filStatus.value) qs.set("status", filStatus.value);
        if (filBulan.value) qs.set("bulan", filBulan.value);
        if (filTahun.value) qs.set("tahun", filTahun.value);
        const data = await MugenApi.get(`/api/reimburse?${qs.toString()}`);
        const rows = Array.isArray(data) ? data : [];
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.buildTable(
          [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            { key: "nama_barber", label: "Karyawan" },
            { key: "kategori", label: "Kategori" },
            { key: "nominal", label: "Nominal", format: MugenUI.formatRupiah },
            { key: "status", label: "Status", format: badgeStatus },
            { key: "bukti", label: "Bukti", format: (_, r) => kolomBukti(r) },
            {
              key: "aksi", label: "Aksi", format: (_, r) => {
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                if (r.status === "pending") {
                  const btnSetujui = MugenUI.el("button", {}, "Setujui");
                  btnSetujui.addEventListener("click", () => ubahStatus(r.id, "disetujui"));
                  const btnTolak = MugenUI.el("button", { class: "btn-danger" }, "Tolak");
                  btnTolak.addEventListener("click", () => ubahStatus(r.id, "ditolak"));
                  wrap.appendChild(btnSetujui);
                  wrap.appendChild(btnTolak);
                  wrap.appendChild(buatTombolUploadBukti(r, loadList));
                  const btnEdit = MugenUI.el("button", {}, "Edit");
                  btnEdit.addEventListener("click", () => isiFormUntukEdit(r));
                  wrap.appendChild(btnEdit);
                  const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                  btnHapus.addEventListener("click", async () => {
                    if (!confirm(`Hapus klaim reimburse ${r.nama_barber} tanggal ${r.tanggal}?`)) return;
                    try {
                      await MugenApi.del(`/api/reimburse/${r.id}`);
                      MugenUI.toast("Klaim reimburse dihapus.", "success");
                      loadList();
                    } catch (e) {
                      MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                    }
                  });
                  wrap.appendChild(btnHapus);
                } else {
                  wrap.appendChild(MugenUI.el("span", { class: "subtitle" },
                    r.catatan_approval ? `Catatan: ${r.catatan_approval}` : "-"));
                }
                return wrap;
              },
            },
          ],
          rows,
          { emptyText: "Belum ada klaim reimburse." },
        ));
      } catch (e) {
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.el("div", {}, e.detail && e.detail.detail ? e.detail.detail : e.message));
      }
    }

    filBarber.addEventListener("change", loadList);
    filStatus.addEventListener("change", loadList);
    filBulan.addEventListener("change", loadList);
    filTahun.addEventListener("change", loadList);

    resetForm();
    loadList();
  }

  async function render(root) {
    const user = MugenState.getUser();
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Reimburse"));

    if (user.role === "barber") {
      await renderBarberView(root);
    } else {
      await renderAdminView(root);
    }
  }

  return { render };
})();
