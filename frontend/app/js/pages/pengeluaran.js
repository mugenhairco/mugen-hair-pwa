// pages/pengeluaran.js — TAHAP 9: CRUD Pengeluaran.
// Halaman ini KHUSUS role admin (barber tidak melihat menunya di nav.js,
// DAN router.js melempar barber keluar dari halaman ini kalau nekat buka
// lewat URL langsung). Backend (routers/pengeluaran.py) juga menolak semua
// request dari barber lewat dependency require_admin, jadi perlindungan
// ada di dua lapis, bukan cuma disembunyikan di frontend.

const PagePengeluaran = (() => {
  function todayIso() {
    return new Date().toISOString().slice(0, 10);
  }

  async function render(root) {
    const today = new Date();
    let editingId = null; // null = mode Tambah, angka = mode Edit
    let barbers = [];
    let kategoriOptions = [];

    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Pengeluaran"));

    const formCard = MugenUI.el("div", { class: "card" });
    const filterCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    root.appendChild(formCard);
    root.appendChild(filterCard);
    root.appendChild(listCard);

    try {
      [barbers, kategoriOptions] = await Promise.all([
        MugenApi.get("/api/input-data/karyawan", { useCache: true }),
        MugenApi.get("/api/pengeluaran/kategori", { useCache: true }),
      ]);
    } catch (e) {
      formCard.appendChild(MugenUI.el("div", {}, e.message));
      return;
    }

    // --- DATALIST kategori (input teks bebas + saran) ---
    const kategoriListId = "pengeluaran-kategori-list";
    const datalist = MugenUI.el("datalist", { id: kategoriListId });
    for (const k of kategoriOptions) datalist.appendChild(MugenUI.el("option", { value: k }));
    root.appendChild(datalist);

    // ================= FORM TAMBAH / EDIT =================
    const formTitle = MugenUI.el("h2", {}, "Tambah Pengeluaran");
    const inputTanggal = MugenUI.el("input", { type: "date", value: todayIso() });
    const inputKategori = MugenUI.el("input", { type: "text", list: kategoriListId, placeholder: "mis. Operasional" });
    const inputKeterangan = MugenUI.el("input", { type: "text", placeholder: "Untuk apa pengeluaran ini" });
    const inputNominal = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    // Sumber Dana (Tahap 12): Uang Kas -> otomatis mengurangi saldo Uang
    // Kas. Uang Karyawan -> otomatis membuat klaim Reimburse tersambung
    // (cair lewat Slip Gaji periode terkait). selBarber jadi WAJIB hanya
    // saat Sumber Dana = Uang Karyawan (pola sama seperti terapkanTampilanJabatan()
    // di slip_gaji.js).
    const selSumberDana = MugenUI.el("select");
    selSumberDana.appendChild(MugenUI.el("option", { value: "kas" }, "Uang Kas"));
    selSumberDana.appendChild(MugenUI.el("option", { value: "karyawan" }, "Uang Karyawan"));
    const wrapKaryawan = MugenUI.el("div");
    const selBarber = MugenUI.el("select");
    selBarber.appendChild(MugenUI.el("option", { value: "" }, "-- pilih karyawan --"));
    for (const b of barbers) selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    wrapKaryawan.appendChild(MugenUI.el("label", {}, "Karyawan (barber/kasir/ob/kru)"));
    wrapKaryawan.appendChild(selBarber);
    const inputAktif = MugenUI.el("input", { type: "checkbox", style: "width:auto;" });
    inputAktif.checked = true;

    function terapkanTampilanSumberDana() {
      wrapKaryawan.style.display = selSumberDana.value === "karyawan" ? "" : "none";
    }
    selSumberDana.addEventListener("change", terapkanTampilanSumberDana);

    const btnSubmit = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
    const btnBatal = MugenUI.el("button", { style: "display:none;" }, "Batal Edit");
    const formError = MugenUI.el("div", { class: "login-error" });

    formCard.appendChild(formTitle);
    formCard.appendChild(MugenUI.el("label", {}, "Tanggal"));
    formCard.appendChild(inputTanggal);
    formCard.appendChild(MugenUI.el("label", {}, "Kategori"));
    formCard.appendChild(inputKategori);
    formCard.appendChild(MugenUI.el("label", {}, "Keterangan"));
    formCard.appendChild(inputKeterangan);
    formCard.appendChild(MugenUI.el("label", {}, "Nominal (Rp)"));
    formCard.appendChild(inputNominal);
    formCard.appendChild(MugenUI.el("label", {}, "Sumber Dana"));
    formCard.appendChild(selSumberDana);
    formCard.appendChild(wrapKaryawan);
    formCard.appendChild(MugenUI.el("label", {}, [inputAktif, " Status Aktif"]));
    formCard.appendChild(formError);
    formCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnSubmit, btnBatal]));

    function resetForm() {
      editingId = null;
      formTitle.textContent = "Tambah Pengeluaran";
      btnSubmit.textContent = "Simpan";
      btnBatal.style.display = "none";
      inputTanggal.value = todayIso();
      inputKategori.value = "";
      inputKeterangan.value = "";
      inputNominal.value = "0";
      selSumberDana.value = "kas";
      selBarber.value = "";
      inputAktif.checked = true;
      formError.textContent = "";
      terapkanTampilanSumberDana();
    }

    function isiFormUntukEdit(p) {
      editingId = p.id;
      formTitle.textContent = `Edit Pengeluaran #${p.id}`;
      btnSubmit.textContent = "Simpan Perubahan";
      btnBatal.style.display = "";
      inputTanggal.value = p.tanggal;
      inputKategori.value = p.kategori || "";
      inputKeterangan.value = p.keterangan || "";
      inputNominal.value = String(p.jumlah);
      selSumberDana.value = p.sumber_dana || "kas";
      selBarber.value = p.barber_id ? String(p.barber_id) : "";
      inputAktif.checked = !!p.aktif;
      formError.textContent = "";
      terapkanTampilanSumberDana();
      formCard.scrollIntoView({ behavior: "smooth" });
    }

    btnBatal.addEventListener("click", resetForm);

    btnSubmit.addEventListener("click", async () => {
      formError.textContent = "";
      const body = {
        tanggal: inputTanggal.value,
        kategori: inputKategori.value.trim(),
        keterangan: inputKeterangan.value.trim(),
        jumlah: Number(inputNominal.value) || 0,
        sumber_dana: selSumberDana.value,
        barber_id: selSumberDana.value === "karyawan" && selBarber.value ? Number(selBarber.value) : null,
        aktif: inputAktif.checked,
      };
      if (!body.kategori) { formError.textContent = "Kategori tidak boleh kosong."; return; }
      if (!body.keterangan) { formError.textContent = "Keterangan tidak boleh kosong."; return; }
      if (!body.jumlah || body.jumlah <= 0) { formError.textContent = "Nominal harus lebih dari 0."; return; }
      if (body.sumber_dana === "karyawan" && !body.barber_id) { formError.textContent = "Pilih karyawan dulu."; return; }

      btnSubmit.disabled = true;
      try {
        await MugenUI.withLoading(async () => {
          if (editingId) {
            await MugenApi.put(`/api/pengeluaran/${editingId}`, body);
            MugenUI.toast("Pengeluaran diperbarui.", "success");
          } else {
            await MugenApi.post("/api/pengeluaran", body);
            MugenUI.toast("Pengeluaran disimpan.", "success");
          }
        }, { message: "Menyimpan…" });
        // Kategori baru yang baru saja diketik langsung ikut jadi saran berikutnya.
        if (!kategoriOptions.includes(body.kategori)) {
          kategoriOptions.push(body.kategori);
          datalist.appendChild(MugenUI.el("option", { value: body.kategori }));
          if (selKategori) selKategori.appendChild(MugenUI.el("option", { value: body.kategori }, body.kategori));
        }
        resetForm();
        loadList();
      } catch (e) {
        formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      } finally {
        btnSubmit.disabled = false;
      }
    });

    // ================= FILTER =================
    filterCard.appendChild(MugenUI.el("h2", {}, "Cari & Filter"));
    const selBulan = MugenUI.el("select");
    for (let m = 1; m <= 12; m++) selBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    selBulan.value = String(today.getMonth() + 1);
    const selTahun = MugenUI.el("select");
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) selTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    selTahun.value = String(today.getFullYear());
    const selKategori = MugenUI.el("select");
    selKategori.appendChild(MugenUI.el("option", { value: "" }, "Semua Kategori"));
    for (const k of kategoriOptions) selKategori.appendChild(MugenUI.el("option", { value: k }, k));
    const inputCari = MugenUI.el("input", { type: "text", placeholder: "Cari keterangan/kategori..." });

    filterCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;" }, [selBulan, selTahun, selKategori, inputCari]));
    // Perbaikan Alur Cetak PDF: Preview PDF dulu, TIDAK langsung mengunduh
    // -- lihat pdf_preview.js.
    const btnDownloadPdf = MugenUI.el("button", {}, "Cetak PDF");
    btnDownloadPdf.addEventListener("click", () => {
      const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
      if (selKategori.value) qs.set("kategori", selKategori.value);
      if (inputCari.value.trim()) qs.set("cari", inputCari.value.trim());
      const bagian = ["Laporan Pengeluaran", selKategori.value || "", MugenUI.namaBulan(Number(selBulan.value)), selTahun.value];
      MugenPdfPreview.open({
        generate: () => MugenApi.fetchBlob(`/api/pengeluaran/pdf?${qs}`),
        filename: MugenUI.namaFileAman(bagian.filter(Boolean).join(" ") + ".pdf"),
      });
    });
    // Feature Gating "export_pdf": lihat catatan sama di pages/rekap.js.
    filterCard.appendChild(
      typeof MugenFeature !== "undefined" && !MugenFeature.has("export_pdf")
        ? MugenFeature.upgradeBlock("Export PDF") : btnDownloadPdf);

    // ================= DAFTAR PENGELUARAN =================
    listCard.appendChild(MugenUI.el("h2", {}, "Daftar Pengeluaran"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    let debounceTimer = null;
    function loadListDebounced() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(loadList, 300);
    }

    async function loadList() {
      listBody.innerHTML = "Memuat...";
      try {
        const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
        if (selKategori.value) qs.set("kategori", selKategori.value);
        if (inputCari.value.trim()) qs.set("cari", inputCari.value.trim());
        const data = await MugenApi.get(`/api/pengeluaran?${qs}`, { useCache: true });
        listBody.innerHTML = "";
        if (data.__offline) listBody.appendChild(MugenUI.offlineBanner(data.__cachedAt));
        const rows = Array.isArray(data) ? data : [];
        listBody.appendChild(MugenUI.buildTable(
          [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            { key: "kategori", label: "Kategori" },
            { key: "keterangan", label: "Keterangan" },
            {
              key: "sumber_dana", label: "Sumber Dana",
              format: (v, r) => v === "karyawan" ? `Uang Karyawan (${r.nama_barber || "-"})` : "Uang Kas",
            },
            { key: "jumlah", label: "Nominal", format: MugenUI.formatRupiah },
            {
              key: "aktif", label: "Status",
              format: (v) => MugenUI.el("span", { class: "badge" + (v ? "" : " badge-libur") }, v ? "Aktif" : "Nonaktif"),
            },
            {
              key: "aksi", label: "Aksi", format: (_, r) => {
                if (r.terkunci) {
                  return MugenUI.el("span", { class: "subtitle", title: "Reimburse terkait sudah dibayar lewat Slip Gaji -- tidak bisa diubah/dihapus." }, "Terkunci");
                }
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnEdit = MugenUI.el("button", {}, "Edit");
                btnEdit.addEventListener("click", () => isiFormUntukEdit(r));
                const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btnHapus.addEventListener("click", async () => {
                  if (!confirm(`Hapus pengeluaran "${r.keterangan}" tanggal ${r.tanggal}?`)) return;
                  try {
                    await MugenUI.withLoading(() => MugenApi.del(`/api/pengeluaran/${r.id}`), { message: "Menghapus…" });
                    MugenUI.toast("Pengeluaran dihapus.", "success");
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
        ));
      } catch (e) {
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.el("div", {}, e.message));
      }
    }

    selBulan.addEventListener("change", () => MugenUI.withLoading(loadList));
    selTahun.addEventListener("change", () => MugenUI.withLoading(loadList));
    selKategori.addEventListener("change", () => MugenUI.withLoading(loadList));
    inputCari.addEventListener("input", loadListDebounced);

    resetForm();
    loadList();
  }

  return { render };
})();
