from flask import Flask, render_template, request, send_file, after_this_request
import os, tempfile, time, urllib.request, shutil, logging, re, uuid
from threading import Thread
import yt_dlp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

HAS_FFMPEG = shutil.which("ffmpeg") is not None
logger.info(f"FFmpeg availability: {HAS_FFMPEG}")

VALID_QUALITIES = ["1080p", "720p", "480p", "360p", "240p"]
COOKIES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")


def render_index(error=None, url="", quality="720p"):
    return render_template("index.html", error=error, url=url, quality=quality)


@app.route("/ping", methods=["GET"])
def ping():
    return {"status": "ok"}, 200


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_index()

    url = (request.form.get("url") or "").strip()
    quality = request.form.get("quality") or "720p"

    if not url or not re.match(r"^https?://", url, re.I):
        return render_index(error="Please paste a valid Instagram or YouTube link.", url=url, quality=quality)

    if quality not in VALID_QUALITIES:
        return render_index(error="Please select a valid quality option.", url=url, quality=quality)

    height = quality[:-1]
    file_id = str(uuid.uuid4())
    outtmpl = os.path.join(DOWNLOAD_DIR, file_id + ".%(ext)s")

    if HAS_FFMPEG:
        fmt = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"
    else:
        fmt = f"best[height<={height}]/best"

    ydl_opts = {
        "format": fmt,
        "outtmpl": outtmpl,
        "quiet": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
    }

    if os.path.isfile(COOKIES_PATH):
        ydl_opts["cookiefile"] = COOKIES_PATH

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        candidates = [
            os.path.join(DOWNLOAD_DIR, name)
            for name in os.listdir(DOWNLOAD_DIR)
            if name.startswith(file_id)
        ]
        if not candidates:
            return render_index(error="Download finished but the file was not found. Try again.", url=url, quality=quality)

        filepath = max(candidates, key=os.path.getmtime)

        @after_this_request
        def cleanup(response):
            try:
                for path in candidates:
                    if os.path.exists(path):
                        os.remove(path)
            except Exception as e:
                logger.error(f"Error cleaning up file: {e}")
            return response

        return send_file(filepath, as_attachment=True, download_name="video.mp4")

    except Exception as e:
        logger.error(f"yt-dlp download failed: {e}")
        msg = str(e)
        if "Private video" in msg or "login" in msg.lower() or "cookies" in msg.lower():
            friendly = "This video may be private or require login. Try a public link."
        elif "Unsupported URL" in msg or "Unable to extract" in msg:
            friendly = "Unsupported link. Use a public Instagram Reel or YouTube URL."
        else:
            friendly = "Download failed. Check the link and try again."
        return render_index(error=friendly, url=url, quality=quality)


def start_self_ping():
    time.sleep(10)
    while True:
        url = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("SELF_URL")
        if url:
            try:
                ping_url = f"{url.rstrip('/')}/ping"
                urllib.request.urlopen(ping_url, timeout=10)
                logger.info(f"Pinged {ping_url} successfully.")
            except Exception as e:
                logger.error(f"Ping failed: {e}")
        else:
            logger.warning("No URL found for self-ping. Ensure RENDER_EXTERNAL_URL or SELF_URL is set.")
            break
        time.sleep(60)


Thread(target=start_self_ping, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
