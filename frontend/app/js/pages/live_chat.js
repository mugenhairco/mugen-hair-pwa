// pages/live_chat.js — FITUR BARU Live Chat: Inbox WhatsApp customer
// terintegrasi, dua arah (lihat docstring backend live_chat_db.py untuk
// arsitektur lengkap -- token Fonnte yang SAMA dengan menu WhatsApp dipakai
// untuk membalas, BUKAN jalur kirim baru).
//
// Layout: kartu Setting (Webhook URL, dipasang Owner sendiri di dashboard
// Fonnte-nya) di atas, lalu 2 kolom -- daftar kontak (kiri) + thread chat
// kontak yang sedang dibuka (kanan). Membuka sebuah thread otomatis
// menandai SEMUA pesan di thread itu "dibuka di Rivoir" (lihat GET
// /api/live-chat/pesan/{nomor_wa} di backend) -- inilah yang memicu
// hitung mundur retensi otomatis (gambar 24 jam, teks 7 hari, PERMINTAAN
// Owner: pesan yang belum pernah dibuka TIDAK PERNAH dihapus).

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

  async function _renderSettingWebhook(card) {
    const body = MugenUI.el("div");
    card.appendChild(body);
    body.appendChild(MugenUI.el("div", { class: "subtitle" }, "Memuat..."));
    const info = await MugenApi.get("/api/live-chat/webhook-info");
    body.innerHTML = "";
    const urlLengkap = (MugenApi.baseUrl || "") + info.webhook_path;
    const inputUrl = MugenUI.el("input", { type: "text", readonly: "readonly", value: urlLengkap, style: "flex:1;" });
    const btnSalin = MugenUI.el("button", {}, "Salin");
    btnSalin.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(urlLengkap);
        MugenUI.toast("URL disalin.", "success");
      } catch (e) {
        inputUrl.select();
        MugenUI.toast("Gagal menyalin otomatis -- URL sudah dipilih, salin manual (Ctrl+C).", "error");
      }
    });
    const btnReset = MugenUI.el("button", { class: "btn-danger" }, "Buat URL Baru");
    btnReset.addEventListener("click", async () => {
      if (!(await MugenUI.confirmModal({
        message: "URL webhook lama akan BERHENTI berfungsi -- pastikan langsung pasang URL baru di dashboard Fonnte Anda. Lanjutkan?",
        danger: true,
      }))) return;
      const baru = await MugenUI.withButtonLoading(btnReset, () => MugenApi.post("/api/live-chat/webhook-info/reset", {}));
      inputUrl.value = (MugenApi.baseUrl || "") + baru.webhook_path;
      MugenUI.toast("URL webhook baru dibuat.", "success");
    });
    body.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:8px;" },
      "Pasang URL ini di dashboard Fonnte Anda (Device > Edit > Webhook) supaya pesan customer otomatis masuk ke sini."));
    body.appendChild(MugenUI.el("div", { class: "row", style: "gap:8px;" }, [inputUrl, btnSalin, btnReset]));
  }

  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.pageTitle("Live Chat", MugenIcons.liveChat));

    const settingCard = MugenUI.el("div", { class: "card" }, [
      MugenUI.el("h2", {}, "Webhook Fonnte"),
    ]);
    root.appendChild(settingCard);
    _renderSettingWebhook(settingCard);

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

  return { render, suntikPesanMasuk };
})();
window.PageLiveChat = PageLiveChat;
