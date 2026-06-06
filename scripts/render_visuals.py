#!/usr/bin/env python3
"""Runware visuals renderer for ThreatNoir Cyber News (b-roll mode).

Generates:
- N still images (default 8) via Runware `imageInference`
- 1 short hero clip via Runware `videoInference` (Seedance 2.0 Fast)

Also tracks per-short cost and enforces a hard cap ($0.50) for Runware media.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from _util import brand, get_secret

RUNWARE_API = "https://api.runware.ai/v1"

# Pinned defaults (LEN-1717)
DEFAULT_STILL_MODEL = "rundiffusion:200@100"  # Juggernaut Z
DEFAULT_HERO_MODEL = "bytedance:seedance@2.0-fast"  # Seedance 2.0 Fast

# Best-effort cost estimates used when the API response omits `cost`.
EST_STILL_COST_USD = 0.015
EST_HERO_COST_USD = 0.24

LOCKED_STYLE_SUFFIX = (
    "cinematic cyberpunk, neon teal and magenta accents, dim violet ambient, "
    "slight scanlines, subtle chromatic aberration, broadcast-news composition, "
    "vertical 9:16, no faces of real people, no readable text, no logos"
)


NEGATIVE_PROMPT = (
    "text, words, letters, captions, watermarks, logos, signage, typography, "
    "signs, labels, ui, hud, numbers, fonts, screen text, sign boards, "
    "lower thirds, on-screen graphics, real human faces, distorted faces, "
    "extra fingers, deformed hands"
)


class CostCapExceeded(RuntimeError):
    pass


def log(msg: str) -> None:
    print(f"[render_visuals] {msg}", flush=True)


def runware_key() -> str:
    return get_secret(env_var="RUNWARE_API_KEY", op_ref="op://Claude/runware/api key")


def _post_tasks(api_key: str, tasks: list[dict], timeout: float = 120.0) -> dict:
    body = json.dumps(tasks).encode("utf-8")
    req = urllib.request.Request(
        RUNWARE_API,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        # Runware returns useful JSON error bodies; surface them for debugging.
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        raise RuntimeError(f"Runware HTTP {e.code}: {body[:2000]}") from e


def _download(url: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, out_path)


@dataclass
class CostItem:
    label: str
    cost: float
    meta: dict


@dataclass
class CostTracker:
    cap: float
    items: list[CostItem]

    @property
    def total(self) -> float:
        return float(sum(i.cost for i in self.items))

    def add(self, *, label: str, cost: float | None, meta: dict | None = None) -> None:
        c = float(cost or 0.0)
        self.items.append(CostItem(label=label, cost=c, meta=meta or {}))
        if self.total > self.cap + 1e-9:
            raise CostCapExceeded(
                f"Runware cost cap exceeded: ${self.total:.4f} > ${self.cap:.2f}"
            )

    def to_json(self) -> dict:
        return {
            "currency": "USD",
            "cap": self.cap,
            "total": round(self.total, 6),
            "items": [
                {"label": i.label, "cost": round(i.cost, 6), "meta": i.meta}
                for i in self.items
            ],
        }

    @classmethod
    def from_json(cls, data: dict, *, fallback_cap: float) -> "CostTracker":
        cap = float(data.get("cap") or fallback_cap)
        items: list[CostItem] = []
        raw_items = data.get("items")
        if isinstance(raw_items, list):
            for it in raw_items:
                if not isinstance(it, dict):
                    continue
                items.append(
                    CostItem(
                        label=str(it.get("label") or ""),
                        cost=float(it.get("cost") or 0.0),
                        meta=dict(it.get("meta") or {}),
                    )
                )
        return cls(cap=cap, items=items)


def _enforce_style(prompt: str) -> str:
    p = (prompt or "").strip()
    if not p:
        p = "cybersecurity news b-roll"
    # Always append the locked suffix; do not allow callers to omit.
    return f"{p}. {LOCKED_STYLE_SUFFIX}. no on-screen text, no subtitles, no UI labels"


def build_still_prompts(parsed: dict, *, count: int) -> list[str]:
    """Create curated b-roll prompts for Runware still generation.

    Rules (LEN-1717):
    - Never use spoken line text as the image prompt.
    - If a line contains `[visual: ...]` (or has `visual_prompt`), prefer that.
    - Otherwise, pick from a curated prompt bank based on scene titles.
    """

    visual_re = re.compile(r"\[visual:\s*([^\]]+)\]", re.IGNORECASE)

    # 1) Explicit directives (highest priority)
    directives: list[str] = []
    for ln in list(parsed.get("lines") or []):
        if not isinstance(ln, dict):
            continue
        vp = str(ln.get("visual_prompt") or "").strip()
        if vp:
            directives.append(vp)
            continue
        t = str(ln.get("text") or "")
        m = visual_re.search(t)
        if m:
            directives.append(str(m.group(1) or "").strip())
            # Strip marker so downstream consumers never speak it (best-effort).
            ln["text"] = visual_re.sub("", t).strip()

    if directives:
        out: list[str] = []
        i = 0
        while len(out) < count:
            out.append(directives[i % len(directives)])
            i += 1
        return out

    # 2) Curated prompt bank (fallback)
    bank: dict[str, list[str]] = {
        "opener": [
            "dim data center aisle, neon teal undertones, racks fading into haze, anonymous silhouette walking away",
            "wide cinematic server hall, cyan rim light, floating dust, shallow depth of field",
            "dark cyber newsroom backdrop, abstract threat map glow, teal and magenta accents",
        ],
        "setup": [
            "abstract glowing circuit board macro, magenta veins, depth-of-field, no signage",
            "fiber optic bundle close-up, teal strands, soft bokeh, high contrast",
            "secure facility corridor, red warning ambience, out-of-focus monitors, no text",
        ],
        "incident": [
            "fragmenting glass padlock, shards flying, magenta on near-black, dramatic lighting",
            "glitching digital lock icon rendered as 3D object, neon teal smoke, cinematic",
            "burning circuit trace, sparks, dark background, teal highlights, no words",
        ],
        "defensive": [
            "vault door closing, soft cyan rim light, heavy steel texture, no logos",
            "secure key exchange abstract, glowing nodes linking, teal and magenta, shallow depth",
            "hands typing on mechanical keyboard, close-up, no UI, moody lighting (no faces)",
        ],
        "outro": [
            "wide cinematic city skyline at night, fiber-optic streaks, dim violet horizon",
            "satellite view of night city grid, neon lines, subtle scanlines, no labels",
            "abstract closing shot: dark gradient, teal glow bars, broadcast vibe",
        ],
        "generic": [
            "dark SOC operations room, glowing screens out of focus, teal and magenta ambience, no readable text",
            "abstract cyber threat visualization, particles forming network graph, cinematic lighting",
            "encrypted data stream abstraction, teal glyph-like shapes (non-readable), depth of field",
        ],
    }

    def category_for_title(title: str) -> str:
        t = (title or "").upper()
        if "OPEN" in t or "INTRO" in t:
            return "opener"
        if "SETUP" in t or "CONTEXT" in t:
            return "setup"
        if any(
            k in t
            for k in [
                "INCIDENT",
                "BREACH",
                "ATTACK",
                "MALWARE",
                "EXPLOIT",
                "LEAK",
                "RANSOM",
            ]
        ):
            return "incident"
        if any(k in t for k in ["TAKEAWAY", "DEFEN", "MITIG", "PATCH", "REMED"]):
            return "defensive"
        if "OUTRO" in t or "WRAP" in t or "CLOSE" in t:
            return "outro"
        return "generic"

    scene_titles: list[str] = []
    for sc in list(parsed.get("scenes") or []):
        if isinstance(sc, dict):
            tt = str(sc.get("title") or "").strip()
            if tt:
                scene_titles.append(tt)
    if not scene_titles:
        scene_titles = ["GENERIC"]

    out2: list[str] = []
    for i in range(count):
        title = scene_titles[i % len(scene_titles)]
        cat = category_for_title(title)
        choices = bank.get(cat) or bank["generic"]
        # Deterministic selection with some variety.
        pick = (i * 5 + len(title)) % len(choices)
        out2.append(choices[pick])
    return out2


def _maybe_notify_abort(msg: str) -> None:
    # Best-effort: only if Discord user id is configured.
    user_id = (
        brand("OPERATOR_DISCORD_ID", "")
        or os.environ.get("DISCORD_DM_USER_ID", "").strip()
    ).strip()
    if not user_id:
        return
    try:
        import discord_notify  # type: ignore

        discord_notify.send_dm(recipient_id=user_id, message=msg)
    except Exception:
        return


def generate_stills(
    *,
    api_key: str,
    prompts: list[str],
    model: str,
    width: int,
    height: int,
    out_dir: Path,
    cost: CostTracker,
) -> tuple[list[Path], list[str]]:
    tasks: list[dict] = []
    uuids: list[str] = []
    for p in prompts:
        tu = str(uuid.uuid4())
        uuids.append(tu)
        tasks.append(
            {
                "taskType": "imageInference",
                "taskUUID": tu,
                "model": model,
                "positivePrompt": _enforce_style(p),
                "negativePrompt": NEGATIVE_PROMPT,
                "width": width,
                "height": height,
                "includeCost": True,
                "numberResults": 1,
            }
        )

    log(f"Runware imageInference x{len(tasks)} (model={model}, {width}x{height})")
    resp = _post_tasks(api_key, tasks, timeout=180.0)
    errors = resp.get("errors") or []
    if errors:
        raise RuntimeError(f"Runware imageInference errors: {errors}")

    data = resp.get("data") or []
    by_uuid = {str(d.get("taskUUID")): d for d in data if d.get("taskUUID")}

    out_paths: list[Path] = []
    out_urls: list[str] = []
    for idx, tu in enumerate(uuids, start=1):
        d = by_uuid.get(tu) or {}
        url = d.get("imageURL")
        if not url:
            raise RuntimeError(
                f"Runware imageInference missing imageURL for task {tu}: {d}"
            )
        out_urls.append(str(url))
        c = d.get("cost")
        cost.add(
            label="runware.imageInference",
            cost=float(c or 0.0),
            meta={"taskUUID": tu, "model": model},
        )

        out_path = out_dir / f"still-{idx:02d}.jpg"
        _download(str(url), out_path)
        out_paths.append(out_path)
    return out_paths, out_urls


def generate_hero_clip(
    *,
    api_key: str,
    seed_image_url: str,
    prompt: str,
    model: str,
    resolution: str,
    duration_s: float,
    out_path: Path,
    cost: CostTracker,
    timeout_s: float = 900.0,
) -> Path:
    task_uuid = str(uuid.uuid4())
    req = {
        "taskType": "videoInference",
        "taskUUID": task_uuid,
        "deliveryMethod": "async",
        "model": model,
        "positivePrompt": _enforce_style(prompt),
        "resolution": resolution,
        # Runware requires integer seconds.
        "duration": int(duration_s),
        "settings": {"audio": False},
        "inputs": {"frameImages": [str(seed_image_url)]},
        "includeCost": True,
        "numberResults": 1,
        # Keep the URL around long enough for our CLI to download it.
        "ttl": 3600,
    }

    log(
        f"Runware videoInference async (model={model}, resolution={resolution}, duration={duration_s}s)"
    )
    resp = _post_tasks(api_key, [req], timeout=60.0)
    errors = resp.get("errors") or []
    if errors:
        raise RuntimeError(f"Runware videoInference submit errors: {errors}")

    # Poll with exponential-ish backoff.
    deadline = time.time() + timeout_s
    delay = 2.0
    while time.time() < deadline:
        time.sleep(delay)
        delay = min(delay * 1.35, 15.0)
        poll = _post_tasks(
            api_key, [{"taskType": "getResponse", "taskUUID": task_uuid}], timeout=30.0
        )
        poll_errors = poll.get("errors") or []
        if poll_errors:
            # If the generation failed, errors will carry taskUUID.
            raise RuntimeError(f"Runware getResponse errors: {poll_errors}")
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
        if status == "error":
            raise RuntimeError(f"Runware videoInference failed: {hit}")
        if status != "success":
            continue

        url = hit.get("videoURL")
        if not url:
            raise RuntimeError(
                f"Runware videoInference success but missing videoURL: {hit}"
            )
        c = hit.get("cost")
        cost.add(
            label="runware.videoInference",
            cost=float(c or 0.0),
            meta={"taskUUID": task_uuid, "model": model},
        )
        _download(str(url), out_path)
        return out_path

    raise TimeoutError(f"Runware videoInference timed out after {timeout_s:.0f}s")


def generate_broll(
    *,
    parsed: dict,
    out_dir: Path,
    still_count: int = 8,
    still_model: str = DEFAULT_STILL_MODEL,
    hero_model: str = DEFAULT_HERO_MODEL,
    still_w: int = 1024,
    # Many diffusion backends require dimensions in multiples of 64.
    still_h: int = 1792,
    hero_resolution: str = "480p",
    hero_duration_s: float = 4.0,
    cost_cap: float = 0.50,
    force: bool = False,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    stills_dir = out_dir / "stills"
    hero_path = out_dir / "hero.mp4"
    manifest_path = stills_dir / "manifest.json"
    runware_cost_path = out_dir / "runware.cost.json"

    # Cache-friendly behavior:
    # - If stills+hero exist: reuse everything.
    # - If stills exist but hero is missing: reuse stills and only generate hero.
    expected_stills = [
        stills_dir / f"still-{i:02d}.jpg" for i in range(1, still_count + 1)
    ]
    if not force and hero_path.exists() and all(p.exists() for p in expected_stills):
        cached_cost = CostTracker(cap=cost_cap, items=[])
        if runware_cost_path.exists():
            try:
                cached_cost = CostTracker.from_json(
                    json.loads(runware_cost_path.read_text(encoding="utf-8")),
                    fallback_cap=cost_cap,
                )
                cached_cost.cap = cost_cap
            except Exception:
                cached_cost = CostTracker(cap=cost_cap, items=[])
        if not cached_cost.items:
            # If we don't have persisted cost, fall back to conservative estimates.
            cached_cost.items = [
                CostItem(
                    label="runware.estimate.stills",
                    cost=float(still_count) * EST_STILL_COST_USD,
                    meta={"estimated": True, "count": still_count},
                ),
                CostItem(
                    label="runware.estimate.hero",
                    cost=EST_HERO_COST_USD,
                    meta={"estimated": True, "duration_s": int(hero_duration_s)},
                ),
            ]
            runware_cost_path.write_text(
                json.dumps(cached_cost.to_json(), indent=2),
                encoding="utf-8",
            )
        return {
            "stills": expected_stills,
            "hero": hero_path,
            "cost": cached_cost,
            "cached": True,
        }

    api_key = runware_key()
    cost = CostTracker(cap=cost_cap, items=[])

    try:
        prompts = build_still_prompts(parsed, count=still_count)

        stills_exist = all(p.exists() for p in expected_stills)
        if not force and stills_exist:
            still_paths = expected_stills
            still_urls: list[str] = []
            if manifest_path.exists():
                try:
                    mf = json.loads(manifest_path.read_text(encoding="utf-8"))
                    urls = mf.get("urls")
                    if isinstance(urls, list):
                        still_urls = [str(u) for u in urls if str(u).strip()]
                except Exception:
                    still_urls = []
        else:
            still_paths, still_urls = generate_stills(
                api_key=api_key,
                prompts=prompts,
                model=still_model,
                width=still_w,
                height=still_h,
                out_dir=stills_dir,
                cost=cost,
            )
            stills_dir.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "model": still_model,
                        "width": still_w,
                        "height": still_h,
                        "prompts": prompts,
                        "urls": still_urls,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

        # Hero clip seeded from a still's remote URL, or a best-effort seed query.
        seed_url = still_urls[0] if still_urls else ""
        if not seed_url:
            seed_task_uuid = str(uuid.uuid4())
            seed_prompt = prompts[0] if prompts else "cybersecurity news b-roll"
            seed_resp = _post_tasks(
                api_key,
                [
                    {
                        "taskType": "imageInference",
                        "taskUUID": seed_task_uuid,
                        "model": still_model,
                        "positivePrompt": _enforce_style(seed_prompt),
                        "negativePrompt": NEGATIVE_PROMPT,
                        "width": still_w,
                        "height": still_h,
                        "includeCost": True,
                        "numberResults": 1,
                    }
                ],
                timeout=180.0,
            )
            if seed_resp.get("errors"):
                raise RuntimeError(
                    f"Runware seed still errors: {seed_resp.get('errors')}"
                )
            seed_data = (seed_resp.get("data") or [None])[0] or {}
            seed_url = str(seed_data.get("imageURL") or "").strip()
            if not seed_url:
                raise RuntimeError(f"Runware seed still missing imageURL: {seed_data}")
            cost.add(
                label="runware.imageInference.seed",
                cost=float(seed_data.get("cost") or 0.0),
                meta={"taskUUID": seed_task_uuid, "model": still_model},
            )

        hero = generate_hero_clip(
            api_key=api_key,
            seed_image_url=seed_url,
            prompt="hero shot, kinetic cyber newsroom b-roll, abstract threat visuals",
            model=hero_model,
            resolution=hero_resolution,
            duration_s=hero_duration_s,
            out_path=hero_path,
            cost=cost,
        )
        runware_cost_path.write_text(
            json.dumps(cost.to_json(), indent=2),
            encoding="utf-8",
        )
        return {
            "stills": still_paths,
            "hero": hero,
            "cost": cost,
            "cached": False,
        }
    except CostCapExceeded as e:
        _maybe_notify_abort(f"ThreatNoir short visuals aborted: {e}")
        raise
    except Exception as e:
        _maybe_notify_abort(f"ThreatNoir short visuals failed: {e}")
        raise


def main() -> int:
    p = argparse.ArgumentParser(description="Generate Runware b-roll assets")
    p.add_argument("--parsed", required=True, help="Path to parsed short JSON")
    p.add_argument("--out-dir", required=True, help="Output directory for visuals")
    p.add_argument("--stills", type=int, default=8)
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    parsed = json.loads(Path(args.parsed).read_text(encoding="utf-8"))
    res = generate_broll(
        parsed=parsed,
        out_dir=Path(args.out_dir),
        still_count=int(args.stills),
        force=bool(args.force),
    )
    log(f"stills: {len(res['stills'])}, hero: {res['hero']}")
    log(f"cost: ${res['cost'].total:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
