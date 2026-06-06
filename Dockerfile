# ThreatNoir Cyber News — render pipeline in a single image.
# Bundles everything the pipeline shells out to: Python + deps, ffmpeg, Node +
# the HyperFrames CLI, and a headless Chromium for compositing.
#
# Build:  docker build -t cyber-news-shorts .
# Run:    docker run --rm --env-file .env -v "$PWD/shorts:/app/shorts" \
#           cyber-news-shorts --mode stock-broll --script shorts/short-002-example.md
FROM node:20-bookworm-slim

# System deps: Python, ffmpeg/ffprobe, headless Chromium + the runtime libs/fonts
# HyperFrames needs to render HTML compositions to frames.
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip \
      ffmpeg \
      chromium \
      fonts-liberation fonts-noto-color-emoji fonts-dejavu-core \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Chromium launched by HyperFrames runs inside a container (often as root, no GPU,
# limited /dev/shm). Wrap it to force the flags that make that reliable.
RUN printf '#!/bin/sh\nexec /usr/bin/chromium --no-sandbox --disable-dev-shm-usage --disable-gpu "$@"\n' \
      > /usr/local/bin/chromium-headless \
 && chmod +x /usr/local/bin/chromium-headless

WORKDIR /app

# Python deps first (layer cache)
COPY requirements.txt ./
RUN python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt

# Pin the HyperFrames CLI so the first render doesn't fetch it at runtime.
RUN npm install -g hyperframes@^0.6

# App source
COPY . .

ENV HYPERFRAMES_BROWSER_PATH=/usr/local/bin/chromium-headless \
    THREATNOIR_PUBLISH=0 \
    PRODUCER_LOW_MEMORY_MODE=1 \
    PYTHONUNBUFFERED=1

# Render a short. Override --mode / --script at `docker run`.
ENTRYPOINT ["python3", "scripts/render_short.py"]
CMD ["--mode", "stock-broll", "--script", "shorts/short-002-example.md"]
