from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def sha1_text(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8"), usedforsecurity=False).hexdigest()


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def op_read(ref: str) -> str:
    res = subprocess.run(
        ["op", "read", ref], capture_output=True, text=True, check=True
    )
    return res.stdout.strip()


def brand(key: str, default: str) -> str:
    """Read a non-secret brand/identity value from env with a safe fallback."""
    v = os.environ.get(key, "").strip()
    return v if v else default


def get_secret(*, env_var: str, op_ref: str | None) -> str:
    v = os.environ.get(env_var, "").strip()
    if v:
        return v
    if not op_ref:
        raise RuntimeError(f"Missing {env_var} and no op_ref provided")
    # Only allow op:// reads when running with a 1Password service account token.
    # This keeps OSS usage env-first and avoids surprising interactive `op` prompts.
    if not os.environ.get("OP_SERVICE_ACCOUNT_TOKEN", "").strip():
        raise RuntimeError(
            f"Missing {env_var} and OP_SERVICE_ACCOUNT_TOKEN not set (op_ref available)"
        )
    return op_read(op_ref)


def _default_user_agent() -> str:
    # Prefer explicit overrides; otherwise derive from shipped brand defaults.
    short = brand("BRAND_SHORT_NAME", "ThreatNoir")
    url = brand("BRAND_URL", "https://threatnoir.com")
    return brand("BRAND_USER_AGENT", f"{short}CyberNews/0.1 (+{url})")


def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None,
    body: Any | None,
    timeout: float,
) -> Any:
    # Some providers (notably Pexels behind Cloudflare) may reject requests
    # without a User-Agent.
    hdrs: dict[str, str] = dict(headers or {})
    if not any(k.lower() == "user-agent" for k in hdrs):
        hdrs["User-Agent"] = _default_user_agent()

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers=hdrs,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", "replace")
        except Exception:
            raw = ""
        raise RuntimeError(f"HTTP {e.code}: {raw[:2000]}") from e


def http_get_json(
    url: str, *, headers: dict[str, str] | None = None, timeout: float = 60
) -> Any:
    return _http_json("GET", url, headers=headers, body=None, timeout=timeout)


def http_post_json(
    url: str, *, headers: dict[str, str] | None, body: Any, timeout: float = 120
) -> Any:
    return _http_json("POST", url, headers=headers, body=body, timeout=timeout)


def download_file(
    url: str,
    out_path: Path,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 180,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    hdrs: dict[str, str] = dict(headers or {})
    if not any(k.lower() == "user-agent" for k in hdrs):
        hdrs["User-Agent"] = _default_user_agent()

    req = urllib.request.Request(url, headers=hdrs, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            with out_path.open("wb") as f:
                while True:
                    chunk = r.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", "replace")
        except Exception:
            raw = ""
        raise RuntimeError(f"download failed HTTP {e.code}: {raw[:2000]}") from e


def b64_data_url_from_file(path: Path, mime: str) -> str:
    b = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b}"


def ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(out.stdout.strip() or 0.0)


def ffmpeg_silence(out_wav: Path, dur_s: float) -> None:
    if dur_s <= 0:
        dur_s = 0.01
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=mono",
            "-t",
            f"{dur_s:.3f}",
            str(out_wav),
        ],
        check=True,
    )


def ffmpeg_concat_wavs(parts: list[Path], out_wav: Path) -> None:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    list_file = out_wav.parent / "_concat_list.txt"
    list_file.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(out_wav),
        ],
        check=True,
    )
