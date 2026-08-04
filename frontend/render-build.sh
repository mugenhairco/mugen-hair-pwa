#!/usr/bin/env bash
# render-build.sh — Build step untuk Render Static Site (frontend/).
# =============================================================================
# KENAPA FILE TERPISAH (bukan buildCommand multi-baris langsung di
# render.yaml): render.yaml sebelumnya menaruh skrip ini sebagai blok YAML
# multi-baris (`buildCommand: |`) -- di Render, itu GAGAL dengan
# "sed: can't read test: No such file or directory". Penyebabnya: Render
# TIDAK menjalankan `buildCommand` sebagai skrip multi-baris di mana setiap
# baris adalah statement terpisah -- newline di antara baris-baris itu
# runtuh jadi SATU baris panjang (spasi), sehingga argumen baris kedua
# ("test", "-n", "$SITE_URL", dst) ikut terbaca sebagai FILE TAMBAHAN oleh
# `sed -i` di baris pertama alih-alih dieksekusi sebagai perintah baru.
# `buildCommand` yang aman untuk Render HARUS satu baris -- solusinya:
# pindahkan seluruh logika ke skrip file sungguhan (file ini), dan
# `buildCommand` di render.yaml cukup `bash render-build.sh` (satu baris,
# tidak mungkin runtuh/ambigu lagi apa pun cara Render menjalankannya).
#
# Proyek ini TIDAK memakai bundler/proses build sungguhan (lihat README) --
# skrip ini HANYA menyuntikkan environment variable ke file statis yang
# sudah ada (config.js, meta tag SEO) sebelum dipublikasikan, bukan
# bundling/transpiling/minifikasi apa pun.

set -euo pipefail

if [ -n "${API_BASE_URL:-}" ]; then
  sed -i "s#window.MUGEN_API_BASE = .*#window.MUGEN_API_BASE = \"$API_BASE_URL\";#" config.js app/config.js
  echo "[render-build] API_BASE_URL diterapkan ke config.js + app/config.js: $API_BASE_URL"
else
  echo "[render-build] API_BASE_URL tidak diisi -- config.js dipakai apa adanya (nilai default di git)."
fi

if [ -n "${SITE_URL:-}" ]; then
  # grep -rl TIDAK menemukan apa pun = exit code 1 (bukan error sungguhan,
  # cuma "tidak ada yang perlu diganti") -- ditangkap eksplisit di sini
  # supaya `set -e` di atas tidak menganggap ini kegagalan build.
  matches="$(grep -rl 'https://www.rivoir.id' . --include='*.html' --include='*.xml' --include='*.txt' || true)"
  if [ -n "$matches" ]; then
    echo "$matches" | xargs -r sed -i "s#https://www.rivoir.id#$SITE_URL#g"
  fi
  echo "[render-build] SITE_URL diterapkan ke tag SEO/sitemap.xml/robots.txt: $SITE_URL"
else
  echo "[render-build] SITE_URL tidak diisi -- placeholder domain di tag SEO dibiarkan apa adanya."
fi

echo "[render-build] Selesai."
