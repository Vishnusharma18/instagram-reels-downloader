
from flask import Flask, render_template, request, send_file
import subprocess, os, uuid, tempfile, threading, time, urllib.request

app = Flask(__name__)
DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

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
            except Exception as e:
                print(f"Self ping failed: {e}")
        time.sleep(10 * 60) # Ping every 10 minutes

# Start keep-alive ping thread
ping_thread = threading.Thread(target=start_self_ping, daemon=True)
ping_thread.start()

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        quality = request.form.get("quality", "best")
        if not url:
            return render_template("index.html", error="Please enter a valid URL")

        file_id = str(uuid.uuid4())
        out_template = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")

        cmd = ["yt-dlp", "-o", out_template]

        if quality == "audio":
            cmd.extend(["-f", "ba/bestaudio/b/best"])
        elif quality in ["1080p", "720p", "480p", "360p", "240p"]:
            height = quality.replace("p", "")
            format_spec = f"b[height<={height}]/best[height<={height}]/bestvideo[height<={height}]+bestaudio/best"
            cmd.extend(["-f", format_spec])
        else:
            # best quality (prefer single-file format 'b' or 'best' first so ffmpeg isn't strictly required)
            cmd.extend(["-f", "b/best/bestvideo+bestaudio"])

        cmd.append(url)

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)

            # Find the generated file (extension might be mp4, m4a, mp3, webm, etc.)
            downloaded_files = [
                os.path.join(DOWNLOAD_DIR, f)
                for f in os.listdir(DOWNLOAD_DIR)
                if f.startswith(file_id)
            ]
            if not downloaded_files:
                return render_template("index.html", error="Failed to find downloaded file. The video may be unavailable.")

            downloaded_file = downloaded_files[0]
            download_name = os.path.basename(downloaded_file)
            return send_file(downloaded_file, as_attachment=True, download_name=download_name)
        except subprocess.CalledProcessError as e:
            error_msg = "Download failed. The video may be private, unavailable, or age-restricted."
            if e.stderr and "unavailable" in e.stderr.lower():
                error_msg = "This video is unavailable or private on YouTube/Instagram."
            return render_template("index.html", error=error_msg)
        except Exception as e:
            return render_template("index.html", error=f"Download failed: {str(e)}")

    return render_template("index.html")
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

    


# python3 -m venv venv
# source venv/bin/activate
# pip install -r requirements.txt
# python app.py
