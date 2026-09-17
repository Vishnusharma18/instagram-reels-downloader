from flask import Flask, render_template, request, send_file, after_this_request
import subprocess, sys, os, uuid, tempfile, threading, time, urllib.request, urllib.parse, shutil, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

HAS_FFMPEG = shutil.which("ffmpeg") is not None
logger.info(f"FFmpeg availability: {HAS_FFMPEG}")

@app.route("/ping", methods=["GET"])
def ping():
    return {"status": "ok"}, 200

def start_self_ping():
    time.sleep(10)
    while True:
        url = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("SELF_URL")
        if url:
            try:
                ping_url = f"{url.rstrip('/')}/ping"
                urllib.request.urlopen(ping_url, timeout=10)
                logger.info("Self ping successful")
            except Exception as e:
                logger.warning(f"Self ping failed: {e}")
        time.sleep(10 * 60) # Ping every 10 minutes

# Only start keep-alive ping thread if a target URL is configured
if os.getenv("RENDER_EXTERNAL_URL") or os.getenv("SELF_URL") or os.getenv("ENABLE_SELF_PING"):
    ping_thread = threading.Thread(target=start_self_ping, daemon=True)
    ping_thread.start()
    logger.info("Keep-alive self ping thread started")

def is_valid_url(url_string):
    if not url_string or not isinstance(url_string, str):
        return False
    try:
        parsed = urllib.parse.urlparse(url_string.strip())
        return parsed.scheme in ["http", "https"] and bool(parsed.netloc)
    except Exception:
        return False

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url", "").strip()
        quality = request.form.get("quality", "best")

        if not url or not is_valid_url(url):
            return render_template("index.html", error="Please enter a valid HTTP or HTTPS URL")

        file_id = str(uuid.uuid4())
        out_template = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")

        sub_args = [
            "-o", out_template,
            "--no-playlist",
            "--concurrent-fragments", "4",
            "--socket-timeout", "20"
        ]

        if quality == "audio":
            if HAS_FFMPEG:
                sub_args.extend(["-f", "ba/bestaudio/b/best", "-x", "--audio-format", "mp3"])
            else:
                sub_args.extend(["-f", "ba[ext=m4a]/ba[ext=mp3]/ba/bestaudio/b/best"])
        elif quality in ["1080p", "720p", "480p", "360p", "240p"]:
            height = quality.replace("p", "")
            if HAS_FFMPEG:
                format_spec = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/b[height<={height}]/best"
            else:
                # Without ffmpeg, prefer single-file formats (b or best) under target height
                format_spec = f"b[height<={height}]/best[height<={height}]/bestvideo[height<={height}]+bestaudio/best"
            sub_args.extend(["-f", format_spec])
        else:
            if HAS_FFMPEG:
                sub_args.extend(["-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best/b"])
            else:
                sub_args.extend(["-f", "b[height<=1080]/best[height<=1080]/bestvideo+bestaudio/best"])

        sub_args.append(url)

        try:
            logger.info(f"Downloading URL: {url} with quality: {quality}")
            try:
                cmd = ["yt-dlp"] + sub_args
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
            except (FileNotFoundError, OSError):
                cmd = [sys.executable, "-m", "yt_dlp"] + sub_args
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)

            downloaded_files = [
                os.path.join(DOWNLOAD_DIR, f)
                for f in os.listdir(DOWNLOAD_DIR)
                if f.startswith(file_id)
            ]
            if not downloaded_files:
                logger.error(f"No file generated for ID {file_id}")
                return render_template("index.html", error="Failed to find downloaded file. The video may be unavailable.")

            downloaded_file = downloaded_files[0]
            download_name = os.path.basename(downloaded_file)

            @after_this_request
            def cleanup_file(response):
                try:
                    if os.path.exists(downloaded_file):
                        os.remove(downloaded_file)
                        logger.info(f"Successfully cleaned up temporary file: {downloaded_file}")
                except Exception as cleanup_err:
                    logger.error(f"Error cleaning up file {downloaded_file}: {cleanup_err}")
                return response

            return send_file(downloaded_file, as_attachment=True, download_name=download_name)
        except subprocess.TimeoutExpired:
            logger.error(f"Download timed out for URL: {url}")
            return render_template("index.html", error="Download timed out. Please try a lower resolution or shorter video.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Process error for URL {url}: {e.stderr}")
            error_msg = "Download failed. The video may be private, unavailable, or age-restricted."
            if e.stderr and "unavailable" in e.stderr.lower():
                error_msg = "This video is unavailable or private on YouTube/Instagram."
            return render_template("index.html", error=error_msg)
        except Exception as e:
            logger.error(f"Unexpected error for URL {url}: {e}")
            return render_template("index.html", error=f"Download failed: {str(e)}")

    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
