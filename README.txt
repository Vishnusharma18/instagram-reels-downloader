ClipFetch — Instagram Reels & YouTube Downloader

LOCAL:
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  python app.py
  Open http://127.0.0.1:5001

RENDER (Docker — required for FFmpeg):
  1. Push this repo to GitHub
  2. New Web Service → Runtime: Docker
  3. Health check path: /ping
  4. Env SELF_URL = https://YOUR-APP.onrender.com
  5. Deploy latest commit

NOTES:
  - Default quality is 360p (fastest / most reliable)
  - YouTube sometimes blocks cloud IPs — wait and retry, or try another video
  - Instagram usually needs cookies.txt in the project root
  - Free Render sleeps when idle; first open can take ~30–60s
