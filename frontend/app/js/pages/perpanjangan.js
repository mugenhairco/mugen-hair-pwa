// pages/perpanjangan.js — FITUR Notifikasi H-7 & Perpanjangan Cepat (diminta
// Owner): dibuka dari tulisan merah di bawah nama tenant (nav.js, HANYA
// tampil H-7 sebelum periode_selesai) ATAU langsung lewat #/perpanjangan --
// BEDA dari pages/billing.js (Owner-only penuh): halaman ini Owner ATAU
// Staff/role custom apa pun (KECUALI 'barber', digerbang router.js & backend
// require_owner_or_staff, lihat routers/billing.py::renewal_options()/
// renewal_checkout()) BOLEH menyelesaikan pembayaran sendiri, TAPI HANYA
// untuk paket sekarang (perpanjang) atau paket DI ATASNYA (upgrade) -- TIDAK
// PERNAH downgrade (opsi itu sengaja tidak ditampilkan sama sekali di sini,
// dan ditolak ulang di backend kalau entah bagaimana dipaksa). Downgrade
// TETAP hanya lewat menu Billing penuh, Owner-only.
//
// Alur checkout (pilih channel -> POST -> modal VA/QR + countdown + polling)
// DIPAKAI BERSAMA pages/billing.js lewat js/billing_checkout_shared.js
// (MugenBillingCheckout) -- TIDAK diduplikasi di sini.
const PagePerpanjangan = (() => {
  function pesanError(e) {
    return (e && e.detail && e.detail.detail) ? e.detail.detail : (e.message || "Terjadi kesalahan.");
  }

  // SAMA PERSIS pages/billing.js::kartuFitur() -- lihat catatan di sana
  // soal kenapa helper tampilan kecil seperti ini TIDAK dipindah ke modul
  // bersama (murni presentasional, beda dari alur checkout yang jauh lebih
  // besar dan genuinely dipakai ulang).
  function kartuFitur(fitur) {
    if (!fitur || !fitur.length) return MugenUI.el("div", { class: "subtitle" }, "Tidak ada fitur tercatat.");
    const wrap = MugenUI.el("div", { style: "display:flex;flex-wrap:wrap;gap:6px;margin:10px 0;" });
    for (const f of fitur) wrap.appendChild(MugenUI.el("span", { class: "badge badge-libur" }, f.nama));
    return wrap;
  }

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

  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Perpanjang / Upgrade Langganan"));
    root.appendChild(MugenUI.skeleton("card", { lines: 4 }));

    let data, config;
    try {
      [data, config] = await Promise.all([
        MugenApi.get("/api/billing/renewal-options"),
        MugenApi.get("/api/billing/config"),
      ]);
    } catch (e) {
      root.innerHTML = "";
      root.appendChild(MugenUI.el("h1", {}, "Perpanjang / Upgrade Langganan"));
      root.appendChild(MugenUI.errorState(pesanError(e)));
      return;
    }

    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Perpanjang / Upgrade Langganan"));

    const card = MugenUI.el("div", { class: "card" });
    root.appendChild(card);
    card.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Perpanjang paket yang sama atau upgrade ke paket lebih tinggi. Downgrade paket hanya bisa dilakukan Owner lewat menu Billing."));
    if (!config.enabled) {
      card.appendChild(MugenUI.el("div", { class: "login-error", style: "margin-top:12px;" },
        "Pembayaran online belum aktif untuk toko ini -- hubungi penyedia layanan."));
    }

    const current = data.package_sekarang;
    let siklusAktif = "tahunan";
    const toggleWrap = MugenUI.el("div", { style: "margin-top:12px;" });
    const grid = MugenUI.el("div", { class: "grid-cards" });
    card.appendChild(toggleWrap);
    card.appendChild(grid);

    function onSelesai() { render(root); }

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
      for (const paket of data.pilihan) {
        const isCurrent = !!(current && paket.kode === current.kode);
        const box = MugenUI.el("div", {
          class: "card", style: "margin-bottom:0;" + (isCurrent ? "border-color:var(--accent);" : ""),
        });
        box.appendChild(MugenUI.el("h2", {}, paket.nama));

        const pakai6 = siklusAktif === "6bulan" && paket.harga > 0 && paket.harga_6bulan;
        const pakaiTahunan = siklusAktif === "tahunan" && paket.harga > 0 && paket.harga_tahunan;
        const hargaTampil = pakai6 ? paket.harga_6bulan : pakaiTahunan ? paket.harga_tahunan : paket.harga;
        const hematRupiah = pakai6 ? (paket.harga * 6 - paket.harga_6bulan) : 0;
        const efektifBulananTahunan = pakaiTahunan ? Math.round(paket.harga_tahunan / 12) : 0;

        if (pakaiTahunan) {
          box.appendChild(MugenUI.el("span", {
            style: "background:var(--success);color:#fff;font-size:11px;font-weight:700;padding:3px 10px;border-radius:999px;margin-bottom:8px;display:inline-block;",
          }, "⭐ Paling Hemat"));
        } else if (pakai6 && hematRupiah > 0) {
          box.appendChild(MugenUI.el("span", {
            style: "background:var(--success);color:#fff;font-size:11px;font-weight:700;padding:3px 10px;border-radius:999px;margin-bottom:8px;display:inline-block;",
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
        }
        if (paket.deskripsi) box.appendChild(MugenUI.el("div", { style: "margin-top:8px;" }, paket.deskripsi));
        box.appendChild(kartuFitur(paket.fitur));

        if (isCurrent) {
          box.appendChild(MugenUI.el("span", { class: "badge badge-success", style: "margin-bottom:10px;display:inline-block;" }, "Paket Aktif"));
        }
        // BUGFIX (konsisten dengan pages/billing.js::renderPaketCard()):
        // paket gratis (harga 0 -- mis. "free", paket default tenant masih
        // trial) TIDAK PERNAH butuh checkout, jadi tombol "Perpanjang"
        // TIDAK ditampilkan untuk paket itu sendiri (akan selalu ditolak
        // backend dengan "Paket ini tidak memerlukan pembayaran").
        // Upgrade ke paket BERBAYAR dari paket gratis tetap tampil normal.
        if (!isCurrent || paket.harga > 0) {
          const btn = MugenUI.el("button", { class: "btn-primary" }, isCurrent ? "Perpanjang" : "Upgrade");
          btn.addEventListener("click", () => MugenBillingCheckout.jalankanCheckout({
            endpoint: "/api/billing/renewal-checkout", packageId: paket.id, siklus: siklusAktif,
            config, onSelesai, btnPemicu: btn,
          }));
          box.appendChild(MugenUI.el("div", {}, btn));
        }
        grid.appendChild(box);
      }
    }

    gambarUlangToggle();
    gambarUlangGrid();
  }

  return { render };
})();
// BUGFIX (halaman Billing/Perpanjangan gagal dimuat produksi): expose
// eksplisit ke window -- pola WAJIB sama persis seperti akhir pages/
// billing.js dst, lihat catatan lengkap di billing_checkout_shared.js.
window.PagePerpanjangan = PagePerpanjangan;
