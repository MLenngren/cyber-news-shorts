## Install

### Prerequisites

- **Python 3**
- **ffmpeg** (must provide `ffmpeg` + `ffprobe` on PATH)
- **Node.js** (so `npx hyperframes ...` works)

If HyperFrames can't find a browser automatically, set:
- `HYPERFRAMES_BROWSER_PATH` (path to Chromium/Chrome)

Optional:
- **1Password CLI (`op`)** if you want `op://` secret reads (requires `OP_SERVICE_ACCOUNT_TOKEN`).

### Python environment

Create a virtualenv and install Python deps:

- `python3 -m venv .venv`
- `source .venv/bin/activate`
- `pip install -r requirements.txt`

> Note: `requirements.txt` includes YouTube client libraries even if you don’t publish. Keeping a single file simplifies setup.

### Environment variables

- Copy `.env.example` to `.env`
- Set at least `ELEVENLABS_API_KEY`
- Add other keys depending on mode (HeyGen, stock providers, AI visuals)

This repo is **env-first**: keys are read from env vars. `op://` reads are only attempted when `OP_SERVICE_ACCOUNT_TOKEN` is set.

### Sanity checks

Parse a script into JSON:
- `python3 scripts/parse_script.py --script shorts/short-001-example.md --output shorts/_parsed.json`

Lint the compositions:
- `cd hyperframes && npx hyperframes lint`

Render an example (requires API keys; may incur cost):
- `python3 scripts/render_short.py --mode stock-broll --script shorts/short-002-example.md`

### HeyGen background assets (talking-head modes)

This OSS snapshot does not ship HeyGen background asset IDs.

To use `--mode talking-head` / `--mode talking-head-hybrid`, create:
- `assets/backgrounds/cyber-newsroom.heygen-asset-id`
- `assets/backgrounds/cyber-newsroom-evening.heygen-asset-id`

Each file should contain a single HeyGen image asset id from **your** HeyGen account.

### API keys (where to get them)

- ElevenLabs: `ELEVENLABS_API_KEY`
- HeyGen: `HEYGEN_API_KEY` (talking-head modes)
- Pexels: `PEXELS_API_KEY` (stock-broll)
- Storyblocks: `STORYBLOCKS_PUBLIC_API_KEY` + `STORYBLOCKS_PRIVATE_API_KEY` (stock-broll; optional fallback)
- OpenRouter: `OPENROUTER_API_KEY` (stock-broll keyframe)
- Runware: `RUNWARE_API_KEY` (stock-broll hero clip, b-roll)

### Troubleshooting

- If `npx hyperframes lint` fails: ensure Node is installed and reachable.
- If audio render fails: verify `ELEVENLABS_API_KEY` and `voices/max_voice_id.txt`.
- If you add new speakers to a script: provide a voice id file and/or flags to `render_audio.py`.
