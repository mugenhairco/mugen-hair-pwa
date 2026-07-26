// brand.js — TAHAP 10. Nama & logo barbershop TIDAK BOLEH lagi hardcode di
// source code (lihat instruksi Tahap 10). Modul ini satu-satunya tempat yang
// tahu cara membaca identitas barbershop dari backend (/api/pengaturan/identitas,
// endpoint publik — tidak perlu login, karena halaman Login pun perlu
// menampilkannya) dan menerapkannya ke elemen manapun yang diberi class
// "brand-name" / "brand-logo", di halaman manapun (Login, sidebar, dst).
//
// Dipakai localStorage sebagai cache supaya nama/logo langsung tampil tanpa
// "flash ke default" setiap kali halaman dibuka, lalu di-refresh ke data
// terbaru di background.

const MugenBrand = (() => {
  const KEY = "mugen_identitas_cache";
  const DEFAULT = { nama_barbershop: "MUGEN Hair Co.", logo_url: null };

  let current = DEFAULT;
  try {
    const cached = JSON.parse(localStorage.getItem(KEY));
    if (cached) current = cached;
  } catch (e) { /* cache rusak/tidak ada, pakai default */ }

  // REVISI: logo/banner sempat "tidak muncul/rusak" saat aplikasi pertama
  // dibuka -- warm up cache gambar milik browser sedini mungkin (begitu modul
  // ini dimuat, memakai data cache localStorage yang sudah ada) supaya saat
  // <img class="brand-logo"> nanti benar-benar butuh src ini, gambarnya
  // kemungkinan besar sudah ada di cache HTTP browser, bukan baru mulai
  // diunduh dari nol.
  function preload(url) {
    if (!url) return;
    const img = new Image();
    img.src = MUGEN_API_BASE + url;
  }
  preload(current.logo_url);
  preload(current.banner_url);

  function get() {
    return current;
  }

  function applyToDom() {
    document.title = current.nama_barbershop || DEFAULT.nama_barbershop;
    document.querySelectorAll(".brand-name").forEach((el) => {
      el.textContent = current.nama_barbershop || DEFAULT.nama_barbershop;
    });
    document.querySelectorAll(".brand-logo").forEach((el) => {
      if (current.logo_url) {
        // REVISI: sembunyikan dulu elemen sampai gambar TERBUKTI berhasil
        // dimuat (onload), dan tetap sembunyikan (bukan ikon broken-image)
        // kalau ternyata gagal dimuat (onerror) -- sebelumnya display
        // langsung diset "tampil" bersamaan dengan src diisi, jadi kalau
        // gambar gagal/lambat dimuat yang terlihat pengguna adalah ikon
        // gambar rusak, bukan placeholder kosong.
        el.style.display = "none";
        el.onload = () => { el.style.display = ""; };
        el.onerror = () => { el.style.display = "none"; el.removeAttribute("src"); };
        el.src = MUGEN_API_BASE + current.logo_url;
      } else {
        el.onload = null;
        el.onerror = null;
        el.removeAttribute("src");
        el.style.display = "none";
      }
    });
  }

  async function refresh() {
    try {
      const data = await MugenApi.get("/api/pengaturan/identitas");
      current = data;
      localStorage.setItem(KEY, JSON.stringify(data));
      preload(current.logo_url);
      preload(current.banner_url);
    } catch (e) {
      // offline / gagal -> tetap pakai cache/default yang sudah ada, jangan error-kan halaman
    }
    applyToDom();
    return current;
  }

  return { get, refresh, applyToDom };
})();
