#!/usr/bin/env python3
"""Generate the single AI keyframe (Gemini Imagegen via OpenRouter)."""

from __future__ import annotations

import argparse
import base64
import datetime as _dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from _util import download_file, get_secret, http_post_json


OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemini-2.5-flash-image"


def _now_utc_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _parse_tags_csv(s: str) -> list[str]:
    parts = [p.strip().lower() for p in (s or "").split(",")]
    tags: list[str] = []
    for t in parts:
        if not t:
            continue
        if t not in tags:
            tags.append(t)
    return tags


def _parse_iso_utc(s: str) -> _dt.datetime | None:
    if not s:
        return None
    try:
        # fromisoformat supports offsets like +00:00.
        dt = _dt.datetime.fromisoformat(str(s))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        return dt.astimezone(_dt.timezone.utc)
    except Exception:
        return None


def _age_days(created_at: _dt.datetime, now: _dt.datetime) -> int:
    age = now - created_at
    return int(age.total_seconds() // 86400)


def _copy_keyframe_to_out(
    *, src: Path, out_path: Path, seed_jpg: Path | None = None
) -> None:
    """Copy/convert a keyframe into --out.

    If out is JPG/JPEG, convert PNG→JPG via ffmpeg.
    seed_jpg is only used for the hash-hit path (seed deterministic lib_jpg).
    """

    if out_path.suffix.lower() in {".jpg", ".jpeg", ""}:
        if src.suffix.lower() in {".jpg", ".jpeg"}:
            shutil.copyfile(src, out_path)
        else:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(src),
                    str(out_path),
                ],
                check=True,
            )
            if seed_jpg is not None:
                try:
                    if not seed_jpg.exists():
                        shutil.copyfile(out_path, seed_jpg)
                except Exception:
                    pass
    else:
        shutil.copyfile(src, out_path)


def _write_library_sidecar(
    *, asset_path: Path, tags: list[str], source_short: str, created_at: str
) -> None:
    meta_path = asset_path.with_suffix(asset_path.suffix + ".meta.json")
    meta = {
        "tags": list(tags or []),
        "created_at": created_at,
        "source_short": source_short or "unknown",
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _select_tag_reuse_candidate(
    *, library_dir: Path, prefix: str, tags: list[str], cooldown_days: int = 7
) -> tuple[Path, list[str], int] | None:
    """Return (asset_path, matched_tags, age_days) or None."""

    if not tags:
        return None

    now = _dt.datetime.now(_dt.timezone.utc)
    tagset = set(tags)
    best: tuple[_dt.datetime, Path, list[str], int] | None = None

    for meta_path in library_dir.glob(f"{prefix}-*.meta.json"):
        try:
            d = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        sidecar_tags = d.get("tags")
        if not isinstance(sidecar_tags, list):
            continue
        sidecar_tags_norm = [
            str(t).strip().lower() for t in sidecar_tags if str(t).strip()
        ]
        overlap = sorted(set(sidecar_tags_norm) & tagset)
        if not overlap:
            continue
        created_at = _parse_iso_utc(str(d.get("created_at") or ""))
        if not created_at:
            continue
        age_days = _age_days(created_at, now)
        if age_days < int(cooldown_days):
            continue

        # Resolve asset path: strip the trailing ".meta.json" suffix.
        asset_path = Path(str(meta_path)[: -len(".meta.json")])
        if not asset_path.exists():
            continue

        if best is None or created_at < best[0]:
            best = (created_at, asset_path, overlap, age_days)

    if not best:
        return None
    _, asset_path, overlap, age_days = best
    return asset_path, overlap, age_days


def _find_image_ref(obj: Any) -> str | None:
    if isinstance(obj, str) and obj.startswith("data:image/"):
        return obj
    if (
        isinstance(obj, str)
        and obj.startswith("http")
        and (".png" in obj or ".jpg" in obj or ".jpeg" in obj or "image" in obj)
    ):
        return obj
    if isinstance(obj, dict):
        # Common OpenAI-ish image field.
        b64_json = obj.get("b64_json")
        if isinstance(b64_json, str) and b64_json:
            return f"data:image/png;base64,{b64_json}"
        # OpenRouter sometimes returns content blocks; be permissive.
        iu = obj.get("image_url")
        if isinstance(iu, dict):
            url = iu.get("url")
            if isinstance(url, str) and (
                url.startswith("data:image/") or url.startswith("http")
            ):
                return url
        if isinstance(iu, str) and (
            iu.startswith("data:image/") or iu.startswith("http")
        ):
            return iu
        url2 = obj.get("url")
        if isinstance(url2, str) and (
            url2.startswith("data:image/") or url2.startswith("http")
        ):
            return url2
    if isinstance(obj, list):
        for it in obj:
            hit = _find_image_ref(it)
            if hit:
                return hit
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="hyperframes/ai/keyframe.jpg")
    p.add_argument("--library-dir", default="hyperframes/ai/library")
    p.add_argument("--debug-response", default="")
    p.add_argument(
        "--tags",
        default="",
        help="Comma-separated producer tags for cache reuse (e.g. worm,npm,server-room)",
    )
    p.add_argument(
        "--source-short",
        default="",
        help="Short slug for provenance (e.g. short-040-memory-patched)",
    )
    p.add_argument(
        "--prompt",
        default=(
            "Wide cinematic shot, dim server room aisle, racks of glowing equipment fading into haze, "
            "slight magenta and teal rim lighting, long vanishing point, no people, no on-screen text, "
            "no logos, vertical 9:16 composition, broadcast-news cinematography, photorealistic"
        ),
    )
    p.add_argument("--width", type=int, default=1024)
    p.add_argument("--height", type=int, default=1820)
    args = p.parse_args()

    prompt = str(args.prompt)
    kf_hash = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12]

    tags = _parse_tags_csv(str(args.tags))
    source_short = str(args.source_short or "").strip() or "unknown"

    library_dir = Path(args.library_dir)
    library_dir.mkdir(parents=True, exist_ok=True)
    lib_jpg = library_dir / f"keyframe-{kf_hash}.jpg"
    lib_png = library_dir / f"keyframe-{kf_hash}.png"

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Library hit: copy without invoking OpenRouter.
    if lib_jpg.exists() or lib_png.exists():
        hit_path = lib_jpg if lib_jpg.exists() else lib_png
        print(f"LIBRARY_HIT keyframe-{kf_hash}", file=sys.stderr, flush=True)
        _copy_keyframe_to_out(src=hit_path, out_path=out_path, seed_jpg=lib_jpg)

        print(f"[render_keyframe] wrote {out_path}")
        return 0

    # Tag-based reuse: allow overlap reuse once the library entry is at least 7 days old.
    cand = _select_tag_reuse_candidate(
        library_dir=library_dir, prefix="keyframe", tags=tags
    )
    if cand is not None:
        asset_path, overlap, age_days = cand
        print(
            f"LIBRARY_REUSE {asset_path.name} tags={','.join(overlap)} age_days={age_days}",
            file=sys.stderr,
            flush=True,
        )
        _copy_keyframe_to_out(src=asset_path, out_path=out_path, seed_jpg=None)
        print(f"[render_keyframe] wrote {out_path}")
        return 0

    api_key = get_secret(
        env_var="OPENROUTER_API_KEY", op_ref="op://Claude/OpenRouter/api-key"
    )

    body = {
        "model": MODEL,
        "modalities": ["image"],
        "image_config": {"width": int(args.width), "height": int(args.height)},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": str(args.prompt)},
                ],
            }
        ],
    }
    resp = http_post_json(
        OPENROUTER_API,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        body=body,
        timeout=180,
    )

    if args.debug_response:
        Path(args.debug_response).parent.mkdir(parents=True, exist_ok=True)
        Path(args.debug_response).write_text(
            json.dumps(resp, indent=2), encoding="utf-8"
        )

    choice = ((resp.get("choices") or [None])[0] or {}).get("message") or {}
    content = choice.get("content")
    ref = _find_image_ref(content) or _find_image_ref(resp)
    if not ref:
        # Best-effort fallback: search for any data:image occurrence.
        s = json.dumps(resp)
        m = re.search(r"data:image/[^\"]+", s)
        if m:
            ref = m.group(0)
    if not ref:
        raise RuntimeError("OpenRouter did not return an image")

    # Miss: generate, persist in library, then copy to --out.
    if ref.startswith("http"):
        tmp = library_dir / f"_tmp-keyframe-{kf_hash}.img"
        download_file(ref, tmp)
        raw = tmp.read_bytes()
        is_jpeg = raw[:3] == b"\xff\xd8\xff"
        is_png = raw[:8] == b"\x89PNG\r\n\x1a\n"
        if is_jpeg:
            lib_jpg.write_bytes(raw)
        elif is_png:
            lib_png.write_bytes(raw)
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(lib_png),
                    str(lib_jpg),
                ],
                check=True,
            )
        else:
            # Unknown image; convert to JPEG deterministically.
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(tmp),
                    str(lib_jpg),
                ],
                check=True,
            )
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
    else:
        header, b64 = ref.split(",", 1)
        mime = header.split(";")[0].split(":", 1)[1]
        raw = base64.b64decode(b64)

        if mime.endswith("jpeg") or mime.endswith("jpg"):
            lib_jpg.write_bytes(raw)
        else:
            # Persist the original PNG (if provided), but always create a JPEG too.
            lib_png.write_bytes(raw)
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(lib_png),
                    str(lib_jpg),
                ],
                check=True,
            )

    shutil.copyfile(lib_jpg, out_path)
    # Sidecar metadata for keyword-based reuse.
    try:
        created_at = _now_utc_iso()
        _write_library_sidecar(
            asset_path=lib_jpg,
            tags=tags,
            source_short=source_short,
            created_at=created_at,
        )
        if lib_png.exists():
            _write_library_sidecar(
                asset_path=lib_png,
                tags=tags,
                source_short=source_short,
                created_at=created_at,
            )
    except Exception:
        # Sidecars are best-effort; do not fail render.
        pass
    print(f"[render_keyframe] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
