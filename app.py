
from flask import Flask, render_template, request, send_file
import subprocess, os, uuid

app = Flask(__name__)
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        if not url:
            return render_template("index.html", error="Please enter a Reel URL")

        filename = f"{uuid.uuid4()}.mp4"
        filepath = os.path.join(DOWNLOAD_DIR, filename)

        try:
            subprocess.run([
                "yt-dlp",
                "-f", "mp4",
                "-o", filepath,
                url
            ], check=True)
        except Exception as e:
            return render_template("index.html", error=str(e))

        return send_file(filepath, as_attachment=True)

    return render_template("index.html")
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

    


# python3 -m venv venv
# source venv/bin/activate
# pip install -r requirements.txt
# python app.py
