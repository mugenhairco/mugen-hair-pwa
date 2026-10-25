// billing_checkout_shared.js — FITUR Notifikasi H-7 & Perpanjangan Cepat
// (diminta Owner): alur checkout SNAP Advance (pilih channel VA/QRIS ->
// POST checkout -> modal VA/QR + countdown + polling status) SEBELUMNYA
// hanya ada di pages/billing.js (mulaiCheckout()/pilihChannelModal()) --
// DIPINDAH ke sini APA ADANYA (TIDAK ADA perubahan logika) supaya halaman
// BARU pages/perpanjangan.js (Owner ATAU Staff/role custom, lihat
// routers/billing.py::renewal_checkout()) bisa memakai alur checkout YANG
// SAMA PERSIS tanpa duplikasi ~170 baris kode, murni beda endpoint target
// (/api/billing/checkout vs /api/billing/renewal-checkout, lihat parameter
// `endpoint` di jalankanCheckout() di bawah). pages/billing.js SENDIRI
// diubah memanggil modul ini (lihat perubahannya di sana), BUKAN lagi
// definisi lokal.
const MugenBillingCheckout = (() => {
  function pesanError(e) {
    return (e && e.detail && e.detail.detail) ? e.detail.detail : (e.message || "Terjadi kesalahan.");
  }

  let _snapLoadPromise = null;
  function muatSnapJs(src, clientKey) {
    if (window.snap) return Promise.resolve();
    if (_snapLoadPromise) return _snapLoadPromise;
    _snapLoadPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.setAttribute("data-client-key", clientKey);
      script.onload = () => resolve();
      script.onerror = () => {
        _snapLoadPromise = null;
        reject(new Error("Gagal memuat modul pembayaran. Periksa koneksi internet Anda."));
      };
      document.head.appendChild(script);
    });
    return _snapLoadPromise;
  }

  function pilihChannelModal(channelAktif, vaBankAktif) {
    const kodeBankList = Object.keys(vaBankAktif || {});
    const adaQris = channelAktif.includes("qris");
    if (channelAktif.includes("va") && kodeBankList.length === 1 && !adaQris) {
      return Promise.resolve({ channel: "va", bankCode: kodeBankList[0] });
    }
    if (adaQris && !channelAktif.includes("va") && channelAktif.length === 1) {
      return Promise.resolve({ channel: "qris", bankCode: null });
    }
    return new Promise((resolve) => {
      const overlay = MugenUI.el("div", { class: "modal-overlay" });
      const box = MugenUI.el("div", { class: "modal-box" });
      box.appendChild(MugenUI.el("h3", {}, "Pilih Metode Pembayaran"));
      overlay.appendChild(box);
      function tutup(hasil) {
        overlay.classList.add("closing");
        setTimeout(() => { overlay.remove(); resolve(hasil); }, 120);
      }
      if (channelAktif.includes("va") && kodeBankList.length) {
        box.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:4px;" }, "Virtual Account"));
        const grid = MugenUI.el("div", { class: "bank-grid" });
        for (const kode of kodeBankList) {
          const card = MugenUI.el("button", { type: "button", class: "bank-card" },
            [MugenUI.bankLogoBadge(kode), MugenUI.el("span", {}, MugenUI.bankNamaLengkap(kode, vaBankAktif[kode]))]);
          card.addEventListener("click", () => tutup({ channel: "va", bankCode: kode }));
          grid.appendChild(card);
        }
        box.appendChild(grid);
      }
      if (adaQris) {
        box.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:14px;" }, "E-Wallet"));
        const btnQris = MugenUI.el("button", { type: "button", class: "book-metode-btn", style: "margin-top:6px;" }, "QRIS");
        btnQris.addEventListener("click", () => tutup({ channel: "qris", bankCode: null }));
        box.appendChild(btnQris);
      }
      const btnBatal = MugenUI.el("button", { type: "button" }, "Batal");
      btnBatal.addEventListener("click", () => tutup(null));
      box.appendChild(MugenUI.el("div", { class: "modal-actions", style: "margin-top:14px;" }, [btnBatal]));
      document.body.appendChild(overlay);
      overlay.addEventListener("click", (e) => { if (e.target === overlay) tutup(null); });
    });
  }

  // `endpoint` (BARU): `/api/billing/checkout` (default, Owner-only, pola
  // LAMA) atau `/api/billing/renewal-checkout` (Owner ATAU Staff/role
  // custom, hanya paket sekarang/di atasnya -- lihat pages/perpanjangan.js).
  async function jalankanCheckout({ packageId, siklus, config, onSelesai, btnPemicu, endpoint = "/api/billing/checkout" }) {
    const pilihan = await pilihChannelModal(config.channel_aktif || [], config.va_bank_aktif || {});
    if (!pilihan) return;
    const { channel, bankCode } = pilihan;
    let invoice;
    try {
      invoice = await MugenUI.withLoading(
        () => MugenApi.post(endpoint, {
          package_id: packageId, siklus: siklus || "bulanan", channel, bank_code: bankCode,
        }),
        { message: "Menyiapkan pembayaran…" },
      );
    } catch (e) {
      MugenUI.toast(pesanError(e), "error");
      return;
    }

    async function segarkanLaluSelesai() {
      await MugenSubscription.refresh();
      onSelesai();
    }

    if (config.checkout_script_url && config.client_key) {
      try {
        await muatSnapJs(config.checkout_script_url, config.client_key);
      } catch (e) {
        MugenUI.toast(e.message, "error");
        return;
      }
      window.snap.pay(invoice.snap_token, {
        onSuccess: () => {
          MugenUI.toast("Pembayaran berhasil, memperbarui status langganan…", "info", { force: true });
          setTimeout(segarkanLaluSelesai, 2000);
        },
        onPending: () => {
          MugenUI.toast("Pembayaran sedang diproses -- paket akan aktif otomatis setelah dikonfirmasi.", "info", { force: true });
          segarkanLaluSelesai();
        },
        onError: () => {
          MugenUI.toast("Pembayaran gagal. Silakan coba lagi.", "error");
          onSelesai();
        },
        onClose: onSelesai,
      });
      return;
    }

    const kontenModal = [];
    if (invoice.channel === "va") {
      kontenModal.push(MugenUI.el("div", { class: "subtitle" },
        invoice.channel_code ? `Virtual Account ${MugenUI.bankNamaLengkap(invoice.channel_code, invoice.va_bank_label)}` : "Virtual Account"));
      kontenModal.push(MugenUI.el("div", { style: "font-size:22px;font-weight:700;letter-spacing:1px;margin-top:4px;" }, invoice.va_number || "-"));
      kontenModal.push(MugenUI.el("div", { class: "subtitle", style: "margin-top:8px;" },
        "Transfer PERSIS sejumlah tagihan ini ke nomor Virtual Account di atas lewat m-banking/ATM."));
    } else if (invoice.channel === "qris" && invoice.qr_url) {
      kontenModal.push(MugenUI.el("img", { src: invoice.qr_url, alt: "QRIS", style: "max-width:240px;width:100%;" }));
      kontenModal.push(MugenUI.el("div", { class: "subtitle", style: "margin-top:8px;" },
        "Scan kode QR di atas lewat app e-wallet/m-banking mana pun yang mendukung QRIS."));
    }

    const countdownEl = MugenUI.el("div", { class: "book-countdown", style: "margin:12px auto 0;" }, "15:00");
    const statusLabelEl = MugenUI.el("div", { class: "subtitle", style: "margin-top:8px;min-height:18px;" }, "");
    const btnSudahBayar = MugenUI.el("button", { type: "button", style: "margin-top:6px;" }, "Saya Sudah Bayar");
    kontenModal.push(MugenUI.el("div", { style: "margin-top:6px;" }, [countdownEl, statusLabelEl, btnSudahBayar]));

    const modalRef = MugenUI.infoModal({ title: "Selesaikan Pembayaran", body: MugenUI.el("div", { style: "text-align:center;" }, kontenModal) });
    MugenUI.toast("Status langganan akan diperbarui otomatis di sini setelah pembayaran dikonfirmasi.", "info", { force: true });

    const deadlineCountdown = Date.now() + 15 * 60 * 1000;
    const countdownTimer = setInterval(() => {
      if (!document.body.contains(countdownEl)) { clearInterval(countdownTimer); return; }
      const sisaMs = deadlineCountdown - Date.now();
      if (sisaMs <= 0) { clearInterval(countdownTimer); countdownEl.textContent = "00:00"; return; }
      const sisaDetik = Math.floor(sisaMs / 1000);
      const mm = String(Math.floor(sisaDetik / 60)).padStart(2, "0");
      const ss = String(sisaDetik % 60).padStart(2, "0");
      countdownEl.textContent = `${mm}:${ss}`;
      countdownEl.classList.toggle("book-countdown-urgent", sisaDetik < 60);
    }, 1000);

    function terapkanStatusInvoice(statusInvoice) {
      if (statusInvoice === "paid") {
        clearInterval(pollTimer);
        clearInterval(countdownTimer);
        modalRef.close();
        MugenUI.toast("Pembayaran berhasil, memperbarui status langganan…", "info", { force: true });
        segarkanLaluSelesai();
        return true;
      }
      if (["denied", "cancelled", "expired"].includes(statusInvoice)) {
        clearInterval(pollTimer);
        clearInterval(countdownTimer);
        modalRef.close();
        MugenUI.toast("Pembayaran tidak berhasil. Silakan coba lagi.", "error");
        onSelesai();
        return true;
      }
      return false;
    }

    btnSudahBayar.addEventListener("click", async () => {
      if (!document.body.contains(btnSudahBayar)) return;
      try {
        await MugenUI.withButtonLoading(btnSudahBayar,
          () => MugenApi.post(`/api/billing/invoices/${invoice.id}/cek-ulang`));
      } catch (e) {
        MugenUI.toast(pesanError(e), "error");
        return;
      }
      let terbaru;
      try {
        terbaru = await MugenApi.get(`/api/billing/invoices/${invoice.id}`);
      } catch (e) {
        return;
      }
      if (!terapkanStatusInvoice(terbaru.status)) {
        statusLabelEl.textContent = "Pembayaran belum terdeteksi -- coba lagi setelah Anda menyelesaikan pembayaran.";
      }
    });

    let sisaPercobaan = 150; // ~150 x 4 detik = 10 menit
    const pollTimer = setInterval(async () => {
      if (btnPemicu && !document.body.contains(btnPemicu)) { clearInterval(pollTimer); return; }
      sisaPercobaan -= 1;
      if (sisaPercobaan <= 0) { clearInterval(pollTimer); return; }
      let terbaru;
      try {
        terbaru = await MugenApi.get(`/api/billing/invoices/${invoice.id}`);
      } catch (e) {
        return;
      }
      terapkanStatusInvoice(terbaru.status);
    }, 4000);
  }

  return { pesanError, pilihChannelModal, jalankanCheckout };
})();
// BUGFIX (Billing/Perpanjangan gagal dimuat produksi): expose eksplisit ke
// window -- top-level `const` di script biasa (BUKAN module) TIDAK membuat
// properti di window, padahal page_loader.js::ensure() mengecek
// window[globalName] untuk memastikan modul benar-benar sudah dimuat
// sebelum dipakai (lihat pola SAMA PERSIS di akhir pages/billing.js dst).
window.MugenBillingCheckout = MugenBillingCheckout;
