
from flask import Flask, render_template, request, send_file
import subprocess, os, uuid

app = Flask(__name__)
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

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
            cmd.extend(["-f", "bestaudio/best", "-x", "--audio-format", "mp3"])
        elif quality in ["1080p", "720p", "480p", "360p", "240p"]:
            height = quality.replace("p", "")
            # Prefer single file format with requested height, fallback to combined or best under/equal height
            format_spec = f"best[height<={height}]/bestvideo[height<={height}]+bestaudio/best"
            cmd.extend(["-f", format_spec])
        else:
            # best quality
            cmd.extend(["-f", "best/bestvideo+bestaudio"])

        cmd.append(url)

        try:
            subprocess.run(cmd, check=True)

            # Find the generated file (extension might be mp4, m4a, mp3, webm, etc.)
            downloaded_files = [
                os.path.join(DOWNLOAD_DIR, f)
                for f in os.listdir(DOWNLOAD_DIR)
                if f.startswith(file_id)
            ]
            if not downloaded_files:
                return render_template("index.html", error="Failed to find downloaded file.")

            downloaded_file = downloaded_files[0]
            download_name = os.path.basename(downloaded_file)
            return send_file(downloaded_file, as_attachment=True, download_name=download_name)
        except Exception as e:
            return render_template("index.html", error=f"Download failed: {str(e)}")

    return render_template("index.html")
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

    


# python3 -m venv venv
# source venv/bin/activate
# pip install -r requirements.txt
# python app.py
