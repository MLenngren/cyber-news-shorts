#!/usr/bin/env python3
"""Publish a rendered ThreatNoir short to YouTube Shorts.

Usage:
  python3 scripts/publish_youtube.py --script shorts/short-NNN-slug.md

Idempotency:
  Writes shorts/short-NNN-slug.youtube-video-id on success.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

import discord_notify
from _util import brand, get_secret

PROJ = Path(__file__).resolve().parent.parent
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
SHORT_NN_RE = re.compile(r"short-(\d{3})-")


def log(msg: str) -> None:
    print(f"[publish_youtube] {msg}", flush=True)


def trim_to_60s(input_mp4: Path, output_mp4: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(input_mp4),
            "-t",
            "60",
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output_mp4),
        ],
        check=True,
    )


def parse_short_number(script_path: Path) -> int | None:
    m = SHORT_NN_RE.search(script_path.name)
    return int(m.group(1)) if m else None


def slugify_tag(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def vendor_tags_from_source(source: str) -> list[str]:
    # Best-effort heuristic: keep distinct TitleCase tokens that aren't generic.
    if not source:
        return []
    stop = {
        brand("BRAND_SHORT_NAME", "ThreatNoir"),
        "Cyber",
        "News",
        "Short",
        "Legal",
        "Briefs",
        "GDPR",
        "CVE",
    }
    tokens = re.findall(r"[A-Z][A-Za-z0-9&]{2,}", source)
    vendors: list[str] = []
    for t in tokens:
        if t in stop:
            continue
        if t not in vendors:
            vendors.append(t)
    return vendors


def derive_title(frontmatter_title: str) -> str:
    # "<Brand Name> — Short 003: Nine Seconds" -> "Nine Seconds | <Brand Name> #Shorts"
    after_dash = frontmatter_title.split("—", 1)[-1].strip()
    story = re.sub(r"^Short\s*\d{3}:\s*", "", after_dash).strip()
    out = f"{story} | {brand('BRAND_NAME', 'ThreatNoir Cyber News')} #Shorts".strip()
    return out[:100]


def hook_from_markdown(md_body: str) -> str:
    lines = md_body.splitlines()
    # Find first H1, then take first non-empty paragraph/blockquote line.
    start_i = 0
    for i, ln in enumerate(lines):
        if ln.strip().startswith("# "):
            start_i = i + 1
            break
    i = start_i
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].lstrip().startswith(">"):
        return lines[i].lstrip().lstrip(">").strip()
    if i < len(lines):
        return lines[i].strip()
    return ""


def transcript_from_timing(timing_path: Path) -> str:
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    out_lines: list[str] = []
    for ln in timing.get("lines", []):
        speaker = str(ln.get("speaker", "")).strip() or "SPEAKER"
        text = str(ln.get("text", "")).strip()
        if text:
            out_lines.append(f"{speaker}: {text}")
    return "\n".join(out_lines)


def build_description(
    hook: str, transcript: str, source: str, source_urls: list[str], hashtags: list[str]
) -> str:
    """Broadcast-style description: hook + frontpage link + hashtags + brand CTA.

    Transcript intentionally omitted — YouTube auto-generates captions from the
    audio, and a long script dump reads as keyword-stuffed spam to the
    practitioner audience. The `transcript`, `source`, and `source_urls` args
    are kept in the signature for backward compatibility but ignored — every
    short links to the threatnoir.com frontpage rather than per-story URLs
    (those landing pages are mostly generic indexes anyway).
    """
    del transcript, source, source_urls  # intentionally unused
    static_tags = brand(
        "BRAND_HASHTAGS",
        "#Cybersecurity #InfoSec #CyberNews #Shorts",
    )
    tag_line = (
        static_tags.strip() + ((" " + " ".join(hashtags)) if hashtags else "")
    ).strip()
    more_url = brand("BRAND_URL", "https://threatnoir.com")
    short_name = brand("BRAND_SHORT_NAME", "ThreatNoir")
    desc = (
        f"{hook}\n\n"
        f"📌 More: {more_url}\n\n"
        f"{tag_line}\n\n"
        f"{short_name} — curated cyber threat intelligence for security practitioners.\n"
    )
    return desc[:5000]


def build_tags(meta: dict[str, Any]) -> list[str]:
    tags: list[str] = [
        "cybersecurity",
        "infosec",
        "threat-intel",
        "shorts",
        "cyber-news",
    ]
    bn = slugify_tag(brand("BRAND_SHORT_NAME", "ThreatNoir"))
    if bn and bn not in tags:
        tags.append(bn)

    for cve in meta.get("cves") or []:
        c = str(cve).lower().replace("-", "")
        if c and c not in tags:
            tags.append(c)

    ta = (meta.get("threat_actor") or "").strip()
    if ta:
        t = slugify_tag(ta)
        if t and t not in tags:
            tags.append(t)

    source = (meta.get("source") or "").strip()
    for vendor in vendor_tags_from_source(source):
        v = slugify_tag(vendor)
        if v and v not in tags:
            tags.append(v)

    # Enforce YouTube 500-char limit (comma-separated total length).
    limited: list[str] = []
    total = 0
    for t in tags:
        add = len(t) + (1 if limited else 0)
        if total + add > 500:
            break
        limited.append(t)
        total += add
    return limited


def compute_privacy(script_path: Path, override: str | None) -> str:
    if override:
        return override
    n = parse_short_number(script_path)
    if n is not None and n <= 5:
        return "unlisted"
    return "public"


def youtube_client() -> Any:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Missing YouTube dependencies. Install with: pip install -r requirements.txt"
        ) from e

    client_id = get_secret(
        env_var="YOUTUBE_CLIENT_ID", op_ref="op://Claude/Youtube/client-id"
    )
    client_secret = get_secret(
        env_var="YOUTUBE_CLIENT_SECRET", op_ref="op://Claude/Youtube/client-secret"
    )
    refresh_token = get_secret(
        env_var="YOUTUBE_REFRESH_TOKEN", op_ref="op://Claude/Youtube/refresh-token"
    )

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def maybe_discord_dm(message: str) -> None:
    """Best-effort DM to the configured operator.

    OSS default: OPERATOR_DISCORD_ID is empty, so this is a no-op.
    """
    user_id = brand("OPERATOR_DISCORD_ID", "").strip()
    if not user_id:
        return
    try:
        discord_notify.send_dm(recipient_id=user_id, message=message)
    except Exception as e:
        log(f"discord dm failed (non-fatal): {e}")


def main() -> int:
    p = argparse.ArgumentParser(
        description=f"{brand('BRAND_SHORT_NAME', 'ThreatNoir')} — publish a short to YouTube Shorts"
    )
    p.add_argument("--script", required=True, help="Path to shorts/short-NNN-slug.md")
    p.add_argument("--privacy", choices=["public", "unlisted", "private"], default=None)
    p.add_argument(
        "--force", action="store_true", help="Re-upload even if sidecar exists"
    )
    p.add_argument(
        "--dry-run", action="store_true", help="Print metadata and exit without upload"
    )
    args = p.parse_args()

    script = Path(args.script).resolve()
    slug = script.stem
    mp4 = PROJ / f"shorts/{slug}.mp4"
    timing = PROJ / f"shorts/{slug}.timing.json"
    sidecar = PROJ / f"shorts/{slug}.youtube-video-id"
    log_path = Path(tempfile.gettempdir()) / f"publish-youtube-{slug}.log"

    if not script.exists():
        sys.stderr.write(f"script not found: {script}\n")
        return 2
    if not mp4.exists():
        sys.stderr.write(f"mp4 not found: {mp4}\n")
        return 2
    if not timing.exists():
        sys.stderr.write(f"timing.json not found: {timing}\n")
        return 2

    if sidecar.exists() and not args.force:
        vid = sidecar.read_text(encoding="utf-8").strip()
        url = f"https://youtube.com/shorts/{vid}" if vid else "(unknown)"
        log(f"already published, video_id={vid}, URL={url}")
        print(url)
        return 0

    try:
        try:
            import frontmatter  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "Missing frontmatter dependency. Install with: pip install -r requirements.txt"
            ) from e

        post = frontmatter.load(script)
        meta = dict(post.metadata)
        title = derive_title(str(meta.get("title", "")))
        hook = hook_from_markdown(post.content)
        transcript = transcript_from_timing(timing)

        # Dynamic hashtags (story-specific)
        hashtags: list[str] = []
        for cve in meta.get("cves") or []:
            tag = "#" + str(cve).upper().replace("-", "")
            if tag not in hashtags:
                hashtags.append(tag)
        ta = (meta.get("threat_actor") or "").strip()
        if ta:
            h = "#" + re.sub(r"[^A-Za-z0-9]", "", ta)
            if h != "#" and h not in hashtags:
                hashtags.append(h)

        desc = build_description(
            hook=hook,
            transcript=transcript,
            source=str(meta.get("source", "")).strip(),
            source_urls=[str(u) for u in (meta.get("source_urls") or [])],
            hashtags=hashtags,
        )
        tags = build_tags(meta)
        privacy = compute_privacy(script, args.privacy)

        log(f"title: {title}")
        log(f"privacy: {privacy}")
        log(f"tags ({len(tags)}): {', '.join(tags)}")

        # YouTube Shorts allows up to 3 min (180s) since Oct 2024 — no trim needed.
        # If a future short exceeds 180s we'll get a YouTube API error and the
        # script writer should shorten the source. For now we upload as-is.
        upload_mp4 = mp4
        try:
            dur_s = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=nw=1:nk=1",
                    str(mp4),
                ],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            dur = float(dur_s) if dur_s else 0.0
        except Exception:
            dur = 0.0
        if dur > 180.0:
            log(
                f"WARN: video is {dur:.1f}s — YouTube Shorts max is 180s. Uploading anyway, may be classified as regular video."
            )

        if args.dry_run:
            print("=== DRY RUN (no upload) ===")
            print(f"script: {script}")
            print(f"mp4: {mp4}")
            print(f"upload: {upload_mp4} ({dur:.1f}s, no trim)")
            print(f"title: {title}")
            print(f"privacy: {privacy}")
            print(f"tags: {tags}")
            print("description:")
            print(desc)
            return 0

        yt = youtube_client()
        try:
            from googleapiclient.errors import HttpError
            from googleapiclient.http import MediaFileUpload
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "Missing YouTube dependencies. Install with: pip install -r requirements.txt"
            ) from e

        body = {
            "snippet": {
                "title": title,
                "description": desc,
                "tags": tags,
                "categoryId": "28",
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }
        try:
            req = yt.videos().insert(
                part="snippet,status",
                body=body,
                media_body=MediaFileUpload(
                    str(upload_mp4), mimetype="video/mp4", resumable=True
                ),
                notifySubscribers=False,
            )
            res = req.execute()
            video_id = res.get("id", "")
            if not video_id:
                raise RuntimeError(f"Upload succeeded but no video id returned: {res}")
            url = f"https://youtube.com/shorts/{video_id}"

            sidecar.write_text(video_id + "\n", encoding="utf-8")
            log(f"uploaded: {url}")
            print(url)
            maybe_discord_dm(
                f"**{brand('BRAND_SHORT_NAME', 'ThreatNoir')} short uploaded**\n{url}"
            )
            return 0

        except HttpError as e:
            raw = getattr(e, "content", b"")
            msg = (
                raw.decode("utf-8", errors="replace")
                if isinstance(raw, (bytes, bytearray))
                else str(e)
            )
            log_path.write_text(msg[:20000], encoding="utf-8")
            if "quotaExceeded" in msg:
                err = f"YouTube upload failed: quotaExceeded. Log: {log_path}"
            else:
                err = f"YouTube upload failed (HttpError). Log: {log_path}"
            log(err)
            maybe_discord_dm(err)
            return 3
    except Exception as e:
        tb = traceback.format_exc()
        log_path.write_text(tb, encoding="utf-8")
        err = f"YouTube upload failed: {e}. Log: {log_path}"
        log(err)
        maybe_discord_dm(err)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
