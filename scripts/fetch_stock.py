#!/usr/bin/env python3
"""Stock search + download with aggressive caching (Pexels first, Storyblocks fallback)."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import time
import urllib.parse
from pathlib import Path
from typing import Any

from _util import (
    download_file,
    get_secret,
    http_get_json,
    read_json,
    sha1_text,
    write_json,
)


PEXELS_SEARCH = "https://api.pexels.com/videos/search"
STORYBLOCKS_BASE = "https://api.storyblocks.com"


def search_pexels(
    *, query: str, per_page: int = 5, cache_dir: Path
) -> list[dict[str, Any]]:
    cache_path = cache_dir / f"pexels-{sha1_text(query)}.json"
    if cache_path.exists():
        data = read_json(cache_path, default={})
    else:
        key = get_secret(env_var="PEXELS_API_KEY", op_ref="op://Claude/pexels/api key")
        params = {"query": query, "per_page": str(per_page), "orientation": "portrait"}
        url = f"{PEXELS_SEARCH}?{urllib.parse.urlencode(params)}"
        data = http_get_json(url, headers={"Authorization": key}, timeout=60)
        write_json(cache_path, data)

    out: list[dict[str, Any]] = []
    for v in (data.get("videos") or [])[:per_page]:
        vid = v.get("id")
        files = v.get("video_files") or []
        # Prefer portrait-ish files.
        best = None
        best_score = -1.0
        for f in files:
            w = float(f.get("width") or 0)
            h = float(f.get("height") or 0)
            link = str(f.get("link") or "")
            if not link or w <= 0 or h <= 0:
                continue
            ar = w / h
            # Target ~9:16 => 0.5625
            score = -abs(ar - 0.5625) + (min(h, 2000) / 2000.0) * 0.1
            if score > best_score:
                best_score = score
                best = {"url": link, "width": int(w), "height": int(h)}
        if best and vid:
            out.append({"provider": "pexels", "id": str(vid), **best})
    return out


def _storyblocks_sign(*, private_key: str, path: str, expires: int) -> str:
    """Return Storyblocks HMAC signature.

    Verified against /api/v2 responses: sign only the URL path (no querystring).

    HMAC = hex(hmac_sha256(key=(private_key + EXPIRES), msg=PATH))
    """

    key = (private_key + str(expires)).encode("utf-8")
    msg = path.encode("utf-8")
    return hmac.new(key, msg=msg, digestmod=hashlib.sha256).hexdigest()


def search_storyblocks(
    *, query: str, per_page: int, cache_dir: Path
) -> list[dict[str, Any]]:
    cache_path = cache_dir / f"storyblocks-{sha1_text(query)}.json"
    if cache_path.exists():
        data = read_json(cache_path, default={})
    else:
        public = get_secret(
            env_var="STORYBLOCKS_PUBLIC_API_KEY",
            op_ref="op://Claude/storyblocks/api key public",
        )
        private = get_secret(
            env_var="STORYBLOCKS_PRIVATE_API_KEY",
            op_ref="op://Claude/storyblocks/api key private",
        )
        expires = int(time.time())
        path = "/api/v2/videos/search"
        # Trial keys appear to accept user_id/project_id = 1.
        user_id = "1"
        project_id = "1"
        params = {
            "keywords": query,
            "results_per_page": str(per_page),
            "page": "1",
            "user_id": user_id,
            "project_id": project_id,
            "APIKEY": public,
            "EXPIRES": str(expires),
        }
        h = _storyblocks_sign(private_key=private, path=path, expires=expires)
        url = f"{STORYBLOCKS_BASE}{path}?{urllib.parse.urlencode(params)}&HMAC={h}"
        data = http_get_json(url, timeout=60)
        write_json(cache_path, data)

    out: list[dict[str, Any]] = []
    for it in (data.get("results") or [])[:per_page]:
        # The API shape varies by version; keep minimal fields.
        asset_id = it.get("id") or it.get("uuid") or it.get("stock_item_id")
        if not asset_id:
            continue
        out.append({"provider": "storyblocks", "id": str(asset_id), "raw": it})
    return out


def storyblocks_download_video(
    *, asset_id: str, out_path: Path, cache_dir: Path
) -> None:
    """Download a Storyblocks asset by id with caching.

    This performs a signed request to retrieve a direct download URL, then downloads.
    """

    public = get_secret(
        env_var="STORYBLOCKS_PUBLIC_API_KEY",
        op_ref="op://Claude/storyblocks/api key public",
    )
    private = get_secret(
        env_var="STORYBLOCKS_PRIVATE_API_KEY",
        op_ref="op://Claude/storyblocks/api key private",
    )
    expires = int(time.time())
    # Best-effort v2 download endpoint (common in Storyblocks partners).
    path = f"/api/v2/videos/download/{asset_id}"
    params = {
        "user_id": "1",
        "project_id": "1",
        "APIKEY": public,
        "EXPIRES": str(expires),
    }
    h = _storyblocks_sign(private_key=private, path=path, expires=expires)
    url = f"{STORYBLOCKS_BASE}{path}?{urllib.parse.urlencode(params)}&HMAC={h}"

    cache_path = cache_dir / f"storyblocks-download-{asset_id}.json"
    if cache_path.exists():
        data = read_json(cache_path, default={})
    else:
        data = http_get_json(url, timeout=60)
        write_json(cache_path, data)

    dl_url = (
        (data.get("download_url") if isinstance(data, dict) else None)
        or (data.get("url") if isinstance(data, dict) else None)
        or (data.get("data", {}) or {}).get("download_url")
    )
    if not dl_url:
        raise RuntimeError(
            f"Storyblocks download response missing download_url for {asset_id}"
        )
    download_file(str(dl_url), out_path)


def download_first_available(
    *,
    query: str,
    out_dir: Path,
    cache_dir: Path,
    storyblocks_counter_path: Path,
    storyblocks_max_total: int,
    storyblocks_max_this_run: int,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Return {provider, id, path} for the first downloadable clip.

    NOTE: Storyblocks download wiring is best-effort; we strongly prefer Pexels.
    """

    candidates = search_pexels(query=query, per_page=5, cache_dir=cache_dir)
    for c in candidates:
        out_path = out_dir / f"pexels-{c['id']}.mp4"
        if out_path.exists():
            return {"provider": "pexels", "id": c["id"], "path": str(out_path)}
        if dry_run:
            return {
                "provider": "pexels",
                "id": c["id"],
                "path": str(out_path),
                "dry_run": True,
            }
        download_file(str(c["url"]), out_path)
        return {"provider": "pexels", "id": c["id"], "path": str(out_path)}

    # Fallback: Storyblocks.
    sb = search_storyblocks(query=query, per_page=5, cache_dir=cache_dir)
    if not sb:
        raise RuntimeError(f"No stock results for query: {query}")

    counter = read_json(storyblocks_counter_path, default={"videos": 0})
    used_total = int(counter.get("videos") or 0)
    used_this_run = 0

    for c in sb:
        asset_id = str(c["id"])
        out_path = out_dir / f"storyblocks-{asset_id}.mp4"
        if out_path.exists():
            return {"provider": "storyblocks", "id": asset_id, "path": str(out_path)}

        if used_total + used_this_run >= storyblocks_max_total:
            raise RuntimeError(
                f"Storyblocks video download cap exceeded: {used_total + used_this_run} >= {storyblocks_max_total}"
            )
        if used_this_run >= storyblocks_max_this_run:
            raise RuntimeError(
                f"Storyblocks per-run cap exceeded: {used_this_run} >= {storyblocks_max_this_run}"
            )

        if dry_run:
            return {
                "provider": "storyblocks",
                "id": asset_id,
                "path": str(out_path),
                "dry_run": True,
            }

        storyblocks_download_video(
            asset_id=asset_id, out_path=out_path, cache_dir=cache_dir
        )
        used_this_run += 1

        counter["videos"] = int(used_total + used_this_run)
        write_json(storyblocks_counter_path, counter)
        return {"provider": "storyblocks", "id": asset_id, "path": str(out_path)}

    raise RuntimeError(
        f"Storyblocks search returned candidates but none were downloadable: {query}"
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--query", required=True)
    p.add_argument("--out-dir", default="hyperframes/stock")
    p.add_argument("--cache-dir", default="assets/cache")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    res = download_first_available(
        query=args.query,
        out_dir=Path(args.out_dir),
        cache_dir=Path(args.cache_dir),
        storyblocks_counter_path=Path(args.cache_dir) / "storyblocks_downloads.json",
        storyblocks_max_total=5,
        storyblocks_max_this_run=3,
        dry_run=bool(args.dry_run),
    )
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
