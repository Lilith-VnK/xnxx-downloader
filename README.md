# xnxx Video Downloader with Auto-Update

Downloader skrip berbasis Python untuk mengunduh video dari situs xnxx.com dengan berbagai fitur seperti resume download, konversi format, dan auto update.

## ⚠️ PERINGATAN LEGAL

> **Skrip ini hanya untuk tujuan edukasi dan penggunaan pribadi. xnxx.com memiliki Terms of Service yang ketat. Jangan gunakan skrip ini untuk tujuan ilegal atau melanggar hak cipta. Dengan menggunakan skrip ini, Anda menyetujui bahwa Anda bertanggung jawab penuh atas penggunaan skrip ini.**

## ✅ Fitur Utama

- **Auto Update**: Skrip akan memeriksa dan mengunduh versi terbaru secara otomatis.
- **Resume Download**: Mendukung lanjutkan unduhan yang terputus.
- **Pilih Kualitas Video**: Pilih antara `low`, `high`, atau `hls`.
- **Batch Mode**: Unduh beberapa video sekaligus dari file teks.
- **Folder Output Khusus**: Simpan video di direktori khusus.
- **Notifikasi (Termux)**: Dapatkan notifikasi saat unduhan selesai.
- **Konversi Format**: Konversi video ke format lain (misalnya MP3).
- **Download Thumbnail**: Unduh gambar pratinjau video.
- **User-Agent Dinamis**: Menghindari pemblokiran dengan `fake-useragent`.

## 📦 Prasyarat

Pastikan Anda telah menginstal Python dan library berikut:

```bash
pip install requests beautifulsoup4 fake-useragent tqdm argparse
```

### Tambahan (Opsional):
- **ffmpeg** (untuk konversi format):
  ```bash
  # Linux
  sudo apt install ffmpeg

  # Termux
  pkg install ffmpeg
  ```

- **termux-notification** (untuk notifikasi di Termux):
  ```bash
  pkg install termux-api
  ```

## 🔧 Penggunaan

### 🔹 Dasar

```bash
python xnxx.py [URL] --download
```

**Contoh**:
```bash
python xnxx.py https://www.xnxx.com/video-123456789/987654321 --download
```

## 🔹 Advanced Usage

| Opsi                  | Deskripsi                                      |
|-----------------------|------------------------------------------------|
| `--download`          | Mengunduh video                                |
| `--quality [low/high/hls]` | Pilih kualitas video                        |
| `--batch [file.txt]`  | Baca daftar URL dari file teks                 |
| `--output [folder]`   | Simpan video di folder khusus                  |
| `--delay [detik]`     | Tambahkan delay antar permintaan                |
| `--download-thumb`    | Unduh thumbnail video                           |
| `--convert [format]`  | Konversi video ke format lain (misalnya `--convert mp3`) |
| `--notify`            | Notifikasi saat unduhan selesai (Termux)      |

### Contoh:
```bash
python xnxx.py https://www.xnxx.com/video-123456789/ --download --quality high --output videos --notify --convert mp3 --download-thumb

## 📁 Batch Mode

Buat file teks dengan daftar URL, misalnya `urls.txt`:

```
https://www.xnxx.com/video-123456789/
https://www.xnxx.com/video-987654321/
```

Lalu jalankan:

```bash
python xnxx.py --batch urls.txt --download --output downloads --delay 5
```

## 🔁 Auto Update

Skrip akan memeriksa versi terbaru di GitHub setiap kali dijalankan. Jika tersedia pembaruan:

- Backup file lama dibuat (`.bak`)
- File baru diunduh
- Hash diverifikasi
- Skrip otomatis di-replace dan perlu dijalankan ulang

## 📁 Output

File akan disimpan di folder `downloads/` secara default atau folder yang Anda tentukan.

Contoh struktur output:

```
downloads/
├── Redhead_Makima.mp4
├── Redhead_Makima.mp3
├── Redhead_Makima_thumb.jpg
```

## 📝 Contoh Output JSON

```json
{
    "status": 200,
    "data": {
        "title": "Redhead Makima Dominates and Gives Pussy Licking, Rough Fucking and Dirty Talk - Cosplay from Chainsaw Man",
        "image": "https://cdn77-pic.xnxx-cdn.com/...",
        "files": {
            "low": "https://cdn77-vid-mp4.xnxx-cdn.com/...",
            "high": "https://cdn77-vid-mp4.xnxx-cdn.com/...",
            "HLS": "https://cdn77-vid.xnxx-cdn.com/..."
        }
    }
```
