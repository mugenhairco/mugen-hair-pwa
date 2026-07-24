// pages/sinkronisasi.js — TAHAP 12: Status Sinkronisasi Google Sheets.
// Khusus Owner (admin), sama seperti Pengeluaran/Produk/Setting: status
// sinkron adalah status operasional TOKO (satu database, satu tujuan
// sinkron), bukan data milik barber manapun. Perlindungan sebenarnya tetap
// di backend (require_admin di setiap endpoint /api/sync/*).
//
// Dua bagian:
// 1. Status Sinkronisasi: jumlah data belum sinkron, waktu sinkron terakhir,
//    status berhasil/gagal + tombol "Sinkronkan Sekarang".
// 2. Backup & Restore Database: menu baru di Tahap 12, TAPI memanggil
//    endpoint /api/pengaturan/backup/export & /import yang SAMA PERSIS
//    dengan yang sudah ada sejak Tahap 10 (routers/pengaturan.py TIDAK
//    disentuh) -- supaya logika backup/restore tetap hanya ada di satu
//    tempat, halaman ini cuma menambah jalan pintas ke situ.

const PageSinkronisasi = (() => {
  function formatWaktu(iso) {
    if (!iso) return "Belum pernah";
    return new Date(iso).toLocaleString("id-ID");
  }

  function statusBadge(status) {
    const label = { berhasil: "Berhasil", gagal: "Gagal", belum_pernah: "Belum pernah sinkron" }[status] || status;
    const kelas = status === "berhasil" ? "badge-success" : status === "gagal" ? "badge-danger" : "";
    return MugenUI.el("span", { class: "badge " + kelas }, label);
  }

  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Sinkronisasi"));

    const statusCard = MugenUI.el("div", { class: "card" });
    const backupCard = MugenUI.el("div", { class: "card" });
    root.appendChild(statusCard);
    root.appendChild(backupCard);

    // ---------------------------------------------------------------
    // 1. STATUS SINKRONISASI
    // ---------------------------------------------------------------
    statusCard.appendChild(MugenUI.el("h2", {}, "Status Sinkronisasi"));
    statusCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Data selalu tersimpan lebih dulu di database lokal (SQLite) apa pun status sinkronnya. " +
      "Sinkron ke Google Sheets berjalan otomatis setiap ada data baru, dan dicoba ulang otomatis " +
      "secara berkala kalau sebelumnya gagal (mis. saat koneksi internet sedang tidak ada)."));

    const statusBody = MugenUI.el("div");
    statusCard.appendChild(statusBody);

    const btnSyncSekarang = MugenUI.el("button", { class: "btn-primary" }, "Sinkronkan Sekarang");
    statusCard.appendChild(MugenUI.el("div", { style: "margin-top:14px;" }, btnSyncSekarang));

    async function loadStatus() {
      statusBody.innerHTML = "Memuat...";
      try {
        const s = await MugenApi.get("/api/sync/status");
        statusBody.innerHTML = "";

        if (!s.dikonfigurasi) {
          statusBody.appendChild(MugenUI.el("div", { class: "offline-banner" },
            "Google Sheets belum dikonfigurasi di server ini (GOOGLE_SHEET_ID / kredensial service account " +
            "belum diisi). Data tetap aman tersimpan lokal, tapi belum bisa tersinkron ke cloud."));
        }

        const grid = MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:14px;" }, [
          statCard("Jumlah Data Belum Sinkron", String(s.jumlah_belum_sinkron)),
          statCardNode("Waktu Sinkron Terakhir", MugenUI.el("div", { class: "big-number", style: "font-size:16px;" }, formatWaktu(s.last_sync_at))),
          statCardNode("Status Sinkron Terakhir", statusBadge(s.last_sync_status)),
        ]);
        statusBody.appendChild(grid);

        if (s.last_sync_message) {
          statusBody.appendChild(MugenUI.el("div", { class: "login-error", style: "margin-top:10px;" },
            `Pesan terakhir: ${s.last_sync_message}`));
        }
      } catch (e) {
        statusBody.innerHTML = "";
        statusBody.appendChild(MugenUI.el("div", {}, e.message));
      }
    }

    function statCard(label, value) {
      return MugenUI.el("div", { class: "card", style: "flex:1;min-width:220px;" }, [
        MugenUI.el("h2", {}, label),
        MugenUI.el("div", { class: "big-number" }, value),
      ]);
    }

    function statCardNode(label, node) {
      return MugenUI.el("div", { class: "card", style: "flex:1;min-width:220px;" }, [
        MugenUI.el("h2", {}, label),
        node,
      ]);
    }

    btnSyncSekarang.addEventListener("click", async () => {
      btnSyncSekarang.disabled = true;
      btnSyncSekarang.textContent = "Menyinkronkan...";
      try {
        const hasil = await MugenApi.post("/api/sync/sekarang", {});
        if (hasil.last_sync_status === "berhasil") {
          MugenUI.toast("Sinkronisasi berhasil.", "success");
        } else {
          MugenUI.toast(hasil.last_sync_message || "Sinkronisasi gagal.", "error");
        }
      } catch (e) {
        MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
      } finally {
        btnSyncSekarang.disabled = false;
        btnSyncSekarang.textContent = "Sinkronkan Sekarang";
        loadStatus();
      }
    });

    // ---------------------------------------------------------------
    // 2. BACKUP & RESTORE DATABASE (menu baru, endpoint lama Tahap 10)
    // ---------------------------------------------------------------
    backupCard.appendChild(MugenUI.el("h2", {}, "Backup Database"));
    backupCard.appendChild(MugenUI.el("div", { class: "subtitle" }, "Unduh salinan file database saat ini (.db)."));
    const btnExport = MugenUI.el("button", { class: "btn-primary" }, "Backup Database");
    backupCard.appendChild(MugenUI.el("div", { style: "margin:12px 0 24px;" }, btnExport));

    btnExport.addEventListener("click", async () => {
      btnExport.disabled = true;
      try {
        const token = MugenState.getToken();
        const res = await fetch(MUGEN_API_BASE + "/api/pengaturan/backup/export", {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) throw new Error("Gagal mengunduh backup.");
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `mugen_hair_backup_${new Date().toISOString().slice(0, 10)}.db`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        MugenUI.toast("Backup berhasil diunduh.", "success");
      } catch (e) {
        MugenUI.toast(e.message, "error");
      } finally {
        btnExport.disabled = false;
      }
    });

    backupCard.appendChild(MugenUI.el("h2", {}, "Restore Database"));
    backupCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "PERHATIAN: ini akan MENGGANTI seluruh data yang sedang berjalan dengan isi file yang diupload. " +
      "Database yang sedang aktif otomatis di-backup dulu sebelum diganti, tapi tetap lakukan ini dengan hati-hati."));
    const inputRestore = MugenUI.el("input", { type: "file", accept: ".db" });
    const btnRestore = MugenUI.el("button", { class: "btn-danger" }, "Restore Database");
    const restoreError = MugenUI.el("div", { class: "login-error" });
    backupCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin:12px 0;" }, [inputRestore, btnRestore]));
    backupCard.appendChild(restoreError);

    btnRestore.addEventListener("click", async () => {
      restoreError.textContent = "";
      if (!inputRestore.files || !inputRestore.files[0]) { restoreError.textContent = "Pilih file .db dulu."; return; }
      if (!confirm("Yakin ingin mengganti seluruh database yang sedang berjalan dengan file ini? Tindakan ini tidak mudah dibatalkan.")) return;
      btnRestore.disabled = true;
      try {
        await MugenApi.uploadFile("/api/pengaturan/backup/import", inputRestore.files[0]);
        MugenUI.toast("Database berhasil di-restore. Memuat ulang halaman...", "success");
        setTimeout(() => location.reload(), 1500);
      } catch (e) {
        restoreError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      } finally {
        btnRestore.disabled = false;
      }
    });

    await loadStatus();
  }

  return { render };
})();
