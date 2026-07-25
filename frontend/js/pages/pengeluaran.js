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
        MugenApi.get("/api/input-data/barbers", { useCache: true }),
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
    const selBarber = MugenUI.el("select");
    selBarber.appendChild(MugenUI.el("option", { value: "" }, "-- tidak terkait barber (opsional) --"));
    for (const b of barbers) selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    const inputAktif = MugenUI.el("input", { type: "checkbox", style: "width:auto;" });
    inputAktif.checked = true;

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
    formCard.appendChild(MugenUI.el("label", {}, "Barber (opsional)"));
    formCard.appendChild(selBarber);
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
      selBarber.value = "";
      inputAktif.checked = true;
      formError.textContent = "";
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
      selBarber.value = p.barber_id ? String(p.barber_id) : "";
      inputAktif.checked = !!p.aktif;
      formError.textContent = "";
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
        barber_id: selBarber.value ? Number(selBarber.value) : null,
        aktif: inputAktif.checked,
      };
      if (!body.kategori) { formError.textContent = "Kategori tidak boleh kosong."; return; }
      if (!body.keterangan) { formError.textContent = "Keterangan tidak boleh kosong."; return; }
      if (!body.jumlah || body.jumlah <= 0) { formError.textContent = "Nominal harus lebih dari 0."; return; }

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
        });
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
            { key: "nama_barber", label: "Barber", format: (v) => v || "-" },
            { key: "jumlah", label: "Nominal", format: MugenUI.formatRupiah },
            {
              key: "aktif", label: "Status",
              format: (v) => MugenUI.el("span", { class: "badge" + (v ? "" : " badge-libur") }, v ? "Aktif" : "Nonaktif"),
            },
            {
              key: "aksi", label: "Aksi", format: (_, r) => {
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnEdit = MugenUI.el("button", {}, "Edit");
                btnEdit.addEventListener("click", () => isiFormUntukEdit(r));
                const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btnHapus.addEventListener("click", async () => {
                  if (!confirm(`Hapus pengeluaran "${r.keterangan}" tanggal ${r.tanggal}?`)) return;
                  try {
                    await MugenUI.withLoading(() => MugenApi.del(`/api/pengeluaran/${r.id}`));
                    MugenUI.toast("Pengeluaran dihapus.", "success");
                    loadList();
                  } catch (e) {
                    MugenUI.toast(e.message, "error");
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
