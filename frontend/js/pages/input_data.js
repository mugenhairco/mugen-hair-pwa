// pages/input_data.js
// Barber: barber_id otomatis dari akun login, tidak ada pilihan barber di form.
// Owner: wajib pilih barber di form.

const PageInputData = (() => {
  function todayIso() {
    const d = new Date();
    return d.toISOString().slice(0, 10);
  }

  async function render(root) {
    const user = MugenState.getUser();
    const isAdmin = user.role === "admin";

    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Input Data"));

    let services = [];
    let barbers = [];
    let editingId = null; // null = mode SIMPAN baru, angka = mode KOREKSI

    const formCard = MugenUI.el("div", { class: "card" });
    root.appendChild(formCard);
    const listCard = MugenUI.el("div", { class: "card" });
    root.appendChild(listCard);
    const liburCard = MugenUI.el("div", { class: "card" });
    root.appendChild(liburCard);

    try {
      [services, barbers] = await Promise.all([
        MugenApi.get("/api/input-data/services", { useCache: true }),
        isAdmin ? MugenApi.get("/api/input-data/barbers", { useCache: true }) : Promise.resolve([]),
      ]);
    } catch (e) {
      formCard.appendChild(MugenUI.el("div", {}, e.message));
      return;
    }

    // --- FORM ---
    const formTitle = MugenUI.el("h2", {}, "Tambah Transaksi");
    const inputTanggal = MugenUI.el("input", { type: "date", value: todayIso() });
    const selBarber = isAdmin ? MugenUI.el("select") : null;
    if (isAdmin) {
      selBarber.appendChild(MugenUI.el("option", { value: "" }, "-- pilih barber --"));
      for (const b of barbers) selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    }
    const inputTips = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const inputCatatan = MugenUI.el("input", { type: "text", placeholder: "Opsional" });

    const itemInputs = {}; // service_id -> input jumlah
    const serviceRows = services.map((s) => {
      const inp = MugenUI.el("input", { type: "number", min: "0", value: "0", style: "max-width:90px;" });
      itemInputs[s.id] = inp;
      return MugenUI.el("div", { class: "row", style: "align-items:center;" }, [
        MugenUI.el("div", { style: "flex:2;" }, `${s.nama} (${MugenUI.formatRupiah(s.harga)})`),
        MugenUI.el("div", { style: "flex:0 0 100px;" }, inp),
      ]);
    });

    const previewBox = MugenUI.el("div", { class: "card", style: "background:var(--bg-input);" }, "Preview: -");
    const btnSubmit = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
    const btnBatalKoreksi = MugenUI.el("button", { style: "display:none;" }, "Batal Koreksi");
    const formError = MugenUI.el("div", { class: "login-error" });

    formCard.appendChild(formTitle);
    formCard.appendChild(MugenUI.el("label", {}, "Tanggal"));
    formCard.appendChild(inputTanggal);
    if (isAdmin) {
      formCard.appendChild(MugenUI.el("label", {}, "Barber"));
      formCard.appendChild(selBarber);
    }
    formCard.appendChild(MugenUI.el("label", {}, "Service & Jumlah"));
    for (const row of serviceRows) formCard.appendChild(row);
    formCard.appendChild(MugenUI.el("label", {}, "Tips (Rp)"));
    formCard.appendChild(inputTips);
    formCard.appendChild(MugenUI.el("label", {}, "Catatan"));
    formCard.appendChild(inputCatatan);
    formCard.appendChild(previewBox);
    formCard.appendChild(formError);
    formCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnSubmit, btnBatalKoreksi]));

    function currentItems() {
      return Object.entries(itemInputs)
        .map(([service_id, inp]) => ({ service_id: Number(service_id), jumlah: Number(inp.value) || 0 }))
        .filter((it) => it.jumlah > 0);
    }

    async function updatePreview() {
      const items = currentItems();
      if (items.length === 0) {
        previewBox.textContent = "Preview: -";
        return;
      }
      try {
        const p = await MugenApi.post("/api/input-data/preview", { items });
        previewBox.textContent = `Preview: Total ${MugenUI.formatRupiah(p.total_harga)} — Komisi ${MugenUI.formatRupiah(p.total_komisi)}`;
      } catch (e) {
        previewBox.textContent = "Preview: -";
      }
    }
    for (const inp of Object.values(itemInputs)) inp.addEventListener("input", updatePreview);

    function resetForm() {
      editingId = null;
      formTitle.textContent = "Tambah Transaksi";
      btnSubmit.textContent = "Simpan";
      btnBatalKoreksi.style.display = "none";
      inputTanggal.value = todayIso();
      if (isAdmin) selBarber.value = "";
      inputTips.value = "0";
      inputCatatan.value = "";
      for (const inp of Object.values(itemInputs)) inp.value = "0";
      updatePreview();
    }

    function isiFormUntukKoreksi(t) {
      editingId = t.id;
      formTitle.textContent = `Koreksi Transaksi #${t.id}`;
      btnSubmit.textContent = "Simpan Koreksi";
      btnBatalKoreksi.style.display = "";
      inputTanggal.value = t.tanggal;
      if (isAdmin) selBarber.value = String(t.barber_id);
      inputTips.value = String(t.tips);
      inputCatatan.value = t.catatan || "";
      for (const inp of Object.values(itemInputs)) inp.value = "0";
      for (const it of t.items) if (itemInputs[it.service_id]) itemInputs[it.service_id].value = String(it.jumlah);
      updatePreview();
      formCard.scrollIntoView({ behavior: "smooth" });
    }

    btnBatalKoreksi.addEventListener("click", resetForm);

    btnSubmit.addEventListener("click", async () => {
      formError.textContent = "";
      const items = currentItems();
      if (items.length === 0) {
        formError.textContent = "Minimal satu service harus diisi jumlahnya.";
        return;
      }
      if (isAdmin && !selBarber.value) {
        formError.textContent = "Pilih barber terlebih dahulu.";
        return;
      }
      const body = {
        tanggal: inputTanggal.value,
        barber_id: isAdmin ? Number(selBarber.value) : null,
        items,
        tips: Number(inputTips.value) || 0,
        catatan: inputCatatan.value || null,
      };
      btnSubmit.disabled = true;
      try {
        await MugenUI.withLoading(async () => {
          if (editingId) {
            await MugenApi.put(`/api/input-data/transaksi/${editingId}`, body);
            MugenUI.toast("Transaksi dikoreksi.", "success");
          } else {
            await MugenApi.post("/api/input-data/transaksi", body);
            MugenUI.toast("Transaksi disimpan.", "success");
          }
        });
        resetForm();
        loadList();
      } catch (e) {
        formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      } finally {
        btnSubmit.disabled = false;
      }
    });

    // --- DAFTAR TRANSAKSI (bulan berjalan) ---
    listCard.appendChild(MugenUI.el("h2", {}, "Transaksi Bulan Ini"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    async function loadList() {
      listBody.innerHTML = "Memuat...";
      try {
        const now = new Date();
        const data = await MugenApi.get(
          `/api/input-data/transaksi?tahun=${now.getFullYear()}&bulan=${now.getMonth() + 1}`,
          { useCache: true },
        );
        listBody.innerHTML = "";
        if (data.__offline) listBody.appendChild(MugenUI.offlineBanner(data.__cachedAt));
        const rows = Array.isArray(data) ? data : data.data || [];
        listBody.appendChild(MugenUI.buildTable(
          [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            ...(isAdmin ? [{ key: "nama_barber", label: "Barber" }] : []),
            { key: "daftar_service", label: "Service" },
            { key: "total_harga", label: "Total", format: MugenUI.formatRupiah },
            { key: "tips", label: "Tips", format: MugenUI.formatRupiah },
            {
              key: "aksi", label: "Aksi", format: (_, r) => {
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnEdit = MugenUI.el("button", {}, "Koreksi");
                btnEdit.addEventListener("click", () => isiFormUntukKoreksi(r));
                const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btnHapus.addEventListener("click", async () => {
                  if (!confirm(`Hapus transaksi #${r.id} tanggal ${r.tanggal}?`)) return;
                  try {
                    await MugenUI.withLoading(() => MugenApi.del(`/api/input-data/transaksi/${r.id}`));
                    MugenUI.toast("Transaksi dihapus.", "success");
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

    // --- TANDAI LIBUR ---
    liburCard.appendChild(MugenUI.el("h2", {}, "Tandai Libur"));
    const liburTanggal = MugenUI.el("input", { type: "date", value: todayIso() });
    const liburBarberSel = isAdmin ? MugenUI.el("select") : null;
    if (isAdmin) {
      liburBarberSel.appendChild(MugenUI.el("option", { value: "" }, "-- pilih barber --"));
      for (const b of barbers) liburBarberSel.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    }
    const btnTandaiLibur = MugenUI.el("button", { class: "btn-primary" }, "Tandai Libur");
    const btnBatalkanLibur = MugenUI.el("button", {}, "Batalkan Libur");
    liburCard.appendChild(MugenUI.el("label", {}, "Tanggal"));
    liburCard.appendChild(liburTanggal);
    if (isAdmin) {
      liburCard.appendChild(MugenUI.el("label", {}, "Barber"));
      liburCard.appendChild(liburBarberSel);
    }
    liburCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnTandaiLibur, btnBatalkanLibur]));

    function liburBody() {
      return { barber_id: isAdmin ? Number(liburBarberSel.value) || null : null, tanggal: liburTanggal.value };
    }
    btnTandaiLibur.addEventListener("click", async () => {
      if (isAdmin && !liburBarberSel.value) { MugenUI.toast("Pilih barber dulu.", "error"); return; }
      try {
        await MugenUI.withLoading(() => MugenApi.post("/api/input-data/libur", liburBody()));
        MugenUI.toast("Ditandai libur.", "success");
      } catch (e) { MugenUI.toast(e.message, "error"); }
    });
    btnBatalkanLibur.addEventListener("click", async () => {
      if (isAdmin && !liburBarberSel.value) { MugenUI.toast("Pilih barber dulu.", "error"); return; }
      try {
        await MugenUI.withLoading(() => MugenApi.del("/api/input-data/libur", liburBody()));
        MugenUI.toast("Libur dibatalkan.", "success");
      } catch (e) { MugenUI.toast(e.message, "error"); }
    });

    resetForm();
    loadList();
  }

  return { render };
})();
