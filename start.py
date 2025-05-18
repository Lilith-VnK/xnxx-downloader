import sys
import os
import time
import json
import re
import argparse
import requests
import subprocess
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from tqdm import tqdm
import hashlib

# === Auto Update ===
def check_update(repo_url, local_path):
    try:
        print("[INFO] Memeriksa pembaruan skrip...")
        response = requests.get(repo_url)
        if response.status_code == 200:
            remote_sha = hashlib.sha256(response.content).hexdigest()
            try:
                with open(local_path, 'rb') as f:
                    local_sha = hashlib.sha256(f.read()).hexdigest()
            except FileNotFoundError:
                local_sha = ""

            if remote_sha != local_sha:
                print("[INFO] Pembaruan tersedia. Mengunduh versi terbaru...")
                with open(local_path, "wb") as f:
                    f.write(response.content)
                print("[INFO] Skrip berhasil diperbarui. Silakan jalankan ulang.")
                sys.exit(0)
            else:
                print("[INFO] Skrip sudah versi terbaru.")
        else:
            print("[ERROR] Gagal memeriksa pembaruan.")
    except Exception as e:
        print(f"[ERROR] Kesalahan saat memeriksa pembaruan: {str(e)}")
        
GITHUB_SCRIPT_URL = "https://raw.githubusercontent.com/username/repo/main/xnxx.py"
LOCAL_SCRIPT_PATH = sys.argv[0]

check_update(GITHUB_SCRIPT_URL, LOCAL_SCRIPT_PATH)

# === Parsing Argumen ===
def parse_args():
    parser = argparse.ArgumentParser(description="Downloader Video xnxx.com dengan fitur lengkap")
    parser.add_argument("url", nargs="?", help="URL video xnxx.com")
    parser.add_argument("--download", action="store_true", help="Unduh video")
    parser.add_argument("--quality", default="high", choices=["low", "high", "hls"], help="Pilih kualitas video")
    parser.add_argument("--batch", help="Baca daftar URL dari file teks")
    parser.add_argument("--output", default="downloads", help="Folder output untuk menyimpan video")
    parser.add_argument("--delay", type=int, default=0, help="Delay antar permintaan (detik)")
    parser.add_argument("--download-thumb", action="store_true", help="Unduh thumbnail video")
    parser.add_argument("--convert", help="Konversi video ke format lain (misalnya mp3)")
    parser.add_argument("--notify", action="store_true", help="Notifikasi saat unduhan selesai (Termux)")
    return parser.parse_args()

def show_disclaimer():
    print("""
    ⚠️ PERINGATAN LEGAL:
    Skrip ini hanya untuk tujuan edukasi dan penggunaan pribadi.
    xnxx.com memiliki Terms of Service yang ketat.
    Jangan gunakan skrip ini untuk tujuan ilegal atau melanggar hak cipta.
    Dengan melanjutkan, Anda menyetujui bahwa Anda bertanggung jawab penuh atas penggunaan skrip ini.
    """)
    agree = input("Setujui? (y/n): ").lower()
    if agree != "y":
        print("Keluar: Anda tidak menyetujui disclaimer.")
        sys.exit(1)

def download_video(url, headers, filename, output_dir):
    full_path = os.path.join(output_dir, filename)
    downloaded = 0
    mode = 'ab' if os.path.exists(full_path) else 'wb'

    try:
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(max_retries=3)
        session.mount('https://', adapter)

        with session.get(url, headers=headers, stream=True, timeout=15) as r:
            r.raise_for_status()

            total_size = int(r.headers.get('content-length', 0))
            if total_size == 0:
                print(f"[INFO] Ukuran file tidak diketahui. Tidak bisa menampilkan progress.")
                total_size = 0

            if os.path.exists(full_path):
                downloaded = os.path.getsize(full_path)
                if downloaded >= total_size:
                    print(f"[INFO] File {filename} sudah lengkap.")
                    return
                headers['Range'] = f'bytes={downloaded}-'
                r = session.get(url, headers=headers, stream=True, timeout=15)

            chunk_size = 32 * 1024  # 32 KB
            with open(full_path, mode) as f:
                with tqdm(total=total_size, initial=downloaded, unit='B', unit_scale=True, desc="📥 Mengunduh", ncols=100) as pbar:
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
            print(f"\n[INFO] Unduhan {filename} selesai.")
    except requests.exceptions.RequestException as e:
        print(f"\n[ERROR] Gagal mengunduh {filename}: {str(e)}")
    except KeyboardInterrupt:
        print("\n\n[INFO] Unduhan dihentikan oleh pengguna (Ctrl+C).")
        print("       Anda bisa melanjutkan dengan flag resume.\n")

# === Download Thumbnail ===
def download_thumbnail(url, headers, filename, output_dir):
    full_path = os.path.join(output_dir, filename)
    try:
        with requests.get(url, headers=headers, stream=True) as r:
            r.raise_for_status()
            with open(full_path, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
        print(f"[INFO] Thumbnail {filename} diunduh.")
    except Exception as e:
        print(f"[ERROR] Gagal mengunduh thumbnail: {str(e)}")

# === Konversi Format Video ===
def convert_video(input_path, output_path, format):
    try:
        print(f"[INFO] Mengonversi {input_path} ke {format}...")
        subprocess.run([
            'ffmpeg', '-i', input_path, output_path
        ], check=True)
        print(f"[INFO] Konversi ke {format} selesai: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Gagal mengonversi video: {str(e)}")

# === Notifikasi Termux ===
def send_notification(title, message):
    try:
        subprocess.run(['termux-notification', '--title', title, '--content', message])
    except Exception as e:
        print(f"[ERROR] Gagal mengirim notifikasi: {str(e)}")

# === Pilih Resolusi Video ===
def xnxx_scrape(url):
    ua = UserAgent(fallback="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36")
    headers = {"User-Agent": ua.random}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return {"status": response.status_code, "message": f"Gagal mengakses URL: {response.reason}"}
        
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')
        
        # Ekstrak judul
        title_tag = soup.find('meta', {'property': 'og:title'})
        title = title_tag['content'].strip() if title_tag else "Tidak ditemukan"
        
        # Ekstrak gambar
        image_tag = soup.find('meta', {'property': 'og:image'})
        image = image_tag['content'] if image_tag else "N/A"
        
        # Cari URL video
        low_url = re.search(r'html5player\.setVideoUrlLow\s*\(\s*[\'"]([^\'"]+)', html)
        high_url = re.search(r'html5player\.setVideoUrlHigh\s*\(\s*[\'"]([^\'"]+)', html)
        hls_url = re.search(r'html5player\.setVideoHLS\s*\(\s*[\'"]([^\'"]+)', html)
        
        return {
            "status": 200,
            "data": {
                "title": title,
                "image": image,
                "files": {
                    "low": low_url.group(1) if low_url else "N/A",
                    "high": high_url.group(1) if high_url else "N/A",
                    "HLS": hls_url.group(1) if hls_url else "N/A"
                }
            }
        }
    except Exception as e:
        return {"status": 500, "message": f"Kesalahan: {str(e)}"}

# === Batch Mode ===
def process_batch_file(file_path, args):
    with open(file_path, 'r') as f:
        urls = [line.strip() for line in f if line.strip()]
    for url in urls:
        print(f"\n[INFO] Memproses: {url}")
        process_single_url(url, args)
        if args.delay > 0:
            print(f"[INFO] Menunggu {args.delay} detik...")
            time.sleep(args.delay)

# === Folder Output ===
def ensure_output_dir(output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

# === Penanganan Error ===
def process_single_url(url, args):
    result = xnxx_scrape(url)
    print(json.dumps(result, indent=4))
    
    if result.get("status") != 200:
        print(f"[ERROR] Gagal memproses {url}: {result.get('message', 'Unknown error')}")
        return
    
    data = result.get("data", {})
    if not data:
        print(f"[ERROR] Tidak ada data ditemukan untuk {url}")
        return
    
    # Unduh video
    if args.download:
        quality = args.quality
        video_url = data["files"].get(quality)
        if video_url == "N/A":
            print(f"[ERROR] URL video {quality} tidak tersedia.")
            return
        
        title = data["title"]
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '', title).strip() + ".mp4"
        ensure_output_dir(args.output)
        download_video(video_url, {"User-Agent": UserAgent().random}, filename, args.output)
        
        # Notifikasi
        if args.notify:
            send_notification("Unduhan Selesai", f"{filename} telah diunduh.")
        
        # Konversi format
        if args.convert:
            input_path = os.path.join(args.output, filename)
            output_path = os.path.splitext(input_path)[0] + "." + args.convert
            convert_video(input_path, output_path, args.convert)
    
    # Unduh thumbnail
    if args.download_thumb and data.get("image") != "N/A":
        thumb_filename = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '', data["title"]) + "_thumb.jpg"
        download_thumbnail(data["image"], {"User-Agent": UserAgent().random}, thumb_filename, args.output)

# === Main ===
def main():
    show_disclaimer()
    args = parse_args()
    
    if args.batch:
        process_batch_file(args.batch, args)
    elif args.url:
        process_single_url(args.url, args)
    else:
        print("URL tidak diberikan. Gunakan --help untuk bantuan.")

if __name__ == "__main__":
    main()