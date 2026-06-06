## ThreatNoir Cyber News (OSS)

[![ci](https://github.com/MLenngren/cyber-news-shorts/actions/workflows/ci.yml/badge.svg)](https://github.com/MLenngren/cyber-news-shorts/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Cyber News Shorts is a small, scriptable pipeline for generating vertical (9:16) cybersecurity news shorts.

▶ **[Watch an example render](https://github.com/MLenngren/cyber-news-shorts/releases/download/v0.1.0/cyber-news-shorts-demo.mp4)** — a ~20s `stock-broll` short produced by the included `shorts/short-002-example.md` (ElevenLabs voiceover + Pexels stock + an AI hero clip, composited with HyperFrames).

It turns a Markdown “script” into:
- structured JSON timing (`shorts/*.json`, `shorts/*.timing.json`)
- TTS audio (ElevenLabs)
- visuals (mode-dependent: HeyGen avatar, stock b-roll, AI hero clip)
- a final MP4 rendered via **HyperFrames** (`npx hyperframes render`)

## Modes (API matrix + rough cost)

Costs depend on provider pricing and your usage, but the intent is “cents per short”, not dollars.

| Mode | What you get | Typical APIs | Rough $/short |
| --- | --- | --- | --- |
| `talking-head` | Avatar reads the script | HeyGen + ElevenLabs | ~0.35 |
| `talking-head-hybrid` | Avatar + stock cutaways | HeyGen + ElevenLabs + Pexels | ~0.35–0.45 |
| `stock-broll` | Stock b-roll + 1 AI hero clip + cards | ElevenLabs + Pexels/Storyblocks + OpenRouter + Runware | ~0.45–0.70 |
| `b-roll` | AI-first visuals (no avatar) | ElevenLabs + Runware | ~0.25–0.60 |

### What’s in this repo
- `scripts/` — the CLI pipeline (parse → audio → visuals → render → optional publish)
- `hyperframes/` — HTML compositions used by HyperFrames
- `voices/` — example ElevenLabs voice id files (non-secret)
- `shorts/` — your scripts and generated outputs

## Quickstart

### Option A — Docker (no local toolchain needed)

Everything the pipeline needs (Python + deps, ffmpeg, Node + HyperFrames, headless Chromium) is bundled in the image.

```bash
cp .env.example .env        # add your API keys — see docs/COSTS.md for which you need
docker compose build

# Morning edition — stock b-roll, no avatar (cheapest):
docker compose run --rm shorts --edition morning --script shorts/short-002-example.md

# Evening edition — HeyGen talking-head + Pexels cutaways (needs HEYGEN_API_KEY):
docker compose run --rm evening
#   ...same as: docker compose run --rm shorts --edition evening --script shorts/short-003-evening-example.md

# the rendered short-NNN.mp4 lands in ./shorts
```

> **Editions:** `--edition morning` renders `stock-broll` (no avatar); `--edition evening` renders `talking-head-hybrid` (HeyGen avatar + cutaways). It also sets the on-screen "MORNING/EVENING BRIEF" badge. Pass an explicit `--mode` to override.

### Option B — local install

1) **Prereqs:** Python 3, `ffmpeg` / `ffprobe`, Node.js (for `npx hyperframes`). Run **`./scripts/setup.sh`** to check prerequisites, create `.env`, and set up a Python venv.

2) **Configure:** copy `.env.example` → `.env` and add your keys. Secrets are **env-first**; optional `op://` reads only happen when `OP_SERVICE_ACCOUNT_TOKEN` is set.

3) **Render an example:**

```bash
# no-API sanity check:
python3 scripts/parse_script.py --script shorts/short-001-example.md --output shorts/_parsed.json
# full render (needs API keys):
python3 scripts/render_short.py --mode stock-broll --script shorts/short-002-example.md
```

Outputs land in `shorts/` as `short-<NNN>-<slug>.mp4`.

> 💸 **What does it cost?** See **[docs/COSTS.md](docs/COSTS.md)** — per-API pricing and per-mode $/short. The cheapest path (`stock-broll` with no AI hero shot) is ≈ **$0.05/short** (Pexels is free; you only pay for ElevenLabs voiceover).

### Gotchas

- **HyperFrames browser:** if Chromium/Chrome isn’t auto-detected, set `HYPERFRAMES_BROWSER_PATH`.
- **WSL2:** complex hybrid compositions with many cutaways can stall on frame 1 in some setups.
  If you hit that, reduce cutaways and/or render on native Linux/macOS.

## Configuration

### Brand / identity (non-secret)
Set these to rebrand the output:
- `BRAND_NAME` (default: “ThreatNoir Cyber News”)
- `BRAND_SHORT_NAME` (default: “ThreatNoir”)
- `BRAND_URL` (default: `https://threatnoir.com`)
- `BRAND_HASHTAGS` (used in YouTube descriptions)
- `BRAND_USER_AGENT` (optional override for outbound HTTP calls)
- `DISCORD_USER_AGENT` (Discord HTTP User-Agent override)
- `NEWS_BRIEF_URL` (used by the cron example; supply your own news feed endpoint)

Optional:
- `OPERATOR_DISCORD_ID` (default empty; when set, some scripts send best-effort DMs)

### Secrets (API keys)
Core pipeline may use:
- `ELEVENLABS_API_KEY`
- `HEYGEN_API_KEY` (talking-head modes)
- `PEXELS_API_KEY` / `STORYBLOCKS_PUBLIC_API_KEY` / `STORYBLOCKS_PRIVATE_API_KEY` (stock-broll)
- `RUNWARE_API_KEY` and/or `OPENROUTER_API_KEY` (AI visuals)

Optional integrations:
- `DISCORD_BOT_TOKEN`
- `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`

## Optional: YouTube publishing
`render_short.py --publish` calls `scripts/publish_youtube.py`.

To bootstrap OAuth refresh tokens:
- `python3 scripts/youtube_oauth_setup.py`

## License
Apache-2.0. See `LICENSE` and `NOTICE`.
