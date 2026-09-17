from flask import Flask, render_template, request
import os, tempfile, time, urllib.request, shutil, logging, re
from threading import Thread

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Flask app setup
app = Flask(__name__)
DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Check FFmpeg availability
HAS_FFMPEG = shutil.which("ffmpeg") is not None
logger.info(f"FFmpeg availability: {HAS_FFMPEG}")

@app.route("/ping", methods=["GET"])
def ping():
    """Health check endpoint."""
    return {"status": "ok"}, 200

@app.route("/", methods=["GET", "POST"])
def index():
    """Main route for the app."""
    if request.method == "GET":
        return render_template("index.html")
    elif request.method == "POST":
        url = request.form.get("url")
        quality = request.form.get("quality")

        # Validate the URL
        if not url or not re.match(r'^https?://', url):
            return "Please enter a valid HTTP or HTTPS URL", 200

        # Validate the quality
        if not quality or quality not in ["720p", "480p"]:
            return "Please select a valid quality option", 200

        # If everything is valid, return success message
        return "Download started", 200

def start_self_ping():
    """Periodically pings the app's /ping endpoint to keep it alive."""
    time.sleep(10)  # Initial delay
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
        time.sleep(60)  # Ping every 60 seconds

# Start the self-ping thread
Thread(target=start_self_ping, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)