#!/usr/bin/env python3
"""Render per-line audio via ElevenLabs, mux into final.wav, emit timing.json.

Per-line behavior:
- Voice ID resolved per speaker.
- AI in Scene 3 (rogue) uses elevated style for menace.
- INTRO in Scene 0 (intro) gets a distorted post-processing pass (pitch down + light delay).
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from _util import get_secret

API_BASE = "https://api.elevenlabs.io/v1"
MODEL = "eleven_multilingual_v2"


def http_post_json(
    url: str, headers: dict[str, str], body: dict, timeout: int = 60
) -> bytes:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            body_resp = (
                e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            )
            transient = e.code in (429, 500, 502, 503, 504)
            if transient and attempt < 4:
                wait = 2**attempt
                print(
                    f"  retry {attempt + 1}/5 after {wait}s (HTTP {e.code}): {body_resp[:200]}",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            raise RuntimeError(f"ElevenLabs HTTP {e.code}: {body_resp[:500]}")
    raise RuntimeError("ElevenLabs: exhausted retries")


def voice_settings_for(speaker: str, scene_number: int) -> dict:
    """Per-line voice settings — adjust style/stability for tone shifts."""
    if speaker == "ANCHOR":
        # Nathaniel as dry-sarcastic cyber news anchor
        return {
            "stability": 0.30,
            "similarity_boost": 0.75,
            "style": 0.55,
            "use_speaker_boost": True,
        }
    if speaker == "INTRO":
        return {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.20,
            "use_speaker_boost": True,
        }
    if speaker == "AI":
        if scene_number == 3:
            return {
                "stability": 0.55,
                "similarity_boost": 0.85,
                "style": 0.55,
                "use_speaker_boost": True,
            }
        return {
            "stability": 0.75,
            "similarity_boost": 0.85,
            "style": 0.05,
            "use_speaker_boost": True,
        }
    return {
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0.15,
        "use_speaker_boost": True,
    }


def _alignment_seconds(alignment: dict) -> tuple[list[str], list[float], list[float]]:
    """Return (characters, start_s, end_s) in seconds from an ElevenLabs alignment object."""
    chars = alignment.get("characters")
    if not isinstance(chars, list):
        return [], [], []
    chars = [str(c) for c in chars]

    if isinstance(alignment.get("character_start_times_seconds"), list) and isinstance(
        alignment.get("character_end_times_seconds"), list
    ):
        s = [float(x) for x in alignment["character_start_times_seconds"]]
        e = [float(x) for x in alignment["character_end_times_seconds"]]
        return chars, s, e

    # Some SDKs/proxies expose ms-based fields.
    if isinstance(alignment.get("char_start_times_ms"), list) and isinstance(
        alignment.get("char_end_times_ms"), list
    ):
        s = [float(x) / 1000.0 for x in alignment["char_start_times_ms"]]
        e = [float(x) / 1000.0 for x in alignment["char_end_times_ms"]]
        return chars, s, e
    return [], [], []


_TRIM_WORD_RE = re.compile(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$")


def words_from_alignment(
    *,
    alignment: dict | None,
    text: str,
    line_start_s: float,
    line_duration_s: float,
) -> list[dict]:
    """Build word-level timings for a single line.

    Returns list of {word, start, end} in absolute seconds (relative to full master).
    """
    # Alignment path (preferred)
    if alignment:
        chars, start_s, end_s = _alignment_seconds(alignment)
        if chars and start_s and end_s and len(chars) == len(start_s) == len(end_s):
            out: list[dict] = []
            i = 0
            n = len(chars)
            while i < n:
                if chars[i].isspace():
                    i += 1
                    continue
                j = i
                while j + 1 < n and not chars[j + 1].isspace():
                    j += 1
                raw = "".join(chars[i : j + 1])
                w = _TRIM_WORD_RE.sub("", raw)
                if w:
                    ws = float(start_s[i])
                    we = float(end_s[j])
                    if we <= ws:
                        we = ws + 0.02
                    out.append(
                        {
                            "word": w,
                            "start": round(line_start_s + ws, 3),
                            "end": round(line_start_s + we, 3),
                        }
                    )
                i = j + 1
            return out

    # Fallback: approximate timings from line duration.
    words = [w for w in re.split(r"\s+", (text or "").strip()) if w]
    if not words:
        return []
    cleaned = [_TRIM_WORD_RE.sub("", w) for w in words]
    cleaned = [w for w in cleaned if w]
    if not cleaned:
        return []

    weights = [max(1, len(w)) for w in cleaned]
    total_w = float(sum(weights))
    t = float(line_start_s)
    out2: list[dict] = []
    for w, wt in zip(cleaned, weights, strict=False):
        frac = float(wt) / total_w
        dur = max(0.06, line_duration_s * frac)
        out2.append({"word": w, "start": round(t, 3), "end": round(t + dur, 3)})
        t += dur
    # Clamp final end to line duration to avoid drift.
    if out2:
        out2[-1]["end"] = round(
            max(out2[-1]["start"] + 0.02, line_start_s + line_duration_s), 3
        )
    return out2


def render_line_tts(
    api_key: str,
    voice_id: str,
    text: str,
    settings: dict,
    out_mp3: Path,
) -> dict | None:
    """Render one line of TTS and (best-effort) return char-level alignment.

    We prefer ElevenLabs' `with-timestamps` endpoint so we can derive per-word timings.
    Falls back to the legacy audio-only endpoint if timestamps are unavailable.
    """
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    body = {"text": text, "model_id": MODEL, "voice_settings": settings}

    # Preferred: JSON response with audio_base64 + alignment
    try:
        url = f"{API_BASE}/text-to-speech/{voice_id}/with-timestamps"
        resp = http_post_json(url, headers, body)
        data = json.loads(resp.decode("utf-8", "replace"))
        audio_b64 = str(data.get("audio_base64") or "").strip()
        if not audio_b64:
            raise RuntimeError("missing audio_base64")
        audio_bytes = base64.b64decode(audio_b64)
        if len(audio_bytes) < 1024:
            raise RuntimeError(
                f"Suspiciously small decoded audio ({len(audio_bytes)} bytes)"
            )
        out_mp3.write_bytes(audio_bytes)

        alignment = data.get("normalized_alignment") or data.get("alignment")
        return alignment if isinstance(alignment, dict) else None
    except Exception as e:
        print(
            f"  warn: timestamps unavailable, falling back to audio-only: {e}",
            file=sys.stderr,
        )

    # Fallback: raw audio bytes
    url2 = f"{API_BASE}/text-to-speech/{voice_id}"
    audio_bytes2 = http_post_json(url2, headers, body)
    if len(audio_bytes2) < 1024:
        raise RuntimeError(
            f"Suspiciously small response ({len(audio_bytes2)} bytes) for: {text[:60]}"
        )
    out_mp3.write_bytes(audio_bytes2)
    return None


def ffmpeg_to_wav(mp3_path: Path, wav_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(mp3_path),
            "-ac",
            "1",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s16le",
            str(wav_path),
        ],
        check=True,
    )


def ffmpeg_distort_intro(in_wav: Path, out_wav: Path) -> None:
    """Distort treatment for the cold-open intro: down-pitch + slight delay tail."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(in_wav),
            "-af",
            # asetrate down (pitch lower), atempo back to keep duration, light reverb
            "asetrate=44100*0.92,aresample=44100,atempo=1.087,"
            "aecho=0.7:0.85:60:0.45,"
            "highpass=f=80,lowpass=f=6500",
            "-ac",
            "1",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s16le",
            str(out_wav),
        ],
        check=True,
    )


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(out.stdout.strip() or 0.0)


def silence_wav(out_path: Path, dur: float) -> None:
    if dur <= 0:
        dur = 0.01
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=mono:sample_rate=44100",
            "-t",
            f"{dur:.3f}",
            "-c:a",
            "pcm_s16le",
            str(out_path),
        ],
        check=True,
    )


def concat_wavs(parts: list[Path], out_path: Path) -> None:
    list_file = out_path.parent / "_concat_list.txt"
    list_file.write_text("\n".join(f"file '{p.resolve()}'" for p in parts) + "\n")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c:a",
            "pcm_s16le",
            str(out_path),
        ],
        check=True,
    )
    list_file.unlink(missing_ok=True)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--parsed", default="pilot/parsed.json")
    p.add_argument("--out-dir", default="pilot/audio")
    p.add_argument("--final", default="pilot/final.wav")
    p.add_argument("--timing", default="pilot/timing.json")
    p.add_argument("--intro-voice-id-file", default="voices/intro_voice_id.txt")
    p.add_argument("--ai-voice-id-file", default="voices/ai_assistant_voice_id.txt")
    p.add_argument("--anchor-voice-id-file", default="voices/max_voice_id.txt")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    try:
        api_key = get_secret(
            env_var="ELEVENLABS_API_KEY",
            op_ref="op://Claude/threatnoir-podcast/elvenlabs api",
        )
    except Exception:
        sys.exit("ELEVENLABS_API_KEY not set")

    def _read_first_line(path_str: str) -> str:
        return Path(path_str).read_text().splitlines()[0].strip()

    voice_ids = {}
    if Path(args.anchor_voice_id_file).exists():
        voice_ids["ANCHOR"] = _read_first_line(args.anchor_voice_id_file)
    if Path(args.intro_voice_id_file).exists():
        voice_ids["INTRO"] = _read_first_line(args.intro_voice_id_file)
    if Path(args.ai_voice_id_file).exists():
        voice_ids["AI"] = _read_first_line(args.ai_voice_id_file)

    parsed = json.loads(Path(args.parsed).read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    lines_dir = out_dir / "lines"
    lines_dir.mkdir(exist_ok=True)
    pauses_dir = out_dir / "pauses"
    pauses_dir.mkdir(exist_ok=True)

    timing: list[dict] = []
    parts_for_concat: list[Path] = []
    cum_t = 0.0

    for ln in parsed["lines"]:
        idx = ln["index"]
        speaker = ln["speaker"]
        scene_n = ln["scene_number"]
        text = ln["text"]

        voice_id = voice_ids[speaker]
        settings = voice_settings_for(speaker, scene_n)

        slug = speaker.lower().replace(".", "").replace(" ", "_")
        mp3_path = lines_dir / f"{idx:03d}_{slug}.mp3"
        wav_path = lines_dir / f"{idx:03d}_{slug}.wav"
        align_path = lines_dir / f"{idx:03d}_{slug}.alignment.json"

        alignment: dict | None = None

        if args.force or not wav_path.exists():
            print(
                f"  TTS line {idx} ({speaker}, scene {scene_n}): {text[:60]}",
                file=sys.stderr,
            )
            alignment = render_line_tts(api_key, voice_id, text, settings, mp3_path)
            if alignment:
                align_path.write_text(
                    json.dumps(alignment, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            ffmpeg_to_wav(mp3_path, wav_path)
            # Distort treatment for Scene 0 INTRO lines (intro voice)
            if speaker == "INTRO" and scene_n == 0:
                distorted = lines_dir / f"{idx:03d}_{slug}_distorted.wav"
                ffmpeg_distort_intro(wav_path, distorted)
                wav_path = distorted
            else:
                pass
        else:
            print(f"  cached line {idx}", file=sys.stderr)
            if align_path.exists():
                try:
                    alignment = json.loads(align_path.read_text(encoding="utf-8"))
                    if not isinstance(alignment, dict):
                        alignment = None
                except Exception:
                    alignment = None
            if speaker == "INTRO" and scene_n == 0:
                d = lines_dir / f"{idx:03d}_{slug}_distorted.wav"
                if d.exists():
                    wav_path = d

        line_start = float(cum_t)
        dur = probe_duration(wav_path)
        words = words_from_alignment(
            alignment=alignment,
            text=text,
            line_start_s=line_start,
            line_duration_s=float(dur),
        )
        timing.append(
            {
                "index": idx,
                "scene_number": scene_n,
                "speaker": speaker,
                "text": text,
                "start": round(cum_t, 3),
                "duration": round(dur, 3),
                "pause_after_sec": float(ln["pause_after_sec"]),
                "words": words,
            }
        )
        parts_for_concat.append(wav_path)
        cum_t += dur

        # Pause after the line
        pause = float(ln["pause_after_sec"])
        if pause > 0:
            pause_path = pauses_dir / f"after_{idx:03d}.wav"
            silence_wav(pause_path, pause)
            parts_for_concat.append(pause_path)
            cum_t += pause

    # Mux to final.wav
    Path(args.final).parent.mkdir(parents=True, exist_ok=True)
    concat_wavs(parts_for_concat, Path(args.final))
    final_dur = probe_duration(Path(args.final))

    # Emit timing.json
    out_timing = {
        "source_script": parsed["source_path"],
        "total_duration": round(final_dur, 3),
        "scenes": parsed["scenes"],
        "lines": timing,
        "speakers": parsed["speakers"],
    }
    Path(args.timing).write_text(
        json.dumps(out_timing, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nfinal: {args.final} ({final_dur:.2f}s, {len(parts_for_concat)} segments)")
    print(f"timing: {args.timing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
