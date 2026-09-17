from flask import (
    Flask,
    render_template,
    request,
    send_file,
    after_this_request,
    Response,
    stream_with_context,
)
import os, tempfile, time, urllib.request, shutil, logging, re, uuid
from threading import Thread
from urllib.parse import quote

import requests
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
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def render_index(error=None, url="", quality="480p"):
    return render_template("index.html", error=error, url=url, quality=quality)


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("http://"):
        url = "https://" + url[7:]
    return url


def base_ydl_opts(height: str) -> dict:
    # Progressive (single file) first = fast stream, no merge wait
    if HAS_FFMPEG:
        fmt = (
            f"b[height<={height}][ext=mp4]/"
            f"b[height<={height}]/"
            f"bv*[height<={height}][ext=mp4]+ba[ext=m4a]/"
            f"bv*[height<={height}]+ba/"
            f"b/bv*+ba"
        )
    else:
        fmt = f"b[height<={height}][ext=mp4]/b[height<={height}]/b"

    opts = {
        "format": fmt,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 20,
        "retries": 3,
        "extractor_args": {
            "youtube": {
                # android often gives progressive mp4 (fast)
                "player_client": ["android", "ios", "web"],
            }
        },
        "http_headers": {"User-Agent": UA},
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
        return "That quality is not available. Try 360p or 480p."
    if "http error 403" in low or "forbidden" in low:
        return "YouTube blocked this server IP. Try again later or use a different video."
    if "timed out" in low or "timeout" in low:
        return "Timed out. Try 360p / a shorter video."
    return "Download failed. Try 360p or another link."


def is_progressive(info: dict) -> bool:
    if not info.get("url"):
        return False
    if info.get("requested_formats"):
        return False
    vcodec = info.get("vcodec") or "none"
    acodec = info.get("acodec") or "none"
    return vcodec != "none" and acodec != "none"


def stream_from_url(media_url: str, headers: dict, filename: str = "video.mp4"):
    upstream = requests.get(media_url, stream=True, headers=headers, timeout=30)
    upstream.raise_for_status()

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=256 * 1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    content_type = upstream.headers.get("Content-Type", "video/mp4")
    resp_headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        "Cache-Control": "no-store",
    }
    length = upstream.headers.get("Content-Length")
    if length:
        resp_headers["Content-Length"] = length

    return Response(
        stream_with_context(generate()),
        status=200,
        headers=resp_headers,
        mimetype=content_type,
    )


def download_to_disk(url: str, height: str):
    file_id = str(uuid.uuid4())
    outtmpl = os.path.join(DOWNLOAD_DIR, file_id + ".%(ext)s")
    opts = base_ydl_opts(height)
    opts.pop("skip_download", None)
    opts["outtmpl"] = outtmpl
    opts["merge_output_format"] = "mp4"
    opts["concurrent_fragment_downloads"] = 4

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    candidates = [
        os.path.join(DOWNLOAD_DIR, name)
        for name in os.listdir(DOWNLOAD_DIR)
        if name.startswith(file_id) and os.path.isfile(os.path.join(DOWNLOAD_DIR, name))
    ]
    candidates = [p for p in candidates if not re.search(r"\.f\d+\.", os.path.basename(p))]
    if not candidates:
        raise RuntimeError("File not found after download")
    return max(candidates, key=os.path.getmtime), candidates


@app.route("/ping", methods=["GET"])
def ping():
    return {"status": "ok"}, 200


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_index()

    url = normalize_url(request.form.get("url") or "")
    quality = request.form.get("quality") or "480p"

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

    try:
        logger.info(f"Resolve: {url} @ {quality}")
        opts = base_ydl_opts(height)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title = (info.get("title") or "video")[:80]
        safe_name = re.sub(r"[^\w\-]+", "_", title).strip("_") or "video"

        # Fast path: stream progressive URL straight to browser
        if is_progressive(info):
            media_url = info["url"]
            headers = {"User-Agent": UA, "Referer": url}
            http_headers = info.get("http_headers") or {}
            headers.update(http_headers)
            logger.info("Fast stream (progressive)")
            return stream_from_url(media_url, headers, filename=f"{safe_name}.mp4")

        # Slow path: merge on disk (only when needed)
        logger.info("Fallback disk download (merge)")
        filepath, candidates = download_to_disk(url, height)

        @after_this_request
        def cleanup(response):
            try:
                for path in candidates:
                    if os.path.exists(path):
                        os.remove(path)
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
            return response

        ext = os.path.splitext(filepath)[1].lstrip(".") or "mp4"
        return send_file(
            filepath,
            as_attachment=True,
            download_name=f"{safe_name}.{ext}",
            mimetype="video/mp4" if ext == "mp4" else None,
        )

    except Exception as e:
        logger.error(f"Download failed: {e}")
        return render_index(error=friendly_error(e), url=url, quality=quality)


def start_self_ping():
    time.sleep(15)
    while True:
        base = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("SELF_URL")
        if not base:
            logger.warning("No SELF_URL / RENDER_EXTERNAL_URL — self-ping disabled")
            break
        try:
            ping_url = f"{base.rstrip('/')}/ping"
            urllib.request.urlopen(ping_url, timeout=10)
            logger.info(f"Pinged {ping_url}")
        except Exception as e:
            logger.error(f"Ping failed: {e}")
        time.sleep(50)


Thread(target=start_self_ping, daemon=True).start()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=True)
