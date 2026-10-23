// feature_access.js — FONDASI Multi-Tenant Phase 4 lanjutan: Feature Gating
// per Paket Langganan. SATU sistem terpusat untuk "apakah paket tenant ini
// menyertakan fitur X" -- setiap halaman yang butuh gerbang fitur (Rekap,
// Kasbon, dst untuk export_pdf; book_public.js untuk booking_online;
// booking.js untuk qris) MEMANGGIL MugenFeature.has()/upgradeBlock() di
// sini, TIDAK mengimplementasikan logikanya sendiri-sendiri.
//
// Sumber data: MugenSubscription.get().features (array kode fitur), sudah
// otomatis tersedia SINKRON begitu MugenSubscription.refresh() selesai
// (dipanggil app.js boot + login.js + billing.js post-checkout, TIDAK ada
// refresh tambahan yang perlu ditambahkan di sini -- lihat
// routers/subscription.py::subscription_status() di backend, field
// `features` dikirim di respons yang SAMA yang sudah disimpan
// MugenSubscription apa adanya).
//
// Load di index.html PERSIS setelah subscription.js.
const MugenFeature = (() => {
  function has(kode) {
    const sub = typeof MugenSubscription !== "undefined" ? MugenSubscription.get() : null;
    return !!(sub && Array.isArray(sub.features) && sub.features.includes(kode));
  }

  // REVISI Work #2 (Superadmin Package Permission Tree): versi has() di
  // atas untuk 4 kode fitur "sejajar" lama (export_pdf/export_excel/
  // booking_online/barber_app) -- hasIzin() di sini untuk key izin_*
  // (permissions.PERMISSION_TREE) yang TERMASUK paket tenant, sumbernya
  // SAMA PERSIS (MugenSubscription.get(), field `izin_paket`, lihat
  // routers/subscription.py::subscription_status()). Dipakai nav.js
  // (ikon gembok sidebar) & router.js (blok "Upgrade Paket" pengganti
  // halaman tujuan) -- BUKAN gerbang Role (itu MugenMenuAccess di
  // menu_access.js, lapisan TERPISAH).
  function hasIzin(izinKey) {
    const sub = typeof MugenSubscription !== "undefined" ? MugenSubscription.get() : null;
    return !!(sub && Array.isArray(sub.izin_paket) && sub.izin_paket.includes(izinKey));
  }

  // Blok pengganti tombol/bagian yang digerbang -- pola sama seperti
  // "disabled + subtitle penjelasan" yang sudah dipakai pengaturan.js untuk
  // izin_* (Hak Akses Admin), bedanya di sini tombolnya "Upgrade Paket"
  // yang mengarahkan ke halaman #/billing (Owner/Admin -- lihat
  // router.js::handle(), 'staff' tidak ikut halaman ini, konsisten dengan
  // cakupan Phase 3/4 billing yang memang Owner-murni).
  function upgradeBlock(featureLabel) {
    const btn = MugenUI.el("button", { class: "btn-primary" }, "Upgrade Paket");
    btn.addEventListener("click", () => {
      location.hash = "#/billing";
      MugenRouter.handle();
    });
    return MugenUI.el("div", { class: "card" }, [
      // REVISI feedback Owner: pesan dipersingkat -- "Upgrade untuk
      // menikmati fitur ini." (bukan lagi "X memerlukan paket yang lebih
      // tinggi. Upgrade untuk menggunakan fitur ini." -- terlalu teknis).
      // `featureLabel` tetap diterima pemanggil (konteks halaman/tab yang
      // memanggilnya sudah cukup jelas fitur mana yang dimaksud).
      MugenUI.el("div", { class: "subtitle" }, "Upgrade untuk menikmati fitur ini."),
      MugenUI.el("div", { style: "margin-top:12px;" }, btn),
    ]);
  }

  return { has, hasIzin, upgradeBlock };
})();
