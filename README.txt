ClipFetch — Instagram Reels & YouTube Downloader

LOCAL SETUP:
1. python3 -m venv venv
2. source venv/bin/activate
3. pip install -r requirements.txt
4. python app.py

Open: http://127.0.0.1:5001

RENDER (recommended):
1. Push this repo to GitHub
2. Render Dashboard → New → Web Service → connect repo
3. IMPORTANT: Runtime = Docker (so FFmpeg installs)
4. Health check path: /ping
5. After deploy, set env SELF_URL = https://YOUR-APP.onrender.com
6. Manual Deploy / push again so latest code goes live

Notes:
- Free Render sleeps after idle; first request can be slow
- YouTube sometimes blocks cloud IPs — try another video or add cookies.txt
- Instagram usually needs cookies.txt
