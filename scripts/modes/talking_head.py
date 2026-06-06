#!/usr/bin/env python3
"""Legacy talking-head mode (HeyGen Tyler avatar).

This module is intentionally self-contained so render_short.py can remain a
thin dispatcher.

Responsibilities:
- Upload master wav to HeyGen
- Render avatar video against edition-aware cyber-newsroom background
- Download avatar.mp4 to hyperframes/
- Extract master.wav from avatar.mp4 (lip-sync perfect)

Hard requirements (see LEN-1717):
- HeyGen poll timeout = 2400s
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
import re
from typing import Any

import frontmatter

from _util import brand, get_secret

HEYGEN_API = "https://api.heygen.com"
HEYGEN_UPLOAD = "https://upload.heygen.com"


def log(msg: str) -> None:
    print(f"[talking-head] {msg}", flush=True)


def http_post(
    url: str, headers: dict[str, str], body: bytes, timeout: float = 120.0
) -> dict:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def http_get(url: str, headers: dict[str, str], timeout: float = 60.0) -> dict:
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def heygen_key() -> str:
    return get_secret(env_var="HEYGEN_API_KEY", op_ref="op://Claude/heygen/api key")


def heygen_upload_audio(api_key: str, wav_path: Path) -> str:
    log(f"upload audio → HeyGen: {wav_path.name}")
    body = wav_path.read_bytes()
    headers = {"X-Api-Key": api_key, "Content-Type": "audio/x-wav"}
    res = http_post(f"{HEYGEN_UPLOAD}/v1/asset", headers, body, timeout=180.0)
    return str(res["data"]["id"])


def heygen_generate(
    api_key: str,
    *,
    avatar_id: str,
    audio_asset_id: str,
    bg_asset_id: str | None = None,
    bg_type: str = "video",
    bg_color: str = "#0a0e1a",
) -> str:
    """bg_type: 'video' (animated bg asset), 'image' (static bg asset), or 'color'
    (solid fill — needs no pre-uploaded HeyGen asset; the out-of-box OSS default).
    Falls back to a color background when no bg_asset_id is supplied."""
    if bg_type == "color" or not bg_asset_id:
        background = {"type": "color", "value": bg_color}
    elif bg_type == "video":
        background = {
            "type": "video",
            "video_asset_id": bg_asset_id,
            "fit": "cover",
            "play_style": "loop",
        }
    else:
        background = {
            "type": "image",
            "image_asset_id": bg_asset_id,
            "fit": "cover",
        }

    payload = {
        "video_inputs": [
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": avatar_id,
                    "avatar_style": "normal",
                },
                "voice": {"type": "audio", "audio_asset_id": audio_asset_id},
                "background": background,
            }
        ],
        "dimension": {"width": 720, "height": 1280},
    }
    headers = {"X-Api-Key": api_key, "Content-Type": "application/json"}
    log(f"submit HeyGen video.generate (avatar={avatar_id}, bg={background['type']})")
    res = http_post(
        f"{HEYGEN_API}/v2/video/generate",
        headers,
        json.dumps(payload).encode("utf-8"),
        timeout=60.0,
    )
    return str(res["data"]["video_id"])


def heygen_poll(api_key: str, video_id: str, timeout_s: int = 2400) -> str:
    """Poll HeyGen for completion. Default 40 min timeout."""
    headers = {"X-Api-Key": api_key}
    log(f"polling video {video_id}")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            res = http_get(
                f"{HEYGEN_API}/v1/video_status.get?video_id={video_id}",
                headers,
                timeout=30.0,
            )
            status = res["data"]["status"]
            log(f"  status={status}")
            if status == "completed":
                return str(res["data"]["video_url"])
            if status == "failed":
                raise RuntimeError(f"HeyGen render failed: {res}")
        except urllib.error.URLError as e:
            log(f"  poll error: {e}")
        time.sleep(8)
    raise TimeoutError(f"HeyGen poll timed out after {timeout_s}s")


def heygen_download(url: str, out_path: Path) -> None:
    log(f"download avatar → {out_path}")
    urllib.request.urlretrieve(url, out_path)


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


def _title_prefix_re() -> re.Pattern[str]:
    # "<Brand Name> — Short 003: Foo" is the canonical frontmatter title.
    name = re.escape(brand("BRAND_NAME", "ThreatNoir Cyber News"))
    return re.compile(
        rf"^{name}\s+[\u2014\-]\s+Short\s+\d{{3}}:\s*",
        re.IGNORECASE,
    )


def _fmt2(x: float) -> str:
    return f"{float(x):.2f}"


def _upper_compact(s: str) -> str:
    s = re.sub(r"\s+", " ", str(s or "").strip())
    return s.upper()


def _truncate(s: str, max_chars: int) -> str:
    s = str(s or "")
    if max_chars <= 0:
        return ""
    if len(s) <= max_chars:
        return s
    if max_chars <= 1:
        return "…"
    return s[: max_chars - 1].rstrip() + "…"


def _edition_badge_text(edition: str) -> str:
    return (
        "MORNING BRIEF"
        if (edition or "").strip().lower() == "morning"
        else "EVENING BRIEF"
    )


def _edition_date_text(story_date_iso: str) -> str:
    # story_date: YYYY-MM-DD
    try:
        d = date.fromisoformat(str(story_date_iso))
    except Exception:
        return ""
    mon = [
        "JAN",
        "FEB",
        "MAR",
        "APR",
        "MAY",
        "JUN",
        "JUL",
        "AUG",
        "SEP",
        "OCT",
        "NOV",
        "DEC",
    ][d.month - 1]
    return f"{d.day:02d} {mon} {d.year}".upper()


def _headline_from_title(title: str) -> str:
    t = str(title or "").strip()
    t = _title_prefix_re().sub("", t)
    return _truncate(_upper_compact(t), 60)


def _js_subs_array_literal(lines: list[dict[str, Any]]) -> str:
    items: list[str] = []
    for ln in lines:
        if not isinstance(ln, dict):
            continue
        text = str(ln.get("text") or "").strip()
        start = float(ln.get("start") or 0.0)
        dur = float(ln.get("duration") or 0.0)
        end = start + max(0.0, dur)
        items.append(
            "  { start: "
            + _fmt2(start)
            + ", end: "
            + _fmt2(end)
            + ", text: "
            + json.dumps(text, ensure_ascii=False)
            + " }"
        )
    return "[\n" + ",\n".join(items) + "\n]"


def _extract_vuln_phrase(source: str) -> str:
    s = _upper_compact(source)
    for p in [
        "HEAP BUFFER OVERFLOW",
        "STACK BUFFER OVERFLOW",
        "BUFFER OVERFLOW",
        "HEAP OVERFLOW",
        "USE-AFTER-FREE",
        "USE AFTER FREE",
        "OUT-OF-BOUNDS",
        "OUT OF BOUNDS",
        "SQL INJECTION",
        "COMMAND INJECTION",
        "DIRECTORY TRAVERSAL",
        "AUTH BYPASS",
        "RCE",
    ]:
        if p in s:
            return p.replace("USE AFTER FREE", "USE-AFTER-FREE").replace(
                "OUT OF BOUNDS", "OUT-OF-BOUNDS"
            )
    return ""


def _extract_module_phrase(source: str) -> str:
    # e.g. "in NGINX's rewrite module" -> "REWRITE MODULE"
    m = re.search(r"\b([A-Za-z0-9_\-]+)\s*'s\s+([A-Za-z0-9_\- ]+?)\s+module\b", source)
    if not m:
        return ""
    mod = _upper_compact(m.group(2))
    mod = re.sub(r"\s+", " ", mod).strip()
    return _truncate(mod + " MODULE", 26)


def _cve_line_a(meta: dict[str, Any]) -> str:
    vendors = meta.get("vendors") or []
    vendor = ""
    if isinstance(vendors, list) and vendors:
        vendor = _upper_compact(str(vendors[0]))
    source = str(meta.get("source") or "")
    mod = _extract_module_phrase(source)
    vuln = _extract_vuln_phrase(source)
    parts = [p for p in [vendor, mod, vuln] if p]
    return _truncate(" · ".join(parts), 60)


def _cve_line_b(meta: dict[str, Any], story_date_iso: str) -> str:
    vendors = meta.get("vendors") or []
    vendor = ""
    if isinstance(vendors, list) and vendors:
        vendor = _upper_compact(str(vendors[-1]))
    # Month/year only
    try:
        d = date.fromisoformat(str(story_date_iso))
        mon = [
            "JAN",
            "FEB",
            "MAR",
            "APR",
            "MAY",
            "JUN",
            "JUL",
            "AUG",
            "SEP",
            "OCT",
            "NOV",
            "DEC",
        ][d.month - 1]
        my = f"{mon} {d.year}".upper()
    except Exception:
        my = ""
    parts = [p for p in ["DISCLOSED", vendor, my] if p]
    return _truncate(" · ".join(parts), 60)


def _chyron_items(meta: dict[str, Any]) -> list[str]:
    hooks = meta.get("hooks") or []
    out: list[str] = []
    if isinstance(hooks, list):
        for h in hooks:
            if not h:
                continue
            out.append(_truncate(_upper_compact(str(h)), 30))
    # fallback if hooks empty
    if not out:
        vendors = meta.get("vendors") or []
        if isinstance(vendors, list) and vendors:
            out.append(
                _truncate(_upper_compact(" · ".join(str(v) for v in vendors if v)), 30)
            )
    return out


def _chyron_schedule(
    avatar_duration: float, items: list[str]
) -> list[tuple[float, float, str]]:
    if not items:
        return []
    # 2-3 chyrons
    n = 3 if len(items) >= 3 else 2
    # Start after the opener beat for longer clips; otherwise start early.
    base = min(4.5, max(0.8, avatar_duration * 0.12))
    # Avoid exact boundary equality between adjacent clips (HyperFrames lint can
    # treat float rounding as an overlap when end==start).
    base = min(avatar_duration, base + 0.01)
    avail = max(0.0, avatar_duration - base - 0.6)
    seg = avail / n if n else 0.0
    out: list[tuple[float, float, str]] = []
    for i in range(n):
        start = base + i * seg
        dur = max(1.6, seg)
        # Ensure adjacent chyrons never overlap on the same track.
        if i < n - 1 and dur > 0.02:
            dur -= 0.01
        # Clamp to composition
        if start + dur > avatar_duration:
            dur = max(0.0, avatar_duration - start)
        out.append((start, dur, items[i]))
    return out


def _ticker_items_html(
    *,
    edition_badge: str,
    edition_date: str,
    story_date_iso: str,
    headline: str,
    vendors: list[str],
    hooks: list[str],
    cve_number: str,
) -> str:
    def item(label: str, klass: str, text: str) -> str:
        label = _upper_compact(label)
        text = _upper_compact(text)
        return f'<span class="item">{label} <span class="{klass}">{text}</span></span>'

    items: list[str] = []
    if edition_badge or edition_date or headline:
        head = " · ".join([p for p in [edition_date, headline] if p])
        items.append(item(edition_badge or "BRIEF", "cool", head))
    if cve_number:
        items.append(item("CVE", "red", cve_number))
    if vendors:
        items.append(
            item("VENDORS", "warm", " · ".join(_upper_compact(v) for v in vendors if v))
        )
    for h in hooks[:4]:
        items.append(item("HOOK", "cool", _truncate(_upper_compact(h), 64)))
    items.append(
        item(
            "SOURCES",
            "warm",
            f"{brand('BRAND_SHORT_NAME', 'ThreatNoir').upper()} {edition_badge} · {story_date_iso}".strip(),
        )
    )
    return "\n        ".join(items)


def _pick_climax_text(meta: dict[str, Any], timing_lines: list[dict[str, Any]]) -> str:
    hooks = meta.get("hooks") or []
    if isinstance(hooks, list) and hooks:
        last = str(hooks[-1] or "")

        # Split by commas/em-dashes; pick a tight 2–4 word tail clause.
        clauses = [c.strip() for c in re.split(r",|—|–", last) if c.strip()]
        tail = clauses[-2:] if len(clauses) >= 2 else clauses
        pick = min(tail, key=lambda c: len(c.split())) if tail else last.strip()
        words = [w for w in re.split(r"\s+", pick) if w]
        if len(words) >= 4:
            out = " ".join(words[-4:])
        elif len(words) >= 3:
            out = " ".join(words[-3:])
        elif len(words) >= 2:
            out = " ".join(words[-2:])
        else:
            out = " ".join(words)
        if out:
            return _truncate(_upper_compact(out), 28)

    # Fallback: last 3 words of last spoken line.
    if timing_lines:
        txt = str(timing_lines[-1].get("text") or "")
        words = [w for w in re.split(r"\s+", txt.strip()) if w]
        if words:
            return _truncate(_upper_compact(" ".join(words[-3:])), 28)
    return ""


def _strip_template_header(html: str) -> str:
    if html.lstrip().startswith("<!-- SOURCE OF TRUTH."):
        end = html.find("-->")
        if end != -1:
            return html[end + 3 :].lstrip("\n")
    return html


def _write_talking_head_composition(
    *,
    script_path: Path,
    hyperframes_dir: Path,
    avatar_mp4: Path,
    timing_json: Path,
    edition: str,
) -> None:
    template_path = hyperframes_dir / "compositions/talking-head.html.tmpl"
    out_path = hyperframes_dir / "compositions/talking-head.html"
    if not template_path.exists():
        raise RuntimeError(f"Missing template: {template_path}")

    # Authoritative duration is the rendered avatar MP4.
    avatar_duration = round(ffprobe_duration(avatar_mp4), 2)

    post = frontmatter.load(str(script_path))
    meta = dict(post.metadata or {})

    story_date_iso = str(meta.get("story_date") or "").strip().strip('"')
    edition_meta = str(meta.get("edition") or "").strip().lower()
    edition_final = (edition or "").strip().lower() or edition_meta
    if edition_final not in ("morning", "evening"):
        edition_final = "evening"
    edition_badge = _edition_badge_text(edition_final)
    edition_date = _edition_date_text(story_date_iso)
    headline = _headline_from_title(str(meta.get("title") or ""))

    cves = meta.get("cves") or []
    cve_number = ""
    if isinstance(cves, list) and cves:
        cve_number = _upper_compact(str(cves[0]))
    cve_line_a = _cve_line_a(meta) if cve_number else ""
    cve_line_b = _cve_line_b(meta, story_date_iso) if cve_number else ""

    # Subtitle lines
    timing = json.loads(timing_json.read_text(encoding="utf-8"))
    lines = timing.get("lines") or []
    if not isinstance(lines, list):
        lines = []
    subs_literal = _js_subs_array_literal([ln for ln in lines if isinstance(ln, dict)])

    vendors = meta.get("vendors") or []
    vendors_list = [str(v) for v in vendors] if isinstance(vendors, list) else []

    # Chyrons
    hooks = meta.get("hooks") or []
    hooks_list = [str(h) for h in hooks] if isinstance(hooks, list) else []
    chyron_texts = _chyron_items(meta)
    # Ensure 2-3 chyrons (spec): synthesize a second item if needed.
    if len(chyron_texts) == 1:
        extra = ""
        if cve_number:
            extra = _truncate(_upper_compact(cve_number), 30)
        elif headline:
            extra = _truncate(_upper_compact(headline), 30)
        elif vendors_list:
            extra = _truncate(_upper_compact(vendors_list[0]), 30)
        if extra and extra != chyron_texts[0]:
            chyron_texts.append(extra)
        else:
            chyron_texts.append(chyron_texts[0])
    sched = _chyron_schedule(avatar_duration, chyron_texts)
    # Always emit 3 placeholders.
    while len(sched) < 3:
        sched.append((0.0, 0.0, ""))

    # Ticker
    ticker_html = _ticker_items_html(
        edition_badge=edition_badge,
        edition_date=edition_date,
        story_date_iso=story_date_iso,
        headline=headline,
        vendors=vendors_list,
        hooks=hooks_list,
        cve_number=cve_number,
    )

    # Climax glitch
    climax_text = _pick_climax_text(meta, [ln for ln in lines if isinstance(ln, dict)])
    climax_start = max(0.0, avatar_duration - 4.5)
    climax_dur = 1.4

    endcard_dur = 1.5
    endcard_start = max(0.0, avatar_duration - endcard_dur)

    html = template_path.read_text(encoding="utf-8")
    if "<!-- LINES_INSERT_HERE -->" not in html:
        raise RuntimeError("Template missing <!-- LINES_INSERT_HERE --> marker")

    html = _strip_template_header(html)
    derived_header = (
        "<!-- DERIVED FILE — DO NOT EDIT.\n"
        "     Generated from hyperframes/compositions/talking-head.html.tmpl by scripts/modes/talking_head.py.\n"
        "     Edit the .tmpl and re-run scripts/render_short.py to regenerate. -->\n"
    )
    html = derived_header + html

    repl = {
        "{{TOTAL_DURATION}}": _fmt2(avatar_duration),
        "{{AVATAR_DURATION}}": _fmt2(avatar_duration),
        "{{EDITION_BADGE_TEXT}}": edition_badge,
        "{{EDITION_DATE}}": edition_date,
        "{{STORY_DATE_ISO}}": story_date_iso,
        "{{STORY_HEADLINE}}": headline,
        "{{CVE_NUMBER}}": cve_number,
        "{{CVE_LINE_A}}": cve_line_a,
        "{{CVE_LINE_B}}": cve_line_b,
        "{{CVE_CARD_STYLE}}": "" if cve_number else "display:none",
        "{{CHYRON_1_TEXT}}": sched[0][2],
        "{{CHYRON_1_START}}": _fmt2(sched[0][0]),
        "{{CHYRON_1_DURATION}}": _fmt2(sched[0][1]),
        "{{CHYRON_2_TEXT}}": sched[1][2],
        "{{CHYRON_2_START}}": _fmt2(sched[1][0]),
        "{{CHYRON_2_DURATION}}": _fmt2(sched[1][1]),
        "{{CHYRON_3_TEXT}}": sched[2][2],
        "{{CHYRON_3_START}}": _fmt2(sched[2][0]),
        "{{CHYRON_3_DURATION}}": _fmt2(sched[2][1]),
        "{{TICKER_ITEMS_HTML}}": ticker_html,
        "{{CLIMAX_TEXT}}": climax_text,
        "{{CLIMAX_START}}": _fmt2(climax_start),
        "{{CLIMAX_DURATION}}": _fmt2(climax_dur),
        "{{ENDCARD_START}}": _fmt2(endcard_start),
        "{{ENDCARD_DURATION}}": _fmt2(endcard_dur),
    }
    for k, v in repl.items():
        html = html.replace(k, str(v))
    html = html.replace("<!-- LINES_INSERT_HERE -->", subs_literal)

    if "{{" in html or "}}" in html:
        raise RuntimeError(
            "Unfilled placeholders remain in generated talking-head.html"
        )
    if "LINES_INSERT_HERE" in html:
        raise RuntimeError("LINES_INSERT_HERE marker not replaced")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    log(f"wrote composition: {out_path}")


def prepare_assets(
    *,
    proj_dir: Path,
    edition: str,
    final_wav: Path,
    script_path: Path,
    hf_dir: Path,
    timing_json: Path,
    skip_heygen: bool,
) -> dict[str, Path]:
    """Ensure hyperframes/avatar.mp4 and hyperframes/master.wav exist."""
    avatar_mp4 = hf_dir / "avatar.mp4"
    master_wav = hf_dir / "master.wav"

    if not skip_heygen:
        bg_filename = (
            "cyber-newsroom-evening.heygen-asset-id"
            if edition == "evening"
            else "cyber-newsroom.heygen-asset-id"
        )
        log(f"HeyGen render (edition={edition or 'default'})")
        avatar_id = (
            (proj_dir / "characters/max_avatar_id.txt")
            .read_text()
            .splitlines()[0]
            .strip()
        )
        bg_asset_id = (
            (proj_dir / f"assets/backgrounds/{bg_filename}").read_text().strip()
        )

        hk = heygen_key()
        audio_asset = heygen_upload_audio(hk, final_wav)
        video_id = heygen_generate(
            hk,
            avatar_id=avatar_id,
            audio_asset_id=audio_asset,
            bg_asset_id=bg_asset_id,
        )
        url = heygen_poll(hk, video_id, timeout_s=2400)
        heygen_download(url, avatar_mp4)
    else:
        log("skip HeyGen (--skip-heygen)")
        if not avatar_mp4.exists():
            raise FileNotFoundError(f"--skip-heygen but {avatar_mp4} missing")

    # Extract HeyGen audio as master (sync-perfect)
    ffmpeg_extract_audio(avatar_mp4, master_wav)

    # Write a fresh HyperFrames composition from the template.
    _write_talking_head_composition(
        script_path=script_path,
        hyperframes_dir=hf_dir,
        avatar_mp4=avatar_mp4,
        timing_json=timing_json,
        edition=edition,
    )
    return {"avatar_mp4": avatar_mp4, "master_wav": master_wav}
