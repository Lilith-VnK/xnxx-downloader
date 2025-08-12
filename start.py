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
from urllib.parse import urljoin, urlparse

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

GITHUB_SCRIPT_URL = "https://raw.githubusercontent.com/Lilith-VnK/xnxx-downloader/refs/heads/main/start.py"
LOCAL_SCRIPT_PATH = sys.argv[0]
check_update(GITHUB_SCRIPT_URL, LOCAL_SCRIPT_PATH)

# === Parsing Argumen ===
def parse_args():
    parser = argparse.ArgumentParser(
        description="Downloader Video xnxx.com dengan fitur lengkap",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  python xnxx_downloader.py https://www.xnxx.com/video-abc123/judul_video 
  python xnxx_downloader.py https://www.xnxx.com/video-abc123/judul_video  --download --quality high
  python xnxx_downloader.py --batch urls.txt --download --output ./videos
  python xnxx_downloader.py --url xnxx.com/milf --how-much 3 --download --quality high
        """
    )
    parser.add_argument("url", nargs="?", help="URL video xnxx.com")
    parser.add_argument("--download", action="store_true", help="Unduh video")
    parser.add_argument("--quality", default="high", choices=["low", "high", "hls"], help="Pilih kualitas video")
    parser.add_argument("--batch", help="Baca daftar URL dari file teks")
    parser.add_argument("--output", default="downloads", help="Folder output untuk menyimpan video")
    parser.add_argument("--delay", type=int, default=0, help="Delay antar permintaan (detik)")
    parser.add_argument("--download-thumb", action="store_true", help="Unduh thumbnail video")
    parser.add_argument("--convert", help="Konversi video ke format lain (misalnya mp3)")
    parser.add_argument("--notify", action="store_true", help="Notifikasi saat unduhan selesai (Termux)")
    parser.add_argument("--resume", action="store_true", help="Lanjutkan unduhan yang terputus")
    parser.add_argument("--proxy", help="Gunakan proxy (format: http://host:port)")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout untuk request (detik)")
    parser.add_argument("--max-retries", type=int, default=3, help="Jumlah maksimal retry")
    # Argumen baru untuk auto-download dari halaman kategori/pencarian
    parser.add_argument("--url", "-u", dest="search_url", help="URL xnxx.com untuk mencari video (contoh: xnxx.com/milf)")
    parser.add_argument("--how-much", "-H", type=int, default=1, help="Jumlah video teratas yang akan diunduh")
    return parser.parse_args()

def show_disclaimer():
    print("""
    ⚠️ PERINGATAN LEGAL:
    Skrip ini hanya untuk tujuan edukasi dan penggunaan pribadi.
    xnxx.com memiliki Terms of Service yang ketat.
    Jangan gunakan skrip ini untuk tujuan ilegal atau melanggar hak cipta.
    Dengan melanjutkan, Anda menyetujui bahwa Anda bertanggung jawab penuh atas penggunaan skrip ini.
    """)
    try:
        agree = input("Setujui? (y/n): ").lower().strip()
        if agree != "y":
            print("Keluar: Anda tidak menyetujui disclaimer.")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nKeluar: Dibatalkan oleh pengguna.")
        sys.exit(1)

def get_session_with_proxy(proxy_url=None):
    session = requests.Session()
    if proxy_url:
        session.proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
    return session

def download_video(url, headers, filename, output_dir, resume=False, timeout=30, max_retries=3, proxy=None):
    full_path = os.path.join(output_dir, filename)
    downloaded = 0
    mode = 'ab' if resume and os.path.exists(full_path) else 'wb'

    try:
        session = get_session_with_proxy(proxy)
        adapter = requests.adapters.HTTPAdapter(max_retries=max_retries)
        session.mount('https://', adapter)
        session.mount('http://', adapter)

        if resume and os.path.exists(full_path):
            downloaded = os.path.getsize(full_path)
            headers['Range'] = f'bytes={downloaded}-'

        with session.get(url, headers=headers, stream=True, timeout=timeout) as r:
            if resume and r.status_code == 416:
                print(f"[INFO] File {filename} sudah lengkap.")
                return True
            elif r.status_code not in [200, 206]:
                r.raise_for_status()

            total_size = int(r.headers.get('content-length', 0))
            if r.status_code == 206:
                content_range = r.headers.get('content-range', '')
                if content_range:
                    total_size = int(content_range.split('/')[-1])

            if total_size == 0:
                total_size = None

            with open(full_path, mode) as f:
                initial = downloaded if total_size else 0
                with tqdm(
                    total=total_size,
                    initial=initial,
                    unit='B',
                    unit_scale=True,
                    desc=f"📥 Mengunduh {filename}",
                    ncols=100,
                    disable=total_size is None,
                    leave=True
                ) as pbar:
                    for chunk in r.iter_content(chunk_size=32*1024):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
            print(f"[INFO] Unduhan {filename} selesai.")
            return True
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Gagal mengunduh {filename}: {str(e)}")
        return False
    except KeyboardInterrupt:
        print("\n[INFO] Unduhan dihentikan oleh pengguna (Ctrl+C).")
        print("       Anda bisa melanjutkan dengan flag --resume.")
        return False
    except Exception as e:
        print(f"[ERROR] Kesalahan saat mengunduh {filename}: {str(e)}")
        return False

# === Download Thumbnail ===
def download_thumbnail(url, headers, filename, output_dir, timeout=30, proxy=None):
    full_path = os.path.join(output_dir, filename)
    try:
        session = get_session_with_proxy(proxy)
        with session.get(url, headers=headers, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            with open(full_path, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
        print(f"[INFO] Thumbnail {filename} diunduh.")
        return True
    except Exception as e:
        print(f"[ERROR] Gagal mengunduh thumbnail: {str(e)}")
        return False

# === Konversi Format Video ===
def convert_video(input_path, output_path, target_format):
    try:
        if not os.path.exists(input_path):
            print(f"[ERROR] File input tidak ditemukan: {input_path}")
            return False

        try:
            subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("[ERROR] ffmpeg tidak ditemukan. Pastikan ffmpeg terinstal.")
            return False

        cmd = ['ffmpeg', '-i', input_path, '-y']

        if target_format.lower() == 'mp3':
            cmd.extend(['-vn', '-ar', '44100', '-ac', '2', '-ab', '192k', '-f', 'mp3'])
        elif target_format.lower() == 'webm':
            cmd.extend(['-c:v', 'libvpx-vp9', '-crf', '30', '-b:v', '0'])

        cmd.append(output_path)

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            print(f"[INFO] Konversi ke {target_format} selesai: {output_path}")
            return True
        else:
            print(f"[ERROR] Gagal mengonversi video: {result.stderr}")
            return False
    except Exception as e:
        print(f"[ERROR] Kesalahan saat konversi video: {str(e)}")
        return False

# === Notifikasi Termux ===
def send_notification(title, message):
    try:
        subprocess.run(
            ['termux-notification', '--title', title, '--content', message],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[WARNING] Gagal mengirim notifikasi Termux.")
        return False
    except Exception as e:
        print(f"[ERROR] Kesalahan saat mengirim notifikasi: {str(e)}")
        return False

def is_valid_xnxx_url(url):
    try:
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https') and \
               'xnxx.com' in parsed.netloc.lower()
    except Exception:
        return False

# === Pilih Resolusi Video ===
def xnxx_scrape(url, timeout=30, proxy=None):
    if not is_valid_xnxx_url(url):
        return {"status": 400, "message": "URL tidak valid atau bukan xnxx.com"}

    ua = UserAgent(fallback="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    headers = {"User-Agent": ua.random}

    try:
        session = get_session_with_proxy(proxy)
        response = session.get(url, headers=headers, timeout=timeout)

        if response.status_code != 200:
            return {"status": response.status_code, "message": f"Gagal mengakses URL: {response.reason}"}

        html = response.text
        soup = BeautifulSoup(html, 'html.parser')

        title = "Unknown Video"
        title_tag = soup.find('meta', {'property': 'og:title'})
        if title_tag:
            title = title_tag['content'].strip()
        else:
            title_h1 = soup.find('h1', {'class': 'page-title'})
            if title_h1:
                title = title_h1.get_text().strip()

        image = "N/A"
        image_tag = soup.find('meta', {'property': 'og:image'})
        if image_tag:
            image = image_tag['content']
        else:
            thumb_match = re.search(r'setThumbUrl\s*\(\s*[\'"]([^\'"]+)', html)
            if thumb_match:
                image = thumb_match.group(1)

        video_files = {}

        patterns = {
            'low': [r'html5player\.setVideoUrlLow\s*\(\s*[\'"]([^\'"]+)', r'"low":[\s\r\n]*[\'"]([^\'"]+)'],
            'high': [r'html5player\.setVideoUrlHigh\s*\(\s*[\'"]([^\'"]+)', r'"high":[\s\r\n]*[\'"]([^\'"]+)'],
            'hls': [r'html5player\.setVideoHLS\s*\(\s*[\'"]([^\'"]+)', r'"hls":[\s\r\n]*[\'"]([^\'"]+)']
        }

        for quality, pattern_list in patterns.items():
            for pattern in pattern_list:
                match = re.search(pattern, html)
                if match:
                    video_files[quality] = match.group(1)
                    break
            if quality not in video_files:
                video_files[quality] = "N/A"

        if all(url == "N/A" for url in video_files.values()):
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    script_content = script.string
                    for quality, pattern_list in patterns.items():
                        for pattern in pattern_list:
                            match = re.search(pattern, script_content)
                            if match and quality not in video_files:
                                video_files[quality] = match.group(1)
                                break

        return {
            "status": 200,
            "data": {
                "title": title,
                "image": image,
                "files": video_files
            }
        }
    except requests.exceptions.RequestException as e:
        return {"status": 503, "message": f"Network error: {e}"}
    except Exception as e:
        return {"status": 500, "message": f"Kesalahan: {e}"}

# === Fungsi Baru: Ambil Daftar Video dari Halaman Kategori/Pencarian ===
def xnxx_search_videos(search_url, how_much=1, timeout=30, proxy=None):
    """Mengambil daftar video dari halaman xnxx.com"""
    if not is_valid_xnxx_url(search_url):
        print(f"[ERROR] URL pencarian tidak valid: {search_url}")
        return []

    ua = UserAgent(fallback="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    headers = {"User-Agent": ua.random}
    
    print(f"[INFO] Mencari video di: {search_url}")
    
    try:
        session = get_session_with_proxy(proxy)
        response = session.get(search_url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        video_links = []
        
        # Cari semua link video berdasarkan class atau pola URL
        video_elements = soup.find_all('div', class_='thumb-block')
        
        for elem in video_elements[:how_much]:
            # Cari link video dalam elemen
            link_elem = elem.find('a', href=re.compile(r'/video-'))
            if link_elem and link_elem.get('href'):
                full_url = urljoin("https://www.xnxx.com", link_elem['href'])
                title_elem = elem.find('p', class_='title')
                title = title_elem.get_text().strip() if title_elem else "Unknown Title"
                video_links.append({
                    'url': full_url,
                    'title': title
                })
                
        if not video_links:
            # Coba metode alternatif: cari semua link yang mengandung /video-
            all_links = soup.find_all('a', href=re.compile(r'/video-'))
            seen_urls = set()
            for link in all_links:
                href = link.get('href')
                if href and href not in seen_urls:
                    seen_urls.add(href)
                    full_url = urljoin("https://www.xnxx.com", href)
                    title = link.get_text().strip() or "Unknown Title"
                    video_links.append({
                        'url': full_url,
                        'title': title
                    })
                    if len(video_links) >= how_much:
                        break
        
        print(f"[INFO] Ditemukan {len(video_links)} video.")
        return video_links[:how_much]
        
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Gagal mengakses halaman pencarian: {str(e)}")
        return []
    except Exception as e:
        print(f"[ERROR] Kesalahan saat mencari video: {str(e)}")
        return []

# === Batch Mode ===
def process_batch_file(file_path, args):
    if not os.path.exists(file_path):
        print(f"[ERROR] File batch tidak ditemukan: {file_path}")
        return

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except Exception as e:
        print(f"[ERROR] Gagal membaca file batch: {str(e)}")
        return

    if not urls:
        print("[INFO] Tidak ada URL valid ditemukan dalam file batch.")
        return

    print(f"[INFO] Memproses {len(urls)} URL dari file batch...")
    for i, url in enumerate(urls, 1):
        print(f"\n[INFO] Memproses URL {i}/{len(urls)}: {url}")
        process_single_url(url, args)
        if args.delay > 0 and i < len(urls):
            print(f"[INFO] Menunggu {args.delay} detik...")
            time.sleep(args.delay)

# === Folder Output ===
def ensure_output_dir(output_dir):
    try:
        os.makedirs(output_dir, exist_ok=True)
        return True
    except Exception as e:
        print(f"[ERROR] Gagal membuat direktori output: {str(e)}")
        return False

# === Sanitasi Nama File ===
def sanitize_filename(filename):
    if not filename:
        return "untitled"
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '', filename)
    if len(filename) > 200:
        filename = filename[:200]
    filename = filename.strip().replace(' ', '_')
    if not filename:
        return "untitled"
    return filename

# === Penanganan Error ===
def process_single_url(url, args):
    if not is_valid_xnxx_url(url):
        print(f"[ERROR] URL tidak valid: {url}")
        return

    print(f"[INFO] Memproses: {url}")
    result = xnxx_scrape(url, timeout=args.timeout, proxy=args.proxy)
    
    if result.get("status") != 200:
        print(f"[ERROR] Gagal memproses {url}: {result.get('message', 'Unknown error')}")
        return

    data = result.get("data", {})
    if not data:
        print(f"[ERROR] Tidak ada data ditemukan untuk {url}")
        return

    print(json.dumps(result, indent=4, ensure_ascii=False))

    if args.download:
        quality = args.quality
        video_url = data["files"].get(quality)
        if video_url == "N/A":
            print(f"[WARNING] Kualitas {quality} tidak tersedia. Mencari alternatif...")
            for alt_quality in ['high', 'low', 'hls']:
                if data["files"].get(alt_quality) != "N/A":
                    quality = alt_quality
                    video_url = data["files"][quality]
                    print(f"[INFO] Menggunakan kualitas {quality} sebagai alternatif.")
                    break
            else:
                print("[ERROR] Tidak ada kualitas video yang tersedia.")
                return

        title = data["title"]
        filename = sanitize_filename(title) + ".mp4"
        if not ensure_output_dir(args.output):
            return

        success = download_video(
            video_url,
            {"User-Agent": UserAgent().random},
            filename,
            args.output,
            resume=args.resume,
            timeout=args.timeout,
            max_retries=args.max_retries,
            proxy=args.proxy
        )

        if success:
            if args.notify:
                send_notification("Unduhan Selesai", f"{filename} telah diunduh.")

            if args.convert:
                input_path = os.path.join(args.output, filename)
                output_name = sanitize_filename(os.path.splitext(filename)[0]) + "." + args.convert.lower()
                output_path = os.path.join(args.output, output_name)
                convert_video(input_path, output_path, args.convert)

    if args.download_thumb and data.get("image") != "N/A":
        thumb_filename = sanitize_filename(data["title"]) + "_thumb.jpg"
        if not ensure_output_dir(args.output):
            return
        download_thumbnail(
            data["image"],
            {"User-Agent": UserAgent().random},
            thumb_filename,
            args.output,
            timeout=args.timeout,
            proxy=args.proxy
        )

# === Main ===
def main():
    try:
        args = parse_args()
        
        # Jika tidak ada argumen, tampilkan disclaimer dan help
        if len(sys.argv) == 1:
            show_disclaimer()
            parse_args().print_help()
            return
            
        # Tampilkan disclaimer kecuali untuk help
        if not any(arg in sys.argv for arg in ['--help', '-h']):
            show_disclaimer()

        # Mode auto-download dari halaman kategori/pencarian
        if args.search_url:
            if not is_valid_xnxx_url(args.search_url):
                # Coba tambahkan https:// jika tidak ada
                if not args.search_url.startswith(('http://', 'https://')):
                    args.search_url = "https://www." + args.search_url
                else:
                    args.search_url = "https://www.xnxx.com"
                    
            video_list = xnxx_search_videos(
                args.search_url, 
                how_much=args.how_much,
                timeout=args.timeout,
                proxy=args.proxy
            )
            
            if not video_list:
                print("[INFO] Tidak ada video ditemukan.")
                return
                
            print(f"[INFO] Mengunduh {len(video_list)} video...")
            for i, video_info in enumerate(video_list, 1):
                print(f"\n[INFO] Memproses video {i}/{len(video_list)}: {video_info['title']}")
                print(f"       URL: {video_info['url']}")
                process_single_url(video_info['url'], args)
                if args.delay > 0 and i < len(video_list):
                    print(f"[INFO] Menunggu {args.delay} detik...")
                    time.sleep(args.delay)
                    
        # Mode batch file
        elif args.batch:
            process_batch_file(args.batch, args)
        # Mode URL tunggal
        elif args.url:
            process_single_url(args.url, args)
        else:
            print("URL tidak diberikan. Gunakan --help untuk bantuan.")

    except KeyboardInterrupt:
        print("\n[INFO] Program dihentikan oleh pengguna.")
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] Kesalahan tidak terduga: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
