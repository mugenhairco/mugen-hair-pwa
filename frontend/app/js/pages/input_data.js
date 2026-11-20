// pages/input_data.js
// PENGHAPUSAN Input Data Barber (keputusan Owner: jalur input transaksi
// harian hanya POS & Manual Customer): mode "Input Data Barber" (form
// Tambah/Koreksi Transaksi qty-per-service + tab "Transaksi Bulan Ini" +
// kartu "Tandai Libur") SUDAH DIHAPUS TOTAL dari halaman ini. Dua fungsi
// yang dulu menempel di mode itu dipindahkan:
// - Tandai Libur -> pages/absensi.js, tab "Kuota Cuti & Libur"
//   (renderTandaiLiburManual()) -- endpoint backend (POST/DELETE
//   /api/input-data/libur) TIDAK berubah, hanya lokasi formnya.
// - Koreksi Transaksi -> pages/rekap.js, tombol "✏ Koreksi" di samping
//   "🗑 Hapus" pada baris bertipe transaksi -- endpoint backend (PUT
//   /api/input-data/transaksi/{id}) TIDAK berubah.
// Router/endpoint `/api/input-data/*` (barbers/karyawan/services/libur/
// transaksi) TETAP ADA APA ADANYA -- dipakai bersama oleh Manual Customer
// (di bawah), Non-Barber (di bawah), Rekap, Booking (Barber Holiday), dan
// Absensi. Halaman ini sekarang HANYA berisi Manual Customer & Input Data
// Non-Barber.

const PageInputData = (() => {
  // PERMINTAAN OWNER: pola SAMA seperti produk.js/rekap.js -- simpan hasil
  // fetch TERAKHIR (Status & Daftar Manual Customer, Data Gaji Non-Barber --
  // key dibedakan lewat `bagian` di bawah) di LUAR render() (modul-level)
  // supaya bertahan lintas navigasi menu. Kalau Input Data dibuka lagi
  // TANPA ada simpan/edit/hapus apa pun sejak terakhir kali BAGIAN itu
  // berhasil dimuat (lihat state.js::halamanPerluRefresh()) DAN filter
  // (url) yang aktif sama persis, tampilkan ulang data ini TANPA
  // fetch/skeleton.
  let _cacheTerakhir = {}; // { [bagian]: { userId, url, data } }

  function _ambilDariCache(bagian, userId, url) {
    const c = _cacheTerakhir[bagian];
    if (!c || c.userId !== userId || c.url !== url) return null;
    return c.data;
  }

  function _simpanKeCache(bagian, userId, url, data) {
    _cacheTerakhir[bagian] = { userId, url, data };
  }

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
    root.appendChild(MugenUI.pageTitle("Input Data", MugenIcons.inputData));

    // AUDIT Hak Akses Menu (permintaan Owner): "Tidak Ada Akses" -- HANYA
    // pesan kosong, tanpa form/data apa pun (mencakup kedua mode: Manual
    // Customer/Non-Barber, satu menu yang sama).
    if (isAdmin && (await MugenMenuAccess.get("input_data")) === "none") {
      root.appendChild(MugenUI.emptyState("Anda tidak memiliki akses ke menu ini."));
      return;
    }

    // Dropdown pemilih mode -- KHUSUS Owner/Admin (Non-Barber murni fitur
    // pengelolaan data, sama seperti seluruh Input Data yang memang sudah
    // Owner/Admin-only). Default "Manual Customer" SELALU terpilih.
    const manualCustomerSection = MugenUI.el("div");
    const nonBarberSection = MugenUI.el("div", { style: "display:none;" });
    if (isAdmin) {
      const selMode = MugenUI.el("select", { style: "max-width:280px;margin-bottom:16px;" }, [
        MugenUI.el("option", { value: "manual_customer" }, "Manual Customer"),
        MugenUI.el("option", { value: "non_barber" }, "Input Data Non-Barber"),
      ]);
      selMode.value = "manual_customer";
      selMode.addEventListener("change", () => {
        manualCustomerSection.style.display = selMode.value === "manual_customer" ? "" : "none";
        nonBarberSection.style.display = selMode.value === "non_barber" ? "" : "none";
      });
      root.appendChild(MugenUI.selectIcon(MugenIcons.filter, selMode));
    }
    root.appendChild(manualCustomerSection);
    root.appendChild(nonBarberSection);

    // Hak Akses Menu: level "Baca" -- sembunyikan form Tambah/Koreksi
    // (kedua mode: Manual Customer/Non-Barber), daftar tetap tampil.
    // Dihitung sekali di sini, dipakai lagi di renderManualCustomer()/
    // renderNonBarber() di bawah lewat closure.
    const bolehEditInputData = !isAdmin || (await MugenMenuAccess.get("input_data")) === "write";

    // `services`/`barbers` dipakai Manual Customer (dropdown Barber +
    // checklist Service di form Booking) -- Non-Barber punya fetch
    // karyawan sendiri (/api/input-data/karyawan), tidak butuh dua ini.
    let services = [];
    let barbers = [];
    try {
      [services, barbers] = await Promise.all([
        MugenApi.get("/api/input-data/services", { useCache: true }),
        isAdmin ? MugenApi.get("/api/input-data/barbers", { useCache: true }) : Promise.resolve([]),
      ]);
    } catch (e) {
      root.appendChild(MugenUI.errorState(e.message));
      return;
    }

    // --- INPUT DATA NON-BARBER (Kasir/OB/Kru/role lainnya) ---
    // Tabel & endpoint baru, TIDAK terhubung ke `transaksi`/Slip Gaji Barber
    // sama sekali (lihat data_non_barber_db.py) -- murni tambahan, bagian
    // ini di-skip total untuk Barber (dropdown mode di atas juga tidak
    // pernah muncul untuknya).
    // PERBAIKAN PERFORMA (keluhan Owner: menu terasa ada jeda): KEDUANYA
    // sengaja TIDAK di-await lagi -- seksi Non-Barber TERSEMBUNYI
    // (display:none) sampai Owner/Admin pilih dropdown modenya, jadi
    // fetch-nya tidak boleh menahan render() Input Data (seksi Manual
    // Customer yang langsung terlihat) selesai lebih dulu.
    if (isAdmin) renderManualCustomer();
    if (isAdmin) renderNonBarber();

    // --- INPUT DATA MANUAL CUSTOMER (Waiting List / Booking) ---
    // Metode input transaksi harian -- lihat manual_customer_db.py untuk
    // aturan lengkap ("satu tanggal satu mode", jam immutable, Closing
    // tidak mengunci Rekap, dst). Tabel & endpoint baru, TIDAK PERNAH
    // menyentuh `transaksi`/Rekap langsung -- hanya lewat
    // database.tambah_transaksi() saat tombol "Tutup & Simpan Hari Ini"
    // ditekan.
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
        const cb = MugenUI.el("input", { type: "checkbox" });
        mcServiceChecks[s.id] = cb;
        mcServiceList.appendChild(MugenUI.el("label", { style: "display:flex;align-items:center;gap:8px;" },
          [cb, `${s.nama} (${MugenUI.formatRupiah(s.harga)})`]));
      }
      const inputTipsMc = MugenUI.el("input", { type: "number", min: "0", placeholder: "—" });
      bookingFields.appendChild(MugenUI.el("label", {}, "Jam Booking"));
      bookingFields.appendChild(inputJamBooking);
      bookingFields.appendChild(MugenUI.el("label", {}, "Barber"));
      bookingFields.appendChild(MugenUI.selectIcon(MugenIcons.karyawan, selBarberMc));
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
      mcFormCard.appendChild(MugenUI.selectIcon(MugenIcons.tag, selJenis));
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
        inputTipsMc.value = "";
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
        inputTipsMc.value = MugenUI.nilaiTampilAngka(e.tips);
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
      async function loadMcStatus(opts = {}) {
        const url = `/api/manual-customer/status?tanggal=${mcTanggal.value}`;

        // PERMINTAAN OWNER: pola SAMA seperti loadMcStatus()/loadProdukList() --
        // lihat catatan panjang di produk.js::loadProdukList(). Hanya
        // berlaku untuk pemuatan AWAL (tanggal default = hari ini) --
        // ganti tanggal/tutup/reset/submit SELALU fetch ulang.
        const cached = opts.bisaDariCache && !MugenState.halamanPerluRefresh("input_data")
          ? _ambilDariCache("mc_status", MugenState.getUser().id, url)
          : null;
        if (cached) {
          mcStatus = cached;
        } else {
          try {
            mcStatus = await MugenApi.get(url);
            _simpanKeCache("mc_status", MugenState.getUser().id, url, mcStatus);
            MugenState.tandaiHalamanBersih("input_data");
          } catch (e) {
            mcStatus = { mode: null, status: null };
          }
        }

        if (mcStatus.mode === null) {
          mcStatusBadge.textContent = "Tanggal ini belum dipakai -- mode bebas dipilih.";
        } else if (mcStatus.mode === "barber") {
          // Data LAMA (dari sebelum mode "Input Data Barber" dihapus) --
          // tanggal itu sudah terkunci mode 'barber' selamanya sampai
          // di-Reset, biarpun form pembuatnya sudah tidak ada lagi.
          mcStatusBadge.textContent = "Tanggal ini sudah memakai metode Input Barber (data lama) -- Manual Customer tidak bisa dipakai (Reset dulu untuk berganti metode).";
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
        if (!(await MugenUI.confirmModal({ message: `Tutup & simpan transaksi Manual Customer tanggal ${mcTanggal.value}? Baris yang sudah punya Barber+Service akan masuk ke Rekap.` }))) return;
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
        if (!(await MugenUI.confirmModal({ message: `Hapus SELURUH transaksi tanggal ${mcTanggal.value} supaya metode bisa dipilih ulang? Tindakan ini tidak bisa dibatalkan.`, danger: true }))) return;
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

      function renderDenganDataMc(rows) {
        mcListBody.innerHTML = "";
        mcListBody.appendChild(MugenUI.buildTable(
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
            { key: "tips", label: "Tips", format: MugenUI.formatRupiahAtauStrip },
            {
              key: "aksi", label: "Aksi", format: (_, r) => {
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnEdit = MugenUI.el("button", {}, "Koreksi");
                btnEdit.addEventListener("click", () => isiMcFormUntukKoreksi(r));
                const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btnHapus.addEventListener("click", async () => {
                  if (!(await MugenUI.confirmModal({ message: `Hapus data customer "${r.nama_customer}"?`, danger: true }))) return;
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
        ));
      }

      async function loadMcList(opts = {}) {
        const url = `/api/manual-customer/transaksi?tanggal=${mcTanggal.value}`;

        // PERMINTAAN OWNER: pola SAMA seperti loadMcStatus() di atas --
        // hanya berlaku untuk pemuatan AWAL, ganti tanggal/tutup/reset/
        // submit/hapus SELALU fetch ulang.
        if (opts.bisaDariCache && !MugenState.halamanPerluRefresh("input_data")) {
          const cached = _ambilDariCache("mc_list", MugenState.getUser().id, url);
          if (cached) {
            renderDenganDataMc(cached);
            return;
          }
        }

        mcListBody.innerHTML = "";
        mcListBody.appendChild(MugenUI.skeleton("table", { cols: 7, rows: 4 }));
        try {
          const rows = await MugenApi.get(url);
          _simpanKeCache("mc_list", MugenState.getUser().id, url, rows);
          MugenState.tandaiHalamanBersih("input_data");
          renderDenganDataMc(rows);
        } catch (e) {
          mcListBody.innerHTML = "";
          mcListBody.appendChild(MugenUI.errorState(e.message));
        }
      }

      resetMcForm();
      await loadMcStatus({ bisaDariCache: true });
      await loadMcList({ bisaDariCache: true });
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
      const inputGajiPerHari = MugenUI.el("input", { type: "number", min: "0", placeholder: "—" });
      const inputHariMasuk = MugenUI.el("input", { type: "number", min: "0", placeholder: "—" });
      const inputHariLibur = MugenUI.el("input", { type: "number", min: "0", placeholder: "—" });
      const inputBonus = MugenUI.el("input", { type: "number", min: "0", placeholder: "—" });
      const inputPotongan = MugenUI.el("input", { type: "number", min: "0", placeholder: "—" });
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
          inputGajiPerHari.value = MugenUI.nilaiTampilAngka(k.gaji_per_hari);
          hitungTotalGaji();
        }
      });

      const nbBtnSubmit = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
      const nbBtnBatal = MugenUI.el("button", { style: "display:none;" }, "Batal Koreksi");
      const nbFormError = MugenUI.el("div", { class: "login-error" });

      nbFormCard.appendChild(nbFormTitle);
      nbFormCard.appendChild(MugenUI.el("label", {}, "Nama Karyawan"));
      nbFormCard.appendChild(MugenUI.selectIcon(MugenIcons.karyawan, selKaryawan));
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
        inputGajiPerHari.value = "";
        inputHariMasuk.value = "";
        inputHariLibur.value = "";
        inputBonus.value = "";
        inputPotongan.value = "";
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
        inputGajiPerHari.value = MugenUI.nilaiTampilAngka(e.gaji_per_hari);
        inputHariMasuk.value = MugenUI.nilaiTampilAngka(e.hari_masuk);
        inputHariLibur.value = MugenUI.nilaiTampilAngka(e.hari_libur);
        inputBonus.value = MugenUI.nilaiTampilAngka(e.bonus);
        inputPotongan.value = MugenUI.nilaiTampilAngka(e.potongan);
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
        // PERMINTAAN Owner ("nilai kosong tidak otomatis dianggap 0"):
        // Gaji per Hari/Hari Masuk/Hari Libur WAJIB diisi (bukan opsional
        // seperti Bonus/Potongan yang labelnya sendiri sudah bilang
        // "Opsional" -- itu TETAP boleh lenient, 0 kalau kosong).
        const gajiPerHari = MugenUI.bacaAngkaWajib(inputGajiPerHari);
        const hariMasuk = MugenUI.bacaAngkaWajib(inputHariMasuk);
        const hariLibur = MugenUI.bacaAngkaWajib(inputHariLibur);
        if (gajiPerHari === null) { nbFormError.textContent = "Gaji per Hari wajib diisi."; return; }
        if (hariMasuk === null) { nbFormError.textContent = "Jumlah Hari Masuk wajib diisi."; return; }
        if (hariLibur === null) { nbFormError.textContent = "Jumlah Hari Libur wajib diisi."; return; }
        const body = {
          barber_id: Number(selKaryawan.value),
          tanggal_mulai: inputTglMulai.value,
          tanggal_selesai: inputTglSelesai.value,
          gaji_per_hari: gajiPerHari,
          hari_masuk: hariMasuk,
          hari_libur: hariLibur,
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

      function renderDenganDataNb(rows) {
        nbListBody.innerHTML = "";
        const daftar = Array.isArray(rows) ? rows : rows.data || [];
        nbListBody.appendChild(MugenUI.buildTable(
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
              // PERMINTAAN OWNER: tombol Hapus Data Gaji Non-Barber dihapus
              // dari sini -- redundan dengan Rekap > Transaksi (lihat
              // rekap.js, kolom Aksi "Hapus Data Gaji Non-Barber").
              key: "aksi", label: "Aksi", format: (_, r) => {
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnEdit = MugenUI.el("button", {}, "Koreksi");
                btnEdit.addEventListener("click", () => isiNbFormUntukKoreksi(r));
                wrap.appendChild(btnEdit);
                return wrap;
              },
            },
          ],
          daftar,
        ));
      }

      async function loadNbList(opts = {}) {
        const now = new Date();
        const url = `/api/data-non-barber?tahun=${now.getFullYear()}&bulan=${now.getMonth() + 1}`;

        // PERMINTAAN OWNER: pola SAMA seperti loadList()/loadProdukList() --
        // lihat catatan panjang di produk.js::loadProdukList().
        if (opts.bisaDariCache && !MugenState.halamanPerluRefresh("input_data")) {
          const cached = _ambilDariCache("non_barber", MugenState.getUser().id, url);
          if (cached) {
            renderDenganDataNb(cached);
            return;
          }
        }

        nbListBody.innerHTML = "";
        nbListBody.appendChild(MugenUI.skeleton("table", { cols: 11, rows: 4 }));
        try {
          const rows = await MugenApi.get(url, { useCache: true });
          if (!rows.__offline) {
            _simpanKeCache("non_barber", MugenState.getUser().id, url, rows);
            MugenState.tandaiHalamanBersih("input_data");
          }
          renderDenganDataNb(rows);
        } catch (e) {
          nbListBody.innerHTML = "";
          nbListBody.appendChild(MugenUI.errorState(e.message));
        }
      }

      resetNbForm();
      loadNbList({ bisaDariCache: true });
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
