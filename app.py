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
DENO_PATH = shutil.which("deno")
NODE_PATH = shutil.which("node")
logger.info("FFmpeg=%s deno=%s node=%s", HAS_FFMPEG, DENO_PATH, NODE_PATH)

VALID_QUALITIES = ["1080p", "720p", "480p", "360p", "240p"]
COOKIES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

PLAYER_CLIENT_SETS = [
    ["tv", "ios", "mweb", "android"],
    ["tv_embedded", "visionos", "web"],
    ["ios", "tv"],
]


def render_index(error=None, url="", quality="360p"):
    return render_template("index.html", error=error, url=url, quality=quality)


def normalize_url(url):
    url = (url or "").strip()
    if url.startswith("http://"):
        url = "https://" + url[7:]
    return url


def build_format(height):
    if HAS_FFMPEG:
        return (
            f"b[height<={height}][ext=mp4]/"
            f"b[height<={height}]/"
            f"bv*[height<={height}][ext=mp4]+ba[ext=m4a]/"
            f"bv*[height<={height}]+ba/"
            f"b/bv*+ba"
        )
    return f"b[height<={height}][ext=mp4]/b[height<={height}]/b"


def js_runtime_opts():
    """YouTube needs a JS runtime to solve challenges (Deno preferred)."""
    runtimes = {}
    if DENO_PATH:
        runtimes["deno"] = {"path": DENO_PATH}
    if NODE_PATH:
        runtimes["node"] = {"path": NODE_PATH}
    return runtimes


def make_opts(height, outtmpl, player_clients):
    opts = {
        "format": build_format(height),
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 3,
        "merge_output_format": "mp4",
        "extractor_args": {"youtube": {"player_client": player_clients}},
        "http_headers": {"User-Agent": UA},
        "remote_components": ["ejs:github"],
    }
    runtimes = js_runtime_opts()
    if runtimes:
        opts["js_runtimes"] = runtimes
    if os.path.isfile(COOKIES_PATH):
        opts["cookiefile"] = COOKIES_PATH
    return opts


def friendly_error(exc):
    msg = str(exc)
    low = msg.lower()
    if "player response" in low:
        return (
            "YouTube blocked extraction on this server. "
            "Wait a minute and retry, or try another public video."
        )
    if any(x in low for x in ("sign in", "login required", "cookies", "private video")):
        return "This video may be private or require login."
    if any(x in low for x in ("unsupported url", "no video formats", "unable to extract")):
        return "Unsupported link. Use a public YouTube or Instagram URL."
    if "requested format is not available" in low:
        return "That quality is not available. Try 360p."
    if any(x in low for x in ("403", "forbidden", "sabr")):
        return "YouTube is blocking cloud servers right now. Wait a few minutes or try another video."
    if "timed out" in low or "timeout" in low:
        return "Timed out. Try 360p or a shorter video."
    if "javascript runtime" in low or "js runtime" in low or "ejs" in low:
        return "Server is missing YouTube JS support. Redeploy the latest Docker image."
    short = msg.replace("ERROR: ", "").strip()
    if len(short) > 160:
        short = short[:160] + "…"
    return f"Download failed: {short}"


def find_downloaded_file(file_id):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    candidates = [
        os.path.join(DOWNLOAD_DIR, name)
        for name in os.listdir(DOWNLOAD_DIR)
        if name.startswith(file_id) and os.path.isfile(os.path.join(DOWNLOAD_DIR, name))
    ]
    candidates = [p for p in candidates if not re.search(r"\.f\d+\.", os.path.basename(p))]
    if not candidates:
        return None, []
    return max(candidates, key=os.path.getmtime), candidates


def download_video(url, height):
    last_error = None
    title = "video"

    for clients in PLAYER_CLIENT_SETS:
        file_id = str(uuid.uuid4())
        outtmpl = os.path.join(DOWNLOAD_DIR, file_id + ".%(ext)s")
        opts = make_opts(height, outtmpl, clients)
        try:
            logger.info("Trying clients=%s for %s", clients, url)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if isinstance(info, dict):
                    title = (info.get("title") or "video")[:80]

            filepath, candidates = find_downloaded_file(file_id)
            if not filepath:
                raise RuntimeError("Download finished but file was not found")
            if os.path.getsize(filepath) < 1024:
                for p in candidates:
                    try:
                        os.remove(p)
                    except OSError:
                        pass
                raise RuntimeError("Downloaded file was empty")

            safe_name = re.sub(r"[^\w\-]+", "_", title).strip("_") or "video"
            return filepath, candidates, safe_name
        except Exception as e:
            last_error = e
            logger.warning("Client set %s failed: %s", clients, e)
            filepath, candidates = find_downloaded_file(file_id)
            for p in candidates:
                try:
                    os.remove(p)
                except OSError:
                    pass

    raise last_error or RuntimeError("Download failed")


@app.route("/ping", methods=["GET"])
def ping():
    return {
        "status": "ok",
        "ffmpeg": HAS_FFMPEG,
        "deno": bool(DENO_PATH),
        "node": bool(NODE_PATH),
    }, 200


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_index()

    url = normalize_url(request.form.get("url") or "")
    quality = request.form.get("quality") or "360p"

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

    try:
        logger.info("Download start: %s @ %s (ffmpeg=%s deno=%s)", url, quality, HAS_FFMPEG, bool(DENO_PATH))
        filepath, candidates, safe_name = download_video(url, quality[:-1])
        logger.info("Download ok: %s (%s bytes)", filepath, os.path.getsize(filepath))

        @after_this_request
        def cleanup(response):
            try:
                for path in candidates:
                    if os.path.exists(path):
                        os.remove(path)
            except Exception as e:
                logger.error("Cleanup error: %s", e)
            return response

        ext = os.path.splitext(filepath)[1].lstrip(".") or "mp4"
        return send_file(
            filepath,
            as_attachment=True,
            download_name="{}.{}".format(safe_name, ext),
            mimetype="video/mp4" if ext == "mp4" else None,
        )
    except Exception as e:
        logger.exception("Download failed")
        return render_index(error=friendly_error(e), url=url, quality=quality)


def start_self_ping():
    time.sleep(15)
    while True:
        base = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("SELF_URL")
        if not base:
            logger.warning("No SELF_URL / RENDER_EXTERNAL_URL — self-ping disabled")
            break
        try:
            ping_url = "{}/ping".format(base.rstrip("/"))
            urllib.request.urlopen(ping_url, timeout=10)
            logger.info("Pinged %s", ping_url)
        except Exception as e:
            logger.error("Ping failed: %s", e)
        time.sleep(50)


Thread(target=start_self_ping, daemon=True).start()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG") == "1")
