from flask import Flask, render_template, request, send_file, after_this_request
import os, tempfile, time, urllib.request, shutil, logging, re, uuid
from threading import Thread
import yt_dlp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "clipfetch_downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

HAS_FFMPEG = shutil.which("ffmpeg") is not None
logger.info(f"FFmpeg availability: {HAS_FFMPEG}")

VALID_QUALITIES = ["1080p", "720p", "480p", "360p", "240p"]
COOKIES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")


def render_index(error=None, url="", quality="720p"):
    return render_template("index.html", error=error, url=url, quality=quality)


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    # youtu.be / shorts / mobile links → keep as-is; yt-dlp handles them
    if url.startswith("http://"):
        url = "https://" + url[7:]
    return url


def build_ydl_opts(outtmpl: str, height: str) -> dict:
    # Prefer merged A/V when ffmpeg exists; otherwise single progressive/best stream
    if HAS_FFMPEG:
        fmt = (
            f"bv*[height<={height}][ext=mp4]+ba[ext=m4a]/"
            f"bv*[height<={height}]+ba/"
            f"b[height<={height}]/"
            f"bv*+ba/b"
        )
    else:
        fmt = f"b[height<={height}]/b/bv*[height<={height}]+ba/bv*+ba"

    opts = {
        "format": fmt,
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 1,
        # YouTube often blocks default web client — try multiple
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "web"],
            }
        },
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        },
    }

    if os.path.isfile(COOKIES_PATH):
        opts["cookiefile"] = COOKIES_PATH

    return opts


def friendly_error(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "sign in" in low or "login" in low or "cookies" in low or "private" in low:
        return "This video may be private or require login. Try a public link."
    if "unsupported url" in low or "no video formats" in low or "unable to extract" in low:
        return "Unsupported link. Use a public Instagram Reel or YouTube URL."
    if "requested format is not available" in low:
        return "That quality is not available for this video. Try a lower quality."
    if "http error 403" in low or "forbidden" in low:
        return "YouTube blocked the download (403). Try again in a minute, or another video."
    if "timed out" in low or "timeout" in low:
        return "Download timed out. Try a shorter video or lower quality."
    return "Download failed. Check the link and try again."


@app.route("/ping", methods=["GET"])
def ping():
    return {"status": "ok"}, 200


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_index()

    url = normalize_url(request.form.get("url") or "")
    quality = request.form.get("quality") or "720p"

    if not url or not re.match(r"^https?://", url, re.I):
        return render_index(
            error="Please paste a valid Instagram or YouTube link.",
            url=url,
            quality=quality,
        )

    if quality not in VALID_QUALITIES:
        return render_index(
            error="Please select a valid quality option.",
            url=url,
            quality=quality,
        )

    height = quality[:-1]
    file_id = str(uuid.uuid4())
    outtmpl = os.path.join(DOWNLOAD_DIR, file_id + ".%(ext)s")
    ydl_opts = build_ydl_opts(outtmpl, height)

    try:
        logger.info(f"Downloading: {url} @ {quality} (ffmpeg={HAS_FFMPEG})")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        candidates = [
            os.path.join(DOWNLOAD_DIR, name)
            for name in os.listdir(DOWNLOAD_DIR)
            if name.startswith(file_id) and os.path.isfile(os.path.join(DOWNLOAD_DIR, name))
        ]
        # Ignore leftover fragment files if any
        candidates = [p for p in candidates if not re.search(r"\.f\d+\.", os.path.basename(p))]

        if not candidates:
            return render_index(
                error="Download finished but the file was not found. Try again.",
                url=url,
                quality=quality,
            )

        filepath = max(candidates, key=os.path.getmtime)
        if os.path.getsize(filepath) < 1024:
            os.remove(filepath)
            return render_index(
                error="Downloaded file was empty. Try another quality or video.",
                url=url,
                quality=quality,
            )

        @after_this_request
        def cleanup(response):
            try:
                for path in candidates:
                    if os.path.exists(path):
                        os.remove(path)
            except Exception as e:
                logger.error(f"Error cleaning up file: {e}")
            return response

        ext = os.path.splitext(filepath)[1].lstrip(".") or "mp4"
        return send_file(
            filepath,
            as_attachment=True,
            download_name=f"video.{ext}",
            mimetype="video/mp4" if ext == "mp4" else None,
        )

    except Exception as e:
        logger.error(f"yt-dlp download failed: {e}")
        return render_index(error=friendly_error(e), url=url, quality=quality)


def start_self_ping():
    time.sleep(10)
    while True:
        base = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("SELF_URL")
        if base:
            try:
                ping_url = f"{base.rstrip('/')}/ping"
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
    port = int(os.getenv("PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=True)
