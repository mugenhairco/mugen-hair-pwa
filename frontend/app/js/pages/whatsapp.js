// pages/whatsapp.js — Notifikasi WhatsApp Otomatis Booking
// =============================================================================
// REVISI (feedback Owner): SEBELUMNYA tab "WhatsApp" di dalam Setting --
// dipindah jadi menu utama sidebar sendiri (lihat nav.js/router.js), supaya
// lebih mudah ditemukan. Isi & perilaku PERSIS SAMA (KHUSUS Owner, backend
// require_admin -- token Fonnte adalah kredensial pihak ketiga milik TOKO
// ini sendiri, tidak didelegasikan ke staff lewat Hak Akses Admin, sama
// seperti dulu di dalam Setting), murni dipindah lokasinya.

const PageWhatsapp = (() => {
  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "WhatsApp"));

    const card = MugenUI.el("div", { class: "card" });
    root.appendChild(card);
    card.appendChild(MugenUI.el("h2", {}, "Notifikasi WhatsApp Booking"));
    card.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Kirim pesan WhatsApp otomatis ke customer dari nomor WhatsApp toko ini sendiri, lewat Fonnte (fonnte.com): " +
      "saat customer memilih pembayaran QRIS (reminder segera bayar), saat pembayaran diverifikasi (manual maupun " +
      "otomatis lewat Payment Gateway), dan saat booking dibatalkan karena belum dibayar."));

    // AUDIT (enforcement paket/subscription): tab ini digerbang fitur
    // "whatsapp_reminder" (backend juga menggerbang GET/PUT
    // /api/pengaturan/whatsapp + POST .../tes) -- pola sama seperti
    // Absensi/Log Error, halaman tetap tampil (judul di atas) tapi isinya
    // diganti blok upgrade.
    if (typeof MugenFeature !== "undefined" && !MugenFeature.has("whatsapp_reminder")) {
      card.appendChild(MugenFeature.upgradeBlock("Notifikasi WhatsApp"));
      return;
    }

    let s;
    try {
      s = await MugenApi.get("/api/pengaturan/whatsapp");
    } catch (e) {
      card.appendChild(MugenUI.errorState(e.message));
      return;
    }

    card.appendChild(MugenUI.el("div", { class: "badge " + (s.aktif ? "badge-success" : "badge-libur"),
      style: "margin-bottom:12px;" }, s.aktif ? "Aktif" : "Belum Diaktifkan"));

    card.appendChild(MugenUI.el("label", {}, "Token API Fonnte"));
    const inputToken = MugenUI.el("input", { type: "text", value: s.fonnte_token || "",
      placeholder: "Tempel token dari dashboard Fonnte Anda" });
    card.appendChild(inputToken);
    card.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:4px;" },
      "Hubungkan nomor WhatsApp toko Anda ke Fonnte (scan QR di dashboard Fonnte), lalu tempel token API-nya di sini."));

    const errorBox = MugenUI.el("div", { class: "login-error" });
    const btnSimpan = MugenUI.el("button", { class: "btn-primary" }, "Simpan Token");
    card.appendChild(errorBox);
    card.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpan));

    btnSimpan.addEventListener("click", async () => {
      errorBox.textContent = "";
      try {
        await MugenUI.withButtonLoading(btnSimpan, () => MugenApi.put("/api/pengaturan/whatsapp", { fonnte_token: inputToken.value.trim() }));
        MugenUI.toast("Token WhatsApp disimpan.", "success");
        render(root);
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
    root.appendChild(templateCard);
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

  return { render };
})();

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js (pola
// sama seperti pages/absensi.js dst) -- ekspos eksplisit ke window supaya
// page_loader.js bisa memverifikasi modul benar-benar berhasil dimuat.
window.PageWhatsapp = PageWhatsapp;
