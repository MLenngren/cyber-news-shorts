#!/usr/bin/env bash
# First-run setup for ThreatNoir Cyber News (OSS).
# Creates .env, checks prerequisites, and (optionally) sets up a Python venv.
# Idempotent — safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== ThreatNoir Cyber News — setup =="
echo

# 1) .env
if [ -f .env ]; then
  echo "[ok]  .env already exists"
else
  cp .env.example .env
  echo "[new] created .env from .env.example — edit it to add your API keys"
fi

# 2) prerequisites
echo
echo "-- prerequisites --"
miss=0
check() {
  if command -v "$1" >/dev/null 2>&1; then
    echo "[ok]  $1"
  else
    echo "[!!]  $1 missing — $2"
    miss=1
  fi
}
check python3 "install Python 3"
check ffmpeg  "install ffmpeg (also provides ffprobe)"
check node    "install Node.js (needed for: npx hyperframes)"
check npx     "comes with Node.js"

# 3) Python venv + deps (optional)
if command -v python3 >/dev/null 2>&1; then
  echo
  if [ -d venv ]; then
    echo "[ok]  Python venv already exists"
  else
    read -r -p "Create a Python venv and install requirements now? [y/N] " ans
    case "${ans:-N}" in
      y|Y)
        python3 -m venv venv
        ./venv/bin/pip install -q --upgrade pip
        ./venv/bin/pip install -q -r requirements.txt
        echo "[ok]  venv ready"
        ;;
      *) echo "[skip] venv — create it later with: python3 -m venv venv && ./venv/bin/pip install -r requirements.txt" ;;
    esac
  fi
fi

echo
echo "Next steps:"
echo "  1) Edit .env with your API keys. For the cheapest path (stock-broll, no AI hero),"
echo "     you only need ELEVENLABS_API_KEY + PEXELS_API_KEY. See docs/COSTS.md."
echo "  2) Render an example:"
echo "       ./venv/bin/python scripts/render_short.py --mode stock-broll --script shorts/short-002-example.md"
echo "     ...or with Docker (no local toolchain needed):"
echo "       docker compose run --rm shorts --mode stock-broll --script shorts/short-002-example.md"
if [ "$miss" = "1" ]; then
  echo
  echo "(!) Some prerequisites are missing above. Install them, or use the Docker path which bundles everything."
fi
