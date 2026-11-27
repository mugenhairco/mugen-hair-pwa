// pages/live_chat.js — FITUR BARU Live Chat: Inbox WhatsApp customer
// terintegrasi, dua arah (lihat docstring backend live_chat_db.py untuk
// arsitektur lengkap -- PERMINTAAN Owner: HANYA lewat koneksi WhatsApp Web
// sendiri/Baileys, jalur webhook Fonnte sudah dihapus total).
//
// Layout: kartu "Hubungkan WhatsApp" (status/QR Baileys) di atas, lalu 2
// kolom -- daftar kontak (kiri) + thread chat kontak yang sedang dibuka
// (kanan). Membuka sebuah thread otomatis menandai SEMUA pesan di thread
// itu "dibuka di Rivoir" (lihat GET /api/live-chat/pesan/{nomor_wa} di
// backend) -- inilah yang memicu hitung mundur retensi otomatis (gambar 24
// jam, teks 7 hari, PERMINTAAN Owner: pesan yang belum pernah dibuka TIDAK
// PERNAH dihapus).

const PageLiveChat = (() => {
  let _kontakList = [];
  let _nomorAktif = null;
  let _elemKontakList = null;
  let _elemThread = null;
  let _elemInputBalas = null;

  function _formatWaktu(iso) {
    if (!iso) return "";
    const d = new Date(iso.replace(" ", "T"));
    if (isNaN(d.getTime())) return "";
    const sekarang = new Date();
    const sameDay = d.toDateString() === sekarang.toDateString();
    const jam = d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
    if (sameDay) return jam;
    return d.toLocaleDateString("id-ID", { day: "2-digit", month: "short" }) + " " + jam;
  }

  async function _muatKontak() {
    _kontakList = await MugenApi.get("/api/live-chat/kontak");
    _renderKontakList();
  }

  function _renderKontakList() {
    _elemKontakList.innerHTML = "";
    if (!_kontakList.length) {
      _elemKontakList.appendChild(MugenUI.el("div", { class: "subtitle", style: "padding:16px;" },
        "Belum ada pesan masuk."));
      return;
    }
    for (const k of _kontakList) {
      const aktif = k.nomor_wa === _nomorAktif;
      const item = MugenUI.el("div", {
        class: "live-chat-kontak-item" + (aktif ? " active" : ""),
        onclick: () => _bukaThread(k.nomor_wa),
      }, [
        MugenUI.el("div", { class: "live-chat-kontak-top" }, [
          MugenUI.el("span", { class: "live-chat-kontak-nama" }, k.nama_kontak || k.nomor_wa),
          MugenUI.el("span", { class: "live-chat-kontak-waktu" }, _formatWaktu(k.waktu_terakhir)),
        ]),
        MugenUI.el("div", { class: "live-chat-kontak-preview" }, k.preview || ""),
      ]);
      if (k.belum_dibuka > 0) {
        item.appendChild(MugenUI.el("span", { class: "badge badge-success live-chat-kontak-badge" }, String(k.belum_dibuka)));
      }
      _elemKontakList.appendChild(item);
    }
  }

  async function _bungkusGambar(p) {
    const wrap = MugenUI.el("div", { class: "live-chat-bubble-img-wrap" },
      MugenUI.el("div", { class: "subtitle" }, "Memuat gambar..."));
    try {
      const blob = await MugenApi.fetchBlob(`/api/live-chat/gambar/${p.id}`);
      const url = URL.createObjectURL(blob);
      wrap.innerHTML = "";
      wrap.appendChild(MugenUI.el("img", { src: url, class: "live-chat-bubble-img", alt: "Gambar" }));
    } catch (e) {
      wrap.innerHTML = "";
      wrap.appendChild(MugenUI.el("div", { class: "subtitle" }, "Gagal memuat gambar."));
    }
    return wrap;
  }

  async function _bangunBubble(p) {
    const bubble = MugenUI.el("div", {
      class: "live-chat-bubble live-chat-bubble--" + (p.arah === "keluar" ? "keluar" : "masuk"),
    });
    if (p.jenis === "gambar") bubble.appendChild(await _bungkusGambar(p));
    else bubble.appendChild(MugenUI.el("div", { class: "live-chat-bubble-teks" }, p.isi_teks || ""));
    bubble.appendChild(MugenUI.el("div", { class: "live-chat-bubble-waktu" }, _formatWaktu(p.waktu)));
    return bubble;
  }

  async function _renderThread(pesanList) {
    _elemThread.innerHTML = "";
    for (const p of pesanList) {
      _elemThread.appendChild(await _bangunBubble(p));
    }
    _elemThread.scrollTop = _elemThread.scrollHeight;
  }

  async function _bukaThread(nomor) {
    _nomorAktif = nomor;
    _renderKontakList();
    _elemThread.innerHTML = "";
    _elemThread.appendChild(MugenUI.el("div", { style: "display:flex;justify-content:center;padding:32px 0;" },
      MugenUI.loadingRing(56).el));
    const pesan = await MugenApi.get(`/api/live-chat/pesan/${encodeURIComponent(nomor)}`);
    if (_nomorAktif !== nomor) return; // user sudah pindah ke kontak lain sebelum fetch ini selesai
    await _renderThread(pesan);
    _muatKontak(); // thread ini baru saja ditandai dibuka di backend -- segarkan badge unread
  }

  async function _kirimBalasan(btnKirim) {
    if (!_nomorAktif) return;
    const teks = _elemInputBalas.value.trim();
    if (!teks) return;
    try {
      await MugenUI.withButtonLoading(btnKirim, () =>
        MugenApi.post(`/api/live-chat/kirim/${encodeURIComponent(_nomorAktif)}`, { pesan: teks }));
      _elemInputBalas.value = "";
      _elemThread.appendChild(await _bangunBubble({
        arah: "keluar", jenis: "teks", isi_teks: teks, waktu: new Date().toISOString(),
      }));
      _elemThread.scrollTop = _elemThread.scrollHeight;
    } catch (e) {
      MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
    }
  }

  // Dipanggil app.js saat push "live_chat_masuk" diterima SEMENTARA halaman
  // ini sedang terbuka (lihat catatan panjang pola sama di app.js dekat
  // "pos_draft_berubah") -- kalau thread kontak ini SEDANG dibuka, muat
  // ulang thread itu (sekaligus memicu tandai_dibuka() backend supaya
  // retensi tetap berjalan untuk pesan yang baru masuk ini); kalau tidak,
  // cukup segarkan daftar kontak (preview+badge unread).
  function suntikPesanMasuk(data) {
    if (!data || !_elemKontakList) return;
    if (_nomorAktif && data.nomor_wa === _nomorAktif) {
      _bukaThread(_nomorAktif);
    } else {
      _muatKontak();
    }
  }

  // FITUR Live Chat via Baileys (PERMINTAAN Owner: HANYA lewat koneksi
  // WhatsApp Web sendiri -- jalur Fonnte sudah dihapus total, lihat
  // docstring backend live_chat_baileys_db.py). Polling status tiap 3
  // detik, berhenti sendiri begitu kartu ini sudah tidak ada di DOM lagi
  // (pola SAMA PERSIS pollTimer di pages/booking.js -- cek
  // document.body.contains(), bukan listener hashchange terpisah).
  async function _renderKartuBaileys(card) {
    const body = MugenUI.el("div");
    card.appendChild(body);

    async function muatUlang() {
      let status;
      try {
        status = await MugenApi.get("/api/live-chat/baileys/status");
      } catch (e) {
        return; // gagal diam-diam, polling berikutnya coba lagi
      }
      body.innerHTML = "";

      if (status.status === "tersambung") {
        body.appendChild(MugenUI.el("div", { style: "font-weight:700;color:var(--accent);margin-bottom:8px;" },
          `Tersambung sebagai ${status.nomor_tersambung || "-"}`));
        const btnPutus = MugenUI.el("button", { class: "btn-danger" }, "Putuskan");
        btnPutus.addEventListener("click", async () => {
          if (!(await MugenUI.confirmModal({
            message: "WhatsApp toko akan diputus dari Rivoir -- Live Chat tidak bisa kirim/terima pesan sampai dihubungkan lagi. Lanjutkan?",
            danger: true,
          }))) return;
          await MugenUI.withButtonLoading(btnPutus, () => MugenApi.post("/api/live-chat/baileys/putuskan", {}));
          await muatUlang();
        });
        body.appendChild(btnPutus);
        return;
      }

      if (status.status === "menunggu_scan") {
        body.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:8px;" },
          "Buka WhatsApp di HP toko -> Pengaturan -> Perangkat Tertaut -> Tautkan Perangkat, lalu arahkan kamera ke kode ini."));
        try {
          const blob = await MugenApi.fetchBlob("/api/live-chat/baileys/qr.png");
          const url = URL.createObjectURL(blob);
          body.appendChild(MugenUI.el("img", { src: url, alt: "Kode QR WhatsApp", style: "width:220px;height:220px;" }));
        } catch (e) {
          body.appendChild(MugenUI.el("div", { class: "subtitle" }, "Kode QR belum siap, menunggu..."));
        }
        return;
      }

      // belum_terhubung / terputus
      body.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:8px;" },
        "Hubungkan WhatsApp toko dulu sebelum bisa kirim/terima pesan di Live Chat -- termasuk pesan " +
        "yang diketik manual dari HP toko (bukan lewat kotak balas di bawah)."));
      const btnHubung = MugenUI.el("button", { class: "btn-primary" }, "Hubungkan WhatsApp Toko");
      btnHubung.addEventListener("click", async () => {
        try {
          await MugenUI.withButtonLoading(btnHubung, () => MugenApi.post("/api/live-chat/baileys/connect", {}));
        } catch (e) {
          MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
          return;
        }
        await muatUlang();
      });
      body.appendChild(btnHubung);
    }

    await muatUlang();
    const timer = setInterval(() => {
      if (!document.body.contains(card)) { clearInterval(timer); return; }
      muatUlang();
    }, 3000);
  }

  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.pageTitle("Live Chat", MugenIcons.liveChat));

    const baileysCard = MugenUI.el("div", { class: "card" }, [
      MugenUI.el("h2", {}, "Hubungkan WhatsApp"),
    ]);
    root.appendChild(baileysCard);
    _renderKartuBaileys(baileysCard);

    const layout = MugenUI.el("div", { class: "card live-chat-layout" });
    _elemKontakList = MugenUI.el("div", { class: "live-chat-kontak-list" });
    const kananCol = MugenUI.el("div", { class: "live-chat-kanan" });
    _elemThread = MugenUI.el("div", { class: "live-chat-thread" },
      MugenUI.el("div", { class: "subtitle", style: "padding:32px;text-align:center;" }, "Pilih kontak di sebelah kiri."));
    _elemInputBalas = MugenUI.el("textarea", { rows: "2", placeholder: "Tulis balasan..." });
    const btnKirim = MugenUI.el("button", { class: "btn-primary" }, "Kirim");
    btnKirim.addEventListener("click", () => _kirimBalasan(btnKirim));
    const formBalas = MugenUI.el("div", { class: "live-chat-form-balas" }, [_elemInputBalas, btnKirim]);
    kananCol.appendChild(_elemThread);
    kananCol.appendChild(formBalas);
    layout.appendChild(_elemKontakList);
    layout.appendChild(kananCol);
    root.appendChild(layout);

    _nomorAktif = null;
    await _muatKontak();
  }

  // BUGFIX (laporan Owner: pesan baru tidak langsung muncul walau halaman
  // Live Chat SUDAH terbuka -- harus pindah menu dulu baru kelihatan):
  // dipastikan perangkat Owner PWA iOS ("Add to Home Screen") -- iOS
  // SECARA AGRESIF membekukan JavaScript halaman begitu PWA tidak di
  // depan mata (layar terkunci/app dipindah ke background). Push
  // notifikasinya SENDIRI terkirim normal (dipastikan lewat log server --
  // tidak ada error), tapi listener "message" di app.js (yang biasanya
  // menyuntik pesan baru lewat suntikPesanMasuk()) tidak sempat berjalan
  // karena halamannya sedang "dibekukan" saat itu. SATU listener
  // document-level ini didaftarkan SEKALI untuk sisa umur SPA (bukan tiap
  // render() -- supaya tidak menumpuk listener kalau Owner bolak-balik ke
  // menu ini), menyegarkan diam-diam begitu halaman terlihat lagi (dicek
  // _elemKontakList masih di DOM -- no-op kalau bukan Live Chat yang lagi
  // aktif) -- Owner TIDAK perlu pindah menu lagi, cukup membuka kembali
  // layar HP/PWA-nya.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    if (!_elemKontakList || !document.body.contains(_elemKontakList)) return;
    _muatKontak();
    if (_nomorAktif) _bukaThread(_nomorAktif);
  });

  return { render, suntikPesanMasuk };
})();
window.PageLiveChat = PageLiveChat;
