// push_notif.js — FITUR Notifikasi Push (Web Push/VAPID, termasuk iPhone
// lewat PWA "Add to Home Screen" sejak iOS 16.4 -- Safari browser biasa
// TIDAK mendukung Web Push sama sekali, HANYA versi yang sudah di-install
// ke Home Screen).
//
// SENGAJA opt-in lewat tombol eksplisit (pages/pengaturan.js untuk admin/
// staff, pages/izin_cuti.js untuk barber) -- TIDAK PERNAH auto-prompt izin
// notifikasi begitu app dibuka (browser membatasi berapa kali Notification.
// requestPermission() boleh diminta sebelum permanen "Denied", jadi diminta
// SEKALI saat pengguna benar-benar menekan tombol "Aktifkan").
//
// Dukungan (isSupported()) sengaja dicek TERPISAH dari status enabled
// backend (GET /api/push/vapid-public-key) -- keduanya independen: browser
// bisa mendukung Push API tapi Owner belum isi VAPID_*, atau sebaliknya
// (browser lama/Safari tab biasa) tidak mendukung sama sekali.
const MugenPushNotif = (() => {
  function isSupported() {
    return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  }

  // Web Push API butuh applicationServerKey dalam bentuk Uint8Array (bukan
  // string base64 polos dari backend) -- konversi standar base64url ->
  // Uint8Array, lihat dokumentasi MDN Push API.
  function _urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const rawData = atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; i++) outputArray[i] = rawData.charCodeAt(i);
    return outputArray;
  }

  async function getStatusBackend() {
    // Gagal diam-diam (fitur opsional, TIDAK boleh mengganggu halaman
    // manapun yang memanggilnya) -- pola sama seperti pengecekan Uang
    // Harian Dinamis aktif di absensi.js.
    try {
      return await MugenApi.get("/api/push/vapid-public-key");
    } catch (e) {
      return { enabled: false, public_key: null };
    }
  }

  async function subscriptionAktif() {
    if (!isSupported()) return false;
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    return sub !== null;
  }

  async function aktifkan() {
    if (!isSupported()) {
      throw new Error(
        "Perangkat/browser ini tidak mendukung Notifikasi Push. Khusus iPhone: harus lewat aplikasi " +
          '"Add to Home Screen" (bukan tab Safari biasa), minimal iOS 16.4.'
      );
    }
    const status = await getStatusBackend();
    if (!status.enabled || !status.public_key) {
      throw new Error("Notifikasi Push belum diaktifkan Owner untuk toko ini.");
    }
    const izin = await Notification.requestPermission();
    if (izin !== "granted") {
      throw new Error("Izin notifikasi ditolak. Aktifkan lewat pengaturan browser/HP kalau ingin mencoba lagi.");
    }
    const reg = await navigator.serviceWorker.ready;
    let sub = await reg.pushManager.getSubscription();
    if (!sub) {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: _urlBase64ToUint8Array(status.public_key),
      });
    }
    const json = sub.toJSON();
    await MugenApi.post("/api/push/subscribe", {
      endpoint: json.endpoint,
      keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
    });
    return true;
  }

  async function nonaktifkan() {
    if (!isSupported()) return;
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (!sub) return;
    const endpoint = sub.endpoint;
    await sub.unsubscribe();
    try {
      await MugenApi.post("/api/push/unsubscribe", { endpoint });
    } catch (e) {
      // Endpoint sudah dicabut di sisi browser -- gagal memberi tahu
      // backend (mis. offline) bukan masalah besar, baris lama di
      // push_subscriptions otomatis dibersihkan sendiri oleh
      // push_service.py begitu provider push membalas 410/404 saat
      // dipakai lain kali.
    }
  }

  // Kartu UI siap pakai (dipanggil pages/pengaturan.js tab Profil untuk
  // admin/staff, dan pages/izin_cuti.js renderBarberView untuk barber) --
  // SATU tempat supaya teks/perilaku toggle konsisten di kedua halaman,
  // tidak perlu duplikasi. Gagal diam-diam & kartu tidak ditampilkan sama
  // sekali kalau backend belum enabled (VAPID_* belum diisi Owner) --
  // fitur opsional, TIDAK boleh mengganggu halaman manapun.
  async function renderCard(container) {
    const status = await getStatusBackend();
    if (!status.enabled) return;

    const card = MugenUI.el("div", { class: "card" });
    container.appendChild(card);
    card.appendChild(MugenUI.el("h2", {}, "Notifikasi Push"));
    card.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:10px;" },
      "Dapat notifikasi langsung di HP walau aplikasi sedang tertutup. Khusus iPhone: WAJIB \"Add to Home " +
      "Screen\" dulu (buka lewat Safari > tombol Share > Add to Home Screen), lalu buka aplikasinya dari " +
      "ikon di layar utama -- notifikasi TIDAK bisa diaktifkan lewat tab Safari biasa."));

    if (!isSupported()) {
      card.appendChild(MugenUI.el("div", { class: "subtitle" },
        "Perangkat/browser ini belum mendukung Notifikasi Push."));
      return;
    }

    const errorBox = MugenUI.el("div", { class: "login-error" });
    const btnToggle = MugenUI.el("button", { class: "btn-primary" }, "Memeriksa…");
    card.appendChild(errorBox);
    card.appendChild(MugenUI.el("div", { style: "margin-top:8px;" }, btnToggle));

    async function segarkanTombol() {
      const aktif = await subscriptionAktif();
      btnToggle.textContent = aktif ? "Nonaktifkan Notifikasi" : "Aktifkan Notifikasi";
      btnToggle.dataset.aktif = aktif ? "1" : "0";
    }

    btnToggle.addEventListener("click", async () => {
      errorBox.textContent = "";
      try {
        await MugenUI.withButtonLoading(btnToggle, async () => {
          if (btnToggle.dataset.aktif === "1") {
            await nonaktifkan();
          } else {
            await aktifkan();
          }
        });
        await segarkanTombol();
        MugenUI.toast("Pengaturan notifikasi disimpan.", "success");
      } catch (e) {
        errorBox.textContent = e.message || "Gagal mengatur notifikasi.";
      }
    });

    await segarkanTombol();
  }

  return { isSupported, getStatusBackend, subscriptionAktif, aktifkan, nonaktifkan, renderCard };
})();
