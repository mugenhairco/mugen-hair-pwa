// pages/whatsapp.js — Notifikasi WhatsApp Otomatis
// =============================================================================
// REVISI (feedback Owner): SEBELUMNYA tab "WhatsApp" di dalam Setting --
// dipindah jadi menu utama sidebar sendiri (lihat nav.js/router.js), supaya
// lebih mudah ditemukan. Isi & perilaku PERSIS SAMA (KHUSUS Owner, backend
// require_admin -- token Fonnte adalah kredensial pihak ketiga milik TOKO
// ini sendiri, tidak didelegasikan ke staff lewat Hak Akses Admin, sama
// seperti dulu di dalam Setting), murni dipindah lokasinya.
//
// FITUR Reminder Absensi via WhatsApp: tab KEDUA ditambahkan di sini
// ("Reminder Absensi"), TERPISAH dari tab "Notifikasi Booking" yang sudah
// ada (permintaan Owner eksplisit -- dua hal berbeda sama sekali: satu
// untuk customer, satu untuk barber). Masing-masing tab menggerbang fitur
// paketnya SENDIRI-SENDIRI (whatsapp_reminder vs absensi) -- BUKAN satu
// gerbang untuk seluruh halaman seperti sebelumnya, supaya tenant yang
// cuma punya salah satu fitur tetap bisa memakai tab yang relevan.

const PageWhatsapp = (() => {
  // PERMINTAAN OWNER: pola SAMA seperti produk.js/pengaturan lain -- simpan
  // hasil fetch TERAKHIR (setting per tab) di LUAR render() supaya
  // bertahan lintas navigasi menu. Kalau WhatsApp dibuka lagi (bukan ganti
  // tab manual) TANPA ada simpan apa pun sejak terakhir kali TAB itu
  // berhasil dimuat (lihat state.js::halamanPerluRefresh("whatsapp")),
  // tampilkan ulang setting ini TANPA fetch. Tidak ada log/riwayat kirim
  // real-time di halaman ini -- murni form setting, aman untuk cache.
  let _cacheTerakhir = {}; // { [bagian]: { userId, data } }

  function _ambilDariCache(bagian, userId) {
    const c = _cacheTerakhir[bagian];
    if (!c || c.userId !== userId) return null;
    return c.data;
  }

  function _simpanKeCache(bagian, userId, data) {
    _cacheTerakhir[bagian] = { userId, data };
  }

  async function renderNotifikasiBooking(body, opts = {}) {
    const card = MugenUI.el("div", { class: "card" });
    body.appendChild(card);
    card.appendChild(MugenUI.el("h2", {}, "Notifikasi WhatsApp Booking"));

    // REVISI Work #2 (Superadmin Package Permission Tree): kode fitur
    // "whatsapp_reminder" tersendiri DIHAPUS -- gate paket SEKARANG murni
    // di backend (izin_whatsapp_notifikasi_booking, lewat require_permission()),
    // BUKAN lagi dicek/ditampilkan sebagai kartu upgrade terpisah di sini.

    let s;
    const cached = opts.bisaDariCache && !MugenState.halamanPerluRefresh("whatsapp")
      ? _ambilDariCache("notifikasi_booking", MugenState.getUser().id)
      : null;
    if (cached) {
      s = cached;
    } else {
      try {
        s = await MugenApi.get("/api/pengaturan/whatsapp");
        _simpanKeCache("notifikasi_booking", MugenState.getUser().id, s);
        MugenState.tandaiHalamanBersih("whatsapp");
      } catch (e) {
        card.appendChild(MugenUI.errorState(e.message));
        return;
      }
    }

    card.appendChild(MugenUI.el("div", { class: "badge " + (s.aktif ? "badge-success" : "badge-libur"),
      style: "margin-bottom:12px;" }, s.aktif ? "Aktif" : "Belum Diaktifkan"));

    card.appendChild(MugenUI.el("label", {}, "Token API"));
    const inputToken = MugenUI.el("input", { type: "text", value: s.fonnte_token || "",
      placeholder: "Tempel token dari dashboard Fonnte Anda" });
    card.appendChild(inputToken);

    const errorBox = MugenUI.el("div", { class: "login-error" });
    const btnSimpan = MugenUI.el("button", { class: "btn-primary" }, "Simpan Token");
    card.appendChild(errorBox);
    card.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpan));

    btnSimpan.addEventListener("click", async () => {
      errorBox.textContent = "";
      try {
        await MugenUI.withButtonLoading(btnSimpan, () => MugenApi.put("/api/pengaturan/whatsapp", { fonnte_token: inputToken.value.trim() }));
        MugenUI.toast("Token WhatsApp disimpan.", "success");
        renderNotifikasiBooking(body);
      } catch (e) {
        errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });

    card.appendChild(MugenUI.el("h3", { style: "margin-top:20px;" }, "Tes Kirim Pesan"));
    const inputNomorTes = MugenUI.el("input", { type: "text", placeholder: "Contoh: 081234567890" });
    card.appendChild(inputNomorTes);
    const errorTes = MugenUI.el("div", { class: "login-error" });
    const btnTes = MugenUI.el("button", {}, "Kirim Pesan Tes");
    card.appendChild(errorTes);
    card.appendChild(MugenUI.el("div", { style: "margin-top:8px;" }, btnTes));
    btnTes.addEventListener("click", async () => {
      errorTes.textContent = "";
      if (!inputNomorTes.value.trim()) { errorTes.textContent = "Isi nomor tujuan dulu."; return; }
      try {
        await MugenUI.withButtonLoading(btnTes, () => MugenApi.post("/api/pengaturan/whatsapp/tes", { nomor_tujuan: inputNomorTes.value.trim() }));
        MugenUI.toast("Pesan tes berhasil dikirim.", "success");
      } catch (e) {
        errorTes.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });

    // ---- Kartu kedua: isi pesan (bisa diatur sendiri per jenis) ----
    const templateCard = MugenUI.el("div", { class: "card" });
    body.appendChild(templateCard);
    templateCard.appendChild(MugenUI.el("h2", {}, "Isi Pesan"));
    templateCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Atur sendiri kalimat yang dikirim ke customer untuk tiap jenis pesan. Kosongkan untuk memakai kalimat bawaan."));

    const placeholderText = s.placeholder_info.map((p) => `${p.placeholder} (${p.keterangan})`).join(", ");
    templateCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:14px;" },
      `Placeholder yang bisa dipakai -- otomatis diisi sistem: ${placeholderText}.`));

    for (const jp of s.jenis_pesan) {
      templateCard.appendChild(MugenUI.el("label", {}, jp.label));
      templateCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:-4px;margin-bottom:6px;" }, jp.deskripsi));
      const textarea = MugenUI.el("textarea", {
        rows: "5", placeholder: s.defaults[jp.jenis],
      }, s.templates[jp.jenis] || "");
      templateCard.appendChild(textarea);
      const btnReset = MugenUI.el("button", { style: "margin:8px 0 18px;" }, "Kembalikan ke Kalimat Bawaan");
      btnReset.addEventListener("click", () => { textarea.value = ""; });
      templateCard.appendChild(btnReset);

      jp._textarea = textarea;
    }

    const errorTemplate = MugenUI.el("div", { class: "login-error" });
    const btnSimpanTemplate = MugenUI.el("button", { class: "btn-primary" }, "Simpan Isi Pesan");
    templateCard.appendChild(errorTemplate);
    templateCard.appendChild(MugenUI.el("div", { style: "margin-top:4px;" }, btnSimpanTemplate));

    btnSimpanTemplate.addEventListener("click", async () => {
      errorTemplate.textContent = "";
      const templates = {};
      for (const jp of s.jenis_pesan) templates[jp.jenis] = jp._textarea.value.trim();
      try {
        await MugenUI.withButtonLoading(btnSimpanTemplate, () => MugenApi.put("/api/pengaturan/whatsapp", { templates }));
        MugenUI.toast("Isi pesan disimpan.", "success");
      } catch (e) {
        errorTemplate.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });
  }

  // FITUR Reminder Absensi via WhatsApp: tab KEDUA, berdiri sendiri total
  // dari tab Notifikasi Booking di atas -- endpoint backend terpisah
  // (/api/pengaturan/absensi-reminder, gerbang fitur "absensi" BUKAN
  // "whatsapp_reminder"), lihat absensi_reminder_db.py. Pengiriman
  // sungguhannya dipicu endpoint cron TERPISAH dari luar aplikasi (lihat
  // routers/cron_reminder.py) -- tab ini HANYA mengatur aktif/nonaktif +
  // isi pesan, TIDAK ada tombol "kirim sekarang" di sini.
  async function renderReminderAbsensi(body, opts = {}) {
    const card = MugenUI.el("div", { class: "card" });
    body.appendChild(card);
    card.appendChild(MugenUI.el("h2", {}, "Reminder Absensi"));
    card.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:14px;" },
      "Kirim pengingat WhatsApp otomatis ke barber yang belum Check In begitu jam operasional toko dimulai, "
      + "dan ke barber yang belum Check Out begitu jam tutup toko lewat. Barber yang sedang Libur/Cuti/Izin "
      + "pada hari itu tidak dikirimi apa pun. Nomor WhatsApp tiap barber diatur di Pengaturan > Karyawan."));

    // REVISI Work #2: kode fitur "absensi" tersendiri DIHAPUS -- gate
    // paket SEKARANG murni di backend (izin_absensi_lihat/izin_whatsapp_
    // reminder_absensi), BUKAN lagi kartu upgrade terpisah di sini.

    let s;
    const cached = opts.bisaDariCache && !MugenState.halamanPerluRefresh("whatsapp")
      ? _ambilDariCache("reminder_absensi", MugenState.getUser().id)
      : null;
    if (cached) {
      s = cached;
    } else {
      try {
        s = await MugenApi.get("/api/pengaturan/absensi-reminder");
        _simpanKeCache("reminder_absensi", MugenState.getUser().id, s);
        MugenState.tandaiHalamanBersih("whatsapp");
      } catch (e) {
        card.appendChild(MugenUI.errorState(e.message));
        return;
      }
    }

    const chkAktif = MugenUI.el("input", { type: "checkbox" });
    chkAktif.checked = !!s.aktif;
    const labelAktif = MugenUI.el("label", { style: "display:flex;align-items:center;gap:8px;font-weight:normal;" },
      [chkAktif, "Aktifkan Reminder Absensi"]);
    card.appendChild(labelAktif);

    const errorAktif = MugenUI.el("div", { class: "login-error" });
    card.appendChild(errorAktif);
    chkAktif.addEventListener("change", async () => {
      errorAktif.textContent = "";
      try {
        await MugenApi.put("/api/pengaturan/absensi-reminder", { aktif: chkAktif.checked });
        MugenUI.toast(chkAktif.checked ? "Reminder Absensi diaktifkan." : "Reminder Absensi dinonaktifkan.", "success");
      } catch (e) {
        chkAktif.checked = !chkAktif.checked;
        errorAktif.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });

    // ---- Kartu kedua: isi pesan (Check In/Check Out) ----
    const templateCard = MugenUI.el("div", { class: "card" });
    body.appendChild(templateCard);
    templateCard.appendChild(MugenUI.el("h2", {}, "Isi Pesan"));
    templateCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Atur sendiri kalimat yang dikirim ke barber untuk tiap jenis pengingat. Kosongkan untuk memakai kalimat bawaan."));

    const placeholderText = s.placeholder_info.map((p) => `${p.placeholder} (${p.keterangan})`).join(", ");
    templateCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:14px;" },
      `Placeholder yang bisa dipakai -- otomatis diisi sistem: ${placeholderText}.`));

    for (const jp of s.jenis_pesan) {
      templateCard.appendChild(MugenUI.el("label", {}, jp.label));
      templateCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:-4px;margin-bottom:6px;" }, jp.deskripsi));
      const textarea = MugenUI.el("textarea", {
        rows: "5", placeholder: s.defaults[jp.jenis],
      }, s.templates[jp.jenis] || "");
      templateCard.appendChild(textarea);
      const btnReset = MugenUI.el("button", { style: "margin:8px 0 18px;" }, "Kembalikan ke Kalimat Bawaan");
      btnReset.addEventListener("click", () => { textarea.value = ""; });
      templateCard.appendChild(btnReset);

      jp._textarea = textarea;
    }

    const errorTemplate = MugenUI.el("div", { class: "login-error" });
    const btnSimpanTemplate = MugenUI.el("button", { class: "btn-primary" }, "Simpan Isi Pesan");
    templateCard.appendChild(errorTemplate);
    templateCard.appendChild(MugenUI.el("div", { style: "margin-top:4px;" }, btnSimpanTemplate));

    btnSimpanTemplate.addEventListener("click", async () => {
      errorTemplate.textContent = "";
      const templates = {};
      for (const jp of s.jenis_pesan) templates[jp.jenis] = jp._textarea.value.trim();
      try {
        await MugenUI.withButtonLoading(btnSimpanTemplate, () => MugenApi.put("/api/pengaturan/absensi-reminder", { templates }));
        MugenUI.toast("Isi pesan disimpan.", "success");
      } catch (e) {
        errorTemplate.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });
  }

  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "WhatsApp"));

    // REVISI Hak Akses (sub-item per tab terpisah, lihat permissions.py::
    // PERMISSION_TREE): dulu DUA tab ini Owner-only murni -- SEKARANG
    // masing-masing punya saklar sendiri (izin_whatsapp_notifikasi_booking/
    // izin_whatsapp_reminder_absensi), Owner tetap lihat semua.
    const ALL_TABS = { "Notifikasi Booking": "izin_whatsapp_notifikasi_booking", "Reminder Absensi": "izin_whatsapp_reminder_absensi" };
    const user = MugenState.getUser();
    let tabsLolos = Object.keys(ALL_TABS);
    if (user.role !== "admin") {
      const hasilIzin = await Promise.all(tabsLolos.map((t) => MugenMenuAccess.has(ALL_TABS[t])));
      tabsLolos = tabsLolos.filter((_, i) => hasilIzin[i]);
    }
    if (!tabsLolos.length) {
      root.appendChild(MugenUI.emptyState("Anda tidak memiliki akses ke menu ini."));
      return;
    }
    const tabItems = tabsLolos.map((t) => ({ key: t, label: t }));
    const body = MugenUI.el("div");

    async function renderBody(activeTab, opts = {}) {
      body.innerHTML = "";
      if (activeTab === "Notifikasi Booking") await renderNotifikasiBooking(body, opts);
      else if (activeTab === "Reminder Absensi") await renderReminderAbsensi(body, opts);
    }

    const tabsCtl = MugenUI.tabs(tabItems, { onChange: (tab) => renderBody(tab) });
    root.appendChild(tabsCtl.bar);
    root.appendChild(body);
    requestAnimationFrame(tabsCtl.moveIndicator);

    renderBody(tabsCtl.active, { bisaDariCache: true });
  }

  return { render };
})();

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js (pola
// sama seperti pages/absensi.js dst) -- ekspos eksplisit ke window supaya
// page_loader.js bisa memverifikasi modul benar-benar berhasil dimuat.
window.PageWhatsapp = PageWhatsapp;
