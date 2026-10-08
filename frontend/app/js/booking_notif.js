// booking_notif.js — REVISI: Notifikasi Booking Baru (badge menu Booking +
// notifikasi suara), KHUSUS Admin/Owner -- HANYA Admin yang bisa
// verifikasi/batalkan booking (lihat routers/booking.py, require_admin di
// endpoint /verifikasi & /batalkan), jadi badge/suara ini tidak berguna
// (dan tidak ditampilkan) untuk akun Barber.
//
// OPTIMASI BANDWIDTH (permintaan Owner): SEBELUMNYA polling periodik ke
// /api/booking/belum-dikonfirmasi setiap beberapa detik SELAMA aplikasi
// terbuka -- dashboard yang ditinggal terbuka seharian (mis. layar kasir/
// resepsionis) menghasilkan request terus-menerus sepanjang hari walau
// tidak ada aktivitas sama sekali. SEKARANG murni EVENT-DRIVEN (TIDAK ADA
// setInterval/timer jaringan sama sekali, pola SAMA PERSIS izin_notif.js
// yang sudah lebih dulu direvisi serupa) -- badge diperbarui HANYA pada
// momen nyata: aplikasi pertama dibuka, setelah login, SETIAP kali user
// berpindah menu (lihat router.js::handle(), "ada aksi klik" pengguna),
// setelah aksi Verifikasi/Batalkan booking, dan saat tab ini kembali
// terlihat setelah disembunyikan (Page Visibility API -- bukan timer,
// murni reaksi atas tab di-switch oleh user).
//
// Suara pengingat: karena tidak ada akses legal untuk menyertakan file suara
// asli iPhone (aset berhak cipta Apple), suara di sini disintesis LANGSUNG
// lewat Web Audio API (osilator + amplop volume) -- dua nada lonceng lembut
// menaik, meniru KARAKTERNYA (lembut, jernih, elegan) tanpa menyalin
// melodi/aset asli apa pun. Konsisten dengan filosofi PWA ini yang lain
// (grafik SVG, animasi CSS) -- tanpa aset eksternal, tetap berfungsi offline.

const MugenBookingNotif = (() => {
  const REMINDER_MS = 60000; // 1 menit, sesuai instruksi -- MURNI lokal (bunyi ulang dari
                             // lastCount yang sudah diketahui), TIDAK ADA request jaringan
                             // sama sekali, jadi TIDAK disentuh oleh optimasi bandwidth ini.

  let lastCount = null; // null = belum pernah polling sukses (baseline belum diketahui)
  let reminderTimer = null;
  let audioCtx = null;

  // ---- Suara: satu AudioContext dipakai ulang (bukan bikin baru tiap
  // bunyi) supaya lebih hemat & lebih andal lolos kebijakan autoplay
  // browser (context yang sama akan tetap "unlocked" begitu sempat
  // di-resume oleh interaksi user pertama, lihat _unlockAudio di bawah). ----
  function _getAudioCtx() {
    if (audioCtx) return audioCtx;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    audioCtx = new Ctx();
    return audioCtx;
  }

  function _unlockAudio() {
    const ctx = _getAudioCtx();
    if (ctx && ctx.state === "suspended") ctx.resume().catch(() => {});
  }
  // Kebijakan autoplay browser modern memblokir suara sebelum ada interaksi
  // user sama sekali -- pasang SEKALI, lepas begitu terpicu (Admin pasti
  // sudah berinteraksi mis. isi form Login sebelum notifikasi pertama bisa
  // saja muncul, tapi ini jaga-jaga kalau belum).
  ["pointerdown", "keydown"].forEach((ev) =>
    document.addEventListener(ev, _unlockAudio, { once: true, passive: true }));

  function playChime() {
    try {
      const ctx = _getAudioCtx();
      if (!ctx) return;
      if (ctx.state === "suspended") ctx.resume().catch(() => {});
      const now = ctx.currentTime;
      // Dua nada menaik (B5 -> E6), sine wave lembut, amplop volume landai
      // (attack cepat 20ms, decay eksponensial) -- durasi total ~1 detik,
      // sedikit lebih panjang dari bunyi notifikasi sekilas biasa supaya
      // cukup terasa sebagai pengingat.
      const notes = [
        { freq: 987.77, start: 0, dur: 0.55 },
        { freq: 1318.51, start: 0.17, dur: 0.9 },
      ];
      const master = ctx.createGain();
      master.gain.value = 0.22;
      master.connect(ctx.destination);
      for (const n of notes) {
        const osc = ctx.createOscillator();
        osc.type = "sine";
        osc.frequency.value = n.freq;
        const gain = ctx.createGain();
        gain.gain.setValueAtTime(0.0001, now + n.start);
        gain.gain.linearRampToValueAtTime(1, now + n.start + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.001, now + n.start + n.dur);
        osc.connect(gain);
        gain.connect(master);
        osc.start(now + n.start);
        osc.stop(now + n.start + n.dur + 0.05);
      }
    } catch (e) {
      // Web Audio tidak didukung/diblokir -- badge tetap ter-update, hanya suaranya dilewati
    }
  }

  // ---- Badge di sidebar (elemen dibuat oleh nav.js, id="booking-badge"
  // HANYA untuk admin -- lihat nav.js). Dicari ulang tiap poll (bukan
  // disimpan referensinya) karena sidebar di-render ULANG setiap pindah
  // menu (lihat router.js shell()), jadi elemen lama sudah tidak ada lagi
  // di DOM setelah navigasi. ----
  function _updateBadge(jumlah) {
    const badge = document.getElementById("booking-badge");
    if (!badge) return;
    if (jumlah > 0) {
      badge.textContent = jumlah > 99 ? "99+" : String(jumlah);
      badge.style.display = "";
    } else {
      badge.style.display = "none";
    }
  }

  function _bolehPoll() {
    if (typeof MugenState === "undefined" || !MugenState.isLoggedIn()) return false;
    const user = MugenState.getUser();
    return !!user && (user.role === "admin" || user.role === "staff");
  }

  function _hentikanReminder() {
    if (reminderTimer) {
      clearInterval(reminderTimer);
      reminderTimer = null;
    }
  }

  function _mulaiReminder() {
    if (reminderTimer) return; // sudah jalan
    reminderTimer = setInterval(() => {
      if (!_bolehPoll() || !(lastCount > 0)) {
        _hentikanReminder();
        return;
      }
      playChime();
    }, REMINDER_MS);
  }

  async function _poll() {
    if (!_bolehPoll()) {
      _updateBadge(0);
      lastCount = null;
      _hentikanReminder();
      return;
    }
    try {
      const hasil = await MugenApi.get("/api/booking/belum-dikonfirmasi");
      const jumlah = hasil.jumlah || 0;
      _updateBadge(jumlah);
      // Bunyi "booking baru masuk" HANYA kalau sudah ada baseline sebelumnya
      // (lastCount !== null) DAN angkanya naik -- supaya poll PERTAMA
      // setelah login/buka app (baseline belum diketahui) tidak dianggap
      // "booking baru" walau kebetulan sudah ada tunggakan booking lama.
      if (lastCount !== null && jumlah > lastCount) {
        playChime();
      }
      lastCount = jumlah;
      if (jumlah > 0) _mulaiReminder();
      else _hentikanReminder();
    } catch (e) {
      // offline/gagal fetch -- diamkan, dicoba lagi di poll berikutnya (pola sama seperti sync_helper.py retry)
    }
  }

  // Dipanggil router.js (tiap pindah menu) dan booking.js (setelah aksi
  // Verifikasi/Batalkan) supaya badge langsung ter-update saat itu juga --
  // SATU-SATUNYA jalur badge ini diperbarui sekarang (lihat init()).
  function refreshNow() {
    _poll();
  }

  // OPTIMASI BANDWIDTH: TIDAK ADA lagi setInterval ke jaringan sama sekali
  // -- badge diperbarui murni event-driven: sekali saat app dibuka (di
  // sini), lagi tiap kali user berpindah menu (router.js::handle(), lihat
  // komentar di atas file ini), setelah aksi Verifikasi/Batalkan
  // (booking.js memanggil refreshNow()), dan saat tab ini kembali
  // terlihat setelah disembunyikan (Page Visibility API -- reaksi atas
  // tab di-switch oleh user, BUKAN timer). Reminder chime (playChime(),
  // lihat _mulaiReminder()) SENGAJA TIDAK terpengaruh -- itu murni bunyi
  // lokal dari lastCount yang sudah diketahui, tanpa request jaringan
  // apa pun.
  function init() {
    _poll();
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") _poll(); // data mungkin sudah basi selama tab disembunyikan
    });
  }

  return { init, refreshNow };
})();
