#!/usr/bin/env python3
"""Stock-broll mode (Pexels/Storyblocks + 1 AI hero + chyrons + chrome).

This ports the validated prototype pipeline into production as an opt-in mode:
  python3 scripts/render_short.py --mode stock-broll --script shorts/short-NNN-slug.md
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fetch_stock
from _util import (
    brand,
    ffmpeg_concat_wavs,
    ffmpeg_silence,
    ffprobe_duration,
    get_secret,
    verify_render_output,
    write_json,
)


PROJ = Path(__file__).resolve().parents[2]

END_CARD_SEC = 1.8

SHORT_NN_RE = re.compile(r"short-(\d{3})-")


def log(msg: str) -> None:
    print(f"[stock-broll] {msg}", flush=True)


def run_cmd(
    cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> None:
    log("$ " + " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, cwd=str(cwd) if cwd else None, env=env)


def run_cmd_capture(
    cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a command while capturing stdout/stderr (needed for library-hit detection)."""

    log("$ " + " ".join(str(c) for c in cmd))
    return subprocess.run(
        cmd,
        check=True,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
    )


def _has_library_hit(stderr: str) -> bool:
    for ln in (stderr or "").splitlines():
        if ln.strip().startswith("LIBRARY_HIT "):
            return True
    return False


def _library_reused_via(stderr: str) -> str | None:
    """Return reuse mechanism for a render subprocess.

    - "hash" when stderr contains LIBRARY_HIT
    - "tags" when stderr contains LIBRARY_REUSE
    """

    via = None
    for ln in (stderr or "").splitlines():
        s = ln.strip()
        if s.startswith("LIBRARY_REUSE "):
            # Prefer explicit reuse signal over generic hit.
            return "tags"
        if s.startswith("LIBRARY_HIT "):
            via = "hash"
    return via


def elevenlabs_key() -> str:
    return get_secret(
        env_var="ELEVENLABS_API_KEY",
        op_ref="op://Claude/threatnoir-podcast/elvenlabs api",
    )


def parse_short_id(script: Path) -> str:
    m = SHORT_NN_RE.search(script.name)
    if not m:
        raise ValueError(f"Cannot find short-NNN- prefix in {script.name}")
    return m.group(1)


def _append_outro_silence(in_wav: Path, out_wav: Path, outro_sec: float) -> None:
    if outro_sec <= 0:
        shutil.copyfile(in_wav, out_wav)
        return
    tmp_silence = out_wav.parent / "_outro_silence.wav"
    ffmpeg_silence(tmp_silence, outro_sec)
    ffmpeg_concat_wavs([in_wav, tmp_silence], out_wav)


def _fmt3(x: float) -> str:
    return f"{float(x):.3f}"


def _wipe_canonical_stock_shots(hf_stock_dir: Path) -> None:
    """Remove canonical per-shot MP4s so we never reuse stale clips across renders.

    Provider caches live elsewhere (e.g. assets/stock/pexels-<id>.mp4). These
    canonical files are derived artifacts for the current render only.
    """

    removed = 0
    for pat in ("shot-*.mp4", "shot-*.mp4.hf.ok"):
        for p in hf_stock_dir.glob(pat):
            try:
                p.unlink()
                removed += 1
            except FileNotFoundError:
                pass

    if removed:
        log(f"wiped {removed} canonical stock shot file(s) in {hf_stock_dir}")


def _normalize_mp4_for_hyperframes(src: Path, dst: Path) -> None:
    """Re-encode an MP4 to 30fps dense-keyframes (HyperFrames seek reliability)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-an",
            "-vf",
            "fps=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-profile:v",
            "high",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-g",
            "30",
            "-keyint_min",
            "30",
            "-sc_threshold",
            "0",
            "-movflags",
            "+faststart",
            str(dst),
        ]
    )


def _write_composition_from_template(
    *, template_path: Path, out_path: Path, total_duration: float, shots_html: str
) -> None:
    if not template_path.exists():
        raise RuntimeError(f"Missing template: {template_path}")
    html = template_path.read_text(encoding="utf-8")
    if "<!-- SHOTS_INSERT_HERE -->" not in html:
        raise RuntimeError("Template missing <!-- SHOTS_INSERT_HERE --> marker")
    html = html.replace("{{TOTAL_DURATION}}", _fmt3(total_duration))
    html = html.replace("<!-- SHOTS_INSERT_HERE -->", shots_html)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


def _shot_start_end_for_line(
    *, by_idx: dict[int, dict[str, Any]], line_index: int, audio_total: float
) -> tuple[float, float]:
    ln = by_idx.get(line_index) or {}
    start = float(ln.get("start") or 0.0)
    next_start = None
    if (line_index + 1) in by_idx:
        next_start = float(by_idx[line_index + 1].get("start") or 0.0)
    end = float(next_start) if next_start is not None else float(audio_total)
    return start, end


@dataclass
class CostItem:
    label: str
    usd: float
    estimated: bool = False
    cached: bool = False
    reused_via: str | None = None
    meta: dict[str, Any] | None = None


def _write_cost_json(
    *, cost_json: Path, short_id: str, slug: str, items: list[CostItem]
) -> None:
    cap = 0.50
    total = float(sum(i.usd for i in items))
    out = {
        "short_id": short_id,
        "slug": slug,
        "mode": "stock-broll",
        "currency": "USD",
        "cap_usd": cap,
        "total_usd": round(total, 4),
        "items": [
            {
                "label": i.label,
                "usd": round(float(i.usd), 6),
                **({"estimated": True} if i.estimated else {}),
                **({"cached": True} if i.cached else {}),
                **({"reused_via": i.reused_via} if i.reused_via else {}),
                **({"meta": i.meta} if i.meta else {}),
            }
            for i in items
        ],
    }
    if total > cap + 1e-9:
        raise RuntimeError(f"Cost cap exceeded: ${total:.4f} > ${cap:.2f}")
    write_json(cost_json, out)


def run(
    *,
    script: Path,
    force_visuals: bool = False,
    skip_audio: bool = False,
    publish: bool = False,
    publish_privacy: str | None = None,
) -> int:
    script = Path(script).resolve()
    if not script.exists():
        raise FileNotFoundError(f"script not found: {script}")

    short_id = parse_short_id(script)
    slug = script.stem

    PY = sys.executable

    parsed_json = PROJ / f"shorts/{slug}.json"
    final_wav = PROJ / f"shorts/{slug}.wav"
    timing_json = PROJ / f"shorts/{slug}.timing.json"
    final_mp4 = PROJ / f"shorts/{slug}.mp4"
    cost_json = PROJ / f"shorts/short-{short_id}.cost.json"

    # Slug-derived audio dir (prevents cross-script cache collision)
    audio_dir = PROJ / "out" / "audio" / slug

    hf_dir = PROJ / "hyperframes"
    hf_master = hf_dir / "master.wav"
    hf_timing = hf_dir / "timing.json"
    hf_manifest = hf_dir / "manifest.json"

    tmpl = hf_dir / "compositions/stock-broll.html.tmpl"
    comp = hf_dir / "compositions/stock-broll.html"

    # === [1] parse_script ===
    log("=== [1] parse script ===")
    run_cmd(
        [
            PY,
            str(PROJ / "scripts/parse_script.py"),
            "--script",
            str(script),
            "--output",
            str(parsed_json),
        ],
        cwd=PROJ,
    )

    parsed = json.loads(parsed_json.read_text(encoding="utf-8"))
    shots_cfg = parsed.get("shots")
    if not isinstance(shots_cfg, list) or not shots_cfg:
        raise RuntimeError(
            "stock-broll mode requires a YAML frontmatter `shots:` list (parsed_json.shots was empty)"
        )

    # === [2] render_audio ===
    if not skip_audio:
        log("=== [2] wipe per-script audio dir ===")
        if audio_dir.exists():
            shutil.rmtree(audio_dir)
        audio_dir.mkdir(parents=True, exist_ok=True)

        log("=== [3] render audio (ElevenLabs ANCHOR) ===")
        env = os.environ.copy()
        env["ELEVENLABS_API_KEY"] = elevenlabs_key()
        run_cmd(
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
            cwd=PROJ,
            env=env,
        )
    else:
        log("=== [3] skip audio (--skip-audio) ===")
        if not final_wav.exists() or not timing_json.exists():
            raise RuntimeError("--skip-audio requires existing final wav + timing.json")

    timing = json.loads(timing_json.read_text(encoding="utf-8"))
    lines = list(timing.get("lines") or [])
    audio_total = float(timing.get("total_duration") or 0.0)
    if audio_total <= 0:
        audio_total = ffprobe_duration(final_wav)

    total = float(audio_total) + float(END_CARD_SEC)

    # Extend audio so the end card can sit in the last END_CARD_SEC seconds.
    master_wav = PROJ / f"shorts/{slug}.master.wav"
    _append_outro_silence(final_wav, master_wav, outro_sec=END_CARD_SEC)
    hf_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(master_wav, hf_master)

    timing["total_duration"] = round(total, 3)
    write_json(hf_timing, timing)

    # === [4] assets + manifest ===
    log("=== [4] stock + hero assets ===")
    cache_dir = PROJ / "assets/cache"
    provider_stock_dir = PROJ / "assets/stock"
    hf_stock_dir = hf_dir / "stock"
    hf_ai_dir = hf_dir / "ai"
    cache_dir.mkdir(parents=True, exist_ok=True)
    provider_stock_dir.mkdir(parents=True, exist_ok=True)
    hf_stock_dir.mkdir(parents=True, exist_ok=True)
    hf_ai_dir.mkdir(parents=True, exist_ok=True)

    hf_ai_library_dir = hf_ai_dir / "library"
    hf_ai_library_dir.mkdir(parents=True, exist_ok=True)

    # Canonical stock shots are keyed only by shot number (shot-01.mp4, ...).
    # If we don't clear them, a new render can accidentally reuse yesterday's
    # clip because the normalization step is expensive and was previously gated
    # on file existence.
    _wipe_canonical_stock_shots(hf_stock_dir)

    by_idx = {int(ln.get("index") or 0): ln for ln in lines if isinstance(ln, dict)}

    # Validate and normalize shots config
    shots: list[dict[str, Any]] = []
    max_shot = 0
    hero_count = 0
    cve_count = 0
    end_count = 0
    for raw in shots_cfg:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "").strip()
        if not kind:
            continue
        shot_num = raw.get("shot")
        try:
            n = int(shot_num) if shot_num is not None else 0
        except Exception:
            n = 0
        if n <= 0:
            # Allow omitting shot number for end card; we'll assign later.
            if kind != "card_end":
                raise RuntimeError(
                    f"shot entries must include integer `shot` (bad entry: {raw})"
                )
        else:
            max_shot = max(max_shot, n)

        if kind == "ai_hero":
            hero_count += 1
        if kind == "card_cve":
            cve_count += 1
        if kind == "card_end":
            end_count += 1

        shots.append(dict(raw))

    if hero_count != 1:
        raise RuntimeError(
            f"stock-broll requires exactly 1 ai_hero shot (found {hero_count})"
        )
    if cve_count > 1:
        raise RuntimeError(
            f"stock-broll supports at most 1 card_cve shot (found {cve_count})"
        )
    if end_count == 0:
        shots.append({"shot": max_shot + 1, "kind": "card_end"})
        max_shot += 1
    else:
        for s in shots:
            if str(s.get("kind") or "") == "card_end":
                if not s.get("shot"):
                    s["shot"] = max_shot + 1
                    max_shot += 1

    shots_out: list[dict[str, Any]] = []
    shots_html_parts: list[str] = []

    # Estimated cost model (hard cap $0.50)
    keyframe_cost = CostItem(
        label="openrouter.gemini.keyframe", usd=0.04, estimated=True
    )
    cost_items: list[CostItem] = [
        CostItem(label="pexels", usd=0.0),
        CostItem(label="storyblocks", usd=0.0),
        keyframe_cost,
        CostItem(label="elevenlabs.tts", usd=0.05, estimated=True),
    ]
    runware_cost_usd = None
    hero_cached = False
    hero_reused_via: str | None = None

    # Track indices: keep videos low, cards higher.
    track_next = 1

    for shot in shots:
        kind = str(shot.get("kind") or "").strip()
        shot_num = int(shot.get("shot") or 0)

        if kind == "card_end":
            end_title = brand("BRAND_SHORT_NAME", "ThreatNoir").upper()
            start = max(0.0, float(total) - float(END_CARD_SEC))
            duration = float(END_CARD_SEC)
            entry = {
                "shot": shot_num,
                "kind": "card_end",
                "start": round(start, 3),
                "duration": round(duration, 3),
            }
            shots_out.append(entry)
            shots_html_parts.append(
                (
                    f'    <div id="cardEnd" class="clip" data-shot="{shot_num}" '
                    f'data-start="{_fmt3(start)}" data-duration="{_fmt3(duration)}" '
                    f'data-track-index="11">\n'
                    '      <div class="endInner">\n'
                    f'        <div class="endTitle">{end_title}</div>\n'
                    '        <div class="endSub"><span class="accent">//</span> CYBER NEWS</div>\n'
                    "      </div>\n"
                    "    </div>"
                )
            )
            continue

        line_index = int(shot.get("line_index") or 0)
        if line_index <= 0 or line_index not in by_idx:
            raise RuntimeError(
                f"shot {shot_num} references invalid line_index={line_index}"
            )

        start, end = _shot_start_end_for_line(
            by_idx=by_idx,
            line_index=line_index,
            audio_total=audio_total,
        )
        duration = max(0.1, float(end) - float(start))

        if kind == "stock":
            query = str(shot.get("query") or "").strip()
            chyron = str(shot.get("chyron") or "").strip()
            if not query:
                raise RuntimeError(f"stock shot {shot_num} missing query")
            if not chyron:
                raise RuntimeError(f"stock shot {shot_num} missing chyron")

            res = fetch_stock.download_first_available(
                query=query,
                out_dir=provider_stock_dir,
                cache_dir=cache_dir,
                storyblocks_counter_path=cache_dir / "storyblocks_downloads.json",
                storyblocks_max_total=5,
                storyblocks_max_this_run=3,
                dry_run=False,
            )
            provider_path = Path(str(res["path"])).resolve()
            canonical = hf_stock_dir / f"shot-{shot_num:02d}.mp4"
            # Always overwrite the canonical file for this render; never gate on
            # existence (otherwise prior renders can leak in).
            _normalize_mp4_for_hyperframes(provider_path, canonical)

            entry = {
                "shot": shot_num,
                "kind": "stock",
                "start": round(start, 3),
                "duration": round(duration, 3),
                "path": f"stock/{canonical.name}",
                "chyron": chyron,
                "query": query,
                "provider": str(res.get("provider") or ""),
            }
            shots_out.append(entry)
            shots_html_parts.append(
                (
                    f'    <video id="shot{shot_num}" class="clip full" data-shot="{shot_num}" '
                    f'data-shot-kind="stock" data-start="{_fmt3(start)}" '
                    f'data-duration="{_fmt3(duration)}" data-track-index="{track_next}" '
                    f'src="{entry["path"]}" muted playsinline></video>'
                )
            )
            track_next += 1
            continue

        if kind == "ai_hero":
            chyron = str(shot.get("chyron") or "").strip()
            keyframe_prompt = str(shot.get("keyframe_prompt") or "").strip()
            hero_motion = str(shot.get("hero_motion") or "").strip()
            raw_tags = shot.get("tags") or []
            tags_list: list[str] = []
            if isinstance(raw_tags, list):
                for t in raw_tags:
                    ts = str(t).strip().lower()
                    if ts and ts not in tags_list:
                        tags_list.append(ts)
            tags_csv = ",".join(tags_list)
            if not chyron:
                raise RuntimeError("ai_hero shot missing chyron")
            if not keyframe_prompt:
                raise RuntimeError("ai_hero shot missing keyframe_prompt")
            if not hero_motion:
                raise RuntimeError("ai_hero shot missing hero_motion")

            ai_cache = PROJ / "assets/stock-broll" / slug / "ai"
            ai_cache.mkdir(parents=True, exist_ok=True)
            keyframe_cache = ai_cache / "keyframe.jpg"
            hero_cache = ai_cache / "hero.mp4"

            if force_visuals or not keyframe_cache.exists():
                res = run_cmd_capture(
                    [
                        PY,
                        str(PROJ / "scripts/render_keyframe.py"),
                        "--library-dir",
                        str(hf_ai_library_dir),
                        "--out",
                        str(keyframe_cache),
                        "--prompt",
                        keyframe_prompt,
                        "--tags",
                        tags_csv,
                        "--source-short",
                        slug,
                    ],
                    cwd=PROJ,
                )
                if res.stdout:
                    sys.stdout.write(res.stdout)
                if res.stderr:
                    sys.stderr.write(res.stderr)
                via = _library_reused_via(res.stderr)
                if via:
                    keyframe_cost.usd = 0.0
                    keyframe_cost.estimated = False
                    keyframe_cost.cached = True
                    keyframe_cost.reused_via = via

            if force_visuals or not hero_cache.exists():
                res = run_cmd_capture(
                    [
                        PY,
                        str(PROJ / "scripts/render_hero_clip.py"),
                        "--keyframe",
                        str(keyframe_cache),
                        "--library-dir",
                        str(hf_ai_library_dir),
                        "--out",
                        str(hero_cache),
                        "--prompt",
                        hero_motion,
                        "--tags",
                        tags_csv,
                        "--source-short",
                        slug,
                    ],
                    cwd=PROJ,
                )
                if res.stdout:
                    sys.stdout.write(res.stdout)
                if res.stderr:
                    sys.stderr.write(res.stderr)
                via = _library_reused_via(res.stderr)
                if via:
                    hero_cached = True
                    hero_reused_via = via

            # Copy into HyperFrames-served dir
            shutil.copyfile(keyframe_cache, hf_ai_dir / "keyframe.jpg")
            shutil.copyfile(hero_cache, hf_ai_dir / "hero.mp4")

            # Best-effort: read Runware cost from hero.mp4.meta.json
            meta_path = hero_cache.with_suffix(hero_cache.suffix + ".meta.json")
            if meta_path.exists():
                try:
                    runware_cost_usd = float(
                        json.loads(meta_path.read_text(encoding="utf-8")).get("cost")
                        or 0.0
                    )
                except Exception:
                    runware_cost_usd = None

            entry = {
                "shot": shot_num,
                "kind": "ai_hero",
                "start": round(start, 3),
                "duration": round(duration, 3),
                "path": "ai/hero.mp4",
                "chyron": chyron,
            }
            shots_out.append(entry)
            shots_html_parts.append(
                (
                    f'    <video id="hero" class="clip full" data-shot="{shot_num}" '
                    f'data-shot-kind="ai_hero" data-start="{_fmt3(start)}" '
                    f'data-duration="{_fmt3(duration)}" data-track-index="{track_next}" '
                    f'src="{entry["path"]}" muted playsinline></video>'
                )
            )
            track_next += 1
            continue

        if kind == "card_cve":
            cve = str(shot.get("cve") or "").strip()
            line_a = str(shot.get("line_a") or "").strip()
            line_b = str(shot.get("line_b") or "").strip()
            if not cve:
                raise RuntimeError("card_cve missing cve")

            entry = {
                "shot": shot_num,
                "kind": "card_cve",
                "start": round(start, 3),
                "duration": round(duration, 3),
                "cve": cve,
                "line_a": line_a,
                "line_b": line_b,
            }
            shots_out.append(entry)
            shots_html_parts.append(
                (
                    f'    <div id="cardCve" class="clip" data-shot="{shot_num}" '
                    f'data-start="{_fmt3(start)}" data-duration="{_fmt3(duration)}" '
                    f'data-track-index="10">\n'
                    '      <div class="cveInner">\n'
                    f'        <div class="cveNumber" id="cveNumber">{cve}</div>\n'
                    '        <div class="cveMeta">\n'
                    f'          <div id="cveLineA">{line_a}</div>\n'
                    '          <div class="sep"></div>\n'
                    f'          <div id="cveLineB">{line_b}</div>\n'
                    "        </div>\n"
                    "      </div>\n"
                    "    </div>"
                )
            )
            continue

        raise RuntimeError(f"Unknown shot kind: {kind}")

    # Finalize cost items
    runware_cost = CostItem(
        label="runware.seedance.hero",
        usd=float(runware_cost_usd) if runware_cost_usd is not None else 0.24,
        estimated=runware_cost_usd is None,
    )
    if hero_cached:
        runware_cost.usd = 0.0
        runware_cost.estimated = False
        runware_cost.cached = True
        runware_cost.reused_via = hero_reused_via or "hash"
    cost_items.append(runware_cost)
    _write_cost_json(
        cost_json=cost_json, short_id=short_id, slug=slug, items=cost_items
    )

    manifest = {
        "format": "cyber-news-shorts.stock-broll.manifest.v1",
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "audio": "master.wav",
        "audio_total": round(float(audio_total), 3),
        "total_duration": round(float(total), 3),
        "shots": shots_out,
    }
    write_json(hf_manifest, manifest)

    # === [4.5] build HyperFrames composition HTML (must be parse-time correct) ===
    log("=== [4.5] build stock-broll composition ===")
    shots_html = "\n".join(shots_html_parts) + "\n"
    _write_composition_from_template(
        template_path=tmpl,
        out_path=comp,
        total_duration=total,
        shots_html=shots_html,
    )

    # === [5] hyperframes lint + render ===
    log("=== [5] hyperframes lint ===")
    # The lint CLI only accepts a directory and lints every HTML in
    # hyperframes/, which includes the unrelated b-roll index.html (a
    # different mode's template) whose pre-existing errors would otherwise
    # fail every stock-broll render. Run lint in JSON mode and only fail the
    # build on error-level findings attributed to the stock-broll composition
    # we just generated.
    lint_res = subprocess.run(
        ["npx", "hyperframes", "lint", "--json"],
        cwd=hf_dir,
        capture_output=True,
        text=True,
    )
    # Always surface the human-readable summary in logs.
    subprocess.run(["npx", "hyperframes", "lint"], cwd=hf_dir)

    stock_errors: list[dict] = []
    try:
        findings = json.loads(lint_res.stdout)
        if isinstance(findings, dict):
            findings = findings.get("findings") or findings.get("results") or []
        for f in findings:
            if not isinstance(f, dict):
                continue
            severity = str(f.get("severity") or f.get("level") or "").lower()
            target = str(f.get("file") or f.get("path") or f.get("composition") or "")
            if severity in ("error", "err") and "stock-broll.html" in target:
                stock_errors.append(f)
    except (json.JSONDecodeError, TypeError):
        # If JSON parsing fails, fall back to strict behavior on our file only.
        if lint_res.returncode != 0 and "stock-broll.html" in (
            lint_res.stdout + lint_res.stderr
        ):
            raise subprocess.CalledProcessError(
                lint_res.returncode, "npx hyperframes lint --json"
            )

    if stock_errors:
        for f in stock_errors:
            log(f"LINT ERROR (stock-broll): {f}")
        raise subprocess.CalledProcessError(1, "npx hyperframes lint --json")
    log("lint: no error-level findings in compositions/stock-broll.html")

    log("=== [6] hyperframes render ===")
    out_cmd = [
        "npx",
        "hyperframes",
        "render",
        "--quality",
        "standard",
        "--composition",
        "compositions/stock-broll.html",
        "--output",
        str(final_mp4),
    ]
    subprocess.run(out_cmd, check=True, cwd=hf_dir)

    log(f"DONE → {final_mp4}")
    log(f"  size: {final_mp4.stat().st_size / 1024 / 1024:.1f} MB")
    log(f"  duration: {ffprobe_duration(final_mp4):.2f}s")

    # Post-render quality gate — refuse to publish a valid-but-broken (all-black /
    # truncated) render. Raises RenderQualityError and quarantines the file.
    qm = verify_render_output(final_mp4)
    log(f"  quality gate OK: mean_luma={qm.get('mean_luma')} bytes={qm.get('bytes')}")

    if publish:
        log("=== [7] publish to YouTube Shorts ===")
        cmd = [
            PY,
            str(PROJ / "scripts/publish_youtube.py"),
            "--script",
            str(script),
        ]
        if publish_privacy:
            cmd += ["--privacy", str(publish_privacy)]
        subprocess.run(cmd, check=True)

    return 0
