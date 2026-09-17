from flask import Flask, render_template, request, send_file, after_this_request
import subprocess, sys, os, uuid, tempfile, threading, time, urllib.request, urllib.parse, shutil, logging, re

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception as e:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

HAS_FFMPEG = shutil.which("ffmpeg") is not None
logger.info(f"FFmpeg availability: {HAS_FFMPEG} (path: {shutil.which('ffmpeg')})")

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
        time.sleep(10 * 60)

if os.getenv("RENDER_EXTERNAL_URL") or os.getenv("SELF_URL") or os.getenv("ENABLE_SELF_PING"):
    ping_thread = threading.Thread(target=start_self_ping, daemon=True)
    ping_thread.start()

def is_valid_url(url_string):
    if not url_string or not isinstance(url_string, str):
        return False
    url_string = url_string.strip()
    try:
        parsed = urllib.parse.urlparse(url_string)
        if parsed.scheme not in ["http", "https"] or not parsed.netloc:
            return False

        domain = parsed.netloc.lower()
        allowed_domains = ["youtube.com", "youtu.be", "instagram.com", "instagr.am", "www.youtube.com", "m.youtube.com", "www.instagram.com"]
        return any(domain == d or domain.endswith("." + d) for d in ["youtube.com", "youtu.be", "instagram.com", "instagr.am"])
    except Exception:
        return False

def parse_ytdlp_error(stderr_text):
    if not stderr_text:
        return "An unknown error occurred during download."

    text = stderr_text.lower()
    if "private video" in text or "video is private" in text:
        return "This video is private."
    if "video unavailable" in text or "this video is unavailable" in text or "not found" in text or "404" in text:
        return "This video is unavailable or has been deleted."
    if "sign in" in text or "confirm your age" in text or "age-restricted" in text:
        return "This video is age-restricted or requires sign-in."
    if "copyright" in text:
        return "This video is blocked due to copyright claims."
    if "requested format is not available" in text:
        return "The requested quality format is not available for this video."
    if "ffmpeg" in text and "not found" in text:
        return "Server media processing error (FFmpeg missing)."
    if "connection" in text or "timed out" in text or "network" in text:
        return "Network connection to video provider failed or timed out."

    return "Failed to process video. Please check the URL and try again."

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url", "").strip()
        quality = request.form.get("quality", "720p")

        if not url or not is_valid_url(url):
            return render_template("index.html", error="Please enter a valid YouTube or Instagram URL.")

        file_id = str(uuid.uuid4())
        out_template = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")

        sub_args = [
            "-o", out_template,
            "--no-playlist",
            "--concurrent-fragments", "4",
            "--socket-timeout", "30"
        ]

        ffmpeg_available = shutil.which("ffmpeg") is not None

        if quality == "audio":
            if ffmpeg_available:
                sub_args.extend(["-x", "--audio-format", "mp3", "-f", "bestaudio/best"])
            else:
                sub_args.extend(["-f", "ba[ext=m4a]/ba[ext=mp3]/ba/bestaudio/best"])
        elif quality in ["1080p", "720p", "480p", "360p", "240p"]:
            height = quality.replace("p", "")
            if ffmpeg_available:
                format_spec = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"
                sub_args.extend(["-f", format_spec, "--merge-output-format", "mp4"])
            else:
                format_spec = f"b[height<={height}]/best[height<={height}]/bestvideo[height<={height}]+bestaudio/best"
                sub_args.extend(["-f", format_spec])
        else: # Best
            if ffmpeg_available:
                sub_args.extend(["-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best", "--merge-output-format", "mp4"])
            else:
                sub_args.extend(["-f", "b[height<=1080]/best[height<=1080]/bestvideo+bestaudio/best"])

        sub_args.append(url)

        try:
            logger.info(f"Executing yt-dlp for URL: {url} | Quality: {quality} | FFmpeg: {ffmpeg_available}")
            try:
                cmd = ["yt-dlp"] + sub_args
                res = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180)
            except (FileNotFoundError, OSError):
                cmd = [sys.executable, "-m", "yt_dlp"] + sub_args
                res = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180)

            downloaded_files = [
                os.path.join(DOWNLOAD_DIR, f)
                for f in os.listdir(DOWNLOAD_DIR)
                if f.startswith(file_id)
            ]
            if not downloaded_files:
                logger.error(f"No output file generated for ID: {file_id}")
                return render_template("index.html", error="Failed to save video file. Please try another quality setting.")

            downloaded_file = downloaded_files[0]
            download_name = os.path.basename(downloaded_file)

            @after_this_request
            def cleanup_file(response):
                try:
                    if os.path.exists(downloaded_file):
                        os.remove(downloaded_file)
                        logger.info(f"Cleaned up file after response: {downloaded_file}")
                except Exception as cleanup_err:
                    logger.error(f"Failed to cleanup file {downloaded_file}: {cleanup_err}")
                return response

            return send_file(downloaded_file, as_attachment=True, download_name=download_name)

        except subprocess.TimeoutExpired:
            logger.error(f"yt-dlp timeout for URL: {url}")
            return render_template("index.html", error="Download timed out. The video may be too large or server connection was slow.")
        except subprocess.CalledProcessError as e:
            logger.error(f"yt-dlp process error for URL {url}:\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}")
            user_msg = parse_ytdlp_error(e.stderr)
            return render_template("index.html", error=user_msg)
        except Exception as e:
            logger.error(f"Unexpected error for URL {url}: {e}")
            return render_template("index.html", error="An unexpected error occurred. Please try again.")
        finally:
            # Cleanup any partial/leftover files for file_id if send_file was not reached (e.g. error during download/processing)
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(file_id):
                    file_path = os.path.join(DOWNLOAD_DIR, f)
                    try:
                        # If file is not being served via send_file, remove leftover file
                        if 'downloaded_file' not in locals() or file_path != downloaded_file:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                                logger.info(f"Cleaned up partial/leftover file: {file_path}")
                    except Exception as clean_err:
                        logger.error(f"Failed to cleanup leftover file {file_path}: {clean_err}")

    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
