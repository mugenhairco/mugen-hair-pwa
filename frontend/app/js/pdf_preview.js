// pdf_preview.js — Preview PDF (Perbaikan Alur Cetak PDF)
// =============================================================================
// Alur BARU untuk seluruh tombol "Cetak PDF"/"Download PDF" di aplikasi:
// Pilih Filter -> Generate PDF -> Preview PDF -> Download PDF atau Print PDF.
// PDF TIDAK PERNAH langsung terunduh lagi begitu tombol "Cetak PDF" ditekan
// -- server tetap membuat PDF yang SAMA PERSIS seperti sebelumnya (isi
// laporan/perhitungan TIDAK berubah sama sekali), hanya alurnya yang beda:
// hasilnya ditampilkan dulu di sini sebagai preview di dalam aplikasi,
// unduhan sungguhan HANYA terjadi kalau Owner menekan tombol "Download PDF"
// di preview ini.
//
// Dipakai lewat MugenPdfPreview.open({ generate, filename }):
//   generate  -> async function TANPA argumen, harus resolve ke Blob PDF
//                (biasanya () => MugenApi.fetchBlob(url)).
//   filename  -> nama file .pdf yang dipakai SAAT tombol Download ditekan
//                (sudah dibuat sesuai filter yang aktif oleh pemanggil).
//
// Render halaman pakai PDF.js (vendor/pdfjs/, lihat pdfjs_boot.js) ke
// <canvas> -- BUKAN <iframe> penampil bawaan browser, supaya Zoom In/Out +
// nomor halaman benar-benar kita kendalikan sendiri dan preview tetap
// konsisten di semua perangkat (banyak browser Android/PWA ter-install
// tidak bisa menampilkan PDF inline lewat <iframe> sama sekali).
const MugenPdfPreview = (() => {
  function ensurePdfJs() {
    if (window.pdfjsLib) return Promise.resolve();
    return new Promise((resolve) => window.addEventListener("pdfjs-ready", () => resolve(), { once: true }));
  }

  async function open({ generate, filename }) {
    let blob;
    try {
      blob = await MugenUI.withLoading(generate, { message: "Membuat PDF…" });
    } catch (e) {
      MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
      return;
    }

    await ensurePdfJs();

    let pdfDoc, loadingTask;
    try {
      const buf = await blob.arrayBuffer();
      loadingTask = window.pdfjsLib.getDocument({ data: buf });
      pdfDoc = await loadingTask.promise;
    } catch (e) {
      MugenUI.toast("Gagal menampilkan preview PDF.", "error", { force: true });
      return;
    }

    const numPages = pdfDoc.numPages;
    let pageNum = 1;
    let scale = null; // null = belum dihitung (fit-to-width pada render pertama)
    let fitScale = 1;
    let renderTask = null;

    const overlay = MugenUI.el("div", { class: "pdf-preview-overlay" });
    const btnKembali = MugenUI.el("button", { class: "pdf-preview-back", type: "button" }, "← Kembali");
    const btnZoomOut = MugenUI.el("button", { type: "button", title: "Perkecil" }, "−");
    const zoomLabel = MugenUI.el("span", { class: "pdf-preview-zoom-label" }, "100%");
    const btnZoomIn = MugenUI.el("button", { type: "button", title: "Perbesar" }, "+");
    const btnPrev = MugenUI.el("button", { type: "button", title: "Halaman sebelumnya" }, "‹");
    const pageLabel = MugenUI.el("span", { class: "pdf-preview-page-label" }, `Halaman 1 / ${numPages}`);
    const btnNext = MugenUI.el("button", { type: "button", title: "Halaman berikutnya" }, "›");
    const btnPrint = MugenUI.el("button", { type: "button" }, "🖨 Print");
    const btnDownload = MugenUI.el("button", { type: "button", class: "btn-primary" }, "⬇ Download PDF");

    const toolbar = MugenUI.el("div", { class: "pdf-preview-toolbar" }, [
      btnKembali,
      MugenUI.el("div", { class: "pdf-preview-zoom" }, [btnZoomOut, zoomLabel, btnZoomIn]),
      MugenUI.el("div", { class: "pdf-preview-page-nav" }, [btnPrev, pageLabel, btnNext]),
      MugenUI.el("div", { class: "pdf-preview-actions" }, [
        ...(typeof window.print === "function" ? [btnPrint] : []),
        btnDownload,
      ]),
    ]);
    const canvas = MugenUI.el("canvas", { class: "pdf-preview-canvas" });
    const body = MugenUI.el("div", { class: "pdf-preview-body" }, canvas);
    overlay.appendChild(toolbar);
    overlay.appendChild(body);
    document.body.appendChild(overlay);

    function tutup() {
      // REVISI UI/UX Premium: animasi KELUAR sungguhan (sebelumnya
      // .remove() instan, overlay ini SEBELUMNYA tidak beranimasi sama
      // sekali baik buka maupun tutup) -- buka sudah otomatis lewat
      // animation di .pdf-preview-overlay (style.css), tutup di sini
      // menunggu mugen-overlay-out selesai (var(--dur-fast)) sebelum
      // benar-benar dilepas dari DOM.
      overlay.classList.add("closing");
      setTimeout(() => {
        overlay.remove();
        loadingTask.destroy();
        window.removeEventListener("resize", onResize);
      }, 120);
    }

    async function renderCurrentPage() {
      if (renderTask) {
        try { renderTask.cancel(); } catch (e) { /* abaikan -- halaman lama sedang dibatalkan */ }
      }
      const page = await pdfDoc.getPage(pageNum);
      if (scale === null) {
        const vpAsli = page.getViewport({ scale: 1 });
        const lebarTersedia = Math.max(200, body.clientWidth - 24);
        fitScale = lebarTersedia / vpAsli.width;
        scale = fitScale;
      }
      const viewport = page.getViewport({ scale });
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const task = page.render({ canvasContext: canvas.getContext("2d"), viewport });
      renderTask = task;
      try {
        await task.promise;
      } catch (e) {
        if (!e || e.name !== "RenderingCancelledException") throw e;
        return;
      } finally {
        if (renderTask === task) renderTask = null;
      }
      zoomLabel.textContent = `${Math.round((scale / fitScale) * 100)}%`;
      pageLabel.textContent = `Halaman ${pageNum} / ${numPages}`;
      btnPrev.disabled = pageNum <= 1;
      btnNext.disabled = pageNum >= numPages;
    }

    function terapkanZoom(faktor) {
      const baru = scale * faktor;
      const minScale = fitScale * 0.4;
      const maxScale = fitScale * 4;
      scale = Math.min(maxScale, Math.max(minScale, baru));
      renderCurrentPage();
    }

    btnKembali.addEventListener("click", tutup);
    btnZoomIn.addEventListener("click", () => terapkanZoom(1.2));
    btnZoomOut.addEventListener("click", () => terapkanZoom(1 / 1.2));
    btnPrev.addEventListener("click", () => {
      if (pageNum <= 1) return;
      pageNum -= 1;
      renderCurrentPage();
    });
    btnNext.addEventListener("click", () => {
      if (pageNum >= numPages) return;
      pageNum += 1;
      renderCurrentPage();
    });
    btnDownload.addEventListener("click", () => {
      MugenApi.saveBlob(blob, filename);
    });
    btnPrint.addEventListener("click", async () => {
      btnPrint.disabled = true;
      const areaCetak = MugenUI.el("div", { class: "pdf-preview-print-area" });
      try {
        await MugenUI.withLoading(async () => {
          for (let i = 1; i <= numPages; i++) {
            const page = await pdfDoc.getPage(i);
            const viewport = page.getViewport({ scale: 2 }); // resolusi lebih tinggi dari layar khusus cetak
            const c = document.createElement("canvas");
            c.width = viewport.width;
            c.height = viewport.height;
            await page.render({ canvasContext: c.getContext("2d"), viewport }).promise;
            areaCetak.appendChild(MugenUI.el("img", { src: c.toDataURL("image/png") }));
          }
        }, { message: "Menyiapkan cetak…" });
        document.body.appendChild(areaCetak);
        window.print();
      } catch (e) {
        MugenUI.toast("Gagal menyiapkan Print.", "error", { force: true });
      } finally {
        areaCetak.remove();
        btnPrint.disabled = false;
      }
    });

    function onResize() {
      scale = null; // hitung ulang fit-to-width kalau layar berganti ukuran/orientasi
      renderCurrentPage();
    }
    window.addEventListener("resize", onResize);

    await renderCurrentPage();
  }

  return { open };
})();
