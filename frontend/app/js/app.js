// app.js — entry point JS frontend.
// TAHAP 3-9: mendaftarkan service worker lalu menjalankan router (login,
// dashboard, input data, rekap, pengeluaran).
// TAHAP 10: refresh identitas barbershop (nama/logo) sekali di awal supaya
// tab/judul browser & sidebar terisi data terbaru dari Setting.
// REVISI: setelah registrasi, panggil registration.update() supaya app aktif
// meminta browser mengecek versi service-worker.js terbaru di setiap kali
// aplikasi dibuka -- sebelumnya hanya mengandalkan jadwal pengecekan bawaan
// browser (yang bisa jarang/lambat), jadi kalau CACHE_NAME dinaikkan di
// deploy baru (lihat service-worker.js), user yang PWA-nya sudah ter-install
// lebih cepat mendapat versi baru pada kunjungan berikutnya.
// PERBAIKAN MEKANISME CACHE & UPDATE PWA (v57): keluhan "harus Hard
// Refresh/hapus cache manual" -- registrasi sekarang pakai
// updateViaCache:"none" (paksa browser SELALU mengambil byte
// service-worker.js dari network, tidak pernah dari HTTP cache, saat
// mengecek update -- tanpa ini, host yang meng-cache file statis secara
// agresif bisa membuat browser mengira service-worker.js "tidak berubah"
// walau sebenarnya sudah di-deploy ulang). Update dicek lebih sering
// (tiap 1 jam + tiap tab kembali terlihat), bukan cuma sekali saat app
// dibuka -- banyak user PWA membiarkan tab/app terbuka berhari-hari.
// REVISI (PERMINTAAN Owner, v204): banner "Versi baru tersedia" + tombol
// "Muat Ulang" manual (pwa_update.js) DIHAPUS total -- update sekarang
// BENAR-BENAR DIAM-DIAM, TIDAK ADA pemberitahuan apa pun ke user. service-
// worker.js SUDAH (dan TETAP) memanggil skipWaiting()/clients.claim() begitu
// Service Worker baru selesai install, jadi versi barunya SUDAH aktif &
// cache-nya SUDAH siap di belakang layar -- user otomatis mendapat versi
// terbaru pada kunjungan BERIKUTNYA (tab baru/reopen PWA/refresh manual utk
// alasan lain), TANPA perlu kode apa pun di sini untuk memaksanya. Prinsip
// lama TETAP dipertahankan: TIDAK PERNAH reload paksa di tengah sesi yang
// sedang berjalan (aplikasi ini penuh form input yang belum tentu sudah
// tersimpan) -- yang berubah HANYA sisi "memberi tahu user", bukan sisi
// keamanan datanya.
// ROBUSTNESS (Owner: layar iPhone asli -- strip blur status bar kadang TIDAK
// full sampai ikon sinyal/baterai, kadang full, tidak konsisten di perangkat
// yang sama): env(safe-area-inset-top) adalah CSS env var LIVE yang
// semestinya ikut bertambah kalau status bar jadi lebih tinggi (pita hijau/
// oranye "Sedang Menelepon"/"Perekaman Layar Aktif" dsb muncul), TAPI WebKit
// punya bug dikenal -- elemen position:fixed yang tingginya pakai calc()
// berisi env() tidak selalu ikut di-repaint ulang saat nilai env() berubah
// live, kecuali ada "nudge" reflow dari luar. Probe tersembunyi ini mengukur
// env(safe-area-inset-top) SUNGGUHAN lewat getBoundingClientRect() (bukan
// CSS murni), lalu menyuntikkannya sebagai custom property --safe-top di
// :root -- SELURUH tempat di style.css yang butuh nilai ini (body::before/
// ::after, .page-topbar, .hamburger, .content, dst) pakai
// var(--safe-top, env(safe-area-inset-top)): (a) tetap benar di render
// PERTAMA sebelum skrip ini sempat jalan (fallback ke env() mentah), (b)
// diukur ULANG & dipaksa reflow di setiap titik yang mungkin mengubah tinggi
// status bar (resize, orientasi berubah, app kembali ke foreground,
// visualViewport resize) -- walau WebKit gagal repaint OTOMATIS, perubahan
// nilai custom property ini sendiri memaksa layout baru di semua elemen yang
// memakainya.
(function jagaSafeAreaTop() {
  const probe = document.createElement("div");
  probe.style.cssText =
    "position:fixed; top:0; left:0; width:0; height:0; margin:0; border:0;" +
    "padding-top:env(safe-area-inset-top); pointer-events:none; visibility:hidden;";
  document.documentElement.appendChild(probe);
  // KOREKSI (Owner: temuan penting -- strip blur status bar SELALU penuh
  // sampai ikon sinyal/baterai begitu sidebar DIBUKA, tapi TIDAK penuh
  // begitu sidebar TERTUTUP/tampilan normal): ".sidebar" sendiri
  // position:fixed; top:0 LANGSUNG -- TIDAK PERNAH bergantung pada
  // env(safe-area-inset-top)/--safe-top sama sekali, jadi wajar selalu
  // "penuh" apa pun kondisinya. "body::before" (strip blur tampilan
  // normal) SATU-SATUNYA yang bergantung pada --safe-top utk tingginya
  // -- kalau nilainya BENAR (computed style) tapi WebKit gagal
  // me-render ulang TINGGINYA tanpa pemicu luar (kategori bug yang sama
  // persis sudah ditemukan berkali-kali utk "left"/"backdrop-filter" di
  // elemen fixed+backdrop-filter serupa), strip itu bisa "nyangkut" di
  // ukuran lama/pendek sampai ADA sesuatu yang memicu render ulang --
  // toggle sidebar kebetulan memicu itu (selector lain ikut berubah di
  // elemen yang sama), menyamarkan bug-nya alih-alih memperbaikinya.
  // _colekRepaint() memaksa render ulang SECARA LANGSUNG setiap kali
  // --safe-top diisi/diubah, TANPA perlu menunggu user membuka sidebar
  // dulu -- trik reflow klasik (display:none lalu dikembalikan SEKETIKA
  // dalam fungsi sinkron yang sama, browser tidak sempat menggambar
  // apa pun di antaranya jadi tidak ada kedipan) pada <body> memaksa
  // WebKit menghitung ULANG seluruh layout+cat turunannya, TERMASUK
  // pseudo-element position:fixed (body::before/::after) yang tidak bisa
  // disentuh langsung lewat JS (bukan node DOM asli).
  function _colekRepaint() {
    const tampilanSemula = document.body.style.display;
    document.body.style.display = "none";
    void document.body.offsetHeight;
    document.body.style.display = tampilanSemula;
  }
  // KOREKSI (Owner: foto hero web booking publik "berkedip-kedip cepat"
  // saat discroll -- TERNYATA bukan soal blur, lihat riwayat commit):
  // iOS Safari menembakkan event "resize"/"visualViewport resize"
  // BERKALI-KALI selama momentum scroll berlangsung (toolbar/address bar
  // animasi sembunyi-muncul mengubah tinggi viewport berulang kali) --
  // SEBELUM perbaikan ini, ukurUlang() (dipanggil listener resize di
  // bawah) SELALU memanggil _colekRepaint() TANPA SYARAT setiap kali,
  // artinya reflow paksa "body display:none lalu balik" (SELURUH
  // halaman, bukan cuma elemen yg butuh --safe-top) bisa terpicu
  // puluhan kali per detik SELAMA scroll berlangsung di halaman mana
  // pun (bukan cuma dashboard internal -- IIFE ini global, berjalan di
  // SEMUA halaman termasuk #/book/... publik) -- reflow sebanyak itu
  // beruntun yang tampak sebagai "kedipan cepat", BUKAN backdrop-filter
  // (yang sudah dicoba dihapus duluan, tidak menyelesaikan masalah).
  // Fix: _colekRepaint() HANYA dipanggil kalau nilai --safe-top SUNGGUH
  // BERUBAH dari sebelumnya -- resize gara-gara toolbar iOS selama
  // scroll vertikal TIDAK mengubah env(safe-area-inset-top) sama sekali
  // (notch/Dynamic Island tidak berpindah), jadi hampir SEMUA event
  // resize selama scroll sekarang jadi no-op (early return), reflow
  // paksa TETAP terjadi seperti sebelumnya HANYA saat nilainya benar-
  // benar berubah (rotasi layar sungguhan, dst -- tujuan awal perbaikan
  // ini TIDAK berubah).
  let _safeTopTerakhir = null;
  function ukurUlang() {
    const tinggi = probe.getBoundingClientRect().height;
    const nilaiBaru = tinggi + "px";
    if (nilaiBaru === _safeTopTerakhir) return;
    _safeTopTerakhir = nilaiBaru;
    document.documentElement.style.setProperty("--safe-top", nilaiBaru);
    _colekRepaint();
  }
  ukurUlang();
  window.addEventListener("resize", ukurUlang);
  window.addEventListener("orientationchange", ukurUlang);
  window.addEventListener("pageshow", ukurUlang);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") ukurUlang();
  });
  if (window.visualViewport) window.visualViewport.addEventListener("resize", ukurUlang);
})();

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js", { updateViaCache: "none" })
      .then((reg) => {
        reg.update().catch(() => {});
        setInterval(() => reg.update().catch(() => {}), 60 * 60 * 1000);
        document.addEventListener("visibilitychange", () => {
          if (document.visibilityState === "visible") reg.update().catch(() => {});
        });
      })
      .catch((err) => {
        console.error("Gagal mendaftarkan service worker:", err);
      });
  });

  // FITUR Auto-Refresh Booking via Push (event-driven, BUKAN polling):
  // service-worker.js merelai pesan ke SEMUA tab app yang terbuka begitu
  // push baru diterima (lihat listener "push" di sana) -- HANYA bereaksi
  // pada push jenis "booking_baru" (push jenis lain, mis. izin_cuti,
  // diabaikan di sini). Reaksinya: refresh badge+chime booking SEKETIKA
  // (bukan menunggu reminder 60 detik), dan kalau tab Booking (List
  // Owner/Admin ATAU Hari Ini/Akan Datang/Semua Booking milik Barber)
  // SEDANG terbuka, data tabel/kartu itu diperbarui DIAM-DIAM di latar
  // belakang (lihat PageBooking.refreshDiamDiam()/_bookingQuietReload di
  // pages/booking.js) -- booking baru langsung tampil TANPA tombol "Muat
  // Ulang" manual (SUDAH DIHAPUS, permintaan Owner) DAN tanpa flash/reset
  // seluruh halaman seperti MugenRouter.handle() SEBELUMNYA. TIDAK
  // menambah aktivitas jaringan saat idle -- listener ini sama sekali
  // tidak memicu apa pun kalau tidak ada push yang masuk.
  navigator.serviceWorker.addEventListener("message", (event) => {
    const data = event.data || {};
    if (data.type !== "push-notifikasi") return;
    if (data.jenis === "booking_baru") {
      if (typeof MugenBookingNotif !== "undefined") MugenBookingNotif.refreshNow();
      if (location.hash.startsWith("#/booking") && typeof PageBooking !== "undefined"
          && typeof PageBooking.refreshDiamDiam === "function") {
        // PERMINTAAN Owner (suntik diam-diam, BUKAN cuma "muat ulang diam-
        // diam"): `data.data` opsional -- baris booking lengkap, diteruskan
        // ke refreshDiamDiam() supaya PageBooking bisa langsung menyuntik
        // baris itu ke tabel/kartu yang sedang tampil TANPA fetch ulang ke
        // server (lihat catatan panjang _bookingSuntikBaris di pages/
        // booking.js) -- otomatis jatuh kembali ke fetch diam-diam lama
        // kalau tab aktif belum siap/payload tidak membawa data.
        PageBooking.refreshDiamDiam(data.data);
      }
      return;
    }
    // FITUR Notifikasi Push "Transaksi POS Baru" (PERMINTAAN Owner,
    // "kerjakan dengan teliti" -- perbaikan SEBELUMNYA, "pos_transaksi" di
    // api.js, cuma membuat tab "Transaksi Hari Ini" fetch ulang PENUH
    // begitu dibuka/dipindah-balik lagi, BUKAN real-time SAMA SEKALI
    // selama tab itu sedang dilihat). Pola SAMA PERSIS "booking_baru" di
    // atas, hanya audiensnya beda: TIDAK ada badge/suara terpisah (menu
    // POS tidak punya itu), dan HANYA suntik diam-diam kalau #/pos
    // sedang terbuka (PagePos baru ter-load lazy, lihat page_loader.js --
    // kalau menu ini belum pernah dibuka sesi ini, PagePos undefined,
    // tidak ada apa pun yang perlu disuntik).
    if (data.jenis === "pos_transaksi_lunas") {
      if (location.hash.startsWith("#/pos") && typeof PagePos !== "undefined"
          && typeof PagePos.suntikTransaksiLunas === "function") {
        PagePos.suntikTransaksiLunas(data.data);
      }
      return;
    }
    // FITUR BARU Draft POS: kartu "Draft Baru" di tab Kasir (Barber + Nama
    // Customer disiapkan lebih awal) harus terlihat SAMA oleh semua kasir/
    // device tenant ini -- pola SAMA PERSIS "pos_transaksi_lunas" di atas,
    // `data.data` membawa FULL list draft terbaru (lihat pos_draft_db.py).
    if (data.jenis === "pos_draft_berubah") {
      if (location.hash.startsWith("#/pos") && typeof PagePos !== "undefined"
          && typeof PagePos.suntikDraftBerubah === "function") {
        PagePos.suntikDraftBerubah(data.data);
      }
      return;
    }
    // FITUR BARU Live Chat: pesan customer baru masuk -- pola SAMA PERSIS
    // "pos_draft_berubah" di atas, `data.data` membawa pesan tunggal yang
    // baru saja masuk (lihat routers/live_chat.py).
    if (data.jenis === "live_chat_masuk") {
      if (location.hash.startsWith("#/live-chat") && typeof PageLiveChat !== "undefined"
          && typeof PageLiveChat.suntikPesanMasuk === "function") {
        PageLiveChat.suntikPesanMasuk(data.data);
      }
    }
  });
}

window.addEventListener("DOMContentLoaded", async () => {
  // FITUR Subdomain Otomatis per Tenant: dicek PALING AWAL, SEBELUM baris
  // apa pun di bawah ini -- kalau domain yang sedang dibuka BERBENTUK
  // subdomain tenant (mis. mugenhairco.rivoirsett.com) TAPI slug-nya tidak
  // dikenal backend, halaman "Tenant Tidak Ditemukan" langsung dirender
  // & seluruh boot NORMAL di bawah (router/subscription/notifikasi dkk)
  // DIHENTIKAN -- lihat tenant_guard.js. Untuk domain BUKAN subdomain
  // tenant (root/www/app/api/admin, mayoritas mutlak trafik hari ini),
  // fungsi ini resolve SEKETIKA tanpa fetch apa pun, jadi TIDAK menambah
  // delay boot sama sekali.
  const appRoot = document.getElementById("app");
  const lanjut = await MugenTenantGuard.cekLaluRender(appRoot);
  if (!lanjut) return;

  // BUGFIX Register (Landing Page SaaS): halaman Register SELALU platform
  // Rivoir, TIDAK PERNAH branding tenant (lihat brand.js::
  // refreshPlatformOnly(), dipanggil sendiri oleh PageRegister.render()
  // di bawah lewat MugenRouter.init()/handle()) -- refresh() tenant-aware
  // di sini (dari slug "diingat") kalau TETAP dipanggil untuk hash ini
  // akan BALAPAN dengan refreshPlatformOnly() (keduanya sama-sama fetch
  // async independen) dan bisa "menang" belakangan, menimpa balik DOM ke
  // branding tenant yang kebetulan pernah dibuka di perangkat itu --
  // dilewati KHUSUS di sini, halaman lain semuanya TIDAK berubah.
  // REVISI Verifikasi Email/Lupa Kata Sandi: #/lupa-password,
  // #/reset-password, #/verify-email SAMA PERSIS seperti #/register --
  // halaman PLATFORM murni yang juga memanggil refreshPlatformOnly()
  // sendiri, jadi rentan balapan yang sama kalau tidak dilewati di sini.
  const HASH_PLATFORM_ONLY = ["#/register", "#/lupa-password", "#/reset-password", "#/verify-email"];
  if (!HASH_PLATFORM_ONLY.some((h) => location.hash.startsWith(h))) {
    MugenBrand.refresh();
  }
  MugenRouter.init();
  // FONDASI Multi-Tenant Phase 3: cache akses_diblokir (dari localStorage,
  // lihat subscription.js) sudah dipakai router.js SAAT init() di atas --
  // refresh() di sini menyegarkannya dari server di background, lalu
  // memanggil handle() lagi supaya kalau statusnya BERBEDA dari cache
  // (mis. baru diblokir Super Admin sejak kunjungan terakhir), halaman
  // langsung dialihkan ke status subscription tanpa perlu navigasi manual.
  MugenSubscription.refresh().then(() => MugenRouter.handle());
  // REVISI: Notifikasi Booking Baru -- dimulai SEKALI di sini (bukan di
  // dalam halaman Booking) supaya badge + suara tetap aktif app-wide,
  // TIDAK terikat ke halaman mana pun yang sedang dibuka Admin. Modul ini
  // sendiri yang memeriksa (tiap poll) apakah user sedang login sebagai
  // admin -- aman dipanggil walau saat ini masih di halaman Login.
  MugenBookingNotif.init();
  // Modul Karyawan Fase 5: Notifikasi Izin & Cuti -- pola sama seperti
  // MugenBookingNotif di atas (badge jumlah pengajuan Pending, app-wide).
  MugenIzinNotif.init();
});
