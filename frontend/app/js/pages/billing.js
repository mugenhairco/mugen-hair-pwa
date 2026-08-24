// pages/billing.js — FONDASI Multi-Tenant Phase 4: Billing & Payment Gateway
// =============================================================================
// Halaman BARU, KHUSUS Owner (require_admin, sama seperti Setting > Subscription
// Phase 3 -- staff TIDAK ikut melihat, lihat nav.js) -- TERPISAH TOTAL dari tab
// "Subscription" read-only di pages/pengaturan.js (Phase 3, TIDAK diubah sama
// sekali di sini): paket aktif + periode + status, katalog paket untuk upgrade/
// downgrade/perpanjang, checkout Payment Gateway hosted, riwayat invoice/pembayaran.
//
// PROVIDER RESMI: Faspay SNAP Advance (payment_provider_client.py, seam
// dinamis -- lihat catatan modul itu) -- checkout SEKARANG minta Owner
// memilih channel (VA/QRIS, lihat pilihChannelModal()) lalu menampilkan
// nomor VA/kode QR LANGSUNG di modal (infoModal()), TIDAK ADA halaman
// hosted sama sekali (config.checkout_script_url/client_key SELALU null,
// SNAP tidak punya JS SDK, sama seperti Xpress v4 sebelumnya). Cabang
// window.snap.pay() DIPERTAHANKAN sebagai jalur adapter generik (script
// dimuat DINAMIS, bukan <script> tetap di index.html -- proyek ini sengaja
// tanpa bundler/CDN tetap apa pun, lihat README) kalau kelak provider lain
// yang punya script checkout dipasang -- TIDAK PERNAH dipakai untuk SNAP.

const PageBilling = (() => {
  const LABEL_PACKAGE = { free: "Free", basic: "Basic", pro: "Pro", enterprise: "Enterprise" };
  const LABEL_STATUS_SUB = {
    trial: "Trial", active: "Aktif", grace_period: "Grace Period",
    expired: "Kedaluwarsa", suspended: "Ditangguhkan", cancelled: "Dibatalkan",
  };
  const BADGE_STATUS_SUB = {
    trial: "badge-libur", active: "badge-success", grace_period: "badge-warning",
    expired: "badge-danger", suspended: "badge-danger", cancelled: "badge-danger",
  };
  const LABEL_STATUS_INVOICE = {
    pending: "Menunggu Pembayaran", paid: "Berhasil", denied: "Ditolak",
    cancelled: "Dibatalkan", expired: "Kedaluwarsa",
  };
  const BADGE_STATUS_INVOICE = {
    pending: "badge-warning", paid: "badge-success", denied: "badge-danger",
    cancelled: "badge-danger", expired: "badge-danger",
  };

  function formatWaktu(iso) {
    if (!iso) return "-";
    const [tanggal, jam] = iso.split("T");
    return `${MugenUI.formatTanggal(tanggal)} ${jam || ""}`.trim();
  }

  // Invoice PAID paling baru yang periode_selesai-nya masih di masa depan
  // -- SATU-SATUNYA sumber "periode aktif sekarang" di frontend (backend
  // TIDAK menyimpan tanggal ini di tenant_subscriptions sama sekali, lihat
  // catatan panjang di billing_webhook.py soal alasannya).
  function invoicePeriodeAktif(invoices) {
    const now = new Date().toISOString();
    const kandidat = (invoices || []).filter((inv) => inv.status === "paid" && inv.periode_selesai && inv.periode_selesai > now);
    if (!kandidat.length) return null;
    return kandidat.reduce((a, b) => (a.periode_selesai > b.periode_selesai ? a : b));
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

  function pesanError(e) {
    return (e && e.detail && e.detail.detail) ? e.detail.detail : (e.message || "Terjadi kesalahan.");
  }

  // Migrasi Faspay SNAP Advance: billing SEBELUMNYA tidak pernah butuh
  // pilihan metode (Xpress v4 = satu jalur checkout hosted tunggal) --
  // SNAP butuh channel (VA/QRIS) dipilih di muka, TIDAK ADA modal generik
  // multi-pilihan di ui.js (hanya confirmModal ya/tidak) jadi dibangun
  // lokal di sini, pola overlay/box SAMA PERSIS MugenUI.confirmModal()
  // supaya tetap konsisten secara visual. Return Promise<string|null> --
  // null kalau Owner batal/klik di luar kotak. Auto-resolve TANPA
  // menampilkan modal kalau cuma satu channel aktif.
  function pilihChannelModal(channelAktif, vaLabel) {
    if (channelAktif.length === 1) return Promise.resolve(channelAktif[0]);
    const label = { va: vaLabel ? `Virtual Account (${vaLabel})` : "Virtual Account", qris: "QRIS" };
    return new Promise((resolve) => {
      const overlay = MugenUI.el("div", { class: "modal-overlay" });
      const box = MugenUI.el("div", { class: "modal-box" });
      box.appendChild(MugenUI.el("h3", {}, "Pilih Metode Pembayaran"));
      overlay.appendChild(box);
      function tutup(hasil) {
        overlay.classList.add("closing");
        setTimeout(() => { overlay.remove(); resolve(hasil); }, 120);
      }
      const tombolTombol = channelAktif.map((c) => {
        const btn = MugenUI.el("button", { type: "button", class: "btn-primary", style: "width:100%;margin-bottom:8px;" }, label[c] || c);
        btn.addEventListener("click", () => tutup(c));
        return btn;
      });
      box.appendChild(MugenUI.el("div", { style: "display:flex;flex-direction:column;margin-top:8px;" }, tombolTombol));
      const btnBatal = MugenUI.el("button", { type: "button" }, "Batal");
      btnBatal.addEventListener("click", () => tutup(null));
      box.appendChild(MugenUI.el("div", { class: "modal-actions" }, [btnBatal]));
      document.body.appendChild(overlay);
      overlay.addEventListener("click", (e) => { if (e.target === overlay) tutup(null); });
    });
  }

  function renderStatusCard(root, sub, invoices, packages, config) {
    const card = MugenUI.el("div", { class: "card" });
    root.appendChild(card);
    card.appendChild(MugenUI.el("h2", {}, "Paket & Status Langganan"));

    if (sub.akses_diblokir) {
      card.appendChild(MugenUI.el("div", { class: "login-error", style: "margin-bottom:12px;" },
        `Akses toko ini sedang dibatasi karena status subscription "${LABEL_STATUS_SUB[sub.status] || sub.status}". ` +
        "Selesaikan pembayaran di bawah untuk mengaktifkan kembali."));
    }
    if (!config.enabled) {
      card.appendChild(MugenUI.el("div", { class: "login-error", style: "margin-bottom:12px;" },
        "Pembayaran online belum aktif untuk toko ini -- hubungi penyedia layanan."));
    }

    const periodeAktif = invoicePeriodeAktif(invoices);
    const ringkasan = MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:24px;margin-bottom:8px;" }, [
      MugenUI.el("div", {}, [
        MugenUI.el("div", { class: "subtitle" }, "Paket"),
        MugenUI.el("div", { style: "font-weight:700;font-size:16px;" }, LABEL_PACKAGE[sub.package] || sub.package),
      ]),
      MugenUI.el("div", {}, [
        MugenUI.el("div", { class: "subtitle" }, "Status"),
        MugenUI.el("span", { class: "badge " + (BADGE_STATUS_SUB[sub.status] || "") },
          LABEL_STATUS_SUB[sub.status] || sub.status),
      ]),
      MugenUI.el("div", {}, [
        MugenUI.el("div", { class: "subtitle" }, "Periode Aktif Berakhir"),
        MugenUI.el("div", { style: "font-weight:700;" }, periodeAktif ? formatWaktu(periodeAktif.periode_selesai) : "-"),
      ]),
    ]);
    card.appendChild(ringkasan);
  }

  function _bersihkanPendingKode() {
    try {
      sessionStorage.removeItem("mugen_pending_package_kode");
      sessionStorage.removeItem("mugen_pending_package_siklus");
    } catch (e) { /* abaikan */ }
  }

  // FITUR Landing Page & Pricing (paket 6 bulan): siklus "bulanan" (default,
  // TIDAK mengubah perilaku lama) atau "6bulan" -- diteruskan APA ADANYA ke
  // body checkout, backend (routers/billing.py) yang menghitung harga/durasi
  // efektifnya (lihat komentar di sana), di sini murni meneruskan pilihan.
  async function mulaiCheckout(packageId, siklus, config, onSelesai, btnPemicu) {
    _bersihkanPendingKode();
    // Migrasi Faspay SNAP Advance: channel (VA/QRIS) WAJIB dipilih SEBELUM
    // memanggil checkout (SNAP tidak punya halaman hosted yang menawarkan
    // semua channel sekaligus seperti Xpress v4 dulu) -- lihat pilihChannelModal().
    const channel = await pilihChannelModal(config.channel_aktif || [], config.va_label);
    if (!channel) return;
    let invoice;
    try {
      invoice = await MugenUI.withLoading(
        () => MugenApi.post("/api/billing/checkout", { package_id: packageId, siklus: siklus || "bulanan", channel }),
        { message: "Menyiapkan pembayaran…" },
      );
    } catch (e) {
      MugenUI.toast(pesanError(e), "error");
      return;
    }

    // BUGFIX: MugenSubscription.refresh() WAJIB di-await SEBELUM onSelesai()
    // di jalur sukses/pending -- tanpa ini, cache localStorage akses_diblokir
    // (dipakai router.js::handle() untuk SETIAP perpindahan menu, lihat
    // subscription.js) tetap "diblokir" walau pembayaran sudah berhasil dan
    // webhook sudah mengaktifkan subscription-nya di backend, sehingga Owner
    // yang baru saja bayar masih dilempar ke halaman blocked begitu klik
    // menu lain -- padahal seharusnya langsung bisa masuk dashboard.
    async function segarkanLaluSelesai() {
      await MugenSubscription.refresh();
      onSelesai();
    }

    // PROVIDER RESMI: Faspay Xpress v4 -- checkout HANYA hosted redirect
    // (config.checkout_script_url selalu null, TIDAK ADA script/token
    // seperti Snap), jadi cabang window.snap.pay() di bawah TIDAK PERNAH
    // dipakai untuk Faspay -- dipertahankan sebagai jalur adapter generik
    // kalau provider lain (yang punya script checkout) dipasang nanti,
    // SAMA seperti pola bukaCheckoutGateway() di pages/book_public.js.
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

    // Migrasi Faspay SNAP Advance: VA/QRIS TIDAK PUNYA halaman hosted
    // seperti Xpress v4 dulu (window.open(snap_redirect_url)) -- nomor VA/
    // kode QR ditampilkan LANGSUNG lewat modal (MugenUI.infoModal(), pola
    // SAMA seperti isiKontenSnapWaiting() di pages/book_public.js).
    const kontenModal = [];
    if (invoice.channel === "va") {
      kontenModal.push(MugenUI.el("div", { class: "subtitle" }, config.va_label ? `Virtual Account (${config.va_label})` : "Virtual Account"));
      kontenModal.push(MugenUI.el("div", { style: "font-size:22px;font-weight:700;letter-spacing:1px;margin-top:4px;" }, invoice.va_number || "-"));
      kontenModal.push(MugenUI.el("div", { class: "subtitle", style: "margin-top:8px;" },
        "Transfer PERSIS sejumlah tagihan ini ke nomor Virtual Account di atas lewat m-banking/ATM."));
    } else if (invoice.channel === "qris" && invoice.qr_url) {
      kontenModal.push(MugenUI.el("img", { src: invoice.qr_url, alt: "QRIS", style: "max-width:240px;width:100%;" }));
      kontenModal.push(MugenUI.el("div", { class: "subtitle", style: "margin-top:8px;" },
        "Scan kode QR di atas lewat app e-wallet/m-banking mana pun yang mendukung QRIS."));
    }
    MugenUI.infoModal({ title: "Selesaikan Pembayaran", body: MugenUI.el("div", { style: "text-align:center;" }, kontenModal) });
    MugenUI.toast("Status langganan akan diperbarui otomatis di sini setelah pembayaran dikonfirmasi.", "info", { force: true });

    // Polling status invoice (READ-ONLY, sama pola dengan gateway-status di
    // book_public.js) -- status pembayaran SUNGGUHAN hanya pernah berubah
    // lewat webhook di backend, polling ini murni menunggu itu lalu
    // menyegarkan tampilan halaman ini. AUDIT (pre-merge): #app dibongkar
    // total (innerHTML="") setiap kali Owner pindah menu (lihat router.js::
    // shell()) -- TANPA guard ini, timer tetap menyala di background sampai
    // 10 menit walau Owner sudah meninggalkan halaman Billing, membuat
    // polling sia-sia (dan onSelesai() akhirnya me-render ULANG ke DOM
    // yatim yang sudah tidak terlihat). btnPemicu (tombol yang diklik) jadi
    // penanda "masih di halaman ini" -- begitu #app dibongkar, tombol itu
    // ikut lepas dari document, pola SAMA PERSIS dengan
    // document.body.contains(countdownEl) di book_public.js.
    let sisaPercobaan = 150; // ~150 x 4 detik = 10 menit
    const pollTimer = setInterval(async () => {
      if (btnPemicu && !document.body.contains(btnPemicu)) { clearInterval(pollTimer); return; }
      sisaPercobaan -= 1;
      if (sisaPercobaan <= 0) { clearInterval(pollTimer); return; }
      let terbaru;
      try {
        terbaru = await MugenApi.get(`/api/billing/invoices/${invoice.id}`);
      } catch (e) {
        return; // hiccup jaringan sesaat -- coba lagi di tick berikutnya
      }
      if (terbaru.status === "paid") {
        clearInterval(pollTimer);
        MugenUI.toast("Pembayaran berhasil, memperbarui status langganan…", "info", { force: true });
        segarkanLaluSelesai();
      } else if (["denied", "cancelled", "expired"].includes(terbaru.status)) {
        clearInterval(pollTimer);
        MugenUI.toast("Pembayaran tidak berhasil. Silakan coba lagi.", "error");
        onSelesai();
      }
    }, 4000);
  }

  async function mulaiDowngrade(btn, paket, onSelesai) {
    const ok = await MugenUI.confirmModal({
      title: "Downgrade Paket",
      message: `Pindah ke paket "${paket.nama}" sekarang? Perubahan berlaku langsung tanpa pembayaran.`,
      confirmText: "Ya, Downgrade",
    });
    if (!ok) return;
    _bersihkanPendingKode();
    try {
      // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading()
      // -- downgrade berlaku instan tanpa gateway pembayaran eksternal,
      // beda dari mulaiCheckout() di atas yang TETAP withLoading() (transisi
      // ke checkout hosted Payment Gateway, genuinely memblokir sampai modal
      // pembayaran siap).
      await MugenUI.withButtonLoading(btn, () => MugenApi.post("/api/billing/downgrade", { package_id: paket.id }));
      // Aksi besar/konfirmasi penting (perubahan paket langganan) -- toast
      // sukses SENGAJA ditampilkan (force:true), lihat whitelist di ui.js.
      MugenUI.toast(`Paket berhasil diubah ke "${paket.nama}".`, "success", { force: true });
    } catch (e) {
      MugenUI.toast(pesanError(e), "error");
      return;
    }
    onSelesai();
  }

  function kartuFitur(fitur) {
    if (!fitur || !fitur.length) return MugenUI.el("div", { class: "subtitle" }, "Tidak ada fitur tercatat.");
    const wrap = MugenUI.el("div", { style: "display:flex;flex-wrap:wrap;gap:6px;margin:10px 0;" });
    for (const f of fitur) wrap.appendChild(MugenUI.el("span", { class: "badge badge-libur" }, f.nama));
    return wrap;
  }

  // FITUR Landing Page & Pricing (Enterprise Exclusive): benefit "Custom
  // Feature Request" HANYA untuk paket kode "enterprise" -- murni tampilan,
  // pola SAMA PERSIS dengan frontend/js/landing.js::benefitEnterprise()
  // (versi Landing Page publik), disalin di sini pakai gaya inline yang
  // sudah dipakai file ini sendiri (BUKAN nambah class baru ke app/css/
  // style.css yang dipakai bersama seluruh halaman internal lain).
  function benefitEnterprise() {
    return MugenUI.el("div", {
      style: "background:var(--bg-input);border-radius:10px;padding:10px 12px;font-size:13px;color:var(--text-dim);margin:10px 0;line-height:1.5;",
    }, [
      MugenUI.el("span", {
        class: "badge", style: "background:var(--accent);color:#fff;margin-bottom:6px;display:inline-block;",
      }, "Enterprise Exclusive"),
      MugenUI.el("div", {}, [
        MugenUI.el("strong", { style: "color:var(--text);" }, "Custom Feature Request — "),
        "ajukan pengembangan fitur khusus sesuai kebutuhan bisnis Anda. Setiap permintaan melalui proses evaluasi (tidak otomatis disetujui), dan permintaan yang disetujui diprioritaskan untuk pelanggan Enterprise.",
      ]),
    ]);
  }

  // FITUR Landing Page & Pricing (paket 6 bulan): toggle Bulanan/6 Bulan --
  // gaya inline (bukan class app/css/style.css baru, pola sama seperti
  // benefitEnterprise() di atas) supaya perubahan tetap terkurung di file
  // Billing ini saja.
  function toggleSiklus(siklusAktif, onChange) {
    const wrap = MugenUI.el("div", {
      style: "display:inline-flex;gap:4px;background:var(--bg-input);border:1px solid var(--border);border-radius:999px;padding:4px;margin-bottom:16px;",
    });
    [["bulanan", "Bulanan"], ["6bulan", "6 Bulan · Hemat Lebih Banyak"], ["tahunan", "Tahunan · ⭐ Paling Hemat"]].forEach(([nilai, label]) => {
      const aktif = nilai === siklusAktif;
      const btn = MugenUI.el("button", {
        type: "button",
        style: "border:none;border-radius:999px;padding:8px 16px;font-weight:600;font-size:13px;cursor:pointer;"
          + (aktif ? "background:var(--accent);color:#fff;" : "background:transparent;color:var(--text-dim);"),
      }, label);
      btn.addEventListener("click", () => { if (nilai !== siklusAktif) onChange(nilai); });
      wrap.appendChild(btn);
    });
    return wrap;
  }

  function renderPaketCard(root, sub, config, packages, onSelesai) {
    const card = MugenUI.el("div", { class: "card" });
    root.appendChild(card);
    card.appendChild(MugenUI.el("h2", {}, "Pilih Paket"));
    card.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Upgrade langsung dibayar lewat Payment Gateway (VA/QRIS/kartu). Downgrade & Perpanjang paket yang sama TIDAK memerlukan pembayaran baru di sini kecuali memang paket berbayar."));

    const current = packages.find((p) => p.kode === sub.package) || null;

    // FONDASI Multi-Tenant Phase 5 (Landing Page SaaS): `pendingKode` (paket
    // yang diklik Owner di Landing Page, sessionStorage, lihat landing.js)
    // disorot/dipilih di sini supaya pilihannya tidak hilang begitu saja
    // setelah harus Register dulu. BUGFIX: SENGAJA TIDAK dihapus di sini
    // begitu dibaca -- register.js (sama seperti login.js) memanggil
    // location.hash= DAN MugenRouter.handle() eksplisit berurutan, yang
    // berarti halaman ini ter-render DUA KALI (sekali lewat pemanggilan
    // eksplisit, sekali lagi async lewat event "hashchange" yang otomatis
    // terpicu) -- kalau value ini dihapus pada render PERTAMA, render KEDUA
    // (yang akhirnya terlihat user) tidak akan menemukan apa pun lagi dan
    // badge "Pilihan Anda" tidak pernah tampak. Dibersihkan sebagai
    // gantinya begitu Owner benar-benar menekan salah satu tombol paket
    // (lihat mulaiCheckout()/mulaiDowngrade() di bawah), bukan di titik
    // render.
    let pendingKode = null;
    try {
      pendingKode = sessionStorage.getItem("mugen_pending_package_kode");
    } catch (e) { /* abaikan (mis. private mode) */ }

    // REVISI (diminta Owner): halaman Billing SELALU terbuka di tab Tahunan
    // sebagai tampilan awal -- TIDAK LAGI mengikuti siklus yang dibawa dari
    // Landing Page (`mugen_pending_package_siklus`, kode lama dihapus di
    // sini) apa pun asal Owner datang. Owner tetap bebas pindah ke Bulanan/
    // 6 Bulan manual kapan saja lewat toggle di bawah.
    let siklusAktif = "tahunan";
    const toggleWrap = MugenUI.el("div", {});
    const grid = MugenUI.el("div", { class: "grid-cards" });
    card.appendChild(toggleWrap);
    card.appendChild(grid);

    function gambarUlangToggle() {
      toggleWrap.innerHTML = "";
      toggleWrap.appendChild(toggleSiklus(siklusAktif, (nilai) => {
        siklusAktif = nilai;
        gambarUlangToggle();
        gambarUlangGrid();
      }));
    }

    function gambarUlangGrid() {
      grid.innerHTML = "";
      let boxDirekomendasikan = null;
      for (const paket of packages) {
        const isCurrent = paket.kode === sub.package;
        const isRekomendasi = !isCurrent && pendingKode && paket.kode === pendingKode;
        const box = MugenUI.el("div", {
          class: "card", style: "margin-bottom:0;" + (isCurrent ? "border-color:var(--accent);" : isRekomendasi ? "border-color:var(--accent-secondary);border-width:2px;" : ""),
        });
        box.appendChild(MugenUI.el("h2", {}, paket.nama));
        if (isRekomendasi) box.appendChild(MugenUI.el("span", { class: "badge badge-libur", style: "margin-bottom:8px;display:inline-block;" }, "Pilihan Anda"));

        // pakai6: paket ini BENAR-BENAR menampilkan harga 6 bulan sekarang --
        // hanya kalau toggle aktif "6bulan" DAN paket ini punya harga_6bulan
        // (paket Free/harga 0, atau belum diisi Super Admin, tetap
        // menampilkan harga bulanan apa adanya).
        const pakai6 = siklusAktif === "6bulan" && paket.harga > 0 && paket.harga_6bulan;
        // FITUR Landing Page & Pricing (paket Tahunan, diminta Owner): pola
        // SAMA PERSIS pakai6 di atas -- pakai6/pakaiTahunan SALING
        // EKSKLUSIF (siklusAktif hanya satu nilai), urutan cek tidak masalah.
        const pakaiTahunan = siklusAktif === "tahunan" && paket.harga > 0 && paket.harga_tahunan;
        const hargaTampil = pakai6 ? paket.harga_6bulan : pakaiTahunan ? paket.harga_tahunan : paket.harga;
        const hematRupiah = pakai6 ? (paket.harga * 6 - paket.harga_6bulan) : 0;
        // "Setara Rp X/bulan" -- dihitung langsung dari harga_tahunan/12,
        // ANGKA YANG SAMA PERSIS dikirim ke checkout (routers/billing.py),
        // tidak ada penyimpangan antara tampilan & harga yang dibayar.
        const efektifBulananTahunan = pakaiTahunan ? Math.round(paket.harga_tahunan / 12) : 0;
        // Badge: "⭐ Paling Hemat" KHUSUS mode Tahunan (BUKAN "Hemat Lebih
        // Banyak", itu badge toggle tab), mode 6 Bulan TETAP "Paling Hemat"
        // seperti sebelumnya (TIDAK diubah sama sekali).
        if (pakaiTahunan) {
          box.appendChild(MugenUI.el("span", {
            style: "background:var(--success);color:#fff;font-size:11px;font-weight:700;padding:3px 10px;border-radius:999px;margin-bottom:8px;display:inline-block;margin-left:8px;",
          }, "⭐ Paling Hemat"));
        } else if (pakai6 && hematRupiah > 0) {
          box.appendChild(MugenUI.el("span", {
            style: "background:var(--success);color:#fff;font-size:11px;font-weight:700;padding:3px 10px;border-radius:999px;margin-bottom:8px;display:inline-block;margin-left:8px;",
          }, "Paling Hemat"));
        }
        box.appendChild(MugenUI.el("div", { style: "font-size:20px;font-weight:700;" }, MugenUI.formatRupiah(hargaTampil)));
        box.appendChild(MugenUI.el("div", { class: "subtitle" }, pakai6 ? "per 6 bulan" : pakaiTahunan ? "per tahun" : `per ${paket.durasi_hari} hari`));
        if (pakai6 && hematRupiah > 0) {
          box.appendChild(MugenUI.el("div", { style: "color:var(--success);font-size:12px;font-weight:600;margin-top:2px;" },
            `Hemat ${MugenUI.formatRupiah(hematRupiah)} dibanding bulanan`));
        }
        if (pakaiTahunan) {
          box.appendChild(MugenUI.el("div", { style: "color:var(--success);font-size:12px;font-weight:600;margin-top:2px;" },
            `Setara ${MugenUI.formatRupiah(efektifBulananTahunan)}/bulan`));
          box.appendChild(MugenUI.el("div", { style: "color:var(--success);font-size:12px;font-weight:600;" },
            "Hemat dengan pembayaran tahunan"));
        }
        if (paket.deskripsi) box.appendChild(MugenUI.el("div", { style: "margin-top:8px;" }, paket.deskripsi));
        if (paket.kode === "enterprise") box.appendChild(benefitEnterprise());
        box.appendChild(kartuFitur(paket.fitur));

        let btn;
        if (isCurrent) {
          box.appendChild(MugenUI.el("span", { class: "badge badge-success", style: "margin-bottom:10px;display:inline-block;" }, "Paket Aktif"));
          if (paket.harga > 0) {
            btn = MugenUI.el("button", { class: "btn-primary" }, "Perpanjang");
            btn.addEventListener("click", () => mulaiCheckout(paket.id, siklusAktif, config, onSelesai, btn));
          }
        } else if (current && paket.urutan > current.urutan) {
          btn = MugenUI.el("button", { class: "btn-primary" }, "Upgrade");
          btn.addEventListener("click", () => mulaiCheckout(paket.id, siklusAktif, config, onSelesai, btn));
        } else if (current && paket.urutan < current.urutan) {
          btn = MugenUI.el("button", {}, "Downgrade");
          btn.addEventListener("click", () => mulaiDowngrade(btn, paket, onSelesai));
        } else {
          btn = MugenUI.el("button", { class: "btn-primary" }, "Pilih Paket");
          btn.addEventListener("click", () => mulaiCheckout(paket.id, siklusAktif, config, onSelesai, btn));
        }
        if (btn) box.appendChild(MugenUI.el("div", {}, btn));
        grid.appendChild(box);
        if (isRekomendasi) boxDirekomendasikan = box;
      }
      if (boxDirekomendasikan) {
        boxDirekomendasikan.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }

    gambarUlangToggle();
    gambarUlangGrid();
  }

  function renderInvoiceCard(root, invoices, reload) {
    const card = MugenUI.el("div", { class: "card" });
    root.appendChild(card);
    card.appendChild(MugenUI.el("h2", {}, "Riwayat Pembayaran"));

    const kolom = [
      { key: "nomor_invoice", label: "No. Invoice" },
      { key: "package_nama", label: "Paket" },
      { key: "jumlah", label: "Jumlah", format: (v) => MugenUI.formatRupiah(v) },
      { key: "metode_pembayaran", label: "Metode", format: (v) => v || "-" },
      { key: "status", label: "Status", format: (v) => MugenUI.el("span", { class: "badge " + (BADGE_STATUS_INVOICE[v] || "") }, LABEL_STATUS_INVOICE[v] || v) },
      { key: "created_at", label: "Tanggal", format: (v) => formatWaktu(v) },
      {
        // AUDIT (perbaikan pasca-audit kesiapan): jalur RESMI untuk invoice
        // yang macet karena webhook TIDAK PERNAH sampai sama sekali --
        // HANYA muncul untuk status "pending" (belum final), server yang
        // memanggil ulang provider (Server Key sendiri), Owner TIDAK PERNAH
        // bisa mengklaim status sendiri (lihat routers/billing.py::
        // cek_ulang_invoice()).
        key: "aksi", label: "Aksi", format: (_, inv) => {
          if (inv.status !== "pending") return "-";
          const btn = MugenUI.el("button", { type: "button" }, "Cek Ulang ke Provider");
          btn.addEventListener("click", async () => {
            try {
              await MugenUI.withButtonLoading(btn, () => MugenApi.post(`/api/billing/invoices/${inv.id}/cek-ulang`));
              MugenUI.toast("Status berhasil diperbarui dari provider.", "success", { force: true });
              reload();
            } catch (e) {
              MugenUI.toast(pesanError(e), "error");
            }
          });
          return btn;
        },
      },
    ];
    card.appendChild(MugenUI.buildTable(kolom, invoices, { emptyText: "Belum ada riwayat pembayaran." }));
  }

  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Billing & Pembayaran"));

    // REVISI UI/UX Premium: skeleton menggantikan teks "Memuat data billing…".
    const loadingCard = MugenUI.skeleton("card", { lines: 3 });
    root.appendChild(loadingCard);

    let sub, config, packages, invoices;
    try {
      [sub, config, packages, invoices] = await Promise.all([
        MugenApi.get("/api/subscription/me"),
        MugenApi.get("/api/billing/config"),
        MugenApi.get("/api/billing/packages"),
        MugenApi.get("/api/billing/invoices"),
      ]);
    } catch (e) {
      loadingCard.innerHTML = "";
      loadingCard.appendChild(MugenUI.errorState(pesanError(e)));
      return;
    }
    loadingCard.remove();

    renderStatusCard(root, sub, invoices, packages, config);
    renderPaketCard(root, sub, config, packages, () => render(root));
    renderInvoiceCard(root, invoices, () => render(root));
  }

  return { render };
})();

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js
// (bukan <script> biasa lagi, lihat index.html/router.js) -- top-level
// "const" TIDAK menempel ke objek window di browser (beda dari "var"),
// jadi page_loader.js TIDAK BISA mendeteksi lewat window.PageBilling begitu saja
// setelah script ini selesai dimuat. Baris di bawah ini SATU-SATUNYA
// perubahan di file ini untuk mendukung lazy-load -- expose eksplisit ke
// window supaya page_loader.js bisa memverifikasi modul benar-benar
// berhasil dimuat sebelum memanggil render()-nya.
window.PageBilling = PageBilling;
