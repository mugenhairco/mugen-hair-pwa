// pages/kasbon.js — Modul Karyawan (Fase 2): Kasbon Karyawan.
// Satu halaman, dua sudut pandang (pola yang sama seperti pages/slip_gaji.js):
// - Owner ('admin') selalu penuh; 'staff' (Admin) HANYA kalau diberi izin
//   izin_kasbon (Setting > Hak Akses Admin) -- lihat renderAdminView().
//   Backend (routers/kasbon.py) yang benar-benar menegakkan ini, frontend
//   di sini hanya menampilkan pesan error kalau ditolak server.
// - 'barber': hanya melihat kasbon & riwayat pembayaran miliknya sendiri,
//   read-only (tidak ada tombol Tambah/Edit/Hapus/Bayar) -- lihat
//   renderBarberView().
//
// Saldo kasbon (kolom Sisa) HANYA benar-benar berkurang saat Slip Gaji yang
// memotongnya ditandai Sudah Dibayar (lihat slip_gaji_db.tandai_status() +
// kasbon_db.terapkan_potongan_slip_gaji()) -- bukan halaman ini yang
// melakukan itu, halaman ini murni untuk kasbon manual (tambah/edit/hapus/
// bayar langsung).

const PageKasbon = (() => {
  function todayIso() {
    return new Date().toISOString().slice(0, 10);
  }

  function badgeStatus(status) {
    return MugenUI.el("span", { class: "badge" + (status === "lunas" ? "" : " badge-libur") },
      status === "lunas" ? "Lunas" : "Belum Lunas");
  }

  async function tampilkanRiwayat(riwayatCard, riwayatBody, kasbon) {
    riwayatCard.querySelector("h2").textContent = `Riwayat Pembayaran — ${kasbon.nama_barber} (${kasbon.tanggal})`;
    riwayatBody.innerHTML = "Memuat...";
    try {
      const data = await MugenApi.get(`/api/kasbon/${kasbon.id}/pembayaran`);
      const rows = Array.isArray(data) ? data : [];
      riwayatBody.innerHTML = "";
      riwayatBody.appendChild(MugenUI.buildTable(
        [
          { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
          { key: "jumlah", label: "Jumlah", format: MugenUI.formatRupiah },
          { key: "sumber", label: "Sumber", format: (v) => v === "potong_gaji" ? "Potong Gaji" : "Manual" },
          { key: "keterangan", label: "Keterangan", format: (v) => v || "-" },
        ],
        rows,
        { emptyText: "Belum ada pembayaran." },
      ));
    } catch (e) {
      riwayatBody.innerHTML = "";
      riwayatBody.appendChild(MugenUI.el("div", {}, e.detail && e.detail.detail ? e.detail.detail : e.message));
    }
    riwayatCard.scrollIntoView({ behavior: "smooth" });
  }

  // ================= BARBER: daftar milik sendiri, read-only =================
  async function renderBarberView(root) {
    const user = MugenState.getUser();
    root.appendChild(MugenUI.el("div", { class: "subtitle" }, "Riwayat Kasbon Anda."));

    const saldoCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    const riwayatCard = MugenUI.el("div", { class: "card" });
    root.appendChild(saldoCard);
    root.appendChild(listCard);
    root.appendChild(riwayatCard);

    saldoCard.appendChild(MugenUI.el("h2", {}, "Saldo Kasbon Belum Lunas"));
    const saldoText = MugenUI.el("div", { style: "font-size:1.4em;font-weight:600;" }, "Memuat...");
    saldoCard.appendChild(saldoText);
    try {
      const saldo = await MugenApi.get(`/api/kasbon/saldo/${user.barber_id}`);
      saldoText.textContent = MugenUI.formatRupiah(saldo.saldo);
    } catch (e) {
      saldoText.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
    }

    listCard.appendChild(MugenUI.el("h2", {}, "Riwayat Kasbon"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    riwayatCard.appendChild(MugenUI.el("h2", {}, "Riwayat Pembayaran"));
    const riwayatBody = MugenUI.el("div", {}, "Klik \"Riwayat\" pada salah satu kasbon di atas untuk melihat riwayat pembayarannya.");
    riwayatCard.appendChild(riwayatBody);

    async function muat() {
      listBody.innerHTML = "Memuat...";
      try {
        const data = await MugenApi.get("/api/kasbon");
        const rows = Array.isArray(data) ? data : [];
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.buildTable(
          [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            { key: "jumlah", label: "Jumlah", format: MugenUI.formatRupiah },
            { key: "sisa", label: "Sisa", format: MugenUI.formatRupiah },
            { key: "status", label: "Status", format: badgeStatus },
            { key: "keterangan", label: "Keterangan", format: (v) => v || "-" },
            {
              key: "aksi", label: "Aksi", format: (_, r) => {
                const btnRiwayat = MugenUI.el("button", {}, "Riwayat");
                btnRiwayat.addEventListener("click", () => tampilkanRiwayat(riwayatCard, riwayatBody, r));
                return btnRiwayat;
              },
            },
          ],
          rows,
          { emptyText: "Belum ada Kasbon." },
        ));
      } catch (e) {
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.el("div", {}, e.detail && e.detail.detail ? e.detail.detail : e.message));
      }
    }
    muat();
  }

  // ================= OWNER/ADMIN: kelola semua kasbon =================
  async function renderAdminView(root) {
    const today = new Date();
    let editingId = null;
    let barbers = [];
    try {
      barbers = await MugenApi.get("/api/input-data/barbers", { useCache: true });
    } catch (e) { /* opsional -- form tetap tampil, dropdown Barber cuma kosong */ }

    const formCard = MugenUI.el("div", { class: "card" });
    const bayarCard = MugenUI.el("div", { class: "card" });
    const filterCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    const riwayatCard = MugenUI.el("div", { class: "card" });
    root.appendChild(formCard);
    root.appendChild(bayarCard);
    root.appendChild(filterCard);
    root.appendChild(listCard);
    root.appendChild(riwayatCard);

    // ---- Form Tambah / Edit Kasbon ----
    const formTitle = MugenUI.el("h2", {}, "Tambah Kasbon");
    const selBarber = MugenUI.el("select");
    for (const b of barbers) selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    const inputTanggal = MugenUI.el("input", { type: "date", value: todayIso(), max: todayIso() });
    const inputJumlah = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const inputKeterangan = MugenUI.el("input", { type: "text", placeholder: "Opsional" });
    const lockedNote = MugenUI.el("div", { class: "subtitle", style: "display:none;" },
      "Kasbon ini sudah punya riwayat pembayaran -- Tanggal dan Jumlah terkunci, hanya Keterangan yang bisa diubah.");
    const btnSubmit = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
    const btnBatal = MugenUI.el("button", { style: "display:none;" }, "Batal Edit");
    const formError = MugenUI.el("div", { class: "login-error" });

    formCard.appendChild(formTitle);
    formCard.appendChild(MugenUI.el("label", {}, "Barber"));
    formCard.appendChild(selBarber);
    formCard.appendChild(MugenUI.el("label", {}, "Tanggal"));
    formCard.appendChild(inputTanggal);
    formCard.appendChild(MugenUI.el("label", {}, "Jumlah (Rp)"));
    formCard.appendChild(inputJumlah);
    formCard.appendChild(MugenUI.el("label", {}, "Keterangan"));
    formCard.appendChild(inputKeterangan);
    formCard.appendChild(lockedNote);
    formCard.appendChild(formError);
    formCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnSubmit, btnBatal]));

    function resetForm() {
      editingId = null;
      formTitle.textContent = "Tambah Kasbon";
      btnSubmit.textContent = "Simpan";
      btnBatal.style.display = "none";
      selBarber.disabled = false;
      inputTanggal.disabled = false;
      inputJumlah.disabled = false;
      inputTanggal.value = todayIso();
      inputJumlah.value = "0";
      inputKeterangan.value = "";
      lockedNote.style.display = "none";
      formError.textContent = "";
    }

    function isiFormUntukEdit(k) {
      editingId = k.id;
      const locked = k.sisa < k.jumlah;
      formTitle.textContent = `Edit Kasbon #${k.id}`;
      btnSubmit.textContent = "Simpan Perubahan";
      btnBatal.style.display = "";
      selBarber.value = String(k.barber_id);
      selBarber.disabled = true; // barber kasbon tidak bisa dipindah lewat form edit
      inputTanggal.value = k.tanggal;
      inputTanggal.disabled = locked;
      inputJumlah.value = String(k.jumlah);
      inputJumlah.disabled = locked;
      inputKeterangan.value = k.keterangan || "";
      lockedNote.style.display = locked ? "" : "none";
      formError.textContent = "";
      formCard.scrollIntoView({ behavior: "smooth" });
    }

    btnBatal.addEventListener("click", resetForm);

    btnSubmit.addEventListener("click", async () => {
      formError.textContent = "";
      if (!selBarber.value) { formError.textContent = "Pilih barber dulu."; return; }
      if (!editingId && (!inputJumlah.value || Number(inputJumlah.value) <= 0)) {
        formError.textContent = "Jumlah harus lebih dari 0."; return;
      }
      btnSubmit.disabled = true;
      try {
        if (editingId) {
          const body = { keterangan: inputKeterangan.value.trim() };
          if (!inputTanggal.disabled) body.tanggal = inputTanggal.value;
          if (!inputJumlah.disabled) body.jumlah = Number(inputJumlah.value) || 0;
          await MugenUI.withLoading(() => MugenApi.put(`/api/kasbon/${editingId}`, body), { message: "Menyimpan…" });
          MugenUI.toast("Kasbon diperbarui.", "success");
        } else {
          await MugenUI.withLoading(() => MugenApi.post("/api/kasbon", {
            barber_id: Number(selBarber.value), tanggal: inputTanggal.value,
            jumlah: Number(inputJumlah.value) || 0, keterangan: inputKeterangan.value.trim(),
          }), { message: "Menyimpan…" });
          MugenUI.toast("Kasbon disimpan.", "success");
        }
        resetForm();
        loadList();
      } catch (e) {
        formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      } finally {
        btnSubmit.disabled = false;
      }
    });

    // ---- Form Bayar Kasbon ----
    bayarCard.appendChild(MugenUI.el("h2", {}, "Bayar Kasbon"));
    const baySubtitle = MugenUI.el("div", { class: "subtitle" },
      "Klik \"Bayar\" pada salah satu kasbon di daftar bawah untuk mengisi form ini.");
    bayarCard.appendChild(baySubtitle);
    const inputBayarTanggal = MugenUI.el("input", { type: "date", value: todayIso(), max: todayIso() });
    const inputBayarJumlah = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const inputBayarKeterangan = MugenUI.el("input", { type: "text", placeholder: "Opsional" });
    const btnBayar = MugenUI.el("button", { class: "btn-primary" }, "Simpan Pembayaran");
    btnBayar.disabled = true;
    const bayarError = MugenUI.el("div", { class: "login-error" });
    bayarCard.appendChild(MugenUI.el("label", {}, "Tanggal Bayar"));
    bayarCard.appendChild(inputBayarTanggal);
    bayarCard.appendChild(MugenUI.el("label", {}, "Jumlah (Rp)"));
    bayarCard.appendChild(inputBayarJumlah);
    bayarCard.appendChild(MugenUI.el("label", {}, "Keterangan"));
    bayarCard.appendChild(inputBayarKeterangan);
    bayarCard.appendChild(bayarError);
    bayarCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnBayar));

    let bayarKasbonId = null;
    function pilihKasbonUntukBayar(k) {
      bayarKasbonId = k.id;
      baySubtitle.textContent = `Bayar kasbon ${k.nama_barber} tanggal ${k.tanggal} — sisa ${MugenUI.formatRupiah(k.sisa)}`;
      inputBayarTanggal.value = todayIso();
      inputBayarJumlah.value = String(k.sisa);
      inputBayarKeterangan.value = "";
      bayarError.textContent = "";
      btnBayar.disabled = false;
      bayarCard.scrollIntoView({ behavior: "smooth" });
    }

    btnBayar.addEventListener("click", async () => {
      bayarError.textContent = "";
      if (!bayarKasbonId) return;
      if (!inputBayarJumlah.value || Number(inputBayarJumlah.value) <= 0) {
        bayarError.textContent = "Jumlah harus lebih dari 0."; return;
      }
      btnBayar.disabled = true;
      try {
        await MugenUI.withLoading(() => MugenApi.post(`/api/kasbon/${bayarKasbonId}/pembayaran`, {
          tanggal: inputBayarTanggal.value, jumlah: Number(inputBayarJumlah.value) || 0,
          keterangan: inputBayarKeterangan.value.trim(),
        }), { message: "Menyimpan pembayaran…" });
        MugenUI.toast("Pembayaran kasbon disimpan.", "success");
        bayarKasbonId = null;
        baySubtitle.textContent = "Klik \"Bayar\" pada salah satu kasbon di daftar bawah untuk mengisi form ini.";
        loadList();
      } catch (e) {
        bayarError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      } finally {
        btnBayar.disabled = bayarKasbonId === null;
      }
    });

    // ---- Filter ----
    filterCard.appendChild(MugenUI.el("h2", {}, "Filter"));
    const filBarber = MugenUI.el("select");
    filBarber.appendChild(MugenUI.el("option", { value: "" }, "Semua Barber"));
    for (const b of barbers) filBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    const filStatus = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "" }, "Semua Status"),
      MugenUI.el("option", { value: "belum_lunas" }, "Belum Lunas"),
      MugenUI.el("option", { value: "lunas" }, "Lunas"),
    ]);
    const filBulan = MugenUI.el("select");
    filBulan.appendChild(MugenUI.el("option", { value: "" }, "Semua Bulan"));
    for (let m = 1; m <= 12; m++) filBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    const filTahun = MugenUI.el("select");
    filTahun.appendChild(MugenUI.el("option", { value: "" }, "Semua Tahun"));
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) filTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    filterCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;" }, [filBarber, filStatus, filBulan, filTahun]));

    // ---- Daftar ----
    listCard.appendChild(MugenUI.el("h2", {}, "Daftar Kasbon"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    riwayatCard.appendChild(MugenUI.el("h2", {}, "Riwayat Pembayaran"));
    const riwayatBody = MugenUI.el("div", {}, "Klik \"Riwayat\" pada salah satu kasbon di atas untuk melihat riwayat pembayarannya.");
    riwayatCard.appendChild(riwayatBody);

    async function loadList() {
      listBody.innerHTML = "Memuat...";
      try {
        const qs = new URLSearchParams();
        if (filBarber.value) qs.set("barber_id", filBarber.value);
        if (filStatus.value) qs.set("status", filStatus.value);
        if (filBulan.value) qs.set("bulan", filBulan.value);
        if (filTahun.value) qs.set("tahun", filTahun.value);
        const data = await MugenApi.get(`/api/kasbon?${qs.toString()}`);
        const rows = Array.isArray(data) ? data : [];
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.buildTable(
          [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            { key: "nama_barber", label: "Barber" },
            { key: "jumlah", label: "Jumlah", format: MugenUI.formatRupiah },
            { key: "sisa", label: "Sisa", format: MugenUI.formatRupiah },
            { key: "status", label: "Status", format: badgeStatus },
            { key: "keterangan", label: "Keterangan", format: (v) => v || "-" },
            {
              key: "aksi", label: "Aksi", format: (_, r) => {
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnRiwayat = MugenUI.el("button", {}, "Riwayat");
                btnRiwayat.addEventListener("click", () => tampilkanRiwayat(riwayatCard, riwayatBody, r));
                wrap.appendChild(btnRiwayat);

                if (r.status !== "lunas") {
                  const btnBayarRow = MugenUI.el("button", {}, "Bayar");
                  btnBayarRow.addEventListener("click", () => pilihKasbonUntukBayar(r));
                  wrap.appendChild(btnBayarRow);
                }

                const btnEdit = MugenUI.el("button", {}, "Edit");
                btnEdit.addEventListener("click", () => isiFormUntukEdit(r));
                wrap.appendChild(btnEdit);

                if (r.sisa >= r.jumlah) { // belum ada pembayaran sama sekali
                  const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                  btnHapus.addEventListener("click", async () => {
                    if (!confirm(`Hapus kasbon ${r.nama_barber} tanggal ${r.tanggal}?`)) return;
                    try {
                      await MugenApi.del(`/api/kasbon/${r.id}`);
                      MugenUI.toast("Kasbon dihapus.", "success");
                      loadList();
                    } catch (e) {
                      MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                    }
                  });
                  wrap.appendChild(btnHapus);
                }
                return wrap;
              },
            },
          ],
          rows,
          { emptyText: "Belum ada Kasbon." },
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
    root.appendChild(MugenUI.el("h1", {}, "Kasbon Karyawan"));

    if (user.role === "barber") {
      await renderBarberView(root);
    } else {
      await renderAdminView(root);
    }
  }

  return { render };
})();
