// pages/input_data.js
// Barber: barber_id otomatis dari akun login, tidak ada pilihan barber di form.
// Owner: wajib pilih barber di form.

const PageInputData = (() => {
  function todayIso() {
    // BUGFIX (audit): lihat catatan lengkap di MugenUI.isoHariIniWib()
    // (dulu toISOString().slice(0,10) di sini salah satu hari antara jam
    // 00:00-06:59 WIB karena mengonversi ke UTC dulu).
    return MugenUI.isoHariIniWib();
  }

  async function render(root) {
    const user = MugenState.getUser();
    const isAdmin = user.role === "admin" || user.role === "staff";

    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Input Data"));

    // AUDIT Hak Akses Menu (permintaan Owner): "Tidak Ada Akses" -- HANYA
    // pesan kosong, tanpa form/data apa pun (mencakup ketiga mode: Barber/
    // Manual Customer/Non-Barber, satu menu yang sama).
    if (isAdmin && (await MugenMenuAccess.get("input_data")) === "none") {
      root.appendChild(MugenUI.emptyState("Anda tidak memiliki akses ke menu ini."));
      return;
    }

    // Dukungan Barber + Non-Barber: dropdown pemilih mode -- KHUSUS Owner/
    // Admin (Non-Barber murni fitur pengelolaan data, sama seperti seluruh
    // Input Data yang memang sudah Owner/Admin-only). Default "Input Data
    // Barber" SELALU terpilih (poin #3) supaya tampilan & alur kerja Barber
    // yang sudah ada TIDAK BERUBAH SAMA SEKALI kalau dropdown ini tidak
    // pernah disentuh -- seksi Non-Barber murni TAMBAHAN yang disembunyikan
    // sampai Owner secara eksplisit memilihnya.
    const barberSection = MugenUI.el("div");
    // FITUR BARU Manual Customer: pilihan KETIGA sejajar dengan Barber/
    // Non-Barber (keputusan eksplisit Owner: "tiga pilihan sejajar",
    // BUKAN sub-mode di dalam Input Barber) -- lihat manual_customer_db.py.
    const manualCustomerSection = MugenUI.el("div", { style: "display:none;" });
    const nonBarberSection = MugenUI.el("div", { style: "display:none;" });
    if (isAdmin) {
      const selMode = MugenUI.el("select", { style: "max-width:280px;margin-bottom:16px;" }, [
        MugenUI.el("option", { value: "barber" }, "Input Data Barber"),
        MugenUI.el("option", { value: "manual_customer" }, "Manual Customer"),
        MugenUI.el("option", { value: "non_barber" }, "Input Data Non-Barber"),
      ]);
      selMode.value = "barber";
      selMode.addEventListener("change", () => {
        barberSection.style.display = selMode.value === "barber" ? "" : "none";
        manualCustomerSection.style.display = selMode.value === "manual_customer" ? "" : "none";
        nonBarberSection.style.display = selMode.value === "non_barber" ? "" : "none";
      });
      root.appendChild(selMode);
    }
    root.appendChild(barberSection);
    root.appendChild(manualCustomerSection);
    root.appendChild(nonBarberSection);

    // Hak Akses Menu: level "Baca" -- sembunyikan form Tambah/Koreksi
    // Transaksi (ketiga mode: Barber/Manual Customer/Non-Barber), daftar
    // tetap tampil. Dihitung sekali di sini, dipakai lagi di
    // renderManualCustomer()/renderNonBarber() di bawah lewat closure.
    const bolehEditInputData = !isAdmin || (await MugenMenuAccess.get("input_data")) === "write";

    let services = [];
    let barbers = [];
    let editingId = null; // null = mode SIMPAN baru, angka = mode KOREKSI

    const formCard = MugenUI.el("div", { class: "card" });
    if (bolehEditInputData) barberSection.appendChild(formCard);
    const listCard = MugenUI.el("div", { class: "card" });
    barberSection.appendChild(listCard);
    const liburCard = MugenUI.el("div", { class: "card" });
    barberSection.appendChild(liburCard);

    try {
      [services, barbers] = await Promise.all([
        MugenApi.get("/api/input-data/services", { useCache: true }),
        isAdmin ? MugenApi.get("/api/input-data/barbers", { useCache: true }) : Promise.resolve([]),
      ]);
    } catch (e) {
      formCard.appendChild(MugenUI.errorState(e.message));
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
      try {
        // REVISI UI/UX Premium: spinner inline di tombol, bukan overlay layar penuh.
        await MugenUI.withButtonLoading(btnSubmit, async () => {
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
      }
    });

    // --- DAFTAR TRANSAKSI (bulan berjalan) ---
    listCard.appendChild(MugenUI.el("h2", {}, "Transaksi Bulan Ini"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    async function loadList() {
      // REVISI UI/UX Premium: skeleton tabel menggantikan teks "Memuat..." --
      // ada banner offline yang bisa ikut tampil di atas tabel, jadi TIDAK
      // dipindah ke refreshInto() (lihat contoh sama di dashboard_owner.js).
      listBody.innerHTML = "";
      listBody.appendChild(MugenUI.skeleton("table", { cols: isAdmin ? 6 : 5, rows: 4 }));
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
            { key: "daftar_service", label: "Service", format: MugenUI.serviceCell },
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
                    // REVISI UI/UX Premium: spinner inline di tombol Hapus.
                    await MugenUI.withButtonLoading(btnHapus, () => MugenApi.del(`/api/input-data/transaksi/${r.id}`));
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
        listBody.appendChild(MugenUI.errorState(e.message));
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
        // REVISI UI/UX Premium: spinner inline di tombol, tanpa overlay layar penuh.
        await MugenUI.withButtonLoading(btnTandaiLibur, () => MugenApi.post("/api/input-data/libur", liburBody()));
        MugenUI.toast("Ditandai libur.", "success");
      } catch (e) { MugenUI.toast(e.message, "error"); }
    });
    btnBatalkanLibur.addEventListener("click", async () => {
      if (isAdmin && !liburBarberSel.value) { MugenUI.toast("Pilih barber dulu.", "error"); return; }
      try {
        await MugenUI.withButtonLoading(btnBatalkanLibur, () => MugenApi.del("/api/input-data/libur", liburBody()));
        MugenUI.toast("Libur dibatalkan.", "success");
      } catch (e) { MugenUI.toast(e.message, "error"); }
    });

    resetForm();
    loadList();

    // --- INPUT DATA NON-BARBER (Kasir/OB/Kru/role lainnya) ---
    // Tabel & endpoint baru, TIDAK terhubung ke `transaksi`/Slip Gaji Barber
    // sama sekali (lihat data_non_barber_db.py) -- murni tambahan, bagian
    // ini di-skip total untuk Barber (dropdown mode di atas juga tidak
    // pernah muncul untuknya).
    if (isAdmin) await renderManualCustomer();
    if (isAdmin) await renderNonBarber();

    // --- INPUT DATA MANUAL CUSTOMER (Waiting List / Booking) ---
    // Metode input KEDUA untuk Input Barber, sejajar (bukan sub-mode) --
    // lihat manual_customer_db.py untuk aturan lengkap ("satu tanggal satu
    // mode", jam immutable, Closing tidak mengunci Rekap, dst). Tabel &
    // endpoint baru, TIDAK PERNAH menyentuh `transaksi`/Rekap langsung --
    // hanya lewat database.tambah_transaksi() yang SAMA PERSIS dipakai
    // Input Barber, saat tombol "Tutup & Simpan Hari Ini" ditekan.
    async function renderManualCustomer() {
      const mcStatusCard = MugenUI.el("div", { class: "card" });
      const mcFormCard = MugenUI.el("div", { class: "card" });
      const mcListCard = MugenUI.el("div", { class: "card" });
      manualCustomerSection.appendChild(mcStatusCard);
      // Hak Akses Menu: level "Baca" -- sembunyikan form Manual Customer.
      if (bolehEditInputData) manualCustomerSection.appendChild(mcFormCard);
      manualCustomerSection.appendChild(mcListCard);

      const mcTanggal = MugenUI.el("input", { type: "date", value: todayIso() });
      mcStatusCard.appendChild(MugenUI.el("h2", {}, "Manual Customer"));
      mcStatusCard.appendChild(MugenUI.el("label", {}, "Tanggal"));
      mcStatusCard.appendChild(mcTanggal);
      const mcStatusBadge = MugenUI.el("div", { class: "card", style: "background:var(--bg-input);margin-top:8px;" }, "Memuat status...");
      mcStatusCard.appendChild(mcStatusBadge);
      const btnTutupHari = MugenUI.el("button", { class: "btn-primary" }, "🔒 Tutup & Simpan Hari Ini");
      const btnResetHari = MugenUI.el("button", { class: "btn-danger" }, "Reset Semua Transaksi Hari Ini");
      mcStatusCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;flex-wrap:wrap;gap:8px;" }, [btnTutupHari, btnResetHari]));

      let mcStatus = { mode: null, status: null };
      let mcEditingId = null;

      // --- FORM TAMBAH ---
      const mcFormTitle = MugenUI.el("h2", {}, "Tambah Customer");
      const inputNamaCustomer = MugenUI.el("input", { type: "text", placeholder: "Nama Customer" });
      const selJenis = MugenUI.el("select", {}, [
        MugenUI.el("option", { value: "waiting_list" }, "Waiting List"),
        MugenUI.el("option", { value: "booking" }, "Booking"),
      ]);
      const bookingFields = MugenUI.el("div", { style: "display:none;" });
      const inputJamBooking = MugenUI.el("input", { type: "time" });
      const selBarberMc = MugenUI.el("select");
      selBarberMc.appendChild(MugenUI.el("option", { value: "" }, "-- pilih barber --"));
      for (const b of barbers) selBarberMc.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
      const mcServiceChecks = {}; // service_id -> checkbox
      const mcServiceList = MugenUI.el("div", { class: "checklist-service" });
      for (const s of services) {
        const cb = MugenUI.el("input", { type: "checkbox", style: "width:auto;" });
        mcServiceChecks[s.id] = cb;
        mcServiceList.appendChild(MugenUI.el("label", { style: "display:flex;align-items:center;gap:8px;" },
          [cb, `${s.nama} (${MugenUI.formatRupiah(s.harga)})`]));
      }
      const inputTipsMc = MugenUI.el("input", { type: "number", min: "0", value: "0" });
      bookingFields.appendChild(MugenUI.el("label", {}, "Jam Booking"));
      bookingFields.appendChild(inputJamBooking);
      bookingFields.appendChild(MugenUI.el("label", {}, "Barber"));
      bookingFields.appendChild(selBarberMc);
      bookingFields.appendChild(MugenUI.el("label", {}, "Service"));
      bookingFields.appendChild(mcServiceList);
      bookingFields.appendChild(MugenUI.el("label", {}, "Tips (Rp, Opsional)"));
      bookingFields.appendChild(inputTipsMc);

      // Field khusus mode Koreksi (jam/jenis TIDAK PERNAH bisa diedit -- lihat
      // manual_customer_db.py -- Koreksi selalu tampilkan Barber/Service/Tips
      // terlepas jenisnya, supaya Waiting List juga bisa dilengkapi belakangan).
      const mcJamJenisInfo = MugenUI.el("div", { class: "subtitle", style: "display:none;" });

      selJenis.addEventListener("change", () => {
        if (mcEditingId) return; // terkunci saat koreksi
        bookingFields.style.display = selJenis.value === "booking" ? "" : "none";
      });

      const mcFormError = MugenUI.el("div", { class: "login-error" });
      const btnMcSubmit = MugenUI.el("button", { class: "btn-primary" }, "Tambah");
      const btnMcBatal = MugenUI.el("button", { style: "display:none;" }, "Batal Koreksi");

      mcFormCard.appendChild(mcFormTitle);
      mcFormCard.appendChild(MugenUI.el("label", {}, "Nama Customer"));
      mcFormCard.appendChild(inputNamaCustomer);
      mcFormCard.appendChild(MugenUI.el("label", {}, "Jenis"));
      mcFormCard.appendChild(selJenis);
      mcFormCard.appendChild(mcJamJenisInfo);
      mcFormCard.appendChild(bookingFields);
      mcFormCard.appendChild(mcFormError);
      mcFormCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnMcSubmit, btnMcBatal]));

      function mcCurrentServiceIds() {
        return Object.entries(mcServiceChecks).filter(([, cb]) => cb.checked).map(([id]) => Number(id));
      }

      function resetMcForm() {
        mcEditingId = null;
        mcFormTitle.textContent = "Tambah Customer";
        btnMcSubmit.textContent = "Tambah";
        btnMcBatal.style.display = "none";
        selJenis.disabled = false;
        mcJamJenisInfo.style.display = "none";
        inputNamaCustomer.value = "";
        selJenis.value = "waiting_list";
        bookingFields.style.display = "none";
        inputJamBooking.value = "";
        selBarberMc.value = "";
        for (const cb of Object.values(mcServiceChecks)) cb.checked = false;
        inputTipsMc.value = "0";
        mcFormError.textContent = "";
      }

      function isiMcFormUntukKoreksi(e) {
        mcEditingId = e.id;
        mcFormTitle.textContent = `Koreksi Customer #${e.id}`;
        btnMcSubmit.textContent = "Simpan Koreksi";
        btnMcBatal.style.display = "";
        selJenis.disabled = true; // jenis immutable
        selJenis.value = e.jenis;
        const labelJenis = e.jenis === "booking" ? "Booking" : "Waiting List";
        mcJamJenisInfo.style.display = "";
        mcJamJenisInfo.textContent = `Jenis: ${labelJenis} — Jam: ${e.jam} (tidak bisa diubah; hapus & buat ulang jika salah).`;
        inputNamaCustomer.value = e.nama_customer;
        bookingFields.style.display = ""; // selalu tampilkan Barber/Service/Tips saat koreksi
        inputJamBooking.value = e.jam || "";
        selBarberMc.value = e.barber_id != null ? String(e.barber_id) : "";
        for (const [id, cb] of Object.entries(mcServiceChecks)) cb.checked = (e.service_ids || []).includes(Number(id));
        inputTipsMc.value = String(e.tips || 0);
        mcFormError.textContent = "";
        mcFormCard.scrollIntoView({ behavior: "smooth" });
      }

      btnMcBatal.addEventListener("click", resetMcForm);

      btnMcSubmit.addEventListener("click", async () => {
        mcFormError.textContent = "";
        const nama = inputNamaCustomer.value.trim();
        if (!nama) { mcFormError.textContent = "Nama Customer wajib diisi."; return; }
        try {
          await MugenUI.withButtonLoading(btnMcSubmit, async () => {
            if (mcEditingId) {
              await MugenApi.put(`/api/manual-customer/transaksi/${mcEditingId}`, {
                nama_customer: nama,
                barber_id: selBarberMc.value ? Number(selBarberMc.value) : null,
                service_ids: mcCurrentServiceIds(),
                tips: Number(inputTipsMc.value) || 0,
              });
              MugenUI.toast("Customer dikoreksi.", "success");
            } else {
              const jenis = selJenis.value;
              if (jenis === "booking") {
                if (!inputJamBooking.value) { throw { message: "Jam Booking wajib diisi." }; }
                if (!selBarberMc.value) { throw { message: "Pilih barber terlebih dahulu untuk Booking." }; }
                if (mcCurrentServiceIds().length === 0) { throw { message: "Pilih minimal satu Service untuk Booking." }; }
              }
              await MugenApi.post("/api/manual-customer/transaksi", {
                tanggal: mcTanggal.value,
                nama_customer: nama,
                jenis,
                jam_booking: jenis === "booking" ? inputJamBooking.value : null,
                barber_id: jenis === "booking" ? Number(selBarberMc.value) : (selBarberMc.value ? Number(selBarberMc.value) : null),
                service_ids: mcCurrentServiceIds(),
                tips: Number(inputTipsMc.value) || 0,
              });
              MugenUI.toast(jenis === "booking" ? "Booking ditambahkan." : "Waiting List ditambahkan.", "success");
            }
          });
          resetMcForm();
          await loadMcStatus();
          await loadMcList();
        } catch (e) {
          mcFormError.textContent = (e.detail && e.detail.detail) ? e.detail.detail : e.message;
        }
      });

      // --- STATUS HARI (mode/OPEN/CLOSED) ---
      async function loadMcStatus() {
        try {
          mcStatus = await MugenApi.get(`/api/manual-customer/status?tanggal=${mcTanggal.value}`);
        } catch (e) {
          mcStatus = { mode: null, status: null };
        }
        if (mcStatus.mode === null) {
          mcStatusBadge.textContent = "Tanggal ini belum dipakai -- mode bebas dipilih.";
        } else if (mcStatus.mode === "barber") {
          mcStatusBadge.textContent = "Tanggal ini sudah memakai metode Input Barber -- Manual Customer tidak bisa dipakai (Reset dulu untuk berganti metode).";
        } else {
          mcStatusBadge.textContent = mcStatus.status === "closed"
            ? "Mode Manual Customer -- sudah DITUTUP (Closing). Data tetap bisa dikoreksi/dihapus lewat Rekap seperti biasa."
            : "Mode Manual Customer -- masih OPEN.";
        }
        const bolehInput = mcStatus.mode === null || (mcStatus.mode === "manual_customer" && mcStatus.status !== "closed");
        inputNamaCustomer.disabled = !bolehInput && !mcEditingId;
        btnMcSubmit.disabled = !bolehInput && !mcEditingId;
        btnTutupHari.style.display = mcStatus.mode === "manual_customer" && mcStatus.status !== "closed" ? "" : "none";
        btnResetHari.style.display = mcStatus.mode !== null ? "" : "none";
      }

      btnTutupHari.addEventListener("click", async () => {
        if (!confirm(`Tutup & simpan transaksi Manual Customer tanggal ${mcTanggal.value}? Baris yang sudah punya Barber+Service akan masuk ke Rekap.`)) return;
        try {
          const hasil = await MugenUI.withButtonLoading(btnTutupHari, () => MugenApi.post(`/api/manual-customer/close?tanggal=${mcTanggal.value}`, {}));
          MugenUI.toast(`Hari ditutup: ${hasil.diproses} masuk Rekap, ${hasil.dilewati} tetap histori (belum lengkap).`, "success", { force: true });
          await loadMcStatus();
          await loadMcList();
        } catch (e) {
          MugenUI.toast((e.detail && e.detail.detail) ? e.detail.detail : e.message, "error");
        }
      });

      btnResetHari.addEventListener("click", async () => {
        if (!confirm(`Hapus SELURUH transaksi tanggal ${mcTanggal.value} (Input Barber maupun Manual Customer) supaya metode bisa dipilih ulang? Tindakan ini tidak bisa dibatalkan.`)) return;
        try {
          await MugenUI.withButtonLoading(btnResetHari, () => MugenApi.post(`/api/manual-customer/reset?tanggal=${mcTanggal.value}`, {}));
          MugenUI.toast("Seluruh transaksi tanggal ini direset.", "success", { force: true });
          resetMcForm();
          await loadMcStatus();
          await loadMcList();
        } catch (e) {
          MugenUI.toast(e.message, "error");
        }
      });

      mcTanggal.addEventListener("change", async () => {
        resetMcForm();
        await loadMcStatus();
        await loadMcList();
      });

      // --- DAFTAR TRANSAKSI HARI ITU ---
      mcListCard.appendChild(MugenUI.el("h2", {}, "Transaksi Hari Ini"));
      const mcListBody = MugenUI.el("div");
      mcListCard.appendChild(mcListBody);

      async function loadMcList() {
        try {
          await MugenUI.refreshInto(mcListBody, async () => {
            const rows = await MugenApi.get(`/api/manual-customer/transaksi?tanggal=${mcTanggal.value}`);
            return MugenUI.buildTable(
              [
                { key: "jam", label: "Jam" },
                {
                  key: "nama_customer", label: "Nama Customer", format: (v, r) => (
                    r.jenis === "booking" ? MugenUI.el("span", { class: "mc-nama-booking" }, v) : v
                  ),
                },
                { key: "jenis", label: "Jenis", format: (v) => (v === "booking" ? "Booking" : "Waiting List") },
                { key: "nama_barber", label: "Barber", format: (v) => v || "-" },
                { key: "daftar_service", label: "Service", format: (v) => (v && v.length ? v.map((s) => s.nama).join(", ") : "-") },
                { key: "tips", label: "Tips", format: MugenUI.formatRupiah },
                {
                  key: "aksi", label: "Aksi", format: (_, r) => {
                    const wrap = MugenUI.el("div", { class: "actions-cell" });
                    const btnEdit = MugenUI.el("button", {}, "Koreksi");
                    btnEdit.addEventListener("click", () => isiMcFormUntukKoreksi(r));
                    const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                    btnHapus.addEventListener("click", async () => {
                      if (!confirm(`Hapus data customer "${r.nama_customer}"?`)) return;
                      try {
                        await MugenUI.withButtonLoading(btnHapus, () => MugenApi.del(`/api/manual-customer/transaksi/${r.id}`));
                        MugenUI.toast("Data customer dihapus.", "success");
                        await loadMcStatus();
                        loadMcList();
                      } catch (e) {
                        MugenUI.toast((e.detail && e.detail.detail) ? e.detail.detail : e.message, "error");
                      }
                    });
                    wrap.appendChild(btnEdit);
                    wrap.appendChild(btnHapus);
                    return wrap;
                  },
                },
              ],
              rows,
            );
          }, { skeleton: { kind: "table", cols: 7, rows: 4 } });
        } catch (e) {
          mcListBody.innerHTML = "";
          mcListBody.appendChild(MugenUI.errorState(e.message));
        }
      }

      resetMcForm();
      await loadMcStatus();
      await loadMcList();
    }

    async function renderNonBarber() {
      const LABEL_JABATAN = { barber: "Barber", kasir: "Kasir", ob: "OB", kru: "Kru" };
      const labelJabatan = (j) => LABEL_JABATAN[j] || j;

      let karyawanNonBarber = [];
      try {
        const semua = await MugenApi.get("/api/input-data/karyawan", { useCache: true });
        karyawanNonBarber = (Array.isArray(semua) ? semua : []).filter((k) => k.jabatan !== "barber");
      } catch (e) { /* form tetap tampil, dropdown karyawan kosong */ }

      const nbFormCard = MugenUI.el("div", { class: "card" });
      const nbListCard = MugenUI.el("div", { class: "card" });
      // Hak Akses Menu: level "Baca" -- sembunyikan form Non-Barber.
      if (bolehEditInputData) nonBarberSection.appendChild(nbFormCard);
      nonBarberSection.appendChild(nbListCard);

      let nbEditingId = null;

      const nbFormTitle = MugenUI.el("h2", {}, "Tambah Data Gaji Non-Barber");
      const selKaryawan = MugenUI.el("select");
      selKaryawan.appendChild(MugenUI.el("option", { value: "" }, "-- pilih karyawan --"));
      for (const k of karyawanNonBarber) {
        selKaryawan.appendChild(MugenUI.el("option", { value: String(k.id) }, `${k.nama} (${labelJabatan(k.jabatan)})`));
      }
      const roleTerpilih = MugenUI.el("div", { class: "subtitle", style: "margin:0 0 8px;" }, "Role: -");

      const inputTglMulai = MugenUI.el("input", { type: "date", value: todayIso() });
      const inputTglSelesai = MugenUI.el("input", { type: "date", value: todayIso() });
      const inputGajiPerHari = MugenUI.el("input", { type: "number", min: "0", value: "0" });
      const inputHariMasuk = MugenUI.el("input", { type: "number", min: "0", value: "0" });
      const inputHariLibur = MugenUI.el("input", { type: "number", min: "0", value: "0" });
      const inputBonus = MugenUI.el("input", { type: "number", min: "0", value: "0" });
      const inputPotongan = MugenUI.el("input", { type: "number", min: "0", value: "0" });
      const inputCatatanNb = MugenUI.el("input", { type: "text", placeholder: "Opsional" });
      const totalGajiBox = MugenUI.el("div", { class: "card", style: "background:var(--bg-input);" }, "Total Gaji: Rp 0");

      function hitungTotalGaji() {
        const total = (Number(inputGajiPerHari.value) || 0) * (Number(inputHariMasuk.value) || 0)
          + (Number(inputBonus.value) || 0) - (Number(inputPotongan.value) || 0);
        totalGajiBox.textContent = `Total Gaji: ${MugenUI.formatRupiah(total)}`;
        return total;
      }
      for (const inp of [inputGajiPerHari, inputHariMasuk, inputBonus, inputPotongan]) {
        inp.addEventListener("input", hitungTotalGaji);
      }
      selKaryawan.addEventListener("change", () => {
        const k = karyawanNonBarber.find((x) => String(x.id) === selKaryawan.value);
        roleTerpilih.textContent = `Role: ${k ? labelJabatan(k.jabatan) : "-"}`;
        if (k && !nbEditingId) {
          inputGajiPerHari.value = String(k.gaji_per_hari || 0);
          hitungTotalGaji();
        }
      });

      const nbBtnSubmit = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
      const nbBtnBatal = MugenUI.el("button", { style: "display:none;" }, "Batal Koreksi");
      const nbFormError = MugenUI.el("div", { class: "login-error" });

      nbFormCard.appendChild(nbFormTitle);
      nbFormCard.appendChild(MugenUI.el("label", {}, "Nama Karyawan"));
      nbFormCard.appendChild(selKaryawan);
      nbFormCard.appendChild(roleTerpilih);
      nbFormCard.appendChild(MugenUI.el("label", {}, "Periode: Tanggal Mulai"));
      nbFormCard.appendChild(inputTglMulai);
      nbFormCard.appendChild(MugenUI.el("label", {}, "Periode: Tanggal Selesai"));
      nbFormCard.appendChild(inputTglSelesai);
      nbFormCard.appendChild(MugenUI.el("label", {}, "Gaji per Hari (Rp)"));
      nbFormCard.appendChild(inputGajiPerHari);
      nbFormCard.appendChild(MugenUI.el("label", {}, "Jumlah Hari Masuk"));
      nbFormCard.appendChild(inputHariMasuk);
      nbFormCard.appendChild(MugenUI.el("label", {}, "Jumlah Hari Libur"));
      nbFormCard.appendChild(inputHariLibur);
      nbFormCard.appendChild(MugenUI.el("label", {}, "Bonus (Rp, Opsional)"));
      nbFormCard.appendChild(inputBonus);
      nbFormCard.appendChild(MugenUI.el("label", {}, "Potongan (Rp, Opsional)"));
      nbFormCard.appendChild(inputPotongan);
      nbFormCard.appendChild(MugenUI.el("label", {}, "Catatan/Keterangan (Opsional)"));
      nbFormCard.appendChild(inputCatatanNb);
      nbFormCard.appendChild(totalGajiBox);
      nbFormCard.appendChild(nbFormError);
      nbFormCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [nbBtnSubmit, nbBtnBatal]));

      function resetNbForm() {
        nbEditingId = null;
        nbFormTitle.textContent = "Tambah Data Gaji Non-Barber";
        nbBtnSubmit.textContent = "Simpan";
        nbBtnBatal.style.display = "none";
        selKaryawan.value = "";
        roleTerpilih.textContent = "Role: -";
        inputTglMulai.value = todayIso();
        inputTglSelesai.value = todayIso();
        inputGajiPerHari.value = "0";
        inputHariMasuk.value = "0";
        inputHariLibur.value = "0";
        inputBonus.value = "0";
        inputPotongan.value = "0";
        inputCatatanNb.value = "";
        hitungTotalGaji();
        nbFormError.textContent = "";
      }

      function isiNbFormUntukKoreksi(e) {
        nbEditingId = e.id;
        nbFormTitle.textContent = `Koreksi Data Gaji #${e.id}`;
        nbBtnSubmit.textContent = "Simpan Koreksi";
        nbBtnBatal.style.display = "";
        selKaryawan.value = String(e.barber_id);
        roleTerpilih.textContent = `Role: ${labelJabatan(e.jabatan)}`;
        inputTglMulai.value = e.tanggal_mulai;
        inputTglSelesai.value = e.tanggal_selesai;
        inputGajiPerHari.value = String(e.gaji_per_hari);
        inputHariMasuk.value = String(e.hari_masuk);
        inputHariLibur.value = String(e.hari_libur);
        inputBonus.value = String(e.bonus);
        inputPotongan.value = String(e.potongan);
        inputCatatanNb.value = e.catatan || "";
        hitungTotalGaji();
        nbFormError.textContent = "";
        nbFormCard.scrollIntoView({ behavior: "smooth" });
      }

      nbBtnBatal.addEventListener("click", resetNbForm);

      nbBtnSubmit.addEventListener("click", async () => {
        nbFormError.textContent = "";
        if (!selKaryawan.value) { nbFormError.textContent = "Pilih karyawan terlebih dahulu."; return; }
        if (!inputTglMulai.value || !inputTglSelesai.value) { nbFormError.textContent = "Periode wajib diisi."; return; }
        const body = {
          barber_id: Number(selKaryawan.value),
          tanggal_mulai: inputTglMulai.value,
          tanggal_selesai: inputTglSelesai.value,
          gaji_per_hari: Number(inputGajiPerHari.value) || 0,
          hari_masuk: Number(inputHariMasuk.value) || 0,
          hari_libur: Number(inputHariLibur.value) || 0,
          bonus: Number(inputBonus.value) || 0,
          potongan: Number(inputPotongan.value) || 0,
          catatan: inputCatatanNb.value || "",
        };
        try {
          // REVISI UI/UX Premium: spinner inline di tombol, bukan overlay layar penuh.
          await MugenUI.withButtonLoading(nbBtnSubmit, async () => {
            if (nbEditingId) {
              await MugenApi.put(`/api/data-non-barber/${nbEditingId}`, body);
              MugenUI.toast("Data gaji dikoreksi.", "success");
            } else {
              await MugenApi.post("/api/data-non-barber", body);
              MugenUI.toast("Data gaji disimpan.", "success");
            }
          });
          resetNbForm();
          loadNbList();
        } catch (e) {
          nbFormError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        }
      });

      // --- DAFTAR DATA GAJI NON-BARBER (bulan berjalan) ---
      nbListCard.appendChild(MugenUI.el("h2", {}, "Data Gaji Non-Barber Bulan Ini"));
      const nbListBody = MugenUI.el("div");
      nbListCard.appendChild(nbListBody);

      async function loadNbList() {
        // REVISI UI/UX Premium: refreshInto() -- satu container, satu tabel
        // hasil, crossfade halus tanpa "flash" kosong (menggantikan
        // innerHTML="Memuat...").
        try {
          await MugenUI.refreshInto(nbListBody, async () => {
            const now = new Date();
            const rows = await MugenApi.get(
              `/api/data-non-barber?tahun=${now.getFullYear()}&bulan=${now.getMonth() + 1}`,
              { useCache: true },
            );
            const daftar = Array.isArray(rows) ? rows : rows.data || [];
            return MugenUI.buildTable(
              [
                { key: "tanggal_mulai", label: "Periode", format: (v, r) => `${MugenUI.formatTanggal(r.tanggal_mulai)} s/d ${MugenUI.formatTanggal(r.tanggal_selesai)}` },
                { key: "nama_barber", label: "Nama" },
                { key: "jabatan", label: "Role", format: (v) => labelJabatan(v) },
                { key: "gaji_per_hari", label: "Gaji/Hari", format: MugenUI.formatRupiah },
                { key: "hari_masuk", label: "Hari Masuk" },
                { key: "hari_libur", label: "Hari Libur" },
                { key: "bonus", label: "Bonus", format: MugenUI.formatRupiah },
                { key: "potongan", label: "Potongan", format: MugenUI.formatRupiah },
                { key: "total_gaji", label: "Total Gaji", format: MugenUI.formatRupiah },
                { key: "catatan", label: "Catatan", format: (v) => v || "-" },
                {
                  key: "aksi", label: "Aksi", format: (_, r) => {
                    const wrap = MugenUI.el("div", { class: "actions-cell" });
                    const btnEdit = MugenUI.el("button", {}, "Koreksi");
                    btnEdit.addEventListener("click", () => isiNbFormUntukKoreksi(r));
                    const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                    btnHapus.addEventListener("click", async () => {
                      if (!confirm(`Hapus data gaji "${r.nama_barber}" periode ${r.tanggal_mulai} s/d ${r.tanggal_selesai}?`)) return;
                      try {
                        await MugenUI.withButtonLoading(btnHapus, () => MugenApi.del(`/api/data-non-barber/${r.id}`));
                        MugenUI.toast("Data gaji dihapus.", "success");
                        loadNbList();
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
              daftar,
            );
          }, { skeleton: { kind: "table", cols: 11, rows: 4 } });
        } catch (e) {
          nbListBody.innerHTML = "";
          nbListBody.appendChild(MugenUI.errorState(e.message));
        }
      }

      resetNbForm();
      loadNbList();
    }
  }

  return { render };
})();

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js
// (bukan <script> biasa lagi, lihat index.html/router.js) -- top-level
// "const" TIDAK menempel ke objek window di browser (beda dari "var"),
// jadi page_loader.js TIDAK BISA mendeteksi lewat window.PageInputData begitu saja
// setelah script ini selesai dimuat. Baris di bawah ini SATU-SATUNYA
// perubahan di file ini untuk mendukung lazy-load -- expose eksplisit ke
// window supaya page_loader.js bisa memverifikasi modul benar-benar
// berhasil dimuat sebelum memanggil render()-nya.
window.PageInputData = PageInputData;
