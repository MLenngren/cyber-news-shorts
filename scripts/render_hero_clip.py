#!/usr/bin/env python3
"""Generate the single AI hero clip (Runware Seedance 2.0 Fast image-to-video)."""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import shutil
import sys
import time
import uuid
from pathlib import Path

from _util import b64_data_url_from_file, download_file, get_secret, http_post_json


RUNWARE_API = "https://api.runware.ai/v1"
MODEL = "bytedance:seedance@2.0-fast"


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
        dt = _dt.datetime.fromisoformat(str(s))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        return dt.astimezone(_dt.timezone.utc)
    except Exception:
        return None


def _age_days(created_at: _dt.datetime, now: _dt.datetime) -> int:
    age = now - created_at
    return int(age.total_seconds() // 86400)


def _select_tag_reuse_candidate(
    *, library_dir: Path, prefix: str, tags: list[str], cooldown_days: int = 7
) -> tuple[Path, Path | None, list[str], int] | None:
    """Return (asset_path, meta_path, matched_tags, age_days) or None."""

    if not tags:
        return None

    now = _dt.datetime.now(_dt.timezone.utc)
    tagset = set(tags)
    best: tuple[_dt.datetime, Path, Path, list[str], int] | None = None

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

        asset_path = Path(str(meta_path)[: -len(".meta.json")])
        if not asset_path.exists():
            continue

        if best is None or created_at < best[0]:
            best = (created_at, asset_path, meta_path, overlap, age_days)

    if not best:
        return None
    _, asset_path, meta_path, overlap, age_days = best
    return asset_path, meta_path, overlap, age_days


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--keyframe", default="hyperframes/ai/keyframe.jpg")
    p.add_argument("--out", default="hyperframes/ai/hero.mp4")
    p.add_argument("--library-dir", default="hyperframes/ai/library")
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
            "slow forward camera push, subtle scanline flicker, racks dissolve into background haze, "
            "no people, no text"
        ),
    )
    p.add_argument("--duration", type=int, default=4)
    p.add_argument("--resolution", default="480p")
    p.add_argument("--timeout", type=int, default=900)
    args = p.parse_args()

    tags = _parse_tags_csv(str(args.tags))
    source_short = str(args.source_short or "").strip() or "unknown"

    keyframe_path = Path(args.keyframe)
    if not keyframe_path.exists():
        raise RuntimeError(f"Missing keyframe: {keyframe_path}")

    keyframe_bytes = keyframe_path.read_bytes()
    motion_prompt = str(args.prompt)
    hero_hash = hashlib.sha1(
        keyframe_bytes + motion_prompt.encode("utf-8")
    ).hexdigest()[:12]

    library_dir = Path(args.library_dir)
    library_dir.mkdir(parents=True, exist_ok=True)
    lib_path = library_dir / f"hero-{hero_hash}.mp4"
    lib_meta_path = lib_path.with_suffix(lib_path.suffix + ".meta.json")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_meta_path = out_path.with_suffix(out_path.suffix + ".meta.json")

    if lib_path.exists():
        print(f"LIBRARY_HIT hero-{hero_hash}", file=sys.stderr, flush=True)
        shutil.copyfile(lib_path, out_path)
        if lib_meta_path.exists():
            shutil.copyfile(lib_meta_path, out_meta_path)
        print(f"[render_hero_clip] wrote {out_path}")
        return 0

    # Tag-based reuse: allow overlap reuse once the library entry is at least 7 days old.
    cand = _select_tag_reuse_candidate(
        library_dir=library_dir, prefix="hero", tags=tags
    )
    if cand is not None:
        asset_path, meta_path, overlap, age_days = cand
        print(
            f"LIBRARY_REUSE {asset_path.name} tags={','.join(overlap)} age_days={age_days}",
            file=sys.stderr,
            flush=True,
        )
        shutil.copyfile(asset_path, out_path)
        if meta_path and Path(meta_path).exists():
            shutil.copyfile(meta_path, out_meta_path)
        print(f"[render_hero_clip] wrote {out_path}")
        return 0

    api_key = get_secret(
        env_var="RUNWARE_API_KEY", op_ref="op://Claude/runware/api key"
    )

    # Note: Runware expects a data URL; we keep JPEG mime for existing pipeline.
    frame = b64_data_url_from_file(keyframe_path, mime="image/jpeg")
    task_uuid = str(uuid.uuid4())
    submit = {
        "taskType": "videoInference",
        "taskUUID": task_uuid,
        "deliveryMethod": "async",
        "model": MODEL,
        "positivePrompt": str(args.prompt),
        "resolution": str(args.resolution),
        "duration": int(args.duration),
        "settings": {"audio": False},
        "inputs": {"frameImages": [{"image": frame, "frame": "first"}]},
        "includeCost": True,
        "numberResults": 1,
        "ttl": 3600,
    }

    http_post_json(
        RUNWARE_API,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        body=[submit],
        timeout=60,
    )

    deadline = time.time() + int(args.timeout)
    delay = 2.0
    while time.time() < deadline:
        time.sleep(delay)
        delay = min(delay * 1.35, 15.0)
        poll = http_post_json(
            RUNWARE_API,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body=[{"taskType": "getResponse", "taskUUID": task_uuid}],
            timeout=30,
        )
        errors = poll.get("errors") or []
        if errors:
            raise RuntimeError(f"Runware getResponse errors: {errors}")
        data = poll.get("data") or []
        hit = None
        for d in data:
            if str(d.get("taskUUID")) == task_uuid:
                hit = d
                break
        if not hit:
            continue
        status = str(hit.get("status") or "").lower()
        if status == "processing":
            continue
        if status != "success":
            raise RuntimeError(
                f"Runware videoInference failed: {json.dumps(hit)[:1500]}"
            )
        url = str(hit.get("videoURL") or "").strip()
        if not url:
            raise RuntimeError(f"Runware success but missing videoURL: {hit}")
        download_file(url, lib_path)
        cost = hit.get("cost")
        meta = {
            "tags": list(tags or []),
            "created_at": _now_utc_iso(),
            "source_short": source_short,
            "taskUUID": task_uuid,
            "model": MODEL,
            "cost": cost,
        }
        lib_meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        shutil.copyfile(lib_path, out_path)
        shutil.copyfile(lib_meta_path, out_meta_path)
        print(f"[render_hero_clip] wrote {out_path}")
        return 0

    raise TimeoutError("Runware videoInference timed out")


if __name__ == "__main__":
    raise SystemExit(main())
