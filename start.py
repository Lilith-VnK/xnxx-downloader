#!/usr/bin/env python3
# coding: utf-8

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
import urllib3
import socket
from urllib.parse import urljoin, urlparse

# === Tambahkan import untuk dnspython ===
try:
    import dns.resolver
    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False
    print("[WARNING] Pustaka 'dnspython' tidak ditemukan. Fitur resolver DNS dinonaktifkan.")
    print("          Untuk mengaktifkannya, instal dengan: pip install dnspython")

# === Retry ===
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# === Helper: DNS Resolve (pakai dnspython jika tersedia, fallback ke socket) ===
def resolve_host_list(host, dns_server=None, timeout=5):
    ips = []
    if DNS_AVAILABLE and dns_server:
        try:
            resolver = dns.resolver.Resolver(configure=False)
            # dns_server bisa berupa string "1.1.1.1" atau "1.1.1.1,8.8.8.8"
            if isinstance(dns_server, str) and ',' in dns_server:
                resolver.nameservers = [s.strip() for s in dns_server.split(',') if s.strip()]
            elif isinstance(dns_server, (list, tuple)):
                resolver.nameservers = list(dns_server)
            else:
                resolver.nameservers = [dns_server]
            resolver.timeout = timeout
            resolver.lifetime = timeout
            answers = resolver.resolve(host, 'A')
            for a in answers:
                ips.append(a.to_text())
            if ips:
                return ips
        except Exception as e:
            # fallthrough to socket
            print(f"[WARNING] DNS resolver ({dns_server}) gagal untuk {host}: {e}")

    # Fallback ke system resolver (socket)
    try:
        for res in socket.getaddrinfo(host, None):
            ip = res[4][0]
            if ip not in ips:
                ips.append(ip)
        return ips
    except Exception as e:
        print(f"[WARNING] Socket resolver gagal untuk {host}: {e}")
        return []

# === Custom HTTP Adapter untuk backward compatibility ===
class DNSHTTPAdapter(HTTPAdapter):
    def __init__(self, dns_server=None, *args, **kwargs):
        self.dns_server = dns_server
        super().__init__(*args, **kwargs)

    def add_headers(self, request, **kwargs):
        # jika request sudah memiliki header Host, biarkan saja
        return super().add_headers(request, **kwargs)

# === fungsi sesi untuk menyertakan DNS ===
def get_session_with_proxy(proxy_url=None, no_verify_ssl=False, dns_server=None, max_retries=3):

    session = requests.Session()

    # Proxies
    if proxy_url:
        session.proxies = {
            'http': proxy_url,
            'https': proxy_url
        }

    # Set default verify flag on session (requests will still accept per-call override)
    session.verify = not no_verify_ssl
    if no_verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # Mount retry-enabled adapter
    retry = Retry(total=max_retries, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    # If no dns_server provided or dnspython absent, do not patch request (use system resolver)
    if not dns_server:
        return session

    # Patch session.request to perform DNS resolve + Host injection per-request
    original_request = session.request

    def patched_request(method, url, *args, **kwargs):
        try:
            parsed = urlparse(url)
            orig_host = parsed.hostname
            if orig_host:
                # Only intercept when hostname is not an IP literal
                is_ip = False
                try:
                    socket.inet_aton(orig_host)
                    is_ip = True
                except Exception:
                    is_ip = False

                if not is_ip:
                    ips = resolve_host_list(orig_host, dns_server=dns_server)
                    if ips:
                        ip = ips[0]
                        # rebuild netloc with possible port
                        new_netloc = ip
                        if parsed.port:
                            new_netloc = f"{ip}:{parsed.port}"

                        # Replace first occurrence of scheme://hostname with scheme://new_netloc
                        scheme_prefix = f"{parsed.scheme}://{orig_host}"
                        new_url = url.replace(scheme_prefix, f"{parsed.scheme}://{new_netloc}", 1)

                        # Prepare headers
                        headers = kwargs.get('headers', {})
                        # preserve existing Host header if present (but override with orig_host)
                        headers['Host'] = orig_host
                        kwargs['headers'] = headers

                        # Because we are requesting IP while TLS expects hostname, default to disabling verify
                        # unless user explicitly set verify in kwargs; we prefer to allow caller to set verify param.
                        if 'verify' not in kwargs:
                            kwargs['verify'] = not no_verify_ssl  # follow session setting

                        # Update url to new_url
                        url = new_url
                        if kwargs.get('stream') is None:
                            # nothing special
                            pass
        except Exception as e:
            # If anything goes wrong here, fallback to original URL without DNS forcing
            print(f"[WARNING] Gagal memaksa resolve untuk {url}: {e}")

        return original_request(method, url, *args, **kwargs)

    session.request = patched_request
    return session

# === Auto Update dengan Konfirmasi ===
def check_update(repo_url, local_path):
    try:
        print("[INFO] Memeriksa pembaruan skrip...")
        # Buat sesi tanpa DNS khusus untuk auto-update (pakai system resolver)
        session = get_session_with_proxy()
        response = session.get(repo_url, timeout=15)
        if response.status_code == 200:
            remote_sha = hashlib.sha256(response.content).hexdigest()
            try:
                with open(local_path, 'rb') as f:
                    local_sha = hashlib.sha256(f.read()).hexdigest()
            except FileNotFoundError:
                local_sha = ""
            if remote_sha != local_sha:
                print("[INFO] Pembaruan tersedia.")
                # Meminta konfirmasi pengguna
                while True:
                    try:
                        choice = input("Apakah Anda ingin mengunduh dan memasang pembaruan? (y/n): ").lower().strip()
                        if choice in ['y', 'yes', 'ya']:
                            print("[INFO] Mengunduh versi terbaru...")
                            with open(local_path, "wb") as f:
                                f.write(response.content)
                            print("[INFO] Skrip berhasil diperbarui.")
                            # Jalankan ulang skrip
                            print("[INFO] Menjalankan ulang skrip yang telah diperbarui...")
                            os.execv(sys.executable, [sys.executable] + sys.argv)
                            break  # Tidak akan pernah tercapai karena execv
                        elif choice in ['n', 'no', 'tidak']:
                            print("[INFO] Melewati pembaruan. Menjalankan skrip versi saat ini.")
                            break
                        else:
                            print("[WARNING] Masukkan tidak valid. Silakan jawab dengan 'y' atau 'n'.")
                    except KeyboardInterrupt:
                        print("\n[INFO] Pembaruan dibatalkan oleh pengguna. Menjalankan skrip versi saat ini.")
                        break
            else:
                print("[INFO] Skrip sudah versi terbaru.")
        else:
            print("[ERROR] Gagal memeriksa pembaruan.")
    except Exception as e:
        print(f"[ERROR] Kesalahan saat memeriksa pembaruan: {str(e)}")

# === Parsing Argumen ===
def parse_args():
    parser = argparse.ArgumentParser(
        description="Downloader Video xnxx.com dengan fitur lengkap",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  python xnxx_downloader.py https://www.xnxx.com/video-abc123/judul_video      
  python xnxx_downloader.py https://www.xnxx.com/video-abc123/judul_video     --download --quality high
  python xnxx_downloader.py --batch urls.txt --download --output ./videos
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
    # Opsi untuk menangani SSL
    parser.add_argument("--no-verify-ssl", action="store_true", help="Nonaktifkan verifikasi sertifikat SSL (tidak aman)")
    # === Opsi DNS Resolver ===
    if DNS_AVAILABLE:
        parser.add_argument("--dns", help="Gunakan DNS khusus untuk resolusi (format: IP_Address atau '1.1.1.1,8.8.8.8')")
    # === Opsi Debug ===
    parser.add_argument("--debug", action="store_true", help="Aktifkan logging debug")
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

def download_video(url, headers, filename, output_dir, resume=False, timeout=30, max_retries=3, proxy=None, no_verify_ssl=False, dns_server=None):
    full_path = os.path.join(output_dir, filename)
    downloaded = 0
    mode = 'ab' if resume and os.path.exists(full_path) else 'wb'

    try:
        session = get_session_with_proxy(proxy, no_verify_ssl, dns_server, max_retries=max_retries)
        if no_verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        if resume and os.path.exists(full_path):
            downloaded = os.path.getsize(full_path)
            headers['Range'] = f'bytes={downloaded}-'

        with session.get(url, headers=headers, stream=True, timeout=timeout, verify=not no_verify_ssl) as r:
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
def download_thumbnail(url, headers, filename, output_dir, timeout=30, proxy=None, no_verify_ssl=False, dns_server=None):
    full_path = os.path.join(output_dir, filename)
    try:
        session = get_session_with_proxy(proxy, no_verify_ssl, dns_server)
        # Nonaktifkan peringatan SSL jika no_verify_ssl aktif
        if no_verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        with session.get(url, headers=headers, stream=True, timeout=timeout, verify=not no_verify_ssl) as r:
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
def xnxx_scrape(url, timeout=30, proxy=None, no_verify_ssl=False, dns_server=None, debug=False):
    if not is_valid_xnxx_url(url):
        return {"status": 400, "message": "URL tidak valid atau bukan xnxx.com"}

    # Gunakan User-Agent yang lebih umum dan modern
    ua = UserAgent(fallback="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    headers = {"User-Agent": ua.random}
    # Tambahkan header umum lainnya yang mungkin membantu
    headers.update({
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0'
    })

    try:
        session = get_session_with_proxy(proxy, no_verify_ssl, dns_server)
        if no_verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        if debug:
            print(f"[DEBUG] Mengakses URL: {url}")
            print(f"[DEBUG] Menggunakan headers: {headers}")
            print(f"[DEBUG] Timeout: {timeout}, Verify SSL: {not no_verify_ssl}, DNS: {dns_server}")

        response = session.get(url, headers=headers, timeout=timeout, verify=not no_verify_ssl)

        if debug:
            print(f"[DEBUG] Status Code diterima: {response.status_code}")
            print(f"[DEBUG] Content-Type: {response.headers.get('content-type', 'N/A')}")
            print(f"[DEBUG] Sebagian respons HTML (500 karakter pertama):\n{response.text[:500]}\n...")

        if response.status_code != 200:
            return {"status": response.status_code, "message": f"Gagal mengakses URL: {response.reason}"}

        html = response.text
        soup = BeautifulSoup(html, 'html.parser')

        # --- Ekstrak Judul ---
        title = "Unknown Video"
        # Coba beberapa metode untuk mendapatkan judul
        title_tag = soup.find('meta', property='og:title')
        if not title_tag:
             title_tag = soup.find('meta', attrs={'name': 'twitter:title'})
        if not title_tag:
            title_h1 = soup.find('h1', class_='page-title') # Sesuaikan class jika perlu
            if title_h1:
                title = title_h1.get_text(strip=True)
        if title_tag:
            title = title_tag.get('content', '').strip() or "Unknown Video"

        # --- Ekstrak Gambar ---
        image = "N/A"
        image_tag = soup.find('meta', property='og:image')
        if not image_tag:
            image_tag = soup.find('meta', attrs={'name': 'twitter:image'})
        if image_tag:
            image = image_tag.get('content', 'N/A')
        # Fallback jika meta tidak ada
        if image == "N/A":
             thumb_match = re.search(r'setThumbUrl\s*\(\s*[\'"]([^\'"]+)', html)
             if thumb_match:
                 image = thumb_match.group(1)

        # --- Ekstrak URL Video ---
        video_files = {'low': 'N/A', 'high': 'N/A', 'hls': 'N/A'}

        patterns = {
            'low': [
                r'html5player\.setVideoUrlLow\s*\(\s*["\']([^"\']+)["\']',
                r'"low"\s*:\s*["\']([^"\']+)["\']',
                r'low["\']\s*:\s*["\']([^"\']+)["\']',
                r'video_url_low["\']?\s*[:=]\s*["\']([^"\']+)["\']'
            ],
            'high': [
                r'html5player\.setVideoUrlHigh\s*\(\s*["\']([^"\']+)["\']',
                r'"high"\s*:\s*["\']([^"\']+)["\']',
                r'high["\']\s*:\s*["\']([^"\']+)["\']',
                r'video_url["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                r'video_url_high["\']?\s*[:=]\s*["\']([^"\']+)["\']'
            ],
            'hls': [
                r'html5player\.setVideoHLS\s*\(\s*["\']([^"\']+)["\']',
                r'"hls"\s*:\s*["\']([^"\']+)["\']',
                r'hls["\']\s*:\s*["\']([^"\']+)["\']',
                r'm3u8_url["\']?\s*[:=]\s*["\']([^"\']+)["\']'
            ]
        }

        found_any = False
        for quality, pattern_list in patterns.items():
            for pattern in pattern_list:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    potential_url = match.group(1)
                    if potential_url.startswith(('http', '//')):
                        video_files[quality] = potential_url
                        found_any = True
                        if debug:
                            print(f"[DEBUG] Found {quality} URL: {potential_url}")
                        break
                elif debug:
                    pass

        if not found_any:
            script_tags = soup.find_all('script')
            for script in script_tags:
                if script.string:
                    script_content = script.string
                    if 'html5player' in script_content or 'setVideo' in script_content:
                        for quality, pattern_list in patterns.items():
                            for pattern in pattern_list:
                                match = re.search(pattern, script_content, re.IGNORECASE)
                                if match:
                                    potential_url = match.group(1)
                                    if potential_url.startswith(('http', '//')):
                                        video_files[quality] = potential_url
                                        found_any = True
                                        if debug:
                                            print(f"[DEBUG] Found {quality} URL in script: {potential_url}")
                                        break
                            if video_files[quality] != "N/A":
                                break
                        if found_any:
                            break

        if not found_any:
            return {
                "status": 200,
                "message": "URL video tidak ditemukan. Struktur HTML xnxx.com mungkin telah berubah.",
                "data": {
                    "title": title,
                    "image": image,
                    "files": video_files
                }
            }

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
        import traceback
        error_details = traceback.format_exc()
        return {"status": 500, "message": f"Kesalahan: {e}\nDetails:\n{error_details}"}

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

    dns_server = getattr(args, 'dns', None) if DNS_AVAILABLE else None
    debug = getattr(args, 'debug', False)
    result = xnxx_scrape(url, timeout=args.timeout, proxy=args.proxy, no_verify_ssl=args.no_verify_ssl, dns_server=dns_server, debug=debug)

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
            proxy=args.proxy,
            no_verify_ssl=args.no_verify_ssl,
            dns_server=dns_server
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
            proxy=args.proxy,
            no_verify_ssl=args.no_verify_ssl,
            dns_server=dns_server
        )

# === Main ===
GITHUB_SCRIPT_URL = "https://raw.githubusercontent.com/Lilith-VnK/xnxx-downloader/refs/heads/main/start.py"
LOCAL_SCRIPT_PATH = sys.argv[0]
# Check update but ignore failures silently if network restricted
try:
    check_update(GITHUB_SCRIPT_URL, LOCAL_SCRIPT_PATH)
except Exception:
    pass

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

        # Mode batch file
        if args.batch:
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