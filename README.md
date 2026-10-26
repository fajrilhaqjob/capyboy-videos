# Capyboy: posting otomatis YouTube Shorts dan TikTok

Repo ini menyimpan 22 video (30 hari konten), jadwal tayang, dan skrip yang memasukkan video ke antrean Buffer
secara otomatis lewat GitHub Actions.

## Isi

- `videos/` 22 video Shorts (MP4 vertikal)
- `schedule/schedule.json` judul, caption, dan hari tayang tiap video. `start_date` = hari pertama, jam tayang 19.30 WIB
- `schedule/state.json` catatan video yang sudah masuk Buffer (diisi otomatis, jangan diedit)
- `scripts/queue_buffer.py` skrip yang membuat postingan di Buffer
- `workflow/buffer-queue.yml` isi workflow. Salin ke `.github/workflows/buffer-queue.yml`

## Cara kerja

1. Video diunduh Buffer dari GitHub Pages: `https://USERNAME.github.io/NAMA-REPO/videos/NN-judul.mp4`
2. Tiap hari pukul 06.00 WIB, GitHub Actions menjalankan skrip. Skrip memasukkan video 7 hari ke depan
   ke Buffer untuk YouTube dan TikTok, selama kapasitas antrean Buffer cukup (paket gratis: 10 postingan terjadwal).
3. Buffer memposting pada jam yang sudah ditentukan.

## Menggeser jadwal

Edit `start_date` di `schedule/schedule.json` (format `2026-10-27`). Semua hari tayang ikut bergeser.
Video yang sudah ada di antrean Buffer tidak diduplikasi. Hapus dulu dari Buffer kalau mau dijadwalkan ulang.

## Keamanan

API key Buffer hanya disimpan di GitHub Secrets dengan nama `BUFFER_API_KEY`. Jangan tulis di file mana pun.

## Menghentikan

Tab Actions > Antrekan ke Buffer > titik tiga > Disable workflow.
