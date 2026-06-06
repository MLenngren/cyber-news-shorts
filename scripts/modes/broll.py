#!/usr/bin/env python3
"""B-roll mode for ThreatNoir Cyber News (Runware stills + hero clip)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import render_visuals


def log(msg: str) -> None:
    print(f"[b-roll] {msg}", flush=True)


def prepare_assets(
    *,
    proj_dir: Path,
    short_id: str,
    slug: str,
    parsed_json: Path,
    hf_dir: Path,
    cost_json: Path,
    still_count: int = 8,
    force_visuals: bool = False,
) -> dict[str, Path]:
    """Generate visuals and write a HyperFrames input file.

    Returns dict with keys: visuals_dir, broll_json
    """
    visuals_dir = proj_dir / "assets" / "visuals" / slug
    parsed = json.loads(parsed_json.read_text(encoding="utf-8"))

    res = render_visuals.generate_broll(
        parsed=parsed,
        out_dir=visuals_dir,
        still_count=still_count,
        force=force_visuals,
    )

    # Copy assets into hyperframes/ so the HyperFrames file server can serve them.
    hf_stills_dir = hf_dir / "stills"
    hf_stills_dir.mkdir(parents=True, exist_ok=True)
    for idx, src in enumerate(res["stills"], start=1):
        dst = hf_stills_dir / f"still-{idx:02d}.jpg"
        shutil.copyfile(src, dst)
    hf_hero = hf_dir / "hero.mp4"
    shutil.copyfile(Path(res["hero"]), hf_hero)

    # Persist cost sidecar (Runware only for now)
    cost_json.write_text(
        json.dumps(
            {
                "short_id": short_id,
                "slug": slug,
                "mode": "b-roll",
                "providers": {"runware": res["cost"].to_json()},
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Write inputs for HyperFrames template (relative to hyperframes/)
    stills_rel = [
        str(Path("stills") / f"still-{i:02d}.jpg") for i in range(1, still_count + 1)
    ]
    hero_rel = "hero.mp4"
    broll_inputs = {
        "short_id": short_id,
        "slug": slug,
        "stills": stills_rel,
        "hero": hero_rel,
    }
    broll_json = hf_dir / "broll.json"
    broll_json.write_text(json.dumps(broll_inputs, indent=2), encoding="utf-8")

    log(f"visuals_dir: {visuals_dir}")
    log(f"broll.json: {broll_json}")
    log(f"runware cost: ${res['cost'].total:.4f} (cap ${res['cost'].cap:.2f})")
    return {"visuals_dir": visuals_dir, "broll_json": broll_json}
