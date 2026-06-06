#!/usr/bin/env python3
"""One-time OAuth bootstrap for YouTube uploads.

This script runs a local webserver flow and prints the *refresh token*.

Store it in your secret store (e.g., 1Password, Vault, etc.).

Optional 1Password fields (used only when OP_SERVICE_ACCOUNT_TOKEN is set):
- op://Claude/Youtube/client-id
- op://Claude/Youtube/client-secret
"""

from __future__ import annotations

import argparse
import sys


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> int:
    from _util import brand, get_secret

    p = argparse.ArgumentParser(
        description=f"{brand('BRAND_SHORT_NAME', 'ThreatNoir')} — YouTube OAuth setup"
    )
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except Exception as e:  # pragma: no cover
        raise SystemExit(
            "Missing YouTube dependencies. Install with: pip install -r requirements.txt"
        ) from e

    client_id = get_secret(
        env_var="YOUTUBE_CLIENT_ID", op_ref="op://Claude/Youtube/client-id"
    )
    client_secret = get_secret(
        env_var="YOUTUBE_CLIENT_SECRET", op_ref="op://Claude/Youtube/client-secret"
    )

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(
        port=args.port, access_type="offline", prompt="consent"
    )

    refresh = getattr(creds, "refresh_token", None)
    if not refresh:
        print(
            "ERROR: No refresh_token received. Ensure you used 'offline' access.",
            file=sys.stderr,
        )
        return 2

    print("\n=== YouTube OAuth setup complete ===")
    print("Refresh token:")
    print(refresh)
    print("\nStore it in your secret manager of choice.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
