// pages/pengaturan.js — TAHAP 10: menu Setting. KHUSUS admin (dijaga di
// router.js + backend require_admin di setiap endpoint /api/pengaturan/*).
// Mengikuti pola tab seperti pages/rekap.js.

const PagePengaturan = (() => {
  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Setting"));

    const tabs = ["Identitas Barbershop", "Komisi & Bonus", "Bonus Service", "Uang Harian", "Barber", "Layanan", "User", "Backup"];
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
      else if (activeTab === "Bonus Service") await renderAcuanService("Bonus Service", "/api/pengaturan/bonus-service-acuan",
        "Pilih service mana saja yang jadi acuan Target Bonus Service (tier bulanan, diatur di tab Komisi & Bonus). Pengaturan ini TERPISAH dari Uang Harian -- mengubah salah satu tidak memengaruhi yang lain.");
      else if (activeTab === "Uang Harian") await renderAcuanService("Uang Harian", "/api/pengaturan/uang-harian-acuan",
        "Pilih service mana saja yang jadi acuan syarat cair Uang Harian (cair kalau total service acuan ini pada satu hari yang sama mencapai minimal 3). Pengaturan ini TERPISAH dari Bonus Service -- mengubah salah satu tidak memengaruhi yang lain.");
      else if (activeTab === "Barber") await renderBarber();
      else if (activeTab === "Layanan") await renderLayanan();
      else if (activeTab === "User") await renderUser();
      else await renderBackup();
    }

    // ================= TAB: BONUS SERVICE / UANG HARIAN (acuan service) =================
    // REVISI: dua pengaturan independen menggantikan hardcode lama (Dry Cut +
    // Cut & Wash) -- SATU fungsi dipakai untuk kedua tab karena bentuknya
    // identik (checklist seluruh service + tombol Simpan), hanya endpoint &
    // teks penjelasannya beda.
    async function renderAcuanService(judul, endpoint, penjelasan) {
      const card = MugenUI.el("div", { class: "card" });
      body.appendChild(card);
      card.appendChild(MugenUI.el("h2", {}, judul));
      card.appendChild(MugenUI.el("div", { class: "subtitle" }, penjelasan));

      let services, acuan;
      try {
        [services, acuan] = await Promise.all([
          MugenApi.get("/api/pengaturan/service"),
          MugenApi.get(endpoint),
        ]);
      } catch (e) {
        card.appendChild(MugenUI.el("div", {}, e.message));
        return;
      }

      const idAktif = new Set(acuan.service_ids || []);
      const checkboxes = {};
      const listBox = MugenUI.el("div", { class: "checklist-service" });
      for (const s of services) {
        const cb = MugenUI.el("input", { type: "checkbox", style: "width:auto;" });
        cb.checked = idAktif.has(s.id);
        checkboxes[s.id] = cb;
        listBox.appendChild(MugenUI.el("label", { style: "display:flex;align-items:center;gap:8px;" },
          [cb, s.nama + (s.aktif ? "" : " (nonaktif)")]));
      }
      card.appendChild(listBox);

      const errorBox = MugenUI.el("div", { class: "login-error" });
      const btnSimpan = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
      card.appendChild(errorBox);
      card.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpan));

      btnSimpan.addEventListener("click", async () => {
        errorBox.textContent = "";
        const service_ids = Object.entries(checkboxes).filter(([, cb]) => cb.checked).map(([id]) => Number(id));
        try {
          await MugenUI.withLoading(() => MugenApi.put(endpoint, { service_ids }));
          MugenUI.toast(`Pengaturan ${judul} disimpan.`, "success");
        } catch (e) {
          errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        }
      });
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
          const hasil = await MugenUI.withLoading(() => MugenApi.uploadFile("/api/pengaturan/logo", inputLogo.files[0]));
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

      const bannerPreview = MugenUI.el("img", { class: "book-banner-img", style: data.banner_url ? "max-width:320px;" : "display:none;", alt: "Banner saat ini" });
      if (data.banner_url) bannerPreview.src = MUGEN_API_BASE + data.banner_url;
      const inputBanner = MugenUI.el("input", { type: "file", accept: "image/jpeg,image/png,image/webp" });
      const btnUploadBanner = MugenUI.el("button", {}, "Upload Banner Baru");
      const bannerError = MugenUI.el("div", { class: "login-error" });

      btnUploadBanner.addEventListener("click", async () => {
        if (!inputBanner.files || !inputBanner.files[0]) { bannerError.textContent = "Pilih file banner dulu (JPG/PNG/WEBP)."; return; }
        bannerError.textContent = "";
        btnUploadBanner.disabled = true;
        try {
          const hasil = await MugenUI.withLoading(() => MugenApi.uploadFile("/api/pengaturan/banner", inputBanner.files[0]));
          bannerPreview.src = MUGEN_API_BASE + hasil.banner_url + "&t=" + Date.now();
          bannerPreview.style.cssText = "max-width:320px;";
          MugenUI.toast("Banner berhasil diganti.", "success");
          MugenBrand.refresh();
        } catch (e) {
          bannerError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        } finally {
          btnUploadBanner.disabled = false;
        }
      });

      card.appendChild(MugenUI.el("label", {}, "Banner Booking (JPG/PNG/WEBP, tampil di atas halaman booking)"));
      card.appendChild(bannerPreview);
      card.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin:8px 0;" }, [inputBanner, btnUploadBanner]));
      card.appendChild(bannerError);

      const inputNama = MugenUI.el("input", { type: "text", value: data.nama_barbershop || "" });
      const inputTagline = MugenUI.el("input", { type: "text", value: data.tagline || "", placeholder: "mis. Sharp Cuts, Sharp Look" });
      const inputDeskripsi = MugenUI.el("textarea", {}, data.deskripsi || "");
      const inputAlamat = MugenUI.el("input", { type: "text", value: data.alamat || "" });
      const inputWA = MugenUI.el("input", { type: "text", value: data.whatsapp || "" });
      const inputEmail = MugenUI.el("input", { type: "text", value: data.email || "" });
      const inputIG = MugenUI.el("input", { type: "text", value: data.instagram || "" });
      const inputWebsite = MugenUI.el("input", { type: "text", value: data.website || "" });
      const inputJam = MugenUI.el("input", { type: "text", value: data.jam_operasional || "", placeholder: "mis. 09:00 - 21:00" });
      const btnSimpan = MugenUI.el("button", { class: "btn-primary" }, "Simpan Identitas");
      const formError = MugenUI.el("div", { class: "login-error" });

      card.appendChild(MugenUI.el("label", {}, "Nama Barbershop"));
      card.appendChild(inputNama);
      card.appendChild(MugenUI.el("label", {}, "Tagline"));
      card.appendChild(inputTagline);
      card.appendChild(MugenUI.el("label", {}, "Deskripsi"));
      card.appendChild(inputDeskripsi);
      card.appendChild(MugenUI.el("label", {}, "Alamat"));
      card.appendChild(inputAlamat);
      card.appendChild(MugenUI.el("label", {}, "Nomor WhatsApp"));
      card.appendChild(inputWA);
      card.appendChild(MugenUI.el("label", {}, "Email"));
      card.appendChild(inputEmail);
      card.appendChild(MugenUI.el("label", {}, "Instagram"));
      card.appendChild(inputIG);
      card.appendChild(MugenUI.el("label", {}, "Website"));
      card.appendChild(inputWebsite);
      card.appendChild(MugenUI.el("label", {}, "Jam Operasional"));
      card.appendChild(inputJam);
      card.appendChild(formError);
      card.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpan));

      btnSimpan.addEventListener("click", async () => {
        formError.textContent = "";
        if (!inputNama.value.trim()) { formError.textContent = "Nama Barbershop tidak boleh kosong."; return; }
        btnSimpan.disabled = true;
        try {
          await MugenUI.withLoading(() => MugenApi.put("/api/pengaturan/identitas", {
            nama_barbershop: inputNama.value.trim(),
            tagline: inputTagline.value.trim(),
            deskripsi: inputDeskripsi.value.trim(),
            alamat: inputAlamat.value.trim(),
            whatsapp: inputWA.value.trim(),
            email: inputEmail.value.trim(),
            instagram: inputIG.value.trim(),
            website: inputWebsite.value.trim(),
            jam_operasional: inputJam.value.trim(),
          }));
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
    // REVISI: Uang Harian dipindah jadi per-barber (lihat tab Barber di
    // bawah), Bonus Kehadiran dihapus total, dan Target Bonus Customer
    // sekarang bertingkat (banyak tier, dikelola terpisah lewat
    // /api/pengaturan/bonus-tiers) -- bukan lagi satu target/nominal saja.
    async function renderKomisi() {
      const card = MugenUI.el("div", { class: "card" });
      body.appendChild(card);
      card.appendChild(MugenUI.el("h2", {}, "Pengaturan Komisi"));
      card.appendChild(MugenUI.el("div", { class: "subtitle" },
        "Nilai ini langsung dipakai oleh rumus komisi/bonus yang sudah berjalan — tidak ada perubahan rumus, hanya nilainya jadi bisa diubah tanpa edit kode."));

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
          maksimal_hari_libur_bonus_customer: Number(inMaksLiburBonus.value),
          potongan_bonus_customer_persen: Number(inPotonganBonus.value),
        };
        for (const [k, v] of Object.entries(body2)) {
          if (Number.isNaN(v) || v < 0) { formError.textContent = `Nilai untuk "${k}" tidak valid (harus angka >= 0).`; return; }
        }
        btnSimpan.disabled = true;
        try {
          await MugenUI.withLoading(() => MugenApi.put("/api/pengaturan/komisi", body2));
          MugenUI.toast("Pengaturan komisi & bonus disimpan.", "success");
        } catch (e) {
          formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        } finally {
          btnSimpan.disabled = false;
        }
      });

      // ================= TARGET BONUS SERVICE (tier bertingkat) =================
      const tierCard = MugenUI.el("div", { class: "card" });
      body.appendChild(tierCard);
      tierCard.appendChild(MugenUI.el("h2", {}, "Target Bonus Service"));
      tierCard.appendChild(MugenUI.el("div", { class: "subtitle" },
        "Dihitung dari jumlah service Dry Cut + Cut & Wash per barber per bulan. Tambah tier sebanyak yang " +
        "dibutuhkan (mis. 100 service → Rp100.000, 115 service → Rp150.000, dst) — barber dapat bonus dari " +
        "tier TERTINGGI yang tercapai bulan itu."));

      const tierListBody = MugenUI.el("div");
      tierCard.appendChild(tierListBody);

      let editingTarget = null; // null = mode Tambah, angka = mode Edit (target lama)
      const tierFormTitle = MugenUI.el("h2", { style: "margin-top:20px;" }, "Tambah Tier");
      const inTierTarget = MugenUI.el("input", { type: "number", min: "1", placeholder: "Jumlah service" });
      const inTierBonus = MugenUI.el("input", { type: "number", min: "0", placeholder: "Nominal bonus (Rp)" });
      const btnTierSimpan = MugenUI.el("button", { class: "btn-primary" }, "Tambah Tier");
      const btnTierBatal = MugenUI.el("button", { style: "display:none;" }, "Batal Edit");
      const tierFormError = MugenUI.el("div", { class: "login-error" });
      tierCard.appendChild(tierFormTitle);
      tierCard.appendChild(MugenUI.el("label", {}, "Target (jumlah service)"));
      tierCard.appendChild(inTierTarget);
      tierCard.appendChild(MugenUI.el("label", {}, "Nominal Bonus (Rp)"));
      tierCard.appendChild(inTierBonus);
      tierCard.appendChild(tierFormError);
      tierCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnTierSimpan, btnTierBatal]));

      function resetTierForm() {
        editingTarget = null;
        tierFormTitle.textContent = "Tambah Tier";
        btnTierSimpan.textContent = "Tambah Tier";
        btnTierBatal.style.display = "none";
        inTierTarget.value = "";
        inTierBonus.value = "";
        tierFormError.textContent = "";
      }
      btnTierBatal.addEventListener("click", resetTierForm);

      async function loadTiers() {
        tierListBody.innerHTML = "Memuat...";
        try {
          const tiers = await MugenApi.get("/api/pengaturan/bonus-tiers");
          tierListBody.innerHTML = "";
          tierListBody.appendChild(MugenUI.buildTable(
            [
              { key: "target", label: "Target (service)" },
              { key: "bonus", label: "Nominal Bonus", format: MugenUI.formatRupiah },
              {
                key: "aksi", label: "Aksi", format: (_, tier) => {
                  const wrap = MugenUI.el("div", { class: "actions-cell" });
                  const btnEdit = MugenUI.el("button", {}, "Edit");
                  btnEdit.addEventListener("click", () => {
                    editingTarget = tier.target;
                    tierFormTitle.textContent = `Edit Tier — ${tier.target} service`;
                    btnTierSimpan.textContent = "Simpan Perubahan";
                    btnTierBatal.style.display = "";
                    inTierTarget.value = String(tier.target);
                    inTierBonus.value = String(tier.bonus);
                    tierFormError.textContent = "";
                    tierCard.scrollIntoView({ behavior: "smooth" });
                  });
                  const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                  btnHapus.addEventListener("click", async () => {
                    if (!confirm(`Hapus tier ${tier.target} service?`)) return;
                    try {
                      await MugenUI.withLoading(() => MugenApi.del(`/api/pengaturan/bonus-tiers/${tier.target}`));
                      MugenUI.toast("Tier dihapus.", "success");
                      loadTiers();
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
            tiers,
            { emptyText: "Belum ada target bonus diatur." },
          ));
        } catch (e) {
          tierListBody.innerHTML = "";
          tierListBody.appendChild(MugenUI.el("div", {}, e.message));
        }
      }

      btnTierSimpan.addEventListener("click", async () => {
        tierFormError.textContent = "";
        const target = Number(inTierTarget.value);
        const bonusNilai = Number(inTierBonus.value);
        if (!target || target <= 0) { tierFormError.textContent = "Target service harus lebih dari 0."; return; }
        if (Number.isNaN(bonusNilai) || bonusNilai < 0) { tierFormError.textContent = "Nominal bonus tidak valid."; return; }
        btnTierSimpan.disabled = true;
        try {
          await MugenUI.withLoading(async () => {
            if (editingTarget !== null) {
              await MugenApi.put(`/api/pengaturan/bonus-tiers/${editingTarget}`, { target, bonus: bonusNilai });
              MugenUI.toast("Tier diperbarui.", "success");
            } else {
              await MugenApi.post("/api/pengaturan/bonus-tiers", { target, bonus: bonusNilai });
              MugenUI.toast("Tier ditambahkan.", "success");
            }
          });
          resetTierForm();
          loadTiers();
        } catch (e) {
          tierFormError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        } finally {
          btnTierSimpan.disabled = false;
        }
      });

      loadTiers();
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
      // REVISI: Uang Harian sekarang per-barber (sebelumnya dua setting global
      // uang_harian_barber/uang_harian_rafiq dipilih dari status RAFIQ).
      const inputUangHarian = MugenUI.el("input", { type: "number", min: "0", value: "0" });
      const btnSubmit = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
      const btnBatal = MugenUI.el("button", { style: "display:none;" }, "Batal Edit");
      const formError = MugenUI.el("div", { class: "login-error" });

      formCard.appendChild(MugenUI.el("label", {}, "Nama Barber"));
      formCard.appendChild(inputNama);
      formCard.appendChild(MugenUI.el("label", {}, "Uang Harian (Rp/hari, cair kalau Dry Cut + Cut & Wash hari itu ≥ 3)"));
      formCard.appendChild(inputUangHarian);
      formCard.appendChild(formError);
      formCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnSubmit, btnBatal]));

      function resetForm() {
        editingId = null;
        formTitle.textContent = "Tambah Barber";
        btnSubmit.textContent = "Simpan";
        btnBatal.style.display = "none";
        inputNama.value = "";
        inputUangHarian.value = "0";
        formError.textContent = "";
      }
      btnBatal.addEventListener("click", resetForm);

      btnSubmit.addEventListener("click", async () => {
        formError.textContent = "";
        if (!inputNama.value.trim()) { formError.textContent = "Nama barber tidak boleh kosong."; return; }
        const uangHarian = Number(inputUangHarian.value);
        if (Number.isNaN(uangHarian) || uangHarian < 0) { formError.textContent = "Uang harian tidak valid."; return; }
        btnSubmit.disabled = true;
        try {
          // REVISI UI/UX: field is_rafiq SENGAJA tidak dikirim lagi dari form
          // ini (label RAFIQ dihapus dari tampilan) -- backend tetap
          // menyimpan nilai is_rafiq yang sudah ada tanpa berubah (endpoint
          // PUT memperlakukan field yang tidak dikirim sebagai "jangan
          // diubah", endpoint POST default-nya False untuk barber baru),
          // jadi data/logika lama tidak tersentuh sama sekali.
          const body2 = { nama: inputNama.value.trim(), uang_harian: uangHarian };
          await MugenUI.withLoading(async () => {
            if (editingId) {
              await MugenApi.put(`/api/pengaturan/barber/${editingId}`, body2);
              MugenUI.toast("Barber diperbarui.", "success");
            } else {
              await MugenApi.post("/api/pengaturan/barber", body2);
              MugenUI.toast("Barber ditambahkan.", "success");
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

      listCard.appendChild(MugenUI.el("h2", {}, "Daftar Barber"));
      const listBody = MugenUI.el("div");
      listCard.appendChild(listBody);

      async function loadList() {
        listBody.innerHTML = "Memuat...";
        try {
          const rows = await MugenApi.get("/api/pengaturan/barber");
          rows.sort((a, b) => (a.urutan || 0) - (b.urutan || 0) || a.nama.localeCompare(b.nama));
          listBody.innerHTML = "";
          listBody.appendChild(MugenUI.buildTable(
            [
              {
                key: "foto_filename", label: "Foto", format: (v, r) => v
                  ? MugenUI.el("img", { src: MUGEN_API_BASE + `/api/public/booking/barber-foto/${r.id}` + `?v=${v}`, class: "book-barber-foto", style: "width:40px;height:40px;margin:0;" })
                  : MugenUI.el("div", { class: "book-barber-foto-kosong", style: "width:40px;height:40px;margin:0;font-size:14px;" }, r.nama.charAt(0).toUpperCase()),
              },
              { key: "nama", label: "Nama" },
              { key: "uang_harian", label: "Uang Harian", format: MugenUI.formatRupiah },
              { key: "aktif", label: "Status", format: (v) => MugenUI.el("span", { class: "badge" + (v ? "" : " badge-libur") }, v ? "Aktif" : "Nonaktif") },
              {
                key: "status_booking", label: "Status Booking", format: (v, r) => {
                  if (!r.aktif) return "-";
                  const sel = MugenUI.el("select", { style: "width:auto;" }, [
                    MugenUI.el("option", { value: "aktif" }, "Aktif"),
                    MugenUI.el("option", { value: "cuti" }, "On Vacation"),
                  ]);
                  sel.value = v || "aktif";
                  sel.addEventListener("change", async () => {
                    try {
                      await MugenUI.withLoading(() => MugenApi.put(`/api/booking/barber/${r.id}/status`, { status_booking: sel.value }));
                      MugenUI.toast("Status booking diperbarui.", "success");
                      loadList();
                    } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); sel.value = v || "aktif"; }
                  });
                  return sel;
                },
              },
              { key: "urutan", label: "Urutan" },
              {
                key: "aksi", label: "Aksi", format: (_, r, idx, allRows) => {
                  const wrap = MugenUI.el("div", { class: "actions-cell" });
                  const btnEdit = MugenUI.el("button", {}, "Edit");
                  btnEdit.addEventListener("click", () => {
                    editingId = r.id;
                    formTitle.textContent = `Edit Barber #${r.id}`;
                    btnSubmit.textContent = "Simpan Perubahan";
                    btnBatal.style.display = "";
                    inputNama.value = r.nama;
                    inputUangHarian.value = String(r.uang_harian || 0);
                    formError.textContent = "";
                    formCard.scrollIntoView({ behavior: "smooth" });
                  });
                  const btnToggle = MugenUI.el("button", {}, r.aktif ? "Nonaktifkan" : "Aktifkan");
                  btnToggle.addEventListener("click", async () => {
                    try {
                      await MugenUI.withLoading(() => MugenApi.put(`/api/pengaturan/barber/${r.id}`, { aktif: !r.aktif }));
                      MugenUI.toast(r.aktif ? "Barber dinonaktifkan." : "Barber diaktifkan.", "success");
                      loadList();
                    } catch (e) { MugenUI.toast(e.message, "error"); }
                  });
                  const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                  btnHapus.addEventListener("click", async () => {
                    if (!confirm(`Hapus barber "${r.nama}"? Hanya bisa dihapus kalau belum ada transaksi.`)) return;
                    try {
                      await MugenUI.withLoading(() => MugenApi.del(`/api/pengaturan/barber/${r.id}`));
                      MugenUI.toast("Barber dihapus.", "success");
                      loadList();
                    } catch (e) {
                      MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                    }
                  });
                  const idxInList = rows.findIndex((x) => x.id === r.id);
                  const btnNaik = MugenUI.el("button", { title: "Naikkan urutan" }, "↑");
                  btnNaik.disabled = idxInList <= 0;
                  btnNaik.addEventListener("click", async () => {
                    const other = rows[idxInList - 1];
                    try {
                      await MugenUI.withLoading(async () => {
                        await MugenApi.put(`/api/booking/barber/${r.id}/urutan`, { urutan: other.urutan || 0 });
                        await MugenApi.put(`/api/booking/barber/${other.id}/urutan`, { urutan: r.urutan || 0 });
                      });
                      loadList();
                    } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                  });
                  const btnTurun = MugenUI.el("button", { title: "Turunkan urutan" }, "↓");
                  btnTurun.disabled = idxInList >= rows.length - 1;
                  btnTurun.addEventListener("click", async () => {
                    const other = rows[idxInList + 1];
                    try {
                      await MugenUI.withLoading(async () => {
                        await MugenApi.put(`/api/booking/barber/${r.id}/urutan`, { urutan: other.urutan || 0 });
                        await MugenApi.put(`/api/booking/barber/${other.id}/urutan`, { urutan: r.urutan || 0 });
                      });
                      loadList();
                    } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                  });
                  const inFoto = MugenUI.el("input", { type: "file", accept: "image/jpeg,image/png,image/webp", style: "display:none;" });
                  const btnFoto = MugenUI.el("button", {}, "Foto");
                  btnFoto.addEventListener("click", () => inFoto.click());
                  inFoto.addEventListener("change", async () => {
                    if (!inFoto.files || !inFoto.files[0]) return;
                    try {
                      await MugenUI.withLoading(() => MugenApi.uploadFile(`/api/booking/barber/${r.id}/foto`, inFoto.files[0]));
                      MugenUI.toast("Foto barber disimpan.", "success");
                      loadList();
                    } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                  });
                  wrap.appendChild(btnEdit);
                  wrap.appendChild(btnToggle);
                  wrap.appendChild(btnFoto);
                  wrap.appendChild(inFoto);
                  wrap.appendChild(btnNaik);
                  wrap.appendChild(btnTurun);
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
          await MugenUI.withLoading(async () => {
            if (editingId) {
              await MugenApi.put(`/api/pengaturan/service/${editingId}`, body2);
              MugenUI.toast("Layanan diperbarui.", "success");
            } else {
              await MugenApi.post("/api/pengaturan/service", body2);
              MugenUI.toast("Layanan ditambahkan.", "success");
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

      listCard.appendChild(MugenUI.el("h2", {}, "Daftar Layanan"));
      const listBody = MugenUI.el("div");
      listCard.appendChild(listBody);

      async function loadList() {
        listBody.innerHTML = "Memuat...";
        try {
          const rows = await MugenApi.get("/api/pengaturan/service");
          rows.sort((a, b) => (a.urutan || 0) - (b.urutan || 0) || a.nama.localeCompare(b.nama));
          listBody.innerHTML = "";
          listBody.appendChild(MugenUI.buildTable(
            [
              { key: "nama", label: "Nama" },
              { key: "harga", label: "Harga", format: MugenUI.formatRupiah },
              { key: "modal", label: "Modal", format: MugenUI.formatRupiah },
              { key: "pakai_potongan_chemical", label: "Potongan Chemical", format: (v) => v ? "Ya" : "Tidak" },
              { key: "aktif", label: "Status", format: (v) => MugenUI.el("span", { class: "badge" + (v ? "" : " badge-libur") }, v ? "Aktif" : "Nonaktif") },
              { key: "urutan", label: "Urutan" },
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
                      await MugenUI.withLoading(() => MugenApi.put(`/api/pengaturan/service/${r.id}`, { aktif: !r.aktif }));
                      MugenUI.toast(r.aktif ? "Layanan dinonaktifkan." : "Layanan diaktifkan.", "success");
                      loadList();
                    } catch (e) { MugenUI.toast(e.message, "error"); }
                  });
                  const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                  btnHapus.addEventListener("click", async () => {
                    if (!confirm(`Hapus layanan "${r.nama}"? Hanya bisa dihapus kalau belum pernah dipakai transaksi.`)) return;
                    try {
                      await MugenUI.withLoading(() => MugenApi.del(`/api/pengaturan/service/${r.id}`));
                      MugenUI.toast("Layanan dihapus.", "success");
                      loadList();
                    } catch (e) {
                      MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                    }
                  });
                  const idxInList = rows.findIndex((x) => x.id === r.id);
                  const btnNaik = MugenUI.el("button", { title: "Naikkan urutan" }, "↑");
                  btnNaik.disabled = idxInList <= 0;
                  btnNaik.addEventListener("click", async () => {
                    const other = rows[idxInList - 1];
                    try {
                      await MugenUI.withLoading(async () => {
                        await MugenApi.put(`/api/booking/service/${r.id}/urutan`, { urutan: other.urutan || 0 });
                        await MugenApi.put(`/api/booking/service/${other.id}/urutan`, { urutan: r.urutan || 0 });
                      });
                      loadList();
                    } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                  });
                  const btnTurun = MugenUI.el("button", { title: "Turunkan urutan" }, "↓");
                  btnTurun.disabled = idxInList >= rows.length - 1;
                  btnTurun.addEventListener("click", async () => {
                    const other = rows[idxInList + 1];
                    try {
                      await MugenUI.withLoading(async () => {
                        await MugenApi.put(`/api/booking/service/${r.id}/urutan`, { urutan: other.urutan || 0 });
                        await MugenApi.put(`/api/booking/service/${other.id}/urutan`, { urutan: r.urutan || 0 });
                      });
                      loadList();
                    } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                  });
                  wrap.appendChild(btnEdit);
                  wrap.appendChild(btnToggle);
                  wrap.appendChild(btnNaik);
                  wrap.appendChild(btnTurun);
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
          await MugenUI.withLoading(() => MugenApi.post("/api/pengaturan/user", {
            username: inputUsername.value.trim(),
            password: inputPassword.value,
            role: selRole.value,
            barber_id: selRole.value === "barber" ? Number(selBarberAkun.value) : null,
          }));
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
                      await MugenUI.withLoading(() => MugenApi.put(`/api/pengaturan/user/${r.id}/username`, { username: baru.trim() }));
                      MugenUI.toast("Username diperbarui.", "success");
                      loadList();
                    } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                  });
                  const btnPassword = MugenUI.el("button", {}, "Ganti Password");
                  btnPassword.addEventListener("click", async () => {
                    const baru = prompt(`Password baru untuk "${r.username}" (min. 4 karakter):`);
                    if (!baru) return;
                    try {
                      await MugenUI.withLoading(() => MugenApi.put(`/api/pengaturan/user/${r.id}/password`, { password: baru }));
                      MugenUI.toast("Password diperbarui.", "success");
                    } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                  });
                  const btnToggle = MugenUI.el("button", {}, r.aktif ? "Nonaktifkan" : "Aktifkan");
                  btnToggle.addEventListener("click", async () => {
                    try {
                      await MugenUI.withLoading(() => MugenApi.put(`/api/pengaturan/user/${r.id}/${r.aktif ? "nonaktifkan" : "aktifkan"}`, {}));
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
          await MugenUI.withLoading(async () => {
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
          });
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
          await MugenUI.withLoading(() => MugenApi.uploadFile("/api/pengaturan/backup/import", inputImport.files[0]));
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
