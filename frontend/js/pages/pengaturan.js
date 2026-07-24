// pages/pengaturan.js — TAHAP 10: menu Setting. KHUSUS admin (dijaga di
// router.js + backend require_admin di setiap endpoint /api/pengaturan/*).
// Mengikuti pola tab seperti pages/rekap.js.

const PagePengaturan = (() => {
  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Setting"));

    const tabs = ["Identitas Barbershop", "Komisi & Bonus", "Barber", "Layanan", "User", "Backup"];
    let activeTab = tabs[0];

    const tabBar = MugenUI.el("div", { class: "tabs" });
    const body = MugenUI.el("div");
    root.appendChild(tabBar);
    root.appendChild(body);

    function renderTabs() {
      tabBar.innerHTML = "";
      for (const t of tabs) {
        const btn = MugenUI.el("button", { class: activeTab === t ? "active" : "" }, t);
        btn.addEventListener("click", () => { activeTab = t; renderTabs(); renderBody(); });
        tabBar.appendChild(btn);
      }
    }

    async function renderBody() {
      body.innerHTML = "";
      if (activeTab === "Identitas Barbershop") await renderIdentitas();
      else if (activeTab === "Komisi & Bonus") await renderKomisi();
      else if (activeTab === "Barber") await renderBarber();
      else if (activeTab === "Layanan") await renderLayanan();
      else if (activeTab === "User") await renderUser();
      else await renderBackup();
    }

    // ================= TAB: IDENTITAS BARBERSHOP =================
    async function renderIdentitas() {
      const card = MugenUI.el("div", { class: "card" });
      body.appendChild(card);
      card.appendChild(MugenUI.el("h2", {}, "Identitas Barbershop"));
      card.appendChild(MugenUI.el("div", { class: "subtitle" },
        "Nama & logo di sini otomatis dipakai di halaman Login dan sidebar seluruh aplikasi."));

      let data;
      try {
        data = await MugenApi.get("/api/pengaturan/identitas");
      } catch (e) {
        card.appendChild(MugenUI.el("div", {}, e.message));
        return;
      }

      const logoPreview = MugenUI.el("img", { class: "logo-preview", style: data.logo_url ? "" : "display:none;", alt: "Logo saat ini" });
      if (data.logo_url) logoPreview.src = MUGEN_API_BASE + data.logo_url;
      const inputLogo = MugenUI.el("input", { type: "file", accept: "image/jpeg,image/png,image/webp" });
      const btnUploadLogo = MugenUI.el("button", {}, "Upload Logo Baru");
      const logoError = MugenUI.el("div", { class: "login-error" });

      btnUploadLogo.addEventListener("click", async () => {
        if (!inputLogo.files || !inputLogo.files[0]) { logoError.textContent = "Pilih file logo dulu (JPG/PNG/WEBP)."; return; }
        logoError.textContent = "";
        btnUploadLogo.disabled = true;
        try {
          const hasil = await MugenApi.uploadFile("/api/pengaturan/logo", inputLogo.files[0]);
          logoPreview.src = MUGEN_API_BASE + hasil.logo_url + "&t=" + Date.now();
          logoPreview.style.display = "";
          MugenUI.toast("Logo berhasil diganti.", "success");
          MugenBrand.refresh();
        } catch (e) {
          logoError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        } finally {
          btnUploadLogo.disabled = false;
        }
      });

      card.appendChild(MugenUI.el("label", {}, "Logo (JPG/PNG/WEBP)"));
      card.appendChild(logoPreview);
      card.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin:8px 0;" }, [inputLogo, btnUploadLogo]));
      card.appendChild(logoError);

      const inputNama = MugenUI.el("input", { type: "text", value: data.nama_barbershop || "" });
      const inputAlamat = MugenUI.el("input", { type: "text", value: data.alamat || "" });
      const inputWA = MugenUI.el("input", { type: "text", value: data.whatsapp || "" });
      const inputEmail = MugenUI.el("input", { type: "text", value: data.email || "" });
      const inputIG = MugenUI.el("input", { type: "text", value: data.instagram || "" });
      const inputJam = MugenUI.el("input", { type: "text", value: data.jam_operasional || "", placeholder: "mis. 09:00 - 21:00" });
      const btnSimpan = MugenUI.el("button", { class: "btn-primary" }, "Simpan Identitas");
      const formError = MugenUI.el("div", { class: "login-error" });

      card.appendChild(MugenUI.el("label", {}, "Nama Barbershop"));
      card.appendChild(inputNama);
      card.appendChild(MugenUI.el("label", {}, "Alamat"));
      card.appendChild(inputAlamat);
      card.appendChild(MugenUI.el("label", {}, "Nomor WhatsApp"));
      card.appendChild(inputWA);
      card.appendChild(MugenUI.el("label", {}, "Email"));
      card.appendChild(inputEmail);
      card.appendChild(MugenUI.el("label", {}, "Instagram"));
      card.appendChild(inputIG);
      card.appendChild(MugenUI.el("label", {}, "Jam Operasional"));
      card.appendChild(inputJam);
      card.appendChild(formError);
      card.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpan));

      btnSimpan.addEventListener("click", async () => {
        formError.textContent = "";
        if (!inputNama.value.trim()) { formError.textContent = "Nama Barbershop tidak boleh kosong."; return; }
        btnSimpan.disabled = true;
        try {
          await MugenApi.put("/api/pengaturan/identitas", {
            nama_barbershop: inputNama.value.trim(),
            alamat: inputAlamat.value.trim(),
            whatsapp: inputWA.value.trim(),
            email: inputEmail.value.trim(),
            instagram: inputIG.value.trim(),
            jam_operasional: inputJam.value.trim(),
          });
          MugenUI.toast("Identitas barbershop disimpan.", "success");
          MugenBrand.refresh();
        } catch (e) {
          formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        } finally {
          btnSimpan.disabled = false;
        }
      });
    }

    // ================= TAB: KOMISI & BONUS =================
    async function renderKomisi() {
      const card = MugenUI.el("div", { class: "card" });
      body.appendChild(card);
      card.appendChild(MugenUI.el("h2", {}, "Pengaturan Komisi"));
      card.appendChild(MugenUI.el("div", { class: "subtitle" },
        "Nilai ini langsung dipakai oleh rumus komisi/bonus yang sudah berjalan (Tahap 2) — tidak ada perubahan rumus, hanya nilainya jadi bisa diubah tanpa edit kode."));

      let s;
      try {
        s = await MugenApi.get("/api/pengaturan/komisi");
      } catch (e) {
        card.appendChild(MugenUI.el("div", {}, e.message));
        return;
      }

      const field = (label, key, satuan) => {
        const input = MugenUI.el("input", { type: "number", min: "0", step: "any", value: String(s[key] ?? 0) });
        card.appendChild(MugenUI.el("label", {}, `${label}${satuan ? ` (${satuan})` : ""}`));
        card.appendChild(input);
        return input;
      };

      const inPersen = field("Persentase Komisi", "persentase_komisi", "%");
      const inPotonganChemical = field("Potongan Modal Chemical", "potongan_modal_chemical", "Rp/transaksi");
      const inUangHarian = field("Uang Harian (Barber biasa)", "uang_harian_barber", "Rp/hari");
      const inUangHarianRafiq = field("Uang Harian (Rafiq)", "uang_harian_rafiq", "Rp/hari");
      const inBonusKehadiran = field("Bonus Kehadiran", "bonus_kehadiran", "Rp/bulan");
      const inMaksLibur = field("Maksimal Hari Libur (utk Bonus Kehadiran)", "maksimal_hari_libur", "hari/bulan");

      card.appendChild(MugenUI.el("h2", { style: "margin-top:24px;" }, "Bonus Bulanan (Bonus Customer)"));
      card.appendChild(MugenUI.el("div", { class: "subtitle" },
        "Catatan: perhitungan bonus bulanan yang sudah berjalan mendukung SATU target (bukan bertingkat 85/100/130/150) — mengubahnya jadi bertingkat berarti mengubah rumus di Tahap 2, di luar cakupan Tahap 10 ini. Target & nominal di bawah bisa diubah bebas."));
      const inTarget = field("Target Jumlah Customer/Bulan", "target_bonus_customer", "customer");
      const inNominalBonus = field("Nominal Bonus jika Target Tercapai", "nominal_bonus_customer", "Rp");
      const inMaksLiburBonus = field("Maksimal Hari Libur (utk Bonus Customer)", "maksimal_hari_libur_bonus_customer", "hari/bulan");
      const inPotonganBonus = field("Potongan Bonus jika Libur Melebihi Batas", "potongan_bonus_customer_persen", "%");

      const btnSimpan = MugenUI.el("button", { class: "btn-primary" }, "Simpan Pengaturan");
      const formError = MugenUI.el("div", { class: "login-error" });
      card.appendChild(formError);
      card.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpan));

      btnSimpan.addEventListener("click", async () => {
        formError.textContent = "";
        const body2 = {
          persentase_komisi: Number(inPersen.value),
          potongan_modal_chemical: Number(inPotonganChemical.value),
          uang_harian_barber: Number(inUangHarian.value),
          uang_harian_rafiq: Number(inUangHarianRafiq.value),
          bonus_kehadiran: Number(inBonusKehadiran.value),
          maksimal_hari_libur: Number(inMaksLibur.value),
          target_bonus_customer: Number(inTarget.value),
          nominal_bonus_customer: Number(inNominalBonus.value),
          maksimal_hari_libur_bonus_customer: Number(inMaksLiburBonus.value),
          potongan_bonus_customer_persen: Number(inPotonganBonus.value),
        };
        for (const [k, v] of Object.entries(body2)) {
          if (Number.isNaN(v) || v < 0) { formError.textContent = `Nilai untuk "${k}" tidak valid (harus angka >= 0).`; return; }
        }
        btnSimpan.disabled = true;
        try {
          await MugenApi.put("/api/pengaturan/komisi", body2);
          MugenUI.toast("Pengaturan komisi & bonus disimpan.", "success");
        } catch (e) {
          formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        } finally {
          btnSimpan.disabled = false;
        }
      });
    }

    // ================= TAB: BARBER =================
    async function renderBarber() {
      const formCard = MugenUI.el("div", { class: "card" });
      const listCard = MugenUI.el("div", { class: "card" });
      body.appendChild(formCard);
      body.appendChild(listCard);

      let editingId = null;
      formCard.appendChild(MugenUI.el("h2", {}, "Tambah Barber"));
      const formTitle = formCard.lastChild;
      const inputNama = MugenUI.el("input", { type: "text", placeholder: "Nama barber" });
      const inputRafiq = MugenUI.el("input", { type: "checkbox", style: "width:auto;" });
      const btnSubmit = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
      const btnBatal = MugenUI.el("button", { style: "display:none;" }, "Batal Edit");
      const formError = MugenUI.el("div", { class: "login-error" });

      formCard.appendChild(MugenUI.el("label", {}, "Nama Barber"));
      formCard.appendChild(inputNama);
      formCard.appendChild(MugenUI.el("label", {}, [inputRafiq, " Barber RAFIQ (uang harian & aturan khusus)"]));
      formCard.appendChild(formError);
      formCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnSubmit, btnBatal]));

      function resetForm() {
        editingId = null;
        formTitle.textContent = "Tambah Barber";
        btnSubmit.textContent = "Simpan";
        btnBatal.style.display = "none";
        inputNama.value = "";
        inputRafiq.checked = false;
        formError.textContent = "";
      }
      btnBatal.addEventListener("click", resetForm);

      btnSubmit.addEventListener("click", async () => {
        formError.textContent = "";
        if (!inputNama.value.trim()) { formError.textContent = "Nama barber tidak boleh kosong."; return; }
        btnSubmit.disabled = true;
        try {
          if (editingId) {
            await MugenApi.put(`/api/pengaturan/barber/${editingId}`, { nama: inputNama.value.trim(), is_rafiq: inputRafiq.checked });
            MugenUI.toast("Barber diperbarui.", "success");
          } else {
            await MugenApi.post("/api/pengaturan/barber", { nama: inputNama.value.trim(), is_rafiq: inputRafiq.checked });
            MugenUI.toast("Barber ditambahkan.", "success");
          }
          resetForm();
          loadList();
        } catch (e) {
          formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        } finally {
          btnSubmit.disabled = false;
        }
      });

      listCard.appendChild(MugenUI.el("h2", {}, "Daftar Barber"));
      const listBody = MugenUI.el("div");
      listCard.appendChild(listBody);

      async function loadList() {
        listBody.innerHTML = "Memuat...";
        try {
          const rows = await MugenApi.get("/api/pengaturan/barber");
          listBody.innerHTML = "";
          listBody.appendChild(MugenUI.buildTable(
            [
              { key: "nama", label: "Nama" },
              { key: "is_rafiq", label: "Rafiq", format: (v) => v ? "Ya" : "-" },
              { key: "aktif", label: "Status", format: (v) => MugenUI.el("span", { class: "badge" + (v ? "" : " badge-libur") }, v ? "Aktif" : "Nonaktif") },
              {
                key: "aksi", label: "Aksi", format: (_, r) => {
                  const wrap = MugenUI.el("div", { class: "actions-cell" });
                  const btnEdit = MugenUI.el("button", {}, "Edit");
                  btnEdit.addEventListener("click", () => {
                    editingId = r.id;
                    formTitle.textContent = `Edit Barber #${r.id}`;
                    btnSubmit.textContent = "Simpan Perubahan";
                    btnBatal.style.display = "";
                    inputNama.value = r.nama;
                    inputRafiq.checked = !!r.is_rafiq;
                    formError.textContent = "";
                    formCard.scrollIntoView({ behavior: "smooth" });
                  });
                  const btnToggle = MugenUI.el("button", {}, r.aktif ? "Nonaktifkan" : "Aktifkan");
                  btnToggle.addEventListener("click", async () => {
                    try {
                      await MugenApi.put(`/api/pengaturan/barber/${r.id}`, { aktif: !r.aktif });
                      MugenUI.toast(r.aktif ? "Barber dinonaktifkan." : "Barber diaktifkan.", "success");
                      loadList();
                    } catch (e) { MugenUI.toast(e.message, "error"); }
                  });
                  const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                  btnHapus.addEventListener("click", async () => {
                    if (!confirm(`Hapus barber "${r.nama}"? Hanya bisa dihapus kalau belum ada transaksi.`)) return;
                    try {
                      await MugenApi.del(`/api/pengaturan/barber/${r.id}`);
                      MugenUI.toast("Barber dihapus.", "success");
                      loadList();
                    } catch (e) {
                      MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                    }
                  });
                  wrap.appendChild(btnEdit);
                  wrap.appendChild(btnToggle);
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
      loadList();
    }

    // ================= TAB: LAYANAN =================
    async function renderLayanan() {
      const formCard = MugenUI.el("div", { class: "card" });
      const listCard = MugenUI.el("div", { class: "card" });
      body.appendChild(formCard);
      body.appendChild(listCard);

      let editingId = null;
      const formTitle = MugenUI.el("h2", {}, "Tambah Layanan");
      formCard.appendChild(formTitle);
      const inputNama = MugenUI.el("input", { type: "text", placeholder: "Nama layanan" });
      const inputHarga = MugenUI.el("input", { type: "number", min: "0", value: "0" });
      const inputModal = MugenUI.el("input", { type: "number", min: "0", value: "0" });
      const selChemical = MugenUI.el("select");
      selChemical.appendChild(MugenUI.el("option", { value: "auto" }, "Otomatis (berdasarkan nama layanan)"));
      selChemical.appendChild(MugenUI.el("option", { value: "ya" }, "Ya, pakai potongan modal chemical"));
      selChemical.appendChild(MugenUI.el("option", { value: "tidak" }, "Tidak"));
      const btnSubmit = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
      const btnBatal = MugenUI.el("button", { style: "display:none;" }, "Batal Edit");
      const formError = MugenUI.el("div", { class: "login-error" });

      formCard.appendChild(MugenUI.el("label", {}, "Nama Layanan"));
      formCard.appendChild(inputNama);
      formCard.appendChild(MugenUI.el("label", {}, "Harga (Rp)"));
      formCard.appendChild(inputHarga);
      formCard.appendChild(MugenUI.el("label", {}, "Modal (Rp)"));
      formCard.appendChild(inputModal);
      formCard.appendChild(MugenUI.el("label", {}, "Potongan Modal Chemical"));
      formCard.appendChild(selChemical);
      formCard.appendChild(formError);
      formCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnSubmit, btnBatal]));

      function resetForm() {
        editingId = null;
        formTitle.textContent = "Tambah Layanan";
        btnSubmit.textContent = "Simpan";
        btnBatal.style.display = "none";
        inputNama.value = "";
        inputHarga.value = "0";
        inputModal.value = "0";
        selChemical.value = "auto";
        formError.textContent = "";
      }
      btnBatal.addEventListener("click", resetForm);

      btnSubmit.addEventListener("click", async () => {
        formError.textContent = "";
        if (!inputNama.value.trim()) { formError.textContent = "Nama layanan tidak boleh kosong."; return; }
        const harga = Number(inputHarga.value);
        const modal = Number(inputModal.value);
        if (Number.isNaN(harga) || harga < 0) { formError.textContent = "Harga tidak valid."; return; }
        if (Number.isNaN(modal) || modal < 0) { formError.textContent = "Modal tidak valid."; return; }
        const pakai = selChemical.value === "auto" ? null : selChemical.value === "ya";
        btnSubmit.disabled = true;
        try {
          const body2 = { nama: inputNama.value.trim(), harga, modal, pakai_potongan_chemical: pakai };
          if (editingId) {
            await MugenApi.put(`/api/pengaturan/service/${editingId}`, body2);
            MugenUI.toast("Layanan diperbarui.", "success");
          } else {
            await MugenApi.post("/api/pengaturan/service", body2);
            MugenUI.toast("Layanan ditambahkan.", "success");
          }
          resetForm();
          loadList();
        } catch (e) {
          formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        } finally {
          btnSubmit.disabled = false;
        }
      });

      listCard.appendChild(MugenUI.el("h2", {}, "Daftar Layanan"));
      const listBody = MugenUI.el("div");
      listCard.appendChild(listBody);

      async function loadList() {
        listBody.innerHTML = "Memuat...";
        try {
          const rows = await MugenApi.get("/api/pengaturan/service");
          listBody.innerHTML = "";
          listBody.appendChild(MugenUI.buildTable(
            [
              { key: "nama", label: "Nama" },
              { key: "harga", label: "Harga", format: MugenUI.formatRupiah },
              { key: "modal", label: "Modal", format: MugenUI.formatRupiah },
              { key: "pakai_potongan_chemical", label: "Potongan Chemical", format: (v) => v ? "Ya" : "Tidak" },
              { key: "aktif", label: "Status", format: (v) => MugenUI.el("span", { class: "badge" + (v ? "" : " badge-libur") }, v ? "Aktif" : "Nonaktif") },
              {
                key: "aksi", label: "Aksi", format: (_, r) => {
                  const wrap = MugenUI.el("div", { class: "actions-cell" });
                  const btnEdit = MugenUI.el("button", {}, "Edit");
                  btnEdit.addEventListener("click", () => {
                    editingId = r.id;
                    formTitle.textContent = `Edit Layanan #${r.id}`;
                    btnSubmit.textContent = "Simpan Perubahan";
                    btnBatal.style.display = "";
                    inputNama.value = r.nama;
                    inputHarga.value = String(r.harga);
                    inputModal.value = String(r.modal || 0);
                    selChemical.value = r.pakai_potongan_chemical ? "ya" : "tidak";
                    formError.textContent = "";
                    formCard.scrollIntoView({ behavior: "smooth" });
                  });
                  const btnToggle = MugenUI.el("button", {}, r.aktif ? "Nonaktifkan" : "Aktifkan");
                  btnToggle.addEventListener("click", async () => {
                    try {
                      await MugenApi.put(`/api/pengaturan/service/${r.id}`, { aktif: !r.aktif });
                      MugenUI.toast(r.aktif ? "Layanan dinonaktifkan." : "Layanan diaktifkan.", "success");
                      loadList();
                    } catch (e) { MugenUI.toast(e.message, "error"); }
                  });
                  const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                  btnHapus.addEventListener("click", async () => {
                    if (!confirm(`Hapus layanan "${r.nama}"? Hanya bisa dihapus kalau belum pernah dipakai transaksi.`)) return;
                    try {
                      await MugenApi.del(`/api/pengaturan/service/${r.id}`);
                      MugenUI.toast("Layanan dihapus.", "success");
                      loadList();
                    } catch (e) {
                      MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                    }
                  });
                  wrap.appendChild(btnEdit);
                  wrap.appendChild(btnToggle);
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
      loadList();
    }

    // ================= TAB: USER =================
    async function renderUser() {
      const formCard = MugenUI.el("div", { class: "card" });
      const listCard = MugenUI.el("div", { class: "card" });
      body.appendChild(formCard);
      body.appendChild(listCard);

      let barbers = [];
      try { barbers = await MugenApi.get("/api/input-data/barbers", { useCache: true }); } catch (e) { /* opsional */ }

      formCard.appendChild(MugenUI.el("h2", {}, "Tambah User"));
      const inputUsername = MugenUI.el("input", { type: "text", placeholder: "Username" });
      const inputPassword = MugenUI.el("input", { type: "password", placeholder: "Password (min. 4 karakter)" });
      const selRole = MugenUI.el("select");
      selRole.appendChild(MugenUI.el("option", { value: "admin" }, "Admin"));
      selRole.appendChild(MugenUI.el("option", { value: "barber" }, "Barber"));
      const selBarberAkun = MugenUI.el("select", { style: "display:none;" });
      selBarberAkun.appendChild(MugenUI.el("option", { value: "" }, "-- pilih barber --"));
      for (const b of barbers) selBarberAkun.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
      selRole.addEventListener("change", () => { selBarberAkun.style.display = selRole.value === "barber" ? "" : "none"; });

      const btnSubmit = MugenUI.el("button", { class: "btn-primary" }, "Tambah User");
      const formError = MugenUI.el("div", { class: "login-error" });

      formCard.appendChild(MugenUI.el("label", {}, "Username"));
      formCard.appendChild(inputUsername);
      formCard.appendChild(MugenUI.el("label", {}, "Password"));
      formCard.appendChild(inputPassword);
      formCard.appendChild(MugenUI.el("label", {}, "Role"));
      formCard.appendChild(selRole);
      formCard.appendChild(MugenUI.el("label", {}, "Terhubung ke Barber (khusus role Barber)"));
      formCard.appendChild(selBarberAkun);
      formCard.appendChild(formError);
      formCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSubmit));

      btnSubmit.addEventListener("click", async () => {
        formError.textContent = "";
        if (!inputUsername.value.trim()) { formError.textContent = "Username tidak boleh kosong."; return; }
        if (!inputPassword.value || inputPassword.value.length < 4) { formError.textContent = "Password minimal 4 karakter."; return; }
        if (selRole.value === "barber" && !selBarberAkun.value) { formError.textContent = "Pilih barber untuk dikaitkan ke akun ini."; return; }
        btnSubmit.disabled = true;
        try {
          await MugenApi.post("/api/pengaturan/user", {
            username: inputUsername.value.trim(),
            password: inputPassword.value,
            role: selRole.value,
            barber_id: selRole.value === "barber" ? Number(selBarberAkun.value) : null,
          });
          MugenUI.toast("User ditambahkan.", "success");
          inputUsername.value = ""; inputPassword.value = ""; selRole.value = "admin"; selBarberAkun.style.display = "none";
          loadList();
        } catch (e) {
          formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        } finally {
          btnSubmit.disabled = false;
        }
      });

      listCard.appendChild(MugenUI.el("h2", {}, "Daftar User"));
      const listBody = MugenUI.el("div");
      listCard.appendChild(listBody);

      async function loadList() {
        listBody.innerHTML = "Memuat...";
        try {
          const rows = await MugenApi.get("/api/pengaturan/user");
          listBody.innerHTML = "";
          listBody.appendChild(MugenUI.buildTable(
            [
              { key: "username", label: "Username" },
              { key: "role", label: "Role", format: (v) => v === "admin" ? "Admin" : "Barber" },
              { key: "aktif", label: "Status", format: (v) => MugenUI.el("span", { class: "badge" + (v ? "" : " badge-libur") }, v ? "Aktif" : "Nonaktif") },
              {
                key: "aksi", label: "Aksi", format: (_, r) => {
                  const wrap = MugenUI.el("div", { class: "actions-cell" });
                  const btnUsername = MugenUI.el("button", {}, "Ganti Username");
                  btnUsername.addEventListener("click", async () => {
                    const baru = prompt(`Username baru untuk "${r.username}":`, r.username);
                    if (!baru || !baru.trim() || baru.trim() === r.username) return;
                    try {
                      await MugenApi.put(`/api/pengaturan/user/${r.id}/username`, { username: baru.trim() });
                      MugenUI.toast("Username diperbarui.", "success");
                      loadList();
                    } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                  });
                  const btnPassword = MugenUI.el("button", {}, "Ganti Password");
                  btnPassword.addEventListener("click", async () => {
                    const baru = prompt(`Password baru untuk "${r.username}" (min. 4 karakter):`);
                    if (!baru) return;
                    try {
                      await MugenApi.put(`/api/pengaturan/user/${r.id}/password`, { password: baru });
                      MugenUI.toast("Password diperbarui.", "success");
                    } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                  });
                  const btnToggle = MugenUI.el("button", {}, r.aktif ? "Nonaktifkan" : "Aktifkan");
                  btnToggle.addEventListener("click", async () => {
                    try {
                      await MugenApi.put(`/api/pengaturan/user/${r.id}/${r.aktif ? "nonaktifkan" : "aktifkan"}`, {});
                      MugenUI.toast(r.aktif ? "User dinonaktifkan." : "User diaktifkan.", "success");
                      loadList();
                    } catch (e) { MugenUI.toast(e.message, "error"); }
                  });
                  wrap.appendChild(btnUsername);
                  wrap.appendChild(btnPassword);
                  wrap.appendChild(btnToggle);
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
      loadList();
    }

    // ================= TAB: BACKUP =================
    async function renderBackup() {
      const card = MugenUI.el("div", { class: "card" });
      body.appendChild(card);
      card.appendChild(MugenUI.el("h2", {}, "Export Database"));
      card.appendChild(MugenUI.el("div", { class: "subtitle" }, "Unduh salinan file database saat ini (.db)."));
      const btnExport = MugenUI.el("button", { class: "btn-primary" }, "Export Database");
      card.appendChild(MugenUI.el("div", { style: "margin:12px 0 24px;" }, btnExport));

      btnExport.addEventListener("click", async () => {
        btnExport.disabled = true;
        try {
          const token = MugenState.getToken();
          const res = await fetch(MUGEN_API_BASE + "/api/pengaturan/backup/export", {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
          });
          if (!res.ok) throw new Error("Gagal mengunduh backup.");
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `mugen_hair_backup_${new Date().toISOString().slice(0, 10)}.db`;
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(url);
          MugenUI.toast("Backup berhasil diunduh.", "success");
        } catch (e) {
          MugenUI.toast(e.message, "error");
        } finally {
          btnExport.disabled = false;
        }
      });

      card.appendChild(MugenUI.el("h2", {}, "Import Database"));
      card.appendChild(MugenUI.el("div", { class: "subtitle" },
        "PERHATIAN: ini akan MENGGANTI seluruh data yang sedang berjalan dengan isi file yang diupload. Database yang sedang aktif otomatis di-backup dulu sebelum diganti, tapi tetap lakukan ini dengan hati-hati."));
      const inputImport = MugenUI.el("input", { type: "file", accept: ".db" });
      const btnImport = MugenUI.el("button", { class: "btn-danger" }, "Import & Ganti Database");
      const importError = MugenUI.el("div", { class: "login-error" });
      card.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin:12px 0;" }, [inputImport, btnImport]));
      card.appendChild(importError);

      btnImport.addEventListener("click", async () => {
        importError.textContent = "";
        if (!inputImport.files || !inputImport.files[0]) { importError.textContent = "Pilih file .db dulu."; return; }
        if (!confirm("Yakin ingin mengganti seluruh database yang sedang berjalan dengan file ini? Tindakan ini tidak mudah dibatalkan.")) return;
        btnImport.disabled = true;
        try {
          await MugenApi.uploadFile("/api/pengaturan/backup/import", inputImport.files[0]);
          MugenUI.toast("Database berhasil diganti. Memuat ulang halaman...", "success");
          setTimeout(() => location.reload(), 1500);
        } catch (e) {
          importError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        } finally {
          btnImport.disabled = false;
        }
      });
    }

    renderTabs();
    renderBody();
  }

  return { render };
})();
