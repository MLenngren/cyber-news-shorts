#!/usr/bin/env python3
"""Parse a short markdown script into a structured JSON timeline.

Recognized syntax:
- Scene markers: ## [SCENE N] or ## [SCENE N — TITLE]
- Speaker markers: **SPEAKER:** on its own line
- (pause N.N) adds a pause in seconds after the previous line
- Lines starting with > are stage direction, ignored for TTS
- Any other line with a current speaker is treated as spoken text

YAML frontmatter:
- Optional shots: list (used by --mode stock-broll). When present it is emitted
  into the parsed JSON output as the top-level field shots.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCENE_RE = re.compile(
    r"^##\s+\[SCENE\s+([0-9]+)(?:\s+[-—]\s*(.+?))?\]\s*$", re.IGNORECASE
)
SPEAKER_RE = re.compile(r"^\*\*([A-ZÅÄÖ. ]+):\*\*\s*$")
PAUSE_RE = re.compile(r"^\(\s*pause\s+([0-9.]+)\s*\)\s*$", re.IGNORECASE)
HEADING_RE = re.compile(r"^#+\s+")

# Tag-shaped substrings should never be spoken (e.g., tool-call artifacts, stray HTML).
TAG_LIKE_RE = re.compile(
    r"<\s*/?\s*[a-zA-Z_][a-zA-Z0-9_\-:]*\s*(?:\s+[^>]*?)?\s*/?\s*>"
)


def _sanitize_spoken_text(text: str, *, script_path: Path) -> str:
    """Sanitize a spoken line before it is written to parsed JSON.

    - Strip any XML/HTML-like tag substrings (tool artifacts, HTML, etc.)
    - Collapse whitespace after stripping
    - Emit a warning when a line is modified
    """

    without_tags = TAG_LIKE_RE.sub("", text)
    cleaned = re.sub(r"\s+", " ", without_tags).strip()

    if cleaned != text:
        print(
            "WARNING: sanitized tag-like artifacts in spoken line",
            file=sys.stderr,
        )
        print(f"  script:   {script_path}", file=sys.stderr)
        print(f"  original: {text!r}", file=sys.stderr)
        print(f"  cleaned:  {cleaned!r}", file=sys.stderr)

    return cleaned


def _strip_yaml_frontmatter(raw: str) -> str:
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return raw
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1 :])
    return raw


def parse_script(md_path: Path) -> dict[str, Any]:
    md_raw = md_path.read_text(encoding="utf-8")

    shots: list[dict[str, Any]] | None = None
    content = md_raw

    # Best-effort YAML frontmatter parsing (for stock-broll mode shots).
    try:
        import frontmatter  # type: ignore

        post = frontmatter.loads(md_raw)
        content = post.content
        meta = post.metadata or {}
        if isinstance(meta, dict):
            s = meta.get("shots")
            if isinstance(s, list):
                shots = [x for x in s if isinstance(x, dict)]
    except Exception:
        content = _strip_yaml_frontmatter(md_raw)

    raw = content
    scenes: list[dict[str, Any]] = []
    current_scene: dict[str, Any] | None = None
    current_speaker: str | None = None
    last_line: dict[str, Any] | None = None
    global_index = 0

    for raw_line in raw.splitlines():
        s = raw_line.strip()
        if not s or s.startswith(">") or s.startswith("---"):
            continue

        m_scene = SCENE_RE.match(s)
        if m_scene:
            current_scene = {
                "scene_number": int(m_scene.group(1)),
                "title": (m_scene.group(2) or "").strip(),
                "lines": [],
            }
            scenes.append(current_scene)
            current_speaker = None
            last_line = None
            continue

        if HEADING_RE.match(s) and not s.lower().startswith("## [scene"):
            current_speaker = None
            continue

        m_speaker = SPEAKER_RE.match(s)
        if m_speaker:
            current_speaker = m_speaker.group(1).strip()
            continue

        m_pause = PAUSE_RE.match(s)
        if m_pause and last_line is not None:
            last_line["pause_after_sec"] = float(m_pause.group(1))
            continue

        if current_scene is None or current_speaker is None:
            continue

        # Spoken text
        cleaned = _sanitize_spoken_text(s, script_path=md_path)
        if not cleaned:
            # Avoid emitting empty TTS lines (silence / downstream failures).
            continue

        global_index += 1
        item = {
            "index": global_index,
            "scene_number": current_scene["scene_number"],
            "speaker": current_speaker,
            "text": cleaned,
            "pause_after_sec": 0.0,
        }
        current_scene["lines"].append(item)
        last_line = item

    flat = [ln for sc in scenes for ln in sc["lines"]]
    out: dict[str, Any] = {
        "source_path": str(md_path),
        "scenes": scenes,
        "lines": flat,
        "speakers": sorted({ln["speaker"] for ln in flat}),
    }
    if shots is not None:
        out["shots"] = shots
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--script", default="pilot/script.md")
    p.add_argument("--output", default="pilot/parsed.json")
    args = p.parse_args()

    parsed = parse_script(Path(args.script))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"wrote {args.output}: {len(parsed['scenes'])} scenes, {len(parsed['lines'])} lines, speakers={parsed['speakers']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
