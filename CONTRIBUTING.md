# Contributing

Thanks for your interest in ThreatNoir Cyber News (OSS) — a scriptable pipeline for generating vertical cybersecurity news Shorts.

## Dev setup

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
# also needed on PATH: ffmpeg / ffprobe, and Node.js (for `npx hyperframes`)
cp .env.example .env   # then add your own API keys — see INSTALL.md
```

## How it works

A Markdown script (`shorts/*.md`) is turned into an MP4 through one of four render modes — `talking-head`, `talking-head-hybrid`, `stock-broll`, `b-roll`. The pipeline stages are: parse → audio (ElevenLabs) → visuals (mode-dependent) → HyperFrames composition → MP4. See `README.md` for the mode/API matrix and `INSTALL.md` for the full setup.

## Ground rules (enforced by CI)

This repo is a public, operator-neutral snapshot. The CI workflow (`.github/workflows/ci.yml`) will **fail your PR** if it finds any of:

- **Operator / personal identity** — real names, personal social handles, Discord or user IDs. Route everything through env vars with safe fallbacks. For example, `OPERATOR_DISCORD_ID` defaults to empty so the pipeline never DMs anyone, and brand strings go through the `brand()` helper in `scripts/_util.py` (`BRAND_NAME`, `BRAND_URL`, …).
- **Hardcoded secrets** — every API key is read from an env var (or an optional 1Password `op://` reference when `OP_SERVICE_ACCOUNT_TOKEN` is set). Never commit `.env` or real keys; `.env` is gitignored.
- **Machine-specific host paths** — derive paths at runtime (e.g. from the script's own directory), don't hardcode `/home/you/...`.

## Submitting a PR

1. Fork and branch.
2. Keep secrets and identity out — the CI audit above is the gate.
3. Python should parse and stay reasonably clean (`ruff` recommended). Shell scripts should pass `bash -n`.
4. Open a PR describing the change and how you tested it.

## Adding a mode or composition

Render modes live in `scripts/modes/`; HyperFrames compositions in `hyperframes/`. Follow the existing pattern, and add a small example script under `shorts/` if your change introduces new frontmatter.
