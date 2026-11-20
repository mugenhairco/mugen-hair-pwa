// pages/absen_mandiri.js — Halaman PUBLIK "/absen" (hash "#/absen"), TANPA
// LOGIN -- FITUR BARU Absen Mandiri (Check In/Check Out GPS untuk karyawan
// Non-Barber: Kasir/OB/Kru/dst, yang TIDAK PERNAH punya akun login sama
// sekali, lihat karyawan_migrasi.py). Pola struktur SAMA PERSIS
// pages/book_public.js (dirender LANGSUNG ke #app, bukan lewat
// MugenRouter.shell() -- bukan bagian dari aplikasi internal), tapi JAUH
// lebih sederhana (tanpa wizard banyak langkah): pilih nama -> ambil lokasi
// -> Check In/Check Out.
//
// Device-lock (anti "titip absen", lihat absen_mandiri_db.py untuk
// penjelasan lengkap): device_id acak dibuat SEKALI per browser dan
// disimpan di localStorage -- dikirim di SETIAP Check In/Check Out supaya
// backend bisa mendeteksi percobaan dari device yang belum terdaftar untuk
// karyawan yang dipilih.
const PageAbsenMandiri = (() => {
  const KUNCI_DEVICE_ID = "mugen_absen_mandiri_device_id";

  function ambilDeviceId() {
    try {
      let id = localStorage.getItem(KUNCI_DEVICE_ID);
      if (!id) {
        id = (window.crypto && window.crypto.randomUUID)
          ? window.crypto.randomUUID()
          : `dev-${Date.now()}-${Math.random().toString(36).slice(2)}`;
        localStorage.setItem(KUNCI_DEVICE_ID, id);
      }
      return id;
    } catch (e) {
      // localStorage bisa gagal (private mode/kuota penuh dkk) -- fallback
      // ID sekali pakai per render (device-lock tidak akan "nempel" antar
      // kunjungan, tapi Check In/Out tetap bisa berjalan, cuma tidak
      // terlindungi device-lock untuk sesi kali ini).
      return `dev-sementara-${Date.now()}`;
    }
  }

  function ambilLokasi() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error("Perangkat/browser ini tidak mendukung Geolocation."));
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve(pos.coords),
        (err) => {
          let pesan = "Gagal mengambil lokasi.";
          if (err.code === err.PERMISSION_DENIED) pesan = "Izin lokasi ditolak. Aktifkan izin lokasi untuk Check In/Check Out.";
          else if (err.code === err.POSITION_UNAVAILABLE) pesan = "Lokasi tidak tersedia. Pastikan GPS aktif.";
          else if (err.code === err.TIMEOUT) pesan = "Waktu pengambilan lokasi habis. Coba lagi.";
          reject(new Error(pesan));
        },
        { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 },
      );
    });
  }

  function jamDariIso(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  }

  function pesanError(e) {
    return (e && e.detail && e.detail.detail) ? e.detail.detail : (e && e.message) || "Terjadi kesalahan.";
  }

  async function renderDaftarNama(root, karyawan) {
    root.innerHTML = "";
    const card = MugenUI.el("div", { class: "card", style: "max-width:480px;margin:32px auto;" });
    root.appendChild(card);
    card.appendChild(MugenUI.el("h2", {}, "Absen Mandiri"));
    card.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:16px;" },
      "Pilih nama Anda, lalu lanjutkan Check In/Check Out menggunakan lokasi perangkat ini."));

    if (!karyawan.length) {
      card.appendChild(MugenUI.errorState("Belum ada karyawan yang terdaftar untuk Absen Mandiri. Hubungi Admin/Owner toko."));
      return;
    }

    const daftar = MugenUI.el("div", { style: "display:flex;flex-direction:column;gap:8px;" });
    card.appendChild(daftar);
    for (const k of karyawan) {
      const btn = MugenUI.el("button", { type: "button", style: "text-align:left;" },
        `${k.nama}${k.jabatan ? ` (${k.jabatan})` : ""}`);
      btn.addEventListener("click", () => renderDetailKaryawan(root, k));
      daftar.appendChild(btn);
    }
  }

  async function renderDetailKaryawan(root, karyawan) {
    root.innerHTML = "";
    const card = MugenUI.el("div", { class: "card", style: "max-width:480px;margin:32px auto;" });
    root.appendChild(card);
    const btnKembali = MugenUI.el("button", { type: "button", style: "margin-bottom:12px;" }, "← Pilih Nama Lain");
    btnKembali.addEventListener("click", () => renderHalamanUtama(root));
    card.appendChild(btnKembali);
    card.appendChild(MugenUI.el("h2", {}, karyawan.nama));
    if (karyawan.jabatan) card.appendChild(MugenUI.el("div", { class: "subtitle" }, karyawan.jabatan));

    const body = MugenUI.el("div", { style: "margin-top:16px;" });
    card.appendChild(body);

    async function muat() {
      body.innerHTML = "";
      body.appendChild(MugenUI.skeleton("card", { lines: 3 }));
      let data;
      try {
        data = await MugenApi.get(`/api/public/absen-mandiri/status/${karyawan.id}`);
      } catch (e) {
        body.innerHTML = "";
        body.appendChild(MugenUI.errorState(pesanError(e)));
        return;
      }
      body.innerHTML = "";
      const log = data.log, status = data.status;

      body.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:24px;margin-bottom:16px;" }, [
        MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Jam Check In"), MugenUI.el("div", {}, jamDariIso(log && log.check_in_at))]),
        MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Jam Check Out"), MugenUI.el("div", {}, jamDariIso(log && log.check_out_at))]),
      ]));

      const sudahCheckIn = !!(log && log.check_in_at);
      const sudahCheckOut = !!(log && log.check_out_at);

      if (sudahCheckIn && sudahCheckOut) {
        body.appendChild(MugenUI.el("div", { class: "subtitle" }, "Anda sudah Check In & Check Out hari ini. Sampai jumpa besok!"));
        return;
      }

      const btn = MugenUI.el("button", { class: "btn-primary" }, sudahCheckIn ? "Check Out" : "Check In");
      body.appendChild(MugenUI.el("div", {}, btn));

      btn.addEventListener("click", async () => {
        const jenis = sudahCheckIn ? "check-out" : "check-in";
        const ok = await MugenUI.confirmModal({
          title: sudahCheckIn ? "Konfirmasi Check Out" : "Konfirmasi Check In",
          message: `Anda akan ${sudahCheckIn ? "Check Out" : "Check In"} sekarang sebagai ${karyawan.nama}, menggunakan lokasi perangkat ini. Lanjutkan?`,
          confirmText: sudahCheckIn ? "Check Out" : "Check In",
        });
        if (!ok) return;
        try {
          await MugenUI.withButtonLoading(btn, async () => {
            const coords = await ambilLokasi();
            await MugenApi.post(`/api/public/absen-mandiri/${jenis}`, {
              barber_id: karyawan.id, latitude: coords.latitude, longitude: coords.longitude,
              accuracy: coords.accuracy, speed: coords.speed, heading: coords.heading,
              device_id: ambilDeviceId(),
            });
          });
          MugenUI.toast(sudahCheckIn ? "Check Out berhasil." : "Check In berhasil.", "success");
          muat();
        } catch (e) {
          MugenUI.infoModal({ title: "Gagal", body: MugenUI.el("p", {}, pesanError(e)) });
        }
      });
    }
    muat();
  }

  async function renderHalamanUtama(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.el("div", { class: "mugen-state" }, "Memuat..."));
    let karyawan;
    try {
      karyawan = await MugenApi.get("/api/public/absen-mandiri/karyawan");
    } catch (e) {
      root.innerHTML = "";
      const card = MugenUI.el("div", { class: "card", style: "max-width:480px;margin:32px auto;" });
      root.appendChild(card);
      card.appendChild(MugenUI.errorState(pesanError(e)));
      return;
    }
    renderDaftarNama(root, karyawan);
  }

  async function render(root) {
    if (typeof MugenTheme !== "undefined") MugenTheme.forceLight();
    renderHalamanUtama(root);
  }

  return { render };
})();

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js (lihat
// router.js) -- top-level "const" TIDAK menempel ke objek window di
// browser (beda dari "var"), jadi page_loader.js TIDAK BISA mendeteksi
// lewat window.PageAbsenMandiri begitu saja setelah script ini selesai
// dimuat. Baris ini SATU-SATUNYA perubahan di file ini untuk mendukung
// lazy-load -- expose eksplisit ke window supaya page_loader.js bisa
// memverifikasi modul benar-benar berhasil dimuat sebelum memanggil
// render()-nya (pola SAMA PERSIS pages/input_data.js/book_public.js).
window.PageAbsenMandiri = PageAbsenMandiri;
