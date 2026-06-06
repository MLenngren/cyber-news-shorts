#!/usr/bin/env python3
"""ThreatNoir Cyber News — render_short.py

Multi-mode short renderer.

Modes:
- talking-head (default): legacy HeyGen Tyler avatar (kept callable)
- talking-head-hybrid: HeyGen Tyler + Pexels cutaways (evening default)
- stock-broll: Pexels/Storyblocks + 1 AI hero + chyrons + chrome (LEN-1744)
- b-roll: Runware stills + hero clip (no avatar)

Shared pipeline:
  1. parse_script  (markdown → JSON)
  2. WIPE shorts/audio-NNN/ (avoid stale per-line files)
  3. render_audio  (ElevenLabs TTS, ANCHOR speaker = Nathaniel)
  4. mode-specific asset prep (b-roll or talking-head)
  5. hyperframes lint
  6. hyperframes render → shorts/short-NNN-slug.mp4
  7. (optional) publish to YouTube Shorts
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from modes import broll, talking_head

from _util import brand, get_secret

PROJ = Path(__file__).resolve().parent.parent


def log(msg: str) -> None:
    print(f"[render_short] {msg}", flush=True)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    log("$ " + " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, check=True, **kwargs)


def elevenlabs_key() -> str:
    return get_secret(
        env_var="ELEVENLABS_API_KEY",
        op_ref="op://Claude/threatnoir-podcast/elvenlabs api",
    )


def ffmpeg_extract_audio(video: Path, audio_out: Path) -> None:
    log(f"extract audio from {video.name} → {audio_out.name}")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-vn",
            "-ar",
            "44100",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(audio_out),
        ],
        check=True,
    )


def ffprobe_duration(media: Path) -> float:
    res = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(media),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(res.stdout.strip())


SHORT_NN_RE = re.compile(r"short-(\d{3})-")

VISUAL_DIRECTIVE_RE = re.compile(r"\[visual:\s*([^\]]+)\]", re.IGNORECASE)

# Default render mode (can be overridden by --mode or THREATNOIR_MODE)
# default_mode = "talking-head"
DEFAULT_MODE = "talking-head"


def strip_visual_directives_in_parsed_json(parsed_json: Path) -> None:
    """Strip `[visual: ...]` directives from line text and persist prompts for visuals.

    This keeps spoken text clean (TTS) while allowing downstream Runware prompt
    selection to remain deterministic and explicit when desired.
    """
    try:
        parsed = json.loads(parsed_json.read_text(encoding="utf-8"))
    except Exception:
        return

    def _scrub_line(ln: dict) -> None:
        t = str(ln.get("text") or "")
        m = VISUAL_DIRECTIVE_RE.search(t)
        if not m:
            return
        prompt = str(m.group(1) or "").strip()
        if prompt:
            ln["visual_prompt"] = prompt
        # Remove all occurrences and normalize whitespace.
        cleaned = VISUAL_DIRECTIVE_RE.sub("", t)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        ln["text"] = cleaned

    lines = parsed.get("lines")
    if isinstance(lines, list):
        for ln in lines:
            if isinstance(ln, dict):
                _scrub_line(ln)
    scenes = parsed.get("scenes")
    if isinstance(scenes, list):
        for sc in scenes:
            if not isinstance(sc, dict):
                continue
            sc_lines = sc.get("lines")
            if isinstance(sc_lines, list):
                for ln in sc_lines:
                    if isinstance(ln, dict):
                        _scrub_line(ln)

    parsed_json.write_text(
        json.dumps(parsed, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def parse_short_id(script: Path) -> str:
    m = SHORT_NN_RE.search(script.name)
    if not m:
        raise ValueError(f"Cannot find short-NNN- prefix in {script.name}")
    return m.group(1)


def find_script_by_id(short_id: str) -> Path:
    shorts_dir = PROJ / "shorts"
    matches = sorted(shorts_dir.glob(f"short-{short_id}-*.md"))
    if not matches:
        raise FileNotFoundError(f"No script found for id {short_id} under {shorts_dir}")
    # If multiple, pick the most recently modified.
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]


def main() -> int:
    p = argparse.ArgumentParser(
        description=f"{brand('BRAND_NAME', 'ThreatNoir Cyber News')} — render short"
    )
    p.add_argument(
        "--mode",
        choices=["b-roll", "talking-head", "talking-head-hybrid", "stock-broll"],
        default=None,
    )
    p.add_argument("--script", required=False, help="Path to shorts/short-NNN-slug.md")
    p.add_argument(
        "--id", required=False, help="Short id NNN (alternative to --script)"
    )
    p.add_argument(
        "--force-visuals",
        action="store_true",
        help="Force regenerating Runware stills/hero (ignore cached assets/visuals)",
    )
    p.add_argument(
        "--skip-heygen",
        action="store_true",
        help="Reuse existing hyperframes/avatar.mp4 (debug)",
    )
    p.add_argument(
        "--skip-audio", action="store_true", help="Reuse existing audio output (debug)"
    )
    p.add_argument(
        "--publish",
        action="store_true",
        help="After render, publish to YouTube Shorts (requires requirements.txt deps + 1Password tokens)",
    )
    p.add_argument(
        "--publish-privacy",
        choices=["public", "unlisted", "private"],
        default=None,
        help="Override YouTube privacy status (default: auto rule in publish_youtube.py)",
    )
    args = p.parse_args()

    mode = (
        args.mode or os.environ.get("THREATNOIR_MODE", "").strip() or DEFAULT_MODE
    ).strip()
    if mode not in ("b-roll", "talking-head", "talking-head-hybrid", "stock-broll"):
        sys.exit(f"invalid mode: {mode}")

    if args.script:
        script = Path(args.script).resolve()
    elif args.id:
        script = find_script_by_id(str(args.id).zfill(3))
    else:
        sys.exit("must pass --script or --id")

    if not script.exists():
        sys.exit(f"script not found: {script}")
    short_id = parse_short_id(script)
    slug = script.stem  # short-NNN-slug

    # Stock-broll is a fully self-contained mode module that owns its own
    # pipeline and composition selection.
    if mode == "stock-broll":
        from modes import stock_broll

        return int(
            stock_broll.run(
                script=script,
                force_visuals=bool(args.force_visuals),
                skip_audio=bool(args.skip_audio),
                publish=bool(args.publish),
                publish_privacy=args.publish_privacy,
            )
        )
    audio_dir = PROJ / f"shorts/audio-{short_id}"
    parsed_json = PROJ / f"shorts/{slug}.json"
    final_wav = PROJ / f"shorts/{slug}.wav"
    timing_json = PROJ / f"shorts/{slug}.timing.json"
    final_mp4 = PROJ / f"shorts/{slug}.mp4"
    cost_json = PROJ / f"shorts/short-{short_id}.cost.json"
    hf_dir = PROJ / "hyperframes"
    master_wav = hf_dir / "master.wav"

    # Always write a cost sidecar (mode modules may overwrite with provider details).
    cost_json.write_text(
        json.dumps(
            {"short_id": short_id, "slug": slug, "mode": mode, "providers": {}},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # === [1] parse_script ===
    # Use sys.executable so subprocesses inherit our (potentially venv) python
    # — required for publish_youtube.py which imports python-frontmatter only
    # installed in the project venv. Same applies to all child python calls.
    PY = sys.executable

    log(f"mode: {mode}")
    log("=== [1] parse script ===")
    run(
        [
            PY,
            str(PROJ / "scripts/parse_script.py"),
            "--script",
            str(script),
            "--output",
            str(parsed_json),
        ]
    )

    # Strip any inline visual directives before TTS so they are never spoken.
    strip_visual_directives_in_parsed_json(parsed_json)

    if not args.skip_audio:
        # === [2] WIPE per-line dir ===
        log("=== [2] wipe per-line audio dir (avoid stale files) ===")
        if audio_dir.exists():
            shutil.rmtree(audio_dir)
        audio_dir.mkdir(parents=True)

        # === [3] render_audio ===
        log("=== [3] render audio (ElevenLabs ANCHOR) ===")
        env = os.environ.copy()
        env["ELEVENLABS_API_KEY"] = elevenlabs_key()
        subprocess.run(
            [
                PY,
                str(PROJ / "scripts/render_audio.py"),
                "--parsed",
                str(parsed_json),
                "--out-dir",
                str(audio_dir),
                "--final",
                str(final_wav),
                "--timing",
                str(timing_json),
                "--anchor-voice-id-file",
                str(PROJ / "voices/max_voice_id.txt"),
            ],
            check=True,
            env=env,
        )
    else:
        log("=== [3] skip audio (--skip-audio) ===")

    audio_dur = ffprobe_duration(final_wav)
    log(f"audio duration: {audio_dur:.2f}s")

    # Provide timing.json to HyperFrames template (b-roll template reads it).
    hf_timing_json = hf_dir / "timing.json"
    shutil.copyfile(timing_json, hf_timing_json)

    # Provide transcript.json (per-word timings) to HyperFrames template.
    # This is derived from timing.json, which includes `words` when available.
    transcript_json = PROJ / f"shorts/{slug}.transcript.json"
    hf_transcript_json = hf_dir / "transcript.json"
    try:
        timing = json.loads(timing_json.read_text(encoding="utf-8"))
        words: list[dict] = []
        for ln in timing.get("lines") or []:
            if not isinstance(ln, dict):
                continue
            for w in ln.get("words") or []:
                if isinstance(w, dict) and w.get("word"):
                    words.append(
                        {
                            "word": str(w.get("word")),
                            "start": float(w.get("start")),
                            "end": float(w.get("end")),
                        }
                    )
        words.sort(key=lambda x: (x.get("start", 0.0), x.get("end", 0.0)))
        transcript_json.write_text(
            json.dumps(
                {
                    "source_timing": str(timing_json),
                    "total_duration": float(timing.get("total_duration") or 0.0),
                    "words": words,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        shutil.copyfile(transcript_json, hf_transcript_json)
    except Exception:
        # Best-effort: b-roll composition will fall back to line-level timing.
        pass

    edition = os.environ.get("THREATNOIR_EDITION", "").strip().lower()
    if edition not in ("morning", "evening"):
        edition = ""

    # === [4] mode-specific asset prep ===

    if mode == "talking-head":
        log("=== [4] talking-head asset prep (HeyGen) ===")
        talking_head.prepare_assets(
            proj_dir=PROJ,
            edition=edition,
            final_wav=final_wav,
            script_path=script,
            hf_dir=hf_dir,
            timing_json=timing_json,
            skip_heygen=bool(args.skip_heygen),
        )

    elif mode == "talking-head-hybrid":
        from modes import talking_head_hybrid

        log("=== [4] talking-head-hybrid asset prep (HeyGen + cutaways) ===")
        talking_head_hybrid.prepare_assets(
            proj_dir=PROJ,
            edition=edition,
            final_wav=final_wav,
            script_path=script,
            hf_dir=hf_dir,
            timing_json=timing_json,
            skip_heygen=bool(args.skip_heygen),
        )
    else:
        # b-roll mode: master audio is the ElevenLabs wav directly.
        log("=== [4] b-roll asset prep (master.wav + Runware visuals) ===")
        shutil.copyfile(final_wav, master_wav)
        broll.prepare_assets(
            proj_dir=PROJ,
            short_id=short_id,
            slug=slug,
            parsed_json=parsed_json,
            hf_dir=hf_dir,
            cost_json=cost_json,
            force_visuals=bool(args.force_visuals),
        )

    # === [5] hyperframes lint ===
    log("=== [5] hyperframes lint ===")
    subprocess.run(["npx", "hyperframes", "lint"], check=True, cwd=hf_dir)

    # === [6] hyperframes render ===
    log("=== [6] hyperframes render ===")
    cmd = [
        "npx",
        "hyperframes",
        "render",
        "--quality",
        "standard",
        "--output",
        str(final_mp4),
    ]

    if mode == "talking-head":
        cmd += ["--composition", "compositions/talking-head.html"]
    elif mode == "talking-head-hybrid":
        cmd += ["--composition", "compositions/talking-head-hybrid.html"]
    subprocess.run(cmd, check=True, cwd=hf_dir)

    log(f"DONE → {final_mp4}")
    log(f"  size: {final_mp4.stat().st_size / 1024 / 1024:.1f} MB")
    log(f"  duration: {ffprobe_duration(final_mp4):.2f}s")

    if args.publish:
        log("=== [7] publish to YouTube Shorts ===")
        cmd = [
            PY,
            str(PROJ / "scripts/publish_youtube.py"),
            "--script",
            str(script),
        ]
        if args.publish_privacy:
            cmd += ["--privacy", args.publish_privacy]
        subprocess.run(cmd, check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
