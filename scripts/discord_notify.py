#!/usr/bin/env python3
"""Discord DM helper.

Used by the rendering pipeline for abort / cost-cap notifications.

Auth:
- DISCORD_BOT_TOKEN env var, or
- 1Password item: op://Claude/Discord/token

This script intentionally avoids printing secrets.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request

from _util import brand, get_secret

DISCORD_API = "https://discord.com/api/v10"
DISCORD_USER_AGENT = brand(
    "DISCORD_USER_AGENT",
    f"DiscordBot ({brand('BRAND_URL', 'https://threatnoir.com')}, 0.1)",
)


def _bot_token() -> str:
    try:
        return get_secret(
            env_var="DISCORD_BOT_TOKEN", op_ref="op://Claude/Discord/token"
        )
    except Exception:
        return ""


def _post_json(url: str, token: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": DISCORD_USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=20.0) as r:
        return json.loads(r.read())


def send_dm(*, recipient_id: str, message: str) -> bool:
    """Send a DM to a Discord user id. Returns True if likely successful."""
    rid = str(recipient_id or "").strip()
    if not rid:
        return False

    token = _bot_token()
    if not token:
        return False

    try:
        ch = _post_json(
            f"{DISCORD_API}/users/@me/channels",
            token,
            {"recipient_id": rid},
        )
        channel_id = ch.get("id", "")
        if not channel_id:
            return False
        _post_json(
            f"{DISCORD_API}/channels/{channel_id}/messages",
            token,
            {"content": message},
        )
        return True
    except urllib.error.URLError:
        return False


def main() -> int:
    p = argparse.ArgumentParser(description="Send a DM to a Discord user")
    p.add_argument("--user-id", required=True, help="Discord recipient user id")
    p.add_argument("--message", required=True, help="Message content")
    args = p.parse_args()

    ok = send_dm(recipient_id=str(args.user_id), message=str(args.message))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
