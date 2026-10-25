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
    trial: "Trial", active: "Aktif",
    expired: "Kedaluwarsa", suspended: "Ditangguhkan", cancelled: "Dibatalkan",
    // FITUR Program Afiliasi Sales/Marketing -- Lisensi Lifetime (Beli
    // Putus): status permanen, akses TIDAK PERNAH diblokir lagi (lihat
    // subscription_db.STATUS_AKSES_DIBLOKIR).
    lifetime: "Lifetime",
  };
  const BADGE_STATUS_SUB = {
    trial: "badge-libur", active: "badge-success",
    expired: "badge-danger", suspended: "badge-danger", cancelled: "badge-danger",
    lifetime: "badge-success",
  };
  // REVISI: "Periode Aktif Berakhir" cukup tanggal, tanpa jam (sebelumnya
  // ikut menampilkan jam mentah dari periode_selesai).
  function formatTanggalSaja(iso) {
    if (!iso) return "-";
    return MugenUI.formatTanggal(iso.split("T")[0]);
  }

  function pesanError(e) {
    return (e && e.detail && e.detail.detail) ? e.detail.detail : (e.message || "Terjadi kesalahan.");
  }

  function renderStatusCard(root, sub, packages, config) {
    const card = MugenUI.el("div", { class: "card" });
    root.appendChild(card);
    card.appendChild(MugenUI.el("h2", {}, "Paket & Status Langganan"));

    if (sub.akses_diblokir) {
      card.appendChild(MugenUI.el("div", { class: "login-error", style: "margin-bottom:12px;" },
        `Akses toko ini sedang dibatasi karena status subscription "${LABEL_STATUS_SUB[sub.status] || sub.status}". ` +
        "Selesaikan pembayaran di bawah untuk mengaktifkan kembali."));
    }
    // REVISI (diminta Owner, hapus toleransi grace): auto-suspend SEKARANG
    // langsung begitu periode_selesai lewat (TIDAK ADA LAGI jeda 7 hari,
    // lihat subscription_db.py::_auto_suspend_jika_lewat()) -- kondisi
    // "periode sudah lewat TAPI akses_diblokir masih false" di bawah ini
    // jadi jendela SANGAT SEMPIT (GET /me tidak memicu ulang pengecekan
    // auto-suspend, murni baca status tersimpan -- lihat routers/
    // subscription.py::subscription_saya()), tapi tetap dipertahankan
    // sebagai jaring pengaman tampilan, bukan dihapus.
    const now = new Date().toISOString();
    if (!sub.akses_diblokir && sub.periode_selesai && sub.periode_selesai < now) {
      card.appendChild(MugenUI.el("div", { class: "login-error", style: "margin-bottom:12px;" },
        "Periode langganan toko ini sudah berakhir. Selesaikan pembayaran di bawah untuk memperpanjang sebelum akses dibatasi."));
    }
    if (!config.enabled) {
      card.appendChild(MugenUI.el("div", { class: "login-error", style: "margin-bottom:12px;" },
        "Pembayaran online belum aktif untuk toko ini -- hubungi penyedia layanan."));
    }

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
      (() => {
        // BUGFIX (dilaporkan Owner): tenant BARU mendaftar (status 'trial')
        // belum pernah punya periode_selesai sama sekali (kolom itu KHUSUS
        // periode BERBAYAR, ditulis set_periode() setelah pembayaran
        // pertama sukses -- lihat subscription_db.py::
        // create_default_subscription()) -- field ini dulu selalu tampil
        // "-" untuk tenant trial, padahal trial_end SUDAH ADA sejak
        // pendaftaran. SEKARANG: pakai periode_selesai kalau sudah ada
        // (tenant sudah pernah bayar), fallback ke trial_end selama masih
        // 'trial', label ikut menyesuaikan supaya tidak disangka periode
        // berbayar.
        const tanggalBerakhir = sub.periode_selesai || (sub.status === "trial" ? sub.trial_end : null);
        const labelBerakhir = sub.periode_selesai ? "Periode Aktif Berakhir" : "Masa Trial Berakhir";
        return MugenUI.el("div", {}, [
          MugenUI.el("div", { class: "subtitle" }, labelBerakhir),
          MugenUI.el("div", { style: "font-weight:700;" }, tanggalBerakhir ? formatTanggalSaja(tanggalBerakhir) : "-"),
        ]);
      })(),
    ]);
    card.appendChild(ringkasan);
  }

  // FITUR Program Afiliasi Sales/Marketing -- Lisensi Lifetime (Beli Putus):
  // transaksi dibuat Super Admin lewat Dashboard Sales & Referral (routers/
  // sales.py::buat_lifetime()), VA/QR-nya ditampilkan di SINI supaya Owner
  // bisa langsung membayar dari halaman Billing miliknya sendiri, TANPA
  // perlu dikirim link/info terpisah -- begitu webhook SNAP Advance
  // menandainya lunas, status subscription otomatis berubah 'lifetime'
  // (lihat snap_webhook.py::_cascade_lifetime_license()), kartu ini
  // otomatis tidak tampil lagi di reload berikutnya (GET /lifetime-pending
  // mengembalikan None begitu tidak ada lagi transaksi 'pending').
  function renderLifetimePendingCard(root, pending) {
    if (!pending) return;
    const card = MugenUI.el("div", { class: "card" });
    root.appendChild(card);
    card.appendChild(MugenUI.el("h2", {}, "Pembayaran Lisensi Lifetime"));
    card.appendChild(MugenUI.el("div", { class: "subtitle" },
      `Super Admin telah membuatkan transaksi Lisensi Lifetime paket ${LABEL_PACKAGE[pending.package_kode] || pending.package_kode} senilai ${MugenUI.formatRupiah(pending.amount)} untuk toko ini. Selesaikan pembayaran di bawah -- status langganan akan otomatis berubah permanen (Lifetime) begitu pembayaran dikonfirmasi.`));

    const konten = [];
    if (pending.channel === "va" && pending.va_number) {
      konten.push(MugenUI.el("div", { class: "subtitle" },
        pending.channel_code ? `Virtual Account ${MugenUI.bankNamaLengkap(pending.channel_code, pending.va_bank_label)}` : "Virtual Account"));
      konten.push(MugenUI.el("div", { style: "font-size:22px;font-weight:700;letter-spacing:1px;margin-top:4px;" }, pending.va_number));
      konten.push(MugenUI.el("div", { class: "subtitle", style: "margin-top:8px;" },
        "Transfer PERSIS sejumlah tagihan di atas ke nomor Virtual Account ini lewat m-banking/ATM."));
    } else if (pending.channel === "qris" && pending.qr_url) {
      konten.push(MugenUI.el("img", { src: pending.qr_url, alt: "QRIS", style: "max-width:240px;width:100%;" }));
      konten.push(MugenUI.el("div", { class: "subtitle", style: "margin-top:8px;" },
        "Scan kode QR di atas lewat app e-wallet/m-banking mana pun yang mendukung QRIS."));
    } else {
      konten.push(MugenUI.el("div", { class: "subtitle" }, "Instrumen pembayaran belum tersedia -- hubungi penyedia layanan."));
    }
    card.appendChild(MugenUI.el("div", { style: "text-align:center;margin-top:12px;" }, konten));
  }

  function _bersihkanPendingKode() {
    try {
      sessionStorage.removeItem("mugen_pending_package_kode");
      sessionStorage.removeItem("mugen_pending_package_siklus");
    } catch (e) { /* abaikan */ }
  }

  // REVISI (FITUR Notifikasi H-7 & Perpanjangan Cepat): alur checkout
  // SNAP Advance (pilih channel -> POST checkout -> modal VA/QR + countdown
  // + polling) DIPINDAH ke js/billing_checkout_shared.js (dipakai bersama
  // pages/perpanjangan.js yang baru) -- TIDAK ADA perubahan logika sama
  // sekali, murni dipanggil lewat modul itu sekarang.
  function mulaiCheckout(packageId, siklus, config, onSelesai, btnPemicu) {
    _bersihkanPendingKode();
    return MugenBillingCheckout.jalankanCheckout({ packageId, siklus, config, onSelesai, btnPemicu });
  }

  // REVISI (FITUR Peringatan Downgrade, diminta Owner): popup konfirmasi
  // SEKARANG menyebutkan fitur/menu spesifik apa saja yang akan hilang
  // (GET /api/billing/downgrade-preview/{id}, lihat billing_db.
  // fitur_hilang_saat_downgrade()) -- SEBELUMNYA cuma teks generik. Kalau
  // preview gagal dimuat (jaringan dsb), popup TETAP tampil dengan pesan
  // generik lama (fail-open informatif, BUKAN memblokir downgrade yang
  // sah hanya karena satu panggilan GET gagal).
  async function mulaiDowngrade(btn, paket, onSelesai) {
    let fiturHilang = [];
    try {
      const preview = await MugenApi.get(`/api/billing/downgrade-preview/${paket.id}`);
      fiturHilang = preview.fitur_hilang || [];
    } catch (e) { /* lanjut dengan pesan generik, lihat catatan di atas */ }

    const pesan = [`Pindah ke paket "${paket.nama}" sekarang? Perubahan berlaku langsung tanpa pembayaran.`];
    if (fiturHilang.length) {
      pesan.push("Fitur/menu berikut akan HILANG dari toko ini setelah downgrade:");
      for (const f of fiturHilang) pesan.push(`• ${f}`);
    }
    const ok = await MugenUI.confirmModal({
      title: "Downgrade Paket",
      message: pesan,
      confirmText: "Ya, Downgrade",
      danger: fiturHilang.length > 0,
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

  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Billing & Pembayaran"));

    // REVISI UI/UX Premium: skeleton menggantikan teks "Memuat data billing…".
    const loadingCard = MugenUI.skeleton("card", { lines: 3 });
    root.appendChild(loadingCard);

    // Perbaikan Billing/Subscription (requirement Owner poin 11, dikonfirmasi
    // via klarifikasi): riwayat pembayaran/invoice DISEMBUNYIKAN TOTAL dari
    // halaman Billing tenant -- Owner hanya melihat status paket/periode &
    // tombol bayar. /api/billing/invoices (list) TIDAK dihapus/dibatasi di
    // backend (tetap dipakai monitoring Super Admin) -- halaman ini murni
    // berhenti memanggilnya. Status "Periode Aktif Berakhir" sekarang dibaca
    // langsung dari sub.periode_selesai (tenant_subscriptions), TIDAK LAGI
    // scan invoices (lihat subscription_db.py::set_periode()).
    let sub, config, packages, lifetimePending;
    try {
      [sub, config, packages, lifetimePending] = await Promise.all([
        MugenApi.get("/api/subscription/me"),
        MugenApi.get("/api/billing/config"),
        MugenApi.get("/api/billing/packages"),
        MugenApi.get("/api/billing/lifetime-pending"),
      ]);
    } catch (e) {
      loadingCard.innerHTML = "";
      loadingCard.appendChild(MugenUI.errorState(pesanError(e)));
      return;
    }
    loadingCard.remove();

    renderStatusCard(root, sub, packages, config);
    renderLifetimePendingCard(root, lifetimePending);
    renderPaketCard(root, sub, config, packages, () => render(root));
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
