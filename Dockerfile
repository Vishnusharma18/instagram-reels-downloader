FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        curl \
        unzip \
    && rm -rf /var/lib/apt/lists/*

# Deno is required for YouTube JS challenge solving (yt-dlp EJS)
ENV DENO_INSTALL=/usr/local
RUN curl -fsSL https://deno.land/install.sh | sh \
    && deno --version

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && yt-dlp --version

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PORT=10000
ENV PATH="/usr/local/bin:${PATH}"

EXPOSE 10000

CMD gunicorn app:app --bind 0.0.0.0:${PORT} --timeout 300 --workers 1 --threads 2 --graceful-timeout 30
