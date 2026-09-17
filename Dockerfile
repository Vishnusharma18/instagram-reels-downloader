FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && yt-dlp --version

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PORT=10000

EXPOSE 10000

# Long timeout: video downloads can take minutes on free tier
CMD gunicorn app:app --bind 0.0.0.0:${PORT} --timeout 300 --workers 1 --threads 2 --graceful-timeout 30
