// pages/pengaturan.js — TAHAP 10: menu Setting. KHUSUS admin (dijaga di
// router.js + backend require_admin di setiap endpoint /api/pengaturan/*).
// Mengikuti pola tab seperti pages/rekap.js.

const PagePengaturan = (() => {
  // REVISI Hak Akses Admin: tab yang dilihat 'staff' (Admin) HANYA yang
  // diizinkan Owner lewat Setting > Hak Akses Admin -- Komisi/Bonus Service/
  // Uang Harian/Barber/Layanan/Hak Akses Admin itu sendiri BUKAN bagian
  // dari hak akses yang bisa diberikan (lihat backend/permissions.py),
  // jadi tetap Owner-murni. Pemetaan tab -> key izin Setting-nya:
  const TAB_KE_IZIN_SETTING = {
    "Identitas Barbershop": "izin_setting_identitas",
    "Tampilan": "izin_setting_tampilan",
    "User": "izin_setting_user",
    "Backup": "izin_setting_backup",
  };

  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Setting"));

    const user = MugenState.getUser();
    const isOwner = user.role === "admin";

    let izinAdmin = {};
    if (!isOwner) {
      try {
        izinAdmin = await MugenApi.get("/api/pengaturan/hak-akses-admin");
      } catch (e) {
        izinAdmin = {};
      }
    }

    const tabs = isOwner
      ? ["Identitas Barbershop", "Tampilan", "Komisi", "Bonus Service", "Uang Harian", "Barber", "Layanan", "User", "Backup", "Hak Akses Admin"]
      : Object.keys(TAB_KE_IZIN_SETTING).filter((t) => izinAdmin[TAB_KE_IZIN_SETTING[t]]);

    if (tabs.length === 0) {
      root.appendChild(MugenUI.el("div", { class: "card" },
        "Belum ada tab Setting yang diizinkan untuk akun Admin ini. Hubungi Owner untuk mengatur hak akses lewat Setting > Hak Akses Admin."));
      return;
    }

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
      else if (activeTab === "Tampilan") await renderTampilan();
      else if (activeTab === "Komisi") await renderKomisi();
      else if (activeTab === "Bonus Service") await renderBonusService();
      else if (activeTab === "Uang Harian") await renderUangHarian();
      else if (activeTab === "Barber") await renderBarber();
      else if (activeTab === "Layanan") await renderLayanan();
      else if (activeTab === "User") await renderUser();
      else if (activeTab === "Backup") await renderBackup();
      else await renderHakAksesAdmin();
    }

    // ================= BONUS SERVICE / UANG HARIAN (checklist acuan service) =================
    // REVISI: dua pengaturan independen menggantikan hardcode lama (Dry Cut +
    // Cut & Wash) -- SATU helper dipakai di tab Bonus Service dan tab Uang
    // Harian karena bagian checklist-nya identik (checklist seluruh service +
    // tombol Simpan), hanya endpoint & teks penjelasannya beda. Masing-masing
    // tab menambahkan bagian lain SETELAH checklist ini (tier bonus untuk
    // Bonus Service, target harian untuk Uang Harian -- lihat renderBonusService/
    // renderUangHarian di bawah).
    async function renderAcuanServiceChecklist(judul, endpoint, penjelasan) {
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
          await MugenUI.withLoading(() => MugenApi.put(endpoint, { service_ids }), { message: "Menyimpan…" });
          MugenUI.toast(`Pengaturan ${judul} disimpan.`, "success");
        } catch (e) {
          errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        }
      });
    }

    // ================= TAB: IDENTITAS BARBERSHOP =================
    // REVISI STRUKTUR WEBSITE CONTENT: Tagline/Deskripsi/Alamat/WhatsApp/
    // Instagram/Website/Jam Operasional/Banner DIPINDAHKAN ke Booking >
    // Website Content (lihat renderWebsiteContent() di booking.js) --
    // BUKAN diduplikasi di sini. Tab ini sekarang hanya menyisakan
    // identitas inti yang dipakai DI LUAR halaman publik /book juga
    // (sidebar, halaman Login, judul tab browser): Nama Barbershop, Email,
    // Logo.
    async function renderIdentitas() {
      const card = MugenUI.el("div", { class: "card" });
      body.appendChild(card);
      card.appendChild(MugenUI.el("h2", {}, "Identitas Barbershop"));
      card.appendChild(MugenUI.el("div", { class: "subtitle" },
        "Nama & logo di sini otomatis dipakai di halaman Login dan sidebar seluruh aplikasi. Konten halaman Website (Tagline, About, Alamat, Kontak, dst) dikelola di Booking → Website Content."));

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
          const hasil = await MugenUI.withLoading(() => MugenApi.uploadFile("/api/pengaturan/logo", inputLogo.files[0]), { message: "Mengunggah…" });
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
      const inputEmail = MugenUI.el("input", { type: "text", value: data.email || "" });
      const btnSimpan = MugenUI.el("button", { class: "btn-primary" }, "Simpan Identitas");
      const formError = MugenUI.el("div", { class: "login-error" });

      card.appendChild(MugenUI.el("label", {}, "Nama Barbershop"));
      card.appendChild(inputNama);
      card.appendChild(MugenUI.el("label", {}, "Email"));
      card.appendChild(inputEmail);
      card.appendChild(formError);
      card.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpan));

      btnSimpan.addEventListener("click", async () => {
        formError.textContent = "";
        if (!inputNama.value.trim()) { formError.textContent = "Nama Barbershop tidak boleh kosong."; return; }
        btnSimpan.disabled = true;
        try {
          await MugenUI.withLoading(() => MugenApi.put("/api/pengaturan/identitas", {
            nama_barbershop: inputNama.value.trim(),
            email: inputEmail.value.trim(),
          }), { message: "Menyimpan…" });
          MugenUI.toast("Identitas barbershop disimpan.", "success");
          MugenBrand.refresh();
        } catch (e) {
          formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        } finally {
          btnSimpan.disabled = false;
        }
      });
    }

    // ================= TAB: TAMPILAN (REVISI UI/UX: Dark Mode) =================
    // Khusus Owner/Admin (lihat spesifikasi) -- user lain (Barber) mengatur
    // tema-nya sendiri lewat switch di sidebar (di atas tombol Keluar,
    // lihat nav.js), bukan lewat menu Setting ini (Barber tidak punya
    // akses ke Setting sama sekali).
    async function renderTampilan() {
      const card = MugenUI.el("div", { class: "card" });
      body.appendChild(card);
      card.appendChild(MugenUI.el("h2", {}, "Tampilan"));
      card.appendChild(MugenUI.el("div", { class: "subtitle" },
        "Preferensi ini tersimpan untuk akun Anda sendiri (bukan pengaturan toko) -- tetap sama walau login dari perangkat lain. Tidak berlaku untuk halaman Web Booking (/book), yang selalu memakai tampilan terang."));
      card.appendChild(MugenUI.el("div", { class: "theme-switch-row", style: "margin-top:14px;" }, [
        MugenUI.el("span", {}, "Dark Mode"),
        MugenUI.themeSwitch(),
      ]));
    }

    // ================= TAB: KOMISI & BONUS =================
    // REVISI: Uang Harian dipindah jadi per-barber (lihat tab Barber di
    // bawah), Bonus Kehadiran dihapus total, dan Target Bonus Customer
    // sekarang bertingkat (banyak tier, dikelola terpisah lewat
    // /api/pengaturan/bonus-tiers) -- bukan lagi satu target/nominal saja.
    // ================= TAB: KOMISI =================
    // REVISI Struktur Setting: disederhanakan -- HANYA persentase komisi +
    // aturan potongan Bonus Customer akibat libur berlebih. Potongan Modal
    // Chemical DIHAPUS dari sini (digantikan Harga Modal per-service di tab
    // Layanan). Target Bonus Service (tier bertingkat) DIPINDAH ke tab
    // Bonus Service (lihat renderBonusService di bawah) -- tab ini sekarang
    // murni tiga angka global.
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
          maksimal_hari_libur_bonus_customer: Number(inMaksLiburBonus.value),
          potongan_bonus_customer_persen: Number(inPotonganBonus.value),
        };
        for (const [k, v] of Object.entries(body2)) {
          if (Number.isNaN(v) || v < 0) { formError.textContent = `Nilai untuk "${k}" tidak valid (harus angka >= 0).`; return; }
        }
        btnSimpan.disabled = true;
        try {
          await MugenUI.withLoading(() => MugenApi.put("/api/pengaturan/komisi", body2), { message: "Menyimpan…" });
          MugenUI.toast("Pengaturan komisi disimpan.", "success");
        } catch (e) {
          formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        } finally {
          btnSimpan.disabled = false;
        }
      });
    }

    // ================= TAB: BONUS SERVICE (pusat seluruh pengaturan bonus) =================
    // REVISI Struktur Setting: sekarang berisi DUA bagian -- checklist acuan
    // service (sudah ada sebelumnya) DAN Target Bonus Service/tier bertingkat
    // (dipindah dari tab Komisi). Teks hardcoded "Dry Cut + Cut & Wash"
    // dihilangkan -- seluruh aturan sudah bisa dikonfigurasi Owner sendiri.
    async function renderBonusService() {
      await renderAcuanServiceChecklist("Bonus Service", "/api/pengaturan/bonus-service-acuan",
        "Pilih service mana saja yang jadi acuan Target Bonus Service (tier bulanan, diatur di bawah). " +
        "Bonus HANYA menghitung service yang dicentang di sini.");

      const tierCard = MugenUI.el("div", { class: "card" });
      body.appendChild(tierCard);
      tierCard.appendChild(MugenUI.el("h2", {}, "Target Bonus Service"));
      tierCard.appendChild(MugenUI.el("div", { class: "subtitle" },
        "Dihitung dari jumlah service acuan (checklist di atas) per barber per bulan. Tambah tier sebanyak yang " +
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
                      await MugenUI.withLoading(() => MugenApi.del(`/api/pengaturan/bonus-tiers/${tier.target}`), { message: "Menghapus…" });
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
          }, { message: "Menyimpan…" });
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

    // ================= TAB: UANG HARIAN =================
    // REVISI Struktur Setting: ditambah field Target Jumlah Service Harian
    // (dulu hardcode 3, sekarang bebas diatur Owner lewat
    // /api/pengaturan/uang-harian-target -- lihat database.py
    // target_uang_harian_per_hari()), di bawah checklist acuan service yang
    // sudah ada.
    async function renderUangHarian() {
      await renderAcuanServiceChecklist("Uang Harian", "/api/pengaturan/uang-harian-acuan",
        "Pilih service mana saja yang jadi acuan syarat cair Uang Harian (cair kalau total service acuan ini " +
        "pada satu hari yang sama mencapai target di bawah).");

      const targetCard = MugenUI.el("div", { class: "card" });
      body.appendChild(targetCard);
      targetCard.appendChild(MugenUI.el("h2", {}, "Target Jumlah Service Harian"));
      targetCard.appendChild(MugenUI.el("div", { class: "subtitle" },
        "Uang Harian cair kalau total service acuan (checklist di atas) pada SATU hari yang sama mencapai " +
        "target ini. Atur bebas sesuai kebijakan toko."));

      let targetSaatIni = 3;
      try {
        const t = await MugenApi.get("/api/pengaturan/uang-harian-target");
        targetSaatIni = t.target;
      } catch (e) {
        targetCard.appendChild(MugenUI.el("div", {}, e.message));
        return;
      }

      const inTarget = MugenUI.el("input", { type: "number", min: "1", value: String(targetSaatIni) });
      targetCard.appendChild(MugenUI.el("label", {}, "Target (jumlah service/hari)"));
      targetCard.appendChild(inTarget);
      const targetError = MugenUI.el("div", { class: "login-error" });
      targetCard.appendChild(targetError);
      const btnSimpanTarget = MugenUI.el("button", { class: "btn-primary" }, "Simpan Target");
      targetCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanTarget));

      btnSimpanTarget.addEventListener("click", async () => {
        targetError.textContent = "";
        const target = Number(inTarget.value);
        if (!target || target <= 0) { targetError.textContent = "Target harus lebih dari 0."; return; }
        btnSimpanTarget.disabled = true;
        try {
          await MugenUI.withLoading(() => MugenApi.put("/api/pengaturan/uang-harian-target", { target }), { message: "Menyimpan…" });
          MugenUI.toast("Target Uang Harian disimpan.", "success");
        } catch (e) {
          targetError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        } finally {
          btnSimpanTarget.disabled = false;
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
      // REVISI: Uang Harian sekarang per-barber (sebelumnya dua setting global
      // uang_harian_barber/uang_harian_rafiq dipilih dari status RAFIQ).
      const inputUangHarian = MugenUI.el("input", { type: "number", min: "0", value: "0" });
      const btnSubmit = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
      const btnBatal = MugenUI.el("button", { style: "display:none;" }, "Batal Edit");
      const formError = MugenUI.el("div", { class: "login-error" });

      formCard.appendChild(MugenUI.el("label", {}, "Nama Barber"));
      formCard.appendChild(inputNama);
      formCard.appendChild(MugenUI.el("label", {}, "Uang Harian"));
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
          }, { message: "Menyimpan…" });
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
                      await MugenUI.withLoading(() => MugenApi.put(`/api/booking/barber/${r.id}/status`, { status_booking: sel.value }), { message: "Menyimpan…" });
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
                      await MugenUI.withLoading(() => MugenApi.put(`/api/pengaturan/barber/${r.id}`, { aktif: !r.aktif }), { message: "Menyimpan…" });
                      MugenUI.toast(r.aktif ? "Barber dinonaktifkan." : "Barber diaktifkan.", "success");
                      loadList();
                    } catch (e) { MugenUI.toast(e.message, "error"); }
                  });
                  const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                  btnHapus.addEventListener("click", async () => {
                    if (!confirm(`Hapus barber "${r.nama}"? Hanya bisa dihapus kalau belum ada transaksi.`)) return;
                    try {
                      await MugenUI.withLoading(() => MugenApi.del(`/api/pengaturan/barber/${r.id}`), { message: "Menghapus…" });
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
                      }, { message: "Menyimpan…" });
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
                      }, { message: "Menyimpan…" });
                      loadList();
                    } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                  });
                  const inFoto = MugenUI.el("input", { type: "file", accept: "image/jpeg,image/png,image/webp", style: "display:none;" });
                  const btnFoto = MugenUI.el("button", {}, "Foto");
                  btnFoto.addEventListener("click", () => inFoto.click());
                  inFoto.addEventListener("change", async () => {
                    if (!inFoto.files || !inFoto.files[0]) return;
                    try {
                      await MugenUI.withLoading(() => MugenApi.uploadFile(`/api/booking/barber/${r.id}/foto`, inFoto.files[0]), { message: "Mengunggah…" });
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
    // REVISI Struktur Setting: "Potongan Modal Chemical" (select per-service)
    // dihapus dari sini -- digantikan "Harga Modal" (field `modal` yang sudah
    // ada, sekarang benar-benar dipakai hitung_komisi_service di backend,
    // lihat revisi_setting_migrasi.py/database.py). Ditambah kolom "Nilai
    // Komisi Barber" (READ-ONLY, dihitung (Harga - Harga Modal) x Persentase
    // Komisi) supaya Owner bisa langsung lihat komisi tiap layanan tanpa
    // hitung manual -- murni tampilan, tidak mengubah data apa pun.
    async function renderLayanan() {
      const formCard = MugenUI.el("div", { class: "card" });
      const listCard = MugenUI.el("div", { class: "card" });
      body.appendChild(formCard);
      body.appendChild(listCard);

      let persentaseKomisi = 0;
      try {
        const k = await MugenApi.get("/api/pengaturan/komisi");
        persentaseKomisi = Number(k.persentase_komisi) || 0;
      } catch (e) { /* kalau gagal, kolom Nilai Komisi Barber tampil 0 -- tidak menghalangi CRUD layanan */ }

      function hitungKomisi(harga, modal) {
        const dasar = Math.max(0, Number(harga || 0) - Number(modal || 0));
        return Math.round(dasar * (persentaseKomisi / 100));
      }

      let editingId = null;
      const formTitle = MugenUI.el("h2", {}, "Tambah Layanan");
      formCard.appendChild(formTitle);
      const inputNama = MugenUI.el("input", { type: "text", placeholder: "Nama layanan" });
      const inputHarga = MugenUI.el("input", { type: "number", min: "0", value: "0" });
      const inputModal = MugenUI.el("input", { type: "number", min: "0", value: "0" });
      const btnSubmit = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
      const btnBatal = MugenUI.el("button", { style: "display:none;" }, "Batal Edit");
      const formError = MugenUI.el("div", { class: "login-error" });

      formCard.appendChild(MugenUI.el("label", {}, "Nama Layanan"));
      formCard.appendChild(inputNama);
      formCard.appendChild(MugenUI.el("label", {}, "Harga (Rp)"));
      formCard.appendChild(inputHarga);
      formCard.appendChild(MugenUI.el("label", {}, "Harga Modal (Rp, opsional)"));
      formCard.appendChild(inputModal);
      formCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:-6px;" },
        "Kosongkan/isi 0 kalau layanan ini tidak punya biaya modal. Kalau diisi, nilainya dikurangkan dari " +
        "Harga sebelum dikali Persentase Komisi (Setting > Komisi)."));
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
        formError.textContent = "";
      }
      btnBatal.addEventListener("click", resetForm);

      btnSubmit.addEventListener("click", async () => {
        formError.textContent = "";
        if (!inputNama.value.trim()) { formError.textContent = "Nama layanan tidak boleh kosong."; return; }
        const harga = Number(inputHarga.value);
        const modal = Number(inputModal.value);
        if (Number.isNaN(harga) || harga < 0) { formError.textContent = "Harga tidak valid."; return; }
        if (Number.isNaN(modal) || modal < 0) { formError.textContent = "Harga Modal tidak valid."; return; }
        btnSubmit.disabled = true;
        try {
          const body2 = { nama: inputNama.value.trim(), harga, modal };
          await MugenUI.withLoading(async () => {
            if (editingId) {
              await MugenApi.put(`/api/pengaturan/service/${editingId}`, body2);
              MugenUI.toast("Layanan diperbarui.", "success");
            } else {
              await MugenApi.post("/api/pengaturan/service", body2);
              MugenUI.toast("Layanan ditambahkan.", "success");
            }
          }, { message: "Menyimpan…" });
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
              { key: "modal", label: "Harga Modal", format: (v) => MugenUI.formatRupiah(v || 0) },
              { key: "nilai_komisi", label: "Nilai Komisi Barber", format: (_, r) => MugenUI.formatRupiah(hitungKomisi(r.harga, r.modal)) },
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
                    formError.textContent = "";
                    formCard.scrollIntoView({ behavior: "smooth" });
                  });
                  const btnToggle = MugenUI.el("button", {}, r.aktif ? "Nonaktifkan" : "Aktifkan");
                  btnToggle.addEventListener("click", async () => {
                    try {
                      await MugenUI.withLoading(() => MugenApi.put(`/api/pengaturan/service/${r.id}`, { aktif: !r.aktif }), { message: "Menyimpan…" });
                      MugenUI.toast(r.aktif ? "Layanan dinonaktifkan." : "Layanan diaktifkan.", "success");
                      loadList();
                    } catch (e) { MugenUI.toast(e.message, "error"); }
                  });
                  const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                  btnHapus.addEventListener("click", async () => {
                    if (!confirm(`Hapus layanan "${r.nama}"? Hanya bisa dihapus kalau belum pernah dipakai transaksi.`)) return;
                    try {
                      await MugenUI.withLoading(() => MugenApi.del(`/api/pengaturan/service/${r.id}`), { message: "Menghapus…" });
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
                      }, { message: "Menyimpan…" });
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
                      }, { message: "Menyimpan…" });
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
      // REVISI Hak Akses Admin: role 'admin' (Owner) dan 'staff' (Admin,
      // BARU) sekarang dua peran berbeda -- lihat backend/permissions.py.
      // Akun ber-role 'staff' HANYA boleh mengelola user ber-role 'barber'
      // (ditegakkan di backend, lihat routers/pengaturan.py -- form/tombol
      // di sini disesuaikan supaya tidak menampilkan aksi yang pasti
      // ditolak backend).
      const LABEL_ROLE = { admin: "Owner", staff: "Admin", barber: "Barber" };
      const isStaffActor = user.role === "staff";

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
      if (!isStaffActor) {
        selRole.appendChild(MugenUI.el("option", { value: "admin" }, "Owner"));
        selRole.appendChild(MugenUI.el("option", { value: "staff" }, "Admin"));
      }
      selRole.appendChild(MugenUI.el("option", { value: "barber" }, "Barber"));
      if (isStaffActor) selRole.value = "barber";
      const selBarberAkun = MugenUI.el("select", { style: isStaffActor ? "" : "display:none;" });
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
          }), { message: "Menyimpan…" });
          MugenUI.toast("User ditambahkan.", "success");
          inputUsername.value = ""; inputPassword.value = "";
          if (isStaffActor) { selBarberAkun.style.display = ""; } else { selRole.value = "admin"; selBarberAkun.style.display = "none"; }
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
              { key: "role", label: "Role", format: (v) => LABEL_ROLE[v] || v },
              { key: "aktif", label: "Status", format: (v) => MugenUI.el("span", { class: "badge" + (v ? "" : " badge-libur") }, v ? "Aktif" : "Nonaktif") },
              {
                key: "aksi", label: "Aksi", format: (_, r) => {
                  const wrap = MugenUI.el("div", { class: "actions-cell" });
                  // REVISI Hak Akses Admin: 'staff' (Admin) hanya boleh
                  // menyasar user ber-role 'barber' -- tombol aksi untuk
                  // baris Owner/Admin lain disembunyikan sama sekali di sini
                  // (bukan hanya ditolak backend) supaya tidak ada tombol
                  // yang pasti berujung error 403.
                  if (isStaffActor && r.role !== "barber") {
                    wrap.appendChild(MugenUI.el("span", { style: "color:var(--text-dim);" }, "-"));
                    return wrap;
                  }
                  if (!isStaffActor) {
                    const btnUsername = MugenUI.el("button", {}, "Ganti Username");
                    btnUsername.addEventListener("click", async () => {
                      const baru = prompt(`Username baru untuk "${r.username}":`, r.username);
                      if (!baru || !baru.trim() || baru.trim() === r.username) return;
                      try {
                        await MugenUI.withLoading(() => MugenApi.put(`/api/pengaturan/user/${r.id}/username`, { username: baru.trim() }), { message: "Menyimpan…" });
                        MugenUI.toast("Username diperbarui.", "success");
                        loadList();
                      } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                    });
                    wrap.appendChild(btnUsername);
                  }
                  const btnPassword = MugenUI.el("button", {}, "Ganti Password");
                  btnPassword.addEventListener("click", async () => {
                    const baru = prompt(`Password baru untuk "${r.username}" (min. 4 karakter):`);
                    if (!baru) return;
                    try {
                      await MugenUI.withLoading(() => MugenApi.put(`/api/pengaturan/user/${r.id}/password`, { password: baru }), { message: "Menyimpan…" });
                      MugenUI.toast("Password diperbarui.", "success");
                    } catch (e) { MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error"); }
                  });
                  const btnToggle = MugenUI.el("button", {}, r.aktif ? "Nonaktifkan" : "Aktifkan");
                  btnToggle.addEventListener("click", async () => {
                    try {
                      await MugenUI.withLoading(() => MugenApi.put(`/api/pengaturan/user/${r.id}/${r.aktif ? "nonaktifkan" : "aktifkan"}`, {}), { message: "Menyimpan…" });
                      MugenUI.toast(r.aktif ? "User dinonaktifkan." : "User diaktifkan.", "success");
                      loadList();
                    } catch (e) { MugenUI.toast(e.message, "error"); }
                  });
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
      // REVISI Hak Akses Admin: Export/Import/Laporan PDF masing-masing
      // permission TERPISAH (bukan hanya izin_setting_backup, yang cuma
      // mengatur akses ke TAB-nya) -- Owner selalu boleh semuanya.
      const bolehExport = isOwner || !!izinAdmin.izin_backup_export;
      const bolehImport = isOwner || !!izinAdmin.izin_backup_import;
      const bolehLaporan = isOwner || !!izinAdmin.izin_laporan_pdf;

      const card = MugenUI.el("div", { class: "card" });
      body.appendChild(card);
      card.appendChild(MugenUI.el("h2", {}, "Export Database"));
      card.appendChild(MugenUI.el("div", { class: "subtitle" }, "Unduh salinan file database saat ini (.db)."));
      const btnExport = MugenUI.el("button", { class: "btn-primary" }, "Export Database");
      btnExport.disabled = !bolehExport;
      if (!bolehExport) card.appendChild(MugenUI.el("div", { class: "subtitle" }, "Admin tidak punya izin untuk Export Database. Hubungi Owner."));
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
      btnImport.disabled = !bolehImport;
      const importError = MugenUI.el("div", { class: "login-error" });
      card.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin:12px 0;" }, [inputImport, btnImport]));
      card.appendChild(importError);

      btnImport.addEventListener("click", async () => {
        importError.textContent = "";
        if (!inputImport.files || !inputImport.files[0]) { importError.textContent = "Pilih file .db dulu."; return; }
        if (!confirm("Yakin ingin mengganti seluruh database yang sedang berjalan dengan file ini? Tindakan ini tidak mudah dibatalkan.")) return;
        btnImport.disabled = true;
        try {
          await MugenUI.withLoading(() => MugenApi.uploadFile("/api/pengaturan/backup/import", inputImport.files[0]), { message: "Memulihkan backup…" });
          MugenUI.toast("Database berhasil diganti. Memuat ulang halaman...", "success");
          setTimeout(() => location.reload(), 1500);
        } catch (e) {
          importError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        } finally {
          btnImport.disabled = false;
        }
      });

      // ================= LAPORAN PDF =================
      const laporanCard = MugenUI.el("div", { class: "card" });
      body.appendChild(laporanCard);
      laporanCard.appendChild(MugenUI.el("h2", {}, "Download Laporan PDF"));
      laporanCard.appendChild(MugenUI.el("div", { class: "subtitle" },
        "PDF berisi nama & logo barbershop, judul laporan, periode, tanggal cetak, nomor halaman, dan nama Anda sebagai pencetak."));

      const today = new Date();
      const todayIso = today.toISOString().slice(0, 10);
      const awalBulanIso = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().slice(0, 10);

      const selJenis = MugenUI.el("select", {}, [
        MugenUI.el("option", { value: "transaksi" }, "Laporan Transaksi"),
        MugenUI.el("option", { value: "pengeluaran" }, "Laporan Pengeluaran"),
        MugenUI.el("option", { value: "rekap_bulanan" }, "Rekap Bulanan Barber"),
      ]);

      // Rekap Bulanan Barber: TETAP Tahun+Bulan (perhitungan komisi/bonus/
      // uang harian bertumpu pada batas bulan kalender, lihat
      // database.py get_ringkasan_barber_bulan() -- tidak bisa dipotong ke
      // rentang tanggal bebas). Transaksi & Pengeluaran: rentang tanggal
      // bebas (Dari - Sampai) supaya Periode di PDF menunjukkan tanggal
      // sebenarnya, bukan cuma "Bulan Tahun".
      const wrapTahunBulan = MugenUI.el("div");
      const selTahunLaporan = MugenUI.el("select");
      for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) selTahunLaporan.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
      selTahunLaporan.value = String(today.getFullYear());
      const selBulanLaporan = MugenUI.el("select");
      for (let m = 1; m <= 12; m++) selBulanLaporan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
      selBulanLaporan.value = String(today.getMonth() + 1);
      wrapTahunBulan.appendChild(MugenUI.el("label", {}, "Tahun"));
      wrapTahunBulan.appendChild(selTahunLaporan);
      wrapTahunBulan.appendChild(MugenUI.el("label", {}, "Bulan"));
      wrapTahunBulan.appendChild(selBulanLaporan);

      const wrapRentang = MugenUI.el("div");
      const inputDari = MugenUI.el("input", { type: "date", value: awalBulanIso, max: todayIso });
      const inputSampai = MugenUI.el("input", { type: "date", value: todayIso, max: todayIso });
      wrapRentang.appendChild(MugenUI.el("label", {}, "Dari Tanggal"));
      wrapRentang.appendChild(inputDari);
      wrapRentang.appendChild(MugenUI.el("label", {}, "Sampai Tanggal"));
      wrapRentang.appendChild(inputSampai);

      const selBarberLaporan = MugenUI.el("select");
      selBarberLaporan.appendChild(MugenUI.el("option", { value: "" }, "Semua Barber"));
      try {
        const barbers = await MugenApi.get("/api/input-data/barbers", { useCache: true });
        for (const b of barbers) selBarberLaporan.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
      } catch (e) { /* opsional -- filter barber tetap bisa "Semua Barber" */ }

      laporanCard.appendChild(MugenUI.el("label", {}, "Jenis Laporan"));
      laporanCard.appendChild(selJenis);
      laporanCard.appendChild(wrapTahunBulan);
      laporanCard.appendChild(wrapRentang);
      laporanCard.appendChild(MugenUI.el("label", {}, "Barber"));
      laporanCard.appendChild(selBarberLaporan);

      function terapkanTampilanJenis() {
        const rekap = selJenis.value === "rekap_bulanan";
        wrapTahunBulan.style.display = rekap ? "" : "none";
        wrapRentang.style.display = rekap ? "none" : "";
      }
      terapkanTampilanJenis();
      selJenis.addEventListener("change", terapkanTampilanJenis);

      const laporanError = MugenUI.el("div", { class: "login-error" });
      const btnLaporan = MugenUI.el("button", { class: "btn-primary" }, "Download PDF");
      btnLaporan.disabled = !bolehLaporan;
      if (!bolehLaporan) laporanCard.appendChild(MugenUI.el("div", { class: "subtitle" }, "Admin tidak punya izin untuk Download Laporan PDF. Hubungi Owner."));
      laporanCard.appendChild(laporanError);
      laporanCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnLaporan));

      btnLaporan.addEventListener("click", async () => {
        laporanError.textContent = "";
        const rekap = selJenis.value === "rekap_bulanan";
        if (!rekap && (!inputDari.value || !inputSampai.value)) {
          laporanError.textContent = "Tanggal Dari dan Sampai wajib diisi.";
          return;
        }
        if (!rekap && inputDari.value > inputSampai.value) {
          laporanError.textContent = "Tanggal Dari tidak boleh setelah Tanggal Sampai.";
          return;
        }
        btnLaporan.disabled = true;
        try {
          await MugenUI.withLoading(async () => {
            const qs = new URLSearchParams({ jenis: selJenis.value });
            if (rekap) {
              qs.set("tahun", selTahunLaporan.value);
              qs.set("bulan", selBulanLaporan.value);
            } else {
              qs.set("tanggal_mulai", inputDari.value);
              qs.set("tanggal_selesai", inputSampai.value);
            }
            if (selBarberLaporan.value) qs.set("barber_id", selBarberLaporan.value);
            const token = MugenState.getToken();
            const res = await fetch(`${MUGEN_API_BASE}/api/pengaturan/laporan/pdf?${qs.toString()}`, {
              headers: token ? { Authorization: `Bearer ${token}` } : {},
            });
            if (!res.ok) {
              let pesan = "Gagal mengunduh laporan.";
              try { pesan = (await res.json()).detail || pesan; } catch (e) { /* body bukan JSON */ }
              throw new Error(pesan);
            }
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            const stamp = rekap ? `${selTahunLaporan.value}-${selBulanLaporan.value}` : `${inputDari.value}_${inputSampai.value}`;
            a.download = `laporan_${selJenis.value}_${stamp}.pdf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
          });
          MugenUI.toast("Laporan PDF berhasil diunduh.", "success");
        } catch (e) {
          laporanError.textContent = e.message;
        } finally {
          btnLaporan.disabled = false;
        }
      });
    }

    // ================= TAB: HAK AKSES ADMIN (Owner-only) =================
    async function renderHakAksesAdmin() {
      const card = MugenUI.el("div", { class: "card" });
      body.appendChild(card);
      card.appendChild(MugenUI.el("h2", {}, "Hak Akses Admin"));
      card.appendChild(MugenUI.el("div", { class: "subtitle" },
        "Atur apa saja yang boleh dilihat/dilakukan akun ber-role Admin (role 'staff'). Owner selalu memiliki akses penuh " +
        "tanpa batasan apa pun -- pengaturan di bawah ini TIDAK berlaku untuk Owner."));

      let izin;
      try {
        izin = await MugenApi.get("/api/pengaturan/hak-akses-admin");
      } catch (e) {
        card.appendChild(MugenUI.el("div", {}, e.message));
        return;
      }

      const GRUP = [
        { judul: "Dashboard", keys: [
          ["izin_dashboard_nilai_service", "Nilai Service"],
          ["izin_dashboard_jumlah_service", "Jumlah Service"],
          ["izin_dashboard_pengeluaran_toko", "Pengeluaran Toko"],
          ["izin_dashboard_penjualan_produk", "Penjualan Produk"],
          ["izin_dashboard_total_komisi", "Total Komisi Barber"],
          ["izin_dashboard_total_tips", "Total Tips"],
          ["izin_dashboard_uang_harian", "Uang Harian"],
          ["izin_dashboard_bonus_customer", "Bonus Customer"],
          ["izin_dashboard_laba_kotor", "Laba Kotor Toko"],
        ]},
        { judul: "User (khusus akun ber-role Barber)", keys: [
          ["izin_user_tambah", "Membuat User Barber"],
          ["izin_user_hapus", "Menghapus (menonaktifkan) User Barber"],
          ["izin_user_ganti_password", "Mengubah Password User Barber"],
        ]},
        // REVISI (kedua): grup "Pengeluaran" dihapus dari sini -- menu
        // Pengeluaran tidak lagi memakai sistem izin sama sekali, Admin
        // selalu punya akses penuh sama persis seperti Owner.
        { judul: "Backup", keys: [
          ["izin_backup_export", "Export Database"],
          ["izin_backup_import", "Import Database"],
        ]},
        { judul: "Laporan", keys: [
          ["izin_laporan_pdf", "Download PDF"],
        ]},
        { judul: "Karyawan", keys: [
          ["izin_slip_gaji", "Kelola Slip Gaji"],
        ]},
        { judul: "Setting (akses tab)", keys: [
          ["izin_setting_identitas", "Identitas Barbershop"],
          ["izin_setting_tampilan", "Tampilan"],
          ["izin_setting_user", "User"],
          ["izin_setting_backup", "Backup"],
        ]},
      ];

      const checkboxes = {};
      for (const grup of GRUP) {
        card.appendChild(MugenUI.el("h3", { style: "margin-top:20px;" }, grup.judul));
        const listBox = MugenUI.el("div", { class: "checklist-service" });
        for (const [key, label] of grup.keys) {
          const cb = MugenUI.el("input", { type: "checkbox", style: "width:auto;" });
          cb.checked = !!izin[key];
          checkboxes[key] = cb;
          listBox.appendChild(MugenUI.el("label", { style: "display:flex;align-items:center;gap:8px;" }, [cb, label]));
        }
        card.appendChild(listBox);
      }

      const errorBox = MugenUI.el("div", { class: "login-error" });
      const btnSimpan = MugenUI.el("button", { class: "btn-primary" }, "Simpan Hak Akses");
      card.appendChild(errorBox);
      card.appendChild(MugenUI.el("div", { style: "margin-top:16px;" }, btnSimpan));

      btnSimpan.addEventListener("click", async () => {
        errorBox.textContent = "";
        const body2 = {};
        for (const [key, cb] of Object.entries(checkboxes)) body2[key] = cb.checked;
        try {
          await MugenUI.withLoading(() => MugenApi.put("/api/pengaturan/hak-akses-admin", { izin: body2 }), { message: "Menyimpan…" });
          MugenUI.toast("Hak akses Admin disimpan.", "success");
        } catch (e) {
          errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        }
      });
    }

    renderTabs();
    renderBody();
  }

  return { render };
})();
