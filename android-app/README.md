# MUGEN Hair Co. — Android App (Capacitor)

Wrapper Android native untuk PWA MUGEN Hair Co. memakai [Capacitor](https://capacitorjs.com/)
(bukan PWABuilder/Bubblewrap). Folder ini **terpisah total** dari `backend/`
dan `frontend/` di root repo — tidak ada satu baris pun kode/fitur/alur
kerja backend atau frontend yang diubah untuk proyek ini.

## Cara kerja: memuat website langsung, BUKAN membundel salinan frontend/

`capacitor.config.json` diatur dengan `server.url` mengarah LANGSUNG ke
```
https://mugen.rivoirsett.com/app/
```
(bukan root domain `rivoirsett.com` — itu landing page marketing SaaS
terpisah tanpa fitur login sama sekali, lihat `frontend/index.html`.
Juga BUKAN `rivoirsett.com/app/` tanpa subdomain tenant — path itu
sendiri langsung `location.replace()` ke `mugen.rivoirsett.com` lewat
script hotfix migrasi subdomain di `frontend/app/index.html`, dan
karena itu lintas-origin, Capacitor akan melempar navigasinya ke
browser eksternal alih-alih menampilkannya di WebView. Arahkan
langsung ke subdomain tenant final ini supaya tidak pernah terjadi
navigasi lintas-origin sama sekali). Artinya WebView aplikasi Android
ini selalu menampilkan versi TERBARU dari frontend yang sudah live di
produksi — persis seperti membuka URL itu di Chrome, hanya dibungkus
jadi aplikasi native dengan ikon/splash sendiri.
**Konsekuensinya**: setiap kali frontend di-deploy ulang, APK
yang sudah terinstal otomatis menampilkan versi terbaru TANPA perlu
build ulang APK — sama seperti PWA pada umumnya. APK hanya perlu dibuild
ulang kalau `appId`/`appName`/ikon/splash/konfigurasi native lain di
folder ini berubah.

Folder `www/` isinya cuma placeholder kosong (Capacitor mewajibkan
`webDir` ada) — TIDAK PERNAH ditampilkan, jangan taruh apa pun penting
di sana.

Karena ini navigasi HTTPS sungguhan (bukan bundel lokal), **semua fitur
PWA tetap berfungsi apa adanya di dalam WebView**: Login, Dashboard,
Input Data, Rekap, Booking, seluruh pemanggilan API (`js/api.js`), dan
Service Worker/offline cache (`service-worker.js`) — WebView Android
modern (Chromium-based, auto-update lewat Play Store di hampir semua
perangkat) mendukung Service Worker sama seperti Chrome biasa.

## Ikon & Splash Screen

Sumber ikon ada di `resources/` (`icon.png`, `icon-foreground.png`,
`icon-background.png`, `splash.png`, `splash-dark.png`). Yang terpasang
SEKARANG adalah logo resmi MUGEN Hair Co. yang sama dipakai ikon PWA
(`frontend/icons/`) — dipakai sebagai default awal supaya proyek ini
langsung bisa dibuild dengan tampilan yang benar tanpa menunggu aset
tambahan.

Kalau nanti ada file logo/splash art dedicated (resolusi lebih tinggi,
atau treatment khusus splash yang beda dari ikon), ganti file di
`resources/` (ikuti nama file yang sama, `icon.png` minimal 1024x1024,
`splash.png` minimal 2732x2732), lalu generate ulang seluruh ukuran:
```
npx @capacitor/assets generate --android
```
Ini akan menimpa semua density (`android/app/src/main/res/mipmap-*` dan
`drawable-*`) secara otomatis — tidak perlu edit manual.

## Prasyarat di komputer Anda

- **Node.js** (v18+) & npm — https://nodejs.org
- **Android Studio** (cara termudah — sudah termasuk Android SDK, JDK,
  dan emulator) — https://developer.android.com/studio

  *(Kalau tidak mau pakai Android Studio, alternatifnya install
  [Android SDK Command-line Tools](https://developer.android.com/studio#command-tools)
  + JDK 17 secara terpisah, lalu build lewat `gradlew` di terminal — lihat
  bagian "Build lewat command line" di bawah.)*

**Catatan penting**: proyek ini SUDAH di-scaffold lengkap (platform
Android sudah ditambahkan, dependency sudah terpasang) di lingkungan
kerja saya sendiri sampai tahap konfigurasi selesai — TAPI saya tidak
bisa menyelesaikan proses compile APK-nya sampai jadi file `.apk` dari
sini, karena `dl.google.com` (satu-satunya sumber resmi Android Gradle
Plugin & Android SDK) diblokir oleh kebijakan jaringan environment saya.
Build APK sungguhan (`gradlew assembleDebug` / tombol Build di Android
Studio) HARUS dijalankan di komputer Anda sendiri, mengikuti langkah di
bawah.

## Langkah build lengkap

### 1. Install dependency
```bash
cd android-app
npm install
```

### 2. Sync ke proyek native Android
```bash
npx cap sync android
```
(Perintah ini menyalin `capacitor.config.json` & plugin ke proyek
`android/`. Jalankan ulang setiap kali `capacitor.config.json` atau
dependency Capacitor berubah.)

### 3. Buka di Android Studio
```bash
npx cap open android
```
Ini otomatis membuka folder `android/` di Android Studio. Tunggu proses
"Gradle Sync" selesai (Android Studio otomatis mengunduh Android SDK
Platform 36 + build-tools yang dibutuhkan kalau belum ada — proses ini
butuh koneksi internet normal ke `dl.google.com`, yang di komputer Anda
seharusnya TIDAK diblokir).

### 4. Build APK debug
Di Android Studio: menu **Build → Build App Bundle(s) / APK(s) → Build APK(s)**.

Setelah selesai, klik notifikasi "APK(s) generated successfully" →
**locate** untuk membuka folder hasilnya, atau cari manual di:
```
android-app/android/app/build/outputs/apk/debug/app-debug.apk
```

**APK ini SUDAH signed** — Android Gradle Plugin otomatis menandatangani
build varian `debug` memakai *debug keystore* bawaan (dibuat otomatis di
`~/.android/debug.keystore` saat build pertama kali kalau belum ada,
tidak perlu diatur manual). Ini beda dari APK unsigned yang sebelumnya
dihasilkan PWABuilder — file ini langsung bisa diinstal.

### Build lewat command line (alternatif tanpa buka Android Studio)
```bash
cd android-app/android
./gradlew assembleDebug
```
Hasilnya di lokasi yang sama: `app/build/outputs/apk/debug/app-debug.apk`.

### 5. Instal ke HP Android
- Pindahkan `app-debug.apk` ke HP (USB/share file/email ke diri sendiri)
  lalu buka file-nya, ATAU
- `adb install app/build/outputs/apk/debug/app-debug.apk` kalau HP
  tersambung USB dengan USB Debugging aktif.
- Aktifkan **"Install unknown apps"** untuk aplikasi yang dipakai membuka
  file APK-nya (Setting → Apps → Special access → Install unknown apps)
  — wajib untuk APK apa pun yang bukan dari Play Store.

## Setelah `appId`/`appName` berubah lagi di masa depan

Kalau `capacitor.config.json` diubah (`appId`, `appName`, `server.url`,
dsb), jalankan `npx cap sync android` lagi sebelum build ulang supaya
perubahan itu ikut ke proyek native.
