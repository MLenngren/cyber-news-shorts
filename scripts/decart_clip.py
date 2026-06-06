#!/usr/bin/env python3
"""Decart Lucy Motion helper — animates a still image into a short MP4.

Usage:
    python3 decart_clip.py --image input.png --trajectory ken-burns --duration 5 --output clip.mp4
    python3 decart_clip.py --image input.png --custom-traj '[{"frame":0,"x":0.3,"y":0.5}]' --output clip.mp4

Trajectory presets:
    static       — minimal drift (barely visible motion)
    ken-burns    — slow zoom + drift, classic doc-style
    pan-right    — horizontal pan left → right
    pan-left     — horizontal pan right → left
    push-in      — zoom toward center (drift inward)
    pull-out     — zoom away from center (drift outward)

Caching:
    Output is cached by sha1(image_bytes + trajectory_json + resolution + duration).
    Re-running with same inputs returns immediately at $0 cost.

Cost guard:
    Prints expected cost before submitting. Fails if estimate > $1 unless --force.

Auth:
    Reads DECART_API_KEY env var (env-first). Optional op:// reads are supported
    only when OP_SERVICE_ACCOUNT_TOKEN is set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

from _util import get_secret

API_BASE = "https://api.decart.ai"
DECART_FPS = 48  # observed from test-call output; trajectory frames use this rate
COST_PER_SEC_LUCY_MOTION = 0.03  # $0.03/sec @ 720p
DEFAULT_RESOLUTION = "720p"

CACHE_DIR = (
    Path(__file__).resolve().parent.parent / "pilot" / "cutaways" / ".decart-cache"
)


def sha1_of(*chunks: bytes | str) -> str:
    h = hashlib.sha1()
    for c in chunks:
        h.update(c if isinstance(c, bytes) else c.encode("utf-8"))
    return h.hexdigest()


def trajectory_for_preset(name: str, duration: float) -> list[dict]:
    """Return trajectory as list of {frame, x, y} keyframes spanning duration seconds."""
    end_frame = int(duration * DECART_FPS)
    presets = {
        "static": [
            {"frame": 0, "x": 0.50, "y": 0.50},
            {"frame": end_frame, "x": 0.51, "y": 0.50},
        ],
        "ken-burns": [
            {"frame": 0, "x": 0.45, "y": 0.45},
            {"frame": end_frame, "x": 0.55, "y": 0.55},
        ],
        "pan-right": [
            {"frame": 0, "x": 0.30, "y": 0.50},
            {"frame": end_frame, "x": 0.70, "y": 0.50},
        ],
        "pan-left": [
            {"frame": 0, "x": 0.70, "y": 0.50},
            {"frame": end_frame, "x": 0.30, "y": 0.50},
        ],
        "push-in": [
            {"frame": 0, "x": 0.40, "y": 0.40},
            {"frame": end_frame, "x": 0.60, "y": 0.60},
        ],
        "pull-out": [
            {"frame": 0, "x": 0.60, "y": 0.60},
            {"frame": end_frame, "x": 0.40, "y": 0.40},
        ],
    }
    if name not in presets:
        raise SystemExit(
            f"Unknown trajectory preset: {name}. Choose: {sorted(presets.keys())}"
        )
    return presets[name]


def submit_lucy_motion(
    api_key: str, image_path: Path, trajectory: list[dict], resolution: str
) -> str:
    url = f"{API_BASE}/v1/jobs/lucy-motion"
    headers = {"x-api-key": api_key}
    with open(image_path, "rb") as f:
        files = {
            "data": (image_path.name, f, "image/png"),
            "trajectory": (None, json.dumps(trajectory)),
            "resolution": (None, resolution),
        }
        for attempt in range(5):
            try:
                resp = requests.post(url, headers=headers, files=files, timeout=60)
                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = 2**attempt
                    print(
                        f"  retry {attempt + 1}/5 after {wait}s (HTTP {resp.status_code})",
                        file=sys.stderr,
                    )
                    time.sleep(wait)
                    f.seek(0)
                    continue
                resp.raise_for_status()
                data = resp.json()
                job_id = data.get("job_id")
                if not job_id:
                    raise RuntimeError(f"No job_id in response: {data}")
                return job_id
            except requests.HTTPError as e:
                body = resp.text[:500] if resp else ""
                raise RuntimeError(
                    f"Decart submit failed: HTTP {resp.status_code} — {body}"
                ) from e
    raise RuntimeError("Decart submit: exhausted retries")


def poll_until_done(api_key: str, job_id: str, max_wait_sec: int = 300) -> dict:
    url = f"{API_BASE}/v1/jobs/{job_id}"
    headers = {"x-api-key": api_key}
    elapsed = 0
    interval = 3
    while elapsed < max_wait_sec:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "?")
        print(f"  [{elapsed:3d}s] status={status}", file=sys.stderr)
        if status == "completed":
            return data
        if status == "failed":
            raise RuntimeError(f"Decart job failed: {data}")
        time.sleep(interval)
        elapsed += interval
    raise RuntimeError(f"Decart job {job_id} did not complete in {max_wait_sec}s")


def download_content(api_key: str, job_id: str, out_path: Path) -> None:
    url = f"{API_BASE}/v1/jobs/{job_id}/content"
    headers = {"x-api-key": api_key}
    resp = requests.get(url, headers=headers, timeout=120)
    resp.raise_for_status()
    if len(resp.content) < 10000:
        raise RuntimeError(f"Suspiciously small response ({len(resp.content)} bytes)")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(resp.content)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--image", required=True, help="Input image path (PNG)")
    p.add_argument(
        "--trajectory",
        default="ken-burns",
        help="Preset name (static/ken-burns/pan-right/pan-left/push-in/pull-out)",
    )
    p.add_argument(
        "--custom-traj",
        default=None,
        help='JSON array overriding the preset (e.g. \'[{"frame":0,"x":0.5,"y":0.5}]\')',
    )
    p.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="Desired output duration in seconds (Decart approx; actual ~5s baseline)",
    )
    p.add_argument("--resolution", default=DEFAULT_RESOLUTION, help="720p (default)")
    p.add_argument("--output", required=True, help="Output MP4 path")
    p.add_argument("--force", action="store_true", help="Bypass cost guard ($1 cap)")
    p.add_argument(
        "--no-cache", action="store_true", help="Skip cache lookup, always re-generate"
    )
    args = p.parse_args()

    try:
        api_key = get_secret(
            env_var="DECART_API_KEY", op_ref="op://Claude/Decart/api-key"
        )
    except Exception as e:
        sys.exit(f"DECART_API_KEY env not set: {e}")

    image_path = Path(args.image)
    if not image_path.exists():
        sys.exit(f"Image not found: {image_path}")

    out_path = Path(args.output)

    # Resolve trajectory
    if args.custom_traj:
        trajectory = json.loads(args.custom_traj)
    else:
        trajectory = trajectory_for_preset(args.trajectory, args.duration)

    # Cost estimate
    estimated_cost = args.duration * COST_PER_SEC_LUCY_MOTION
    print(
        f"Decart Lucy Motion: {args.duration}s @ {args.resolution} → est. ${estimated_cost:.2f}",
        file=sys.stderr,
    )
    if estimated_cost > 1.0 and not args.force:
        sys.exit(
            f"Cost guard: estimate ${estimated_cost:.2f} exceeds $1.00. Use --force to override."
        )

    # Cache lookup
    image_bytes = image_path.read_bytes()
    cache_key = sha1_of(
        image_bytes,
        json.dumps(trajectory, sort_keys=True),
        args.resolution,
        str(args.duration),
    )
    cache_path = CACHE_DIR / f"{cache_key}.mp4"

    if not args.no_cache and cache_path.exists() and cache_path.stat().st_size > 10000:
        print(f"  CACHED: {cache_path}", file=sys.stderr)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(cache_path.read_bytes())
        print(f"wrote {out_path} (from cache, $0)", file=sys.stderr)
        return 0

    # Submit + poll + download
    print(
        f"Submitting Lucy Motion job (trajectory: {args.trajectory})...",
        file=sys.stderr,
    )
    job_id = submit_lucy_motion(api_key, image_path, trajectory, args.resolution)
    print(f"  job_id: {job_id}", file=sys.stderr)
    poll_until_done(api_key, job_id)

    # Download to cache, then copy to output
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    download_content(api_key, job_id, cache_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(cache_path.read_bytes())
    print(
        f"wrote {out_path} ({cache_path.stat().st_size} bytes, ~${estimated_cost:.2f})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
