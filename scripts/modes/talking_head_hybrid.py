#!/usr/bin/env python3
"""Talking-head HYBRID mode (HeyGen Tyler + Pexels cutaways).

Keeps Tyler's voice continuous (HeyGen audio is still the master). Tyler may
shrink into a bottom-right picture-in-picture for the main story section while
cutaways fade in/out independently.

Template source-of-truth: hyperframes/compositions/talking-head-hybrid.html.tmpl
Derived composition:       hyperframes/compositions/talking-head-hybrid.html
"""

from __future__ import annotations

import json
import re
import html as _html
from pathlib import Path
from typing import Any

import frontmatter

import fetch_stock
from _util import download_file
from modes import stock_broll, talking_head


_POWER_WORD_PATTERNS = [
    re.compile(r"^\d{4}$"),  # 4-digit years (2018, 2026)
    re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE),  # CVE IDs
    re.compile(r"^\d{1,3}[KMB]?\+?$"),  # numeric magnitudes (1M, 25K)
]

_POWER_WORD_DICT = {
    "million",
    "billion",
    "thousand",
    "hundred",
    "hijacked",
    "breached",
    "exploited",
    "compromised",
    "leaked",
    "stolen",
    "bypassed",
    "patched",
    "disclosed",
    "exposed",
    "abused",
    "weaponized",
    "ransomware",
    "botnet",
    "backdoor",
    "exploit",
    "vulnerability",
    "flaw",
    "attacker",
    "victim",
    "incident",
}

# Stop words: NEVER highlight even if producer brackets them, even if they
# happen to match the auto-detected list. Common articles, generic verbs,
# greeting words, and weak nouns that don't carry story meaning.
_HIGHLIGHT_STOPWORDS = {
    # articles + pronouns
    "the", "a", "an", "this", "that", "these", "those", "it", "its",
    "i", "you", "we", "they", "he", "she", "him", "her", "them",
    # prepositions + conjunctions
    "of", "for", "in", "on", "at", "to", "and", "or", "but", "with", "by",
    "from", "as", "if", "so", "is", "are", "was", "were", "be", "been",
    "being", "do", "does", "did", "have", "has", "had", "than", "then",
    "into", "onto", "over", "under", "out", "up", "down",
    # weak verbs / generic nouns / greetings
    "good", "evening", "morning", "night", "today", "tonight", "yesterday",
    "device", "thing", "stuff", "way", "people", "person",
    "gets", "got", "get", "give", "gave", "make", "made", "take", "took",
    "go", "went", "come", "came", "say", "said", "see", "saw",
    "now", "then", "here", "there", "when", "where", "how", "why",
    "surprised", "ready", "fine", "old", "new",
}


def log(msg: str) -> None:
    print(f"[talking-head-hybrid] {msg}", flush=True)


def _fmt3(x: float) -> str:
    return f"{float(x):.3f}"


def _load_transcript_words(script_path: Path) -> list[dict[str, Any]]:
    """Load per-word Whisper timings from <slug>.transcript.json.

    Returns [] if file missing (fallback to no per-word subs; the JS will just
    render nothing inside the subtitle window).
    """

    transcript = script_path.with_suffix(".transcript.json")
    if not transcript.exists():
        return []
    try:
        data = json.loads(transcript.read_text(encoding="utf-8"))
    except Exception:
        return []
    words = data.get("words") or []
    return [w for w in words if isinstance(w, dict) and "start" in w and "word" in w]


def _highlight_word_set(
    meta: dict, transcript_words: list[dict] | None = None
) -> list[str]:
    """Extract words for yellow <mark> highlighting.

    Sources (deduplicated, preserves insertion order):
    1. Producer-bracketed [word] markup in subtitles: (authoritative)
    2. Auto-detected power words from the transcript (years, CVEs, magnitudes,
       small dictionary of cyber-news action verbs / outcome words)
    """

    out: list[str] = []
    seen: set[str] = set()

    def add(w: str) -> None:
        # Lowercase for case-insensitive matching against Whisper word case.
        wl = w.lower() if w else ""
        # Drop stop words even if producer brackets them — "THE", "GOOD",
        # "EVENING", "DEVICE" shouldn't yellow-highlight.
        if wl and wl not in seen and wl not in _HIGHLIGHT_STOPWORDS:
            seen.add(wl)
            out.append(wl)

    # 1. Producer-authored brackets in subtitles list
    subs = meta.get("subtitles") or []
    for s in subs:
        if not isinstance(s, dict):
            continue
        txt = str(s.get("text") or "")
        for m in re.finditer(r"\[([^\[\]]+)\]", txt):
            for w in m.group(1).split():
                add(w)

    # 2. Auto-detected power words from transcript
    if transcript_words:
        for w_obj in transcript_words:
            word = str(w_obj.get("word") or "").strip()
            if not word:
                continue
            bare = re.sub(r"[.,;:!?\"']+$", "", word)
            if not bare:
                continue
            if any(p.match(bare) for p in _POWER_WORD_PATTERNS):
                add(word)
                continue
            if bare.lower() in _POWER_WORD_DICT:
                add(word)
    return out


def _build_words_array_literal(words: list[dict[str, Any]]) -> str:
    """Emit per-word objects as a JS array literal (no HTML conversion).

    JS-side handles uppercase + yellow-mark wrapping at runtime.
    """

    items: list[str] = []
    for w in words:
        try:
            start = float(w.get("start") or 0.0)
            end = float(w.get("end") or (start + 0.3))
            word = str(w.get("word") or "").strip()
        except Exception:
            continue
        if not word:
            continue
        items.append(
            f"{{ word: {json.dumps(word, ensure_ascii=False)}, "
            f"start: {start:.3f}, end: {end:.3f} }}"
        )
    return "[" + ", ".join(items) + "]"


def _normalize_opener_text(opener_text: Any) -> list[str]:
    """Normalize opener_text to 0-2 uppercase lines, each capped to 4 words."""

    items: list[str] = []
    if isinstance(opener_text, str):
        items = [opener_text]
    elif isinstance(opener_text, list):
        items = [str(x) for x in opener_text]

    items = [str(s or "").strip() for s in items]
    items = [s for s in items if s]
    if not items:
        return []

    if len(items) > 2:
        log("WARN: opener_text has >2 lines; truncating to first 2")
        items = items[:2]

    out: list[str] = []
    for i, raw in enumerate(items):
        words = [w for w in re.split(r"\s+", raw.strip()) if w]
        if len(words) > 4:
            log(f"WARN: opener_text line {i + 1} has >4 words; truncating")
            words = words[:4]
        s = " ".join(words)
        out.append(talking_head._upper_compact(s))
    return [s for s in out if s]


def _opener_text_html(lines: list[str]) -> str:
    if not lines:
        return ""
    parts: list[str] = []
    for i, ln in enumerate(lines[:2]):
        klass = ' class="accent"' if i == 1 and len(lines) >= 2 else ""
        parts.append(f"<div{klass}>{_html.escape(ln)}</div>")
    return "".join(parts)


def _climax_words_html(climax_text: str) -> str:
    words = [w for w in re.split(r"\s+", str(climax_text or "").strip()) if w]
    if len(words) > 4:
        log("WARN: climax text has >4 words; truncating")
        words = words[:4]
    return "".join(f'<div class="word">{_html.escape(w)}</div>' for w in words if w)


def _pexels_download_top(*, query: str, out_dir: Path, cache_dir: Path) -> Path:
    """Download (or reuse cached) top Pexels portrait-ish video for query."""

    results = fetch_stock.search_pexels(query=query, per_page=5, cache_dir=cache_dir)
    if not results:
        raise RuntimeError(f"No Pexels results for query: {query}")
    top = results[0]
    out_path = out_dir / f"pexels-{top['id']}.mp4"
    if out_path.exists():
        return out_path
    download_file(str(top["url"]), out_path)
    return out_path


def _pexels_download_min_duration(
    *, query: str, out_dir: Path, cache_dir: Path, min_seconds: float
) -> Path:
    """Download (or reuse cached) first Pexels result whose MP4 is >= min_seconds."""

    results = fetch_stock.search_pexels(query=query, per_page=10, cache_dir=cache_dir)
    if not results:
        raise RuntimeError(f"No Pexels results for query: {query}")

    first_path: Path | None = None
    for i, r in enumerate(results):
        out_path = out_dir / f"pexels-{r['id']}.mp4"
        if not out_path.exists():
            download_file(str(r["url"]), out_path)
        if first_path is None:
            first_path = out_path
        try:
            dur = float(talking_head.ffprobe_duration(out_path))
        except Exception:
            dur = 0.0
        if dur >= float(min_seconds):
            return out_path

        log(
            f"WARN: pexels-{r['id']} duration {dur:.1f}s < {min_seconds:.1f}s; trying next"
        )
        # Keep at most a couple of attempts to avoid long download loops.
        if i >= 3:
            break

    if first_path is not None:
        return first_path
    raise RuntimeError(f"No downloadable Pexels result for query: {query}")


def _cutaway_start_for_line(
    *, by_idx: dict[int, dict[str, Any]], line_index: int
) -> float:
    ln = by_idx.get(int(line_index) or 0) or {}
    return float(ln.get("start") or 0.0)


def _normalize_cutaway_durations(cuts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extend durations slightly when two cutaways are within 1s to enable crossfade."""

    cuts = sorted(cuts, key=lambda c: float(c.get("start") or 0.0))
    for i in range(len(cuts) - 1):
        cur = cuts[i]
        nxt = cuts[i + 1]
        start = float(cur.get("start") or 0.0)
        dur = float(cur.get("duration") or 0.0)
        end = start + max(0.0, dur)
        next_start = float(nxt.get("start") or 0.0)
        if next_start - end < 1.0:
            desired_end = next_start + 0.2
            cur["duration"] = min(6.0, max(dur, desired_end - start))
    return cuts


def _extract_punch_phrase(s: str) -> str:
    """Return a short, uppercase punch phrase from a hook."""

    s = str(s or "").strip()
    if not s:
        return ""

    clauses = [c.strip() for c in re.split(r",|—|–", s) if c.strip()]
    tail = clauses[-1] if clauses else s
    words = [w for w in re.split(r"\s+", tail) if w]
    if not words:
        return ""
    out = " ".join(words[:3])
    return talking_head._truncate(talking_head._upper_compact(out), 30)


def _enforce_min_spacing(
    bullets: list[dict[str, Any]], *, min_gap: float = 4.0
) -> list[dict[str, Any]]:
    """Ensure bullet timestamps are spaced by at least min_gap seconds."""

    bullets = sorted(bullets, key=lambda b: float(b.get("at_sec") or 0.0))
    out: list[dict[str, Any]] = []
    last_at = -1e9
    for b in bullets:
        at = float(b.get("at_sec") or 0.0)
        if out and at < last_at + float(min_gap):
            at = last_at + float(min_gap)
        out.append(
            {
                "at_sec": round(at, 3),
                "text": str(b.get("text") or "").strip().upper()[:30],
                "sub": str(b.get("sub") or "").strip().upper()[:60],
            }
        )
        last_at = at
    return out


def _resolve_flash_bullets(
    meta: dict[str, Any], timing: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return list of {at_sec, text, sub} for the composition.

    If frontmatter has `flash_bullets`, resolve at_line → at_sec from timing.
    Otherwise auto-generate 3 from hooks + CVE + vendor.
    """

    explicit = meta.get("flash_bullets") or []
    lines = timing.get("lines") or []
    lines_list = (
        [ln for ln in lines if isinstance(ln, dict)] if isinstance(lines, list) else []
    )

    line_starts = {
        (int(ln.get("index") or 0) or (i + 1)): float(ln.get("start") or 0.0)
        for i, ln in enumerate(lines_list)
    }

    if isinstance(explicit, list) and explicit:
        out: list[dict[str, Any]] = []
        for b in explicit[:4]:
            if not isinstance(b, dict):
                continue
            line_idx = int(b.get("at_line") or 1)
            out.append(
                {
                    "at_sec": float(line_starts.get(line_idx, 0.0)),
                    "text": str(b.get("text") or "").strip().upper()[:30],
                    "sub": str(b.get("sub") or "").strip().upper()[:60],
                }
            )
        return _enforce_min_spacing(out, min_gap=4.0)

    hooks = meta.get("hooks") or []
    cves = meta.get("cves") or []
    vendors = meta.get("vendors") or []

    hooks_list = [str(h) for h in hooks] if isinstance(hooks, list) else []
    cves_list = [str(c) for c in cves] if isinstance(cves, list) else []
    vendors_list = [str(v) for v in vendors] if isinstance(vendors, list) else []

    # If hooks/cves/vendors aren't explicitly authored, derive what we can from
    # existing frontmatter fields (incident/source/title) so hybrid still renders bullets.
    incident = str(meta.get("incident") or "")
    source = str(meta.get("source") or "")
    title = str(meta.get("title") or "")
    blob = " ".join([incident, source, title]).strip()

    if blob:
        if not cves_list:
            cves_list = re.findall(r"(?i)\bCVE-[0-9]{4}-[0-9]{4,7}\b", blob)[:1]

        if not vendors_list:
            # Best-effort: first ALLCAPS token that's not a generic acronym.
            blacklist = {
                "CVE",
                "CVSS",
                "UTC",
                "HTTP",
                "HTTPS",
                "TLS",
                "SSH",
                "RCE",
                "DDOS",
            }
            for tok in re.findall(r"\b[A-Z]{3,}\b", blob):
                if tok in blacklist:
                    continue
                vendors_list = [tok]
                break

    bullets: list[dict[str, Any]] = []

    # Bullet 1: hook/punch
    first_text = ""
    if hooks_list:
        first_text = _extract_punch_phrase(hooks_list[0])
    elif blob:
        blob_l = blob.lower()
        if re.search(r"\b(8|eight)\b.*\byear", blob_l):
            first_text = "8 YEARS"
        else:
            first_text = _extract_punch_phrase(incident or title or blob)
    if first_text:
        bullets.append({"text": first_text, "sub": ""})

    # Bullet 2: vendor + CVE
    if cves_list and vendors_list:
        bullets.append(
            {
                "text": talking_head._truncate(
                    talking_head._upper_compact(vendors_list[0]), 30
                ),
                "sub": talking_head._truncate(
                    talking_head._upper_compact(cves_list[0]), 60
                ),
            }
        )

    # Bullet 3: patch year (best effort), else a second hook.
    year_text = ""
    years = (
        [int(y) for y in re.findall(r"\b(19[0-9]{2}|20[0-9]{2})\b", blob)]
        if blob
        else []
    )
    if years:
        year_text = f"PATCH: {min(years)}"
    elif len(hooks_list) > 1:
        year_text = _extract_punch_phrase(hooks_list[-1])
    elif title:
        year_text = _extract_punch_phrase(title)
    if year_text:
        bullets.append({"text": year_text, "sub": ""})

    # Ensure we have up to 3 bullets even if metadata is sparse.
    while len(bullets) < 3:
        bullets.append({"text": "PATCH NOW", "sub": ""})

    # Position at 25% / 50% / 75% of total spoken lines
    n = max(len(lines_list), 4)
    pcts = [0.25, 0.50, 0.75]
    for i, b in enumerate(bullets[:3]):
        idx = max(1, min(n, int(n * pcts[i]) + 1))
        b["at_sec"] = float(line_starts.get(idx, 0.0))
    return _enforce_min_spacing(bullets[:3], min_gap=4.0)


def _write_talking_head_hybrid_composition(
    *,
    script_path: Path,
    hyperframes_dir: Path,
    avatar_mp4: Path,
    timing_json: Path,
    edition: str,
    cutaways_desc: list[dict[str, Any]],
    cutaways_html: str,
    ambient_src: str,
) -> None:
    template_path = hyperframes_dir / "compositions/talking-head-hybrid.html.tmpl"
    out_path = hyperframes_dir / "compositions/talking-head-hybrid.html"
    if not template_path.exists():
        raise RuntimeError(f"Missing template: {template_path}")

    avatar_duration = round(talking_head.ffprobe_duration(avatar_mp4), 2)

    post = frontmatter.load(str(script_path))
    meta = dict(post.metadata or {})

    story_date_iso = str(meta.get("story_date") or "").strip().strip('"')
    edition_meta = str(meta.get("edition") or "").strip().lower()
    edition_final = (edition or "").strip().lower() or edition_meta
    if edition_final not in ("morning", "evening"):
        edition_final = "evening"
    edition_badge = talking_head._edition_badge_text(edition_final)
    edition_date = talking_head._edition_date_text(story_date_iso)
    headline = talking_head._headline_from_title(str(meta.get("title") or ""))

    cves = meta.get("cves") or []
    cve_number = ""
    if isinstance(cves, list) and cves:
        cve_number = talking_head._upper_compact(str(cves[0]))

    timing = json.loads(timing_json.read_text(encoding="utf-8"))
    lines = timing.get("lines") or []
    if not isinstance(lines, list):
        lines = []
    timing_lines = [ln for ln in lines if isinstance(ln, dict)]

    word_objs = _load_transcript_words(script_path)
    words_literal = _build_words_array_literal(word_objs)
    highlight_words = _highlight_word_set(meta, word_objs)
    highlights_literal = json.dumps(highlight_words, ensure_ascii=False)

    opener_lines = _normalize_opener_text(meta.get("opener_text"))
    opener_enabled = bool(opener_lines)
    if opener_enabled:
        opener_duration = 4.0
        opener_display = ""
        opener_text_html = _opener_text_html(opener_lines)
    else:
        opener_duration = 0.01
        opener_display = "display: none;"
        opener_text_html = ""

    # PIP rhythm: big → corner → big (exactly two transitions total).
    pip_start = 0.0
    pip_end = 0.0
    if len(timing_lines) >= 3:
        pip_start = float(timing_lines[1].get("start") or 0.0) + 0.3
        if opener_enabled:
            pip_start = max(pip_start, 0.5 + opener_duration + 0.3)
        pip_end = float(timing_lines[-1].get("start") or 0.0) - 0.4
        if pip_end - pip_start < 5.0:
            pip_start = 0.0
            pip_end = 0.0

    # Subtitle window: opens when Tyler is PIPed, closes 0.3s before final spoken line
    # (so Tyler returns to full-bleed cleanly for the takeaway and climax).
    last_line_start = (
        float(timing_lines[-1].get("start") or avatar_duration)
        if timing_lines
        else avatar_duration
    )
    subtitle_start = float(pip_start)
    subtitle_end = max(subtitle_start + 1.0, last_line_start - 0.3)

    vendors = meta.get("vendors") or []
    vendors_list = [str(v) for v in vendors] if isinstance(vendors, list) else []

    hooks = meta.get("hooks") or []
    hooks_list = [str(h) for h in hooks] if isinstance(hooks, list) else []

    chyron_texts = talking_head._chyron_items(meta)
    if len(chyron_texts) == 1:
        extra = ""
        if cve_number:
            extra = talking_head._truncate(talking_head._upper_compact(cve_number), 30)
        elif headline:
            extra = talking_head._truncate(talking_head._upper_compact(headline), 30)
        elif vendors_list:
            extra = talking_head._truncate(
                talking_head._upper_compact(vendors_list[0]), 30
            )
        chyron_texts.append(extra or chyron_texts[0])
    sched = talking_head._chyron_schedule(avatar_duration, chyron_texts)
    while len(sched) < 3:
        sched.append((0.0, 0.0, ""))

    ticker_html = talking_head._ticker_items_html(
        edition_badge=edition_badge,
        edition_date=edition_date,
        story_date_iso=story_date_iso,
        headline=headline,
        vendors=vendors_list,
        hooks=hooks_list,
        cve_number=cve_number,
    )

    climax_text = talking_head._pick_climax_text(meta, timing_lines)
    climax_words_html = _climax_words_html(climax_text)

    # v3.3: pad 3s after audio ends so climax can complete before end card.
    TAIL_PADDING = 3.0
    total_duration = avatar_duration + TAIL_PADDING

    # Climax: lands ~2.5s before audio ends (lands on the punchline word)
    climax_start = max(0.0, avatar_duration - 2.5)
    climax_dur = 3.5  # holds across audio end into the tail

    ambient_duration = 0.01
    ambient_display = "display: none;"
    ambient_src_final = ""
    if pip_end > pip_start and pip_start >= 0:
        ambient_duration = max(0.01, float(pip_end - pip_start))
        ambient_display = ""
        ambient_src_final = str(ambient_src or "")

    # End card: pushed into the tail, after climax has had its window
    endcard_dur = 2.0
    endcard_start = avatar_duration + 1.0

    html = template_path.read_text(encoding="utf-8")
    if "<!-- LINES_INSERT_HERE -->" not in html:
        raise RuntimeError("Template missing <!-- LINES_INSERT_HERE --> marker")
    if "<!-- HIGHLIGHTS_INSERT_HERE -->" not in html:
        raise RuntimeError("Template missing <!-- HIGHLIGHTS_INSERT_HERE --> marker")
    if "<!-- CUTAWAYS_INSERT_HERE -->" not in html:
        raise RuntimeError("Template missing <!-- CUTAWAYS_INSERT_HERE --> marker")
    if "<!-- FLASH_BULLETS_INSERT_HERE -->" not in html:
        raise RuntimeError("Template missing <!-- FLASH_BULLETS_INSERT_HERE --> marker")
    if "{{CUTAWAYS_JSON}}" not in html:
        raise RuntimeError("Template missing {{CUTAWAYS_JSON}} placeholder")
    if "{{FLASH_BULLETS_JSON}}" not in html:
        raise RuntimeError("Template missing {{FLASH_BULLETS_JSON}} placeholder")
    if "{{PIP_START_TIME}}" not in html or "{{PIP_END_TIME}}" not in html:
        raise RuntimeError("Template missing PIP time placeholders")
    for ph in (
        "{{OPENER_DURATION}}",
        "{{OPENER_DURATION_FLOAT}}",
        "{{OPENER_DISPLAY}}",
        "{{OPENER_TEXT_HTML}}",
        "{{SUBTITLE_START}}",
        "{{SUBTITLE_END}}",
        "{{AMBIENT_SRC}}",
        "{{AMBIENT_DURATION}}",
        "{{AMBIENT_DISPLAY}}",
        "{{CLIMAX_WORDS_HTML}}",
    ):
        if ph not in html:
            raise RuntimeError(f"Template missing {ph} placeholder")

    html = talking_head._strip_template_header(html)
    derived_header = (
        "<!-- DERIVED FILE — DO NOT EDIT.\n"
        "     Generated from hyperframes/compositions/talking-head-hybrid.html.tmpl by scripts/modes/talking_head_hybrid.py.\n"
        "     Edit the .tmpl and re-run scripts/render_short.py to regenerate. -->\n"
    )
    html = derived_header + html

    cutaways_json = json.dumps(cutaways_desc, ensure_ascii=False)

    flash_bullets = _resolve_flash_bullets(meta, timing)
    flash_bullets_json = json.dumps(flash_bullets, ensure_ascii=False)

    flash_bullets_html_parts: list[str] = []
    for i, b in enumerate(flash_bullets):
        text = str(b.get("text") or "").strip().upper()[:30]
        sub = str(b.get("sub") or "").strip().upper()[:60]
        if not text:
            continue
        sub_html = f'<div class="sub">{sub}</div>' if sub else ""
        flash_bullets_html_parts.append(
            f'    <div id="flash-{i}" class="flash-bullet"><div class="main">{text}</div>{sub_html}</div>'
        )
    flash_bullets_html = "\n".join(flash_bullets_html_parts)
    if flash_bullets_html:
        flash_bullets_html += "\n"
    cutaway_html = (cutaways_html or "").strip()
    if cutaway_html:
        cutaway_html += "\n"

    repl = {
        "{{TOTAL_DURATION}}": talking_head._fmt2(total_duration),
        "{{AVATAR_DURATION}}": talking_head._fmt2(avatar_duration),
        "{{EDITION_BADGE_TEXT}}": edition_badge,
        "{{EDITION_DATE}}": edition_date,
        "{{STORY_DATE_ISO}}": story_date_iso,
        "{{STORY_HEADLINE}}": headline,
        "{{CVE_NUMBER}}": cve_number,
        "{{CHYRON_1_TEXT}}": sched[0][2],
        "{{CHYRON_1_START}}": talking_head._fmt2(sched[0][0]),
        "{{CHYRON_1_DURATION}}": talking_head._fmt2(sched[0][1]),
        "{{CHYRON_2_TEXT}}": sched[1][2],
        "{{CHYRON_2_START}}": talking_head._fmt2(sched[1][0]),
        "{{CHYRON_2_DURATION}}": talking_head._fmt2(sched[1][1]),
        "{{CHYRON_3_TEXT}}": sched[2][2],
        "{{CHYRON_3_START}}": talking_head._fmt2(sched[2][0]),
        "{{CHYRON_3_DURATION}}": talking_head._fmt2(sched[2][1]),
        "{{TICKER_ITEMS_HTML}}": ticker_html,
        "{{CLIMAX_WORDS_HTML}}": climax_words_html,
        "{{SUBTITLE_START}}": f"{subtitle_start:.2f}",
        "{{SUBTITLE_END}}": f"{subtitle_end:.2f}",
        "{{CLIMAX_START}}": f"{climax_start:.2f}",
        "{{CLIMAX_DURATION}}": f"{climax_dur:.2f}",
        "{{ENDCARD_START}}": f"{endcard_start:.2f}",
        "{{ENDCARD_DURATION}}": f"{endcard_dur:.2f}",
        "{{CUTAWAYS_JSON}}": cutaways_json,
        "{{FLASH_BULLETS_JSON}}": flash_bullets_json,
        "{{PIP_START_TIME}}": talking_head._fmt2(pip_start),
        "{{PIP_END_TIME}}": talking_head._fmt2(pip_end),
        "{{OPENER_DURATION}}": _fmt3(opener_duration),
        "{{OPENER_DURATION_FLOAT}}": str(float(opener_duration)),
        "{{OPENER_DISPLAY}}": opener_display,
        "{{OPENER_TEXT_HTML}}": opener_text_html,
        "{{AMBIENT_SRC}}": ambient_src_final,
        "{{AMBIENT_DURATION}}": _fmt3(ambient_duration),
        "{{AMBIENT_DISPLAY}}": ambient_display,
    }
    for k, v in repl.items():
        html = html.replace(k, str(v))
    html = html.replace("<!-- LINES_INSERT_HERE -->", words_literal)
    html = html.replace("<!-- HIGHLIGHTS_INSERT_HERE -->", highlights_literal)
    html = html.replace("<!-- CUTAWAYS_INSERT_HERE -->", cutaway_html)
    html = html.replace("<!-- FLASH_BULLETS_INSERT_HERE -->", flash_bullets_html)

    if "{{" in html or "}}" in html:
        raise RuntimeError(
            "Unfilled placeholders remain in generated talking-head-hybrid.html"
        )
    if (
        "LINES_INSERT_HERE" in html
        or "HIGHLIGHTS_INSERT_HERE" in html
        or "CUTAWAYS_INSERT_HERE" in html
        or "FLASH_BULLETS_INSERT_HERE" in html
    ):
        raise RuntimeError("Insert markers not replaced in talking-head-hybrid.html")

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
    """Ensure hyperframes/avatar.mp4 and hyperframes/master.wav exist, plus cutaways."""

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
        hk = talking_head.heygen_key()
        audio_asset = talking_head.heygen_upload_audio(hk, final_wav)
        video_id = talking_head.heygen_generate(
            hk,
            avatar_id=avatar_id,
            audio_asset_id=audio_asset,
            bg_asset_id=bg_asset_id,
        )
        url = talking_head.heygen_poll(hk, video_id, timeout_s=2400)
        talking_head.heygen_download(url, avatar_mp4)
    else:
        log("skip HeyGen (--skip-heygen)")
        if not avatar_mp4.exists():
            raise FileNotFoundError(f"--skip-heygen but {avatar_mp4} missing")

    # Extract HeyGen audio as master (sync-perfect)
    talking_head.ffmpeg_extract_audio(avatar_mp4, master_wav)

    avatar_duration = float(talking_head.ffprobe_duration(avatar_mp4))

    post = frontmatter.load(str(script_path))
    meta = dict(post.metadata or {})
    cut_cfg = meta.get("cutaways") or []
    cut_cfg_list = cut_cfg if isinstance(cut_cfg, list) else []

    timing = json.loads(timing_json.read_text(encoding="utf-8"))
    timing_lines = timing.get("lines") or []
    if not isinstance(timing_lines, list):
        timing_lines = []
    by_idx = {
        int(ln.get("index") or 0): ln
        for ln in timing_lines
        if isinstance(ln, dict) and ln.get("index")
    }

    # Prepare cutaway timings + download/normalize.
    cache_dir = proj_dir / "assets/cache"
    provider_stock_dir = proj_dir / "assets/stock"
    hf_stock_dir = hf_dir / "stock"
    cache_dir.mkdir(parents=True, exist_ok=True)
    provider_stock_dir.mkdir(parents=True, exist_ok=True)
    hf_stock_dir.mkdir(parents=True, exist_ok=True)

    ambient_query = str(meta.get("ambient_query") or "").strip()
    if not ambient_query:
        ambient_query = "abstract cyber server room slow motion dim"
    ambient_provider = _pexels_download_min_duration(
        query=ambient_query,
        out_dir=provider_stock_dir,
        cache_dir=cache_dir,
        min_seconds=8.0,
    )
    ambient_canonical = hf_stock_dir / "ambient-bg.mp4"
    stock_broll._normalize_mp4_for_hyperframes(ambient_provider, ambient_canonical)
    ambient_src = f"stock/{ambient_canonical.name}"

    cuts: list[dict[str, Any]] = []
    for raw in cut_cfg_list:
        if not isinstance(raw, dict):
            continue
        line_index = int(raw.get("line_index") or 0)
        query = str(raw.get("pexels_query") or "").strip()
        if line_index <= 0 or not query:
            continue
        base_start = _cutaway_start_for_line(by_idx=by_idx, line_index=line_index)
        start = max(0.0, float(base_start) + 0.1)
        dur = float(raw.get("duration") or 4.0)
        dur = max(0.1, min(6.0, dur))

        if start >= avatar_duration:
            continue
        dur = min(dur, max(0.05, avatar_duration - start))
        cuts.append(
            {
                "start": start,
                "duration": dur,
                "pexels_query": query,
                "line_index": line_index,
            }
        )

    cuts = _normalize_cutaway_durations(cuts)

    cutaways_desc: list[dict[str, Any]] = []
    cutaways_html_parts: list[str] = []
    for i, c in enumerate(cuts):
        query = str(c.get("pexels_query") or "").strip()
        stock_path = _pexels_download_top(
            query=query, out_dir=provider_stock_dir, cache_dir=cache_dir
        )
        canonical = hf_stock_dir / f"cutaway-{i}.mp4"
        stock_broll._normalize_mp4_for_hyperframes(stock_path, canonical)
        src = f"stock/{canonical.name}"
        start = float(c.get("start") or 0.0)
        dur = float(c.get("duration") or 0.0)
        dur = max(0.05, min(6.0, dur))

        cutaways_desc.append(
            {
                "start": round(start, 3),
                "duration": round(dur, 3),
                "src": src,
            }
        )
        cutaways_html_parts.append(
            (
                f'    <video id="cutaway-{i}" class="clip cutaway-video" '
                f'data-start="{talking_head._fmt2(start)}" data-duration="{talking_head._fmt2(dur)}" '
                f'data-track-index="{30 + i}" src="{src}" muted playsinline></video>'
            )
        )

    # Write a fresh HyperFrames composition from the hybrid template.
    _write_talking_head_hybrid_composition(
        script_path=script_path,
        hyperframes_dir=hf_dir,
        avatar_mp4=avatar_mp4,
        timing_json=timing_json,
        edition=edition,
        cutaways_desc=cutaways_desc,
        cutaways_html="\n".join(cutaways_html_parts),
        ambient_src=ambient_src,
    )
    return {"avatar_mp4": avatar_mp4, "master_wav": master_wav}
