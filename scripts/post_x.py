#!/usr/bin/env python3
"""Post text content to X (Twitter) via API v2.

Usage:
  python3 post_x.py "Post text here"
  python3 post_x.py --dry-run "Post text here"

Requires env vars:
  X_API_KEY — API key (consumer key)
  X_API_SECRET — API secret (consumer secret)
  X_ACCESS_TOKEN — user access token
  X_ACCESS_TOKEN_SECRET — user access token secret

Note: X API uses a pay-per-usage model for write access.
"""

import json
import os
import sys
import time
import hashlib
import hmac
import base64
import urllib.parse
import uuid
import requests
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.shared import load_env, ensure_setup, handle_error, retry_on_5xx
load_env()

TWEET_URL = "https://api.twitter.com/2/tweets"


def _oauth_header(method, url, params, api_key, api_secret, token, token_secret):
    """Generate OAuth 1.0a Authorization header."""
    oauth_params = {
        "oauth_consumer_key": api_key,
        "oauth_nonce": uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }

    all_params = {**oauth_params, **params}
    sorted_params = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
        for k, v in sorted(all_params.items())
    )
    base_string = f"{method}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(sorted_params, safe='')}"
    signing_key = f"{urllib.parse.quote(api_secret, safe='')}&{urllib.parse.quote(token_secret, safe='')}"

    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()

    oauth_params["oauth_signature"] = signature
    auth_header = "OAuth " + ", ".join(
        f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"'
        for k, v in sorted(oauth_params.items())
    )
    return auth_header


def post_to_x(text: str, dry_run: bool = False) -> str:
    """Publish a tweet. Returns the tweet URL."""
    if not ensure_setup("x", interactive=sys.stdin.isatty()):
        print("Error: X not configured. Run: python3 configure.py x", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("X_API_KEY")
    api_secret = os.environ.get("X_API_SECRET")
    token = os.environ.get("X_ACCESS_TOKEN")
    token_secret = os.environ.get("X_ACCESS_TOKEN_SECRET")

    if len(text) > 280:
        print(f"Warning: Tweet is {len(text)} chars (limit 280). May be truncated.", file=sys.stderr)

    if dry_run:
        print(f"[DRY RUN] Would post to X ({len(text)} chars):", file=sys.stderr)
        print(text, file=sys.stderr)
        return "https://x.com/dry-run"

    payload = json.dumps({"text": text})

    def make_request():
        auth = _oauth_header("POST", TWEET_URL, {}, api_key, api_secret, token, token_secret)
        return requests.post(
            TWEET_URL,
            headers={
                "Authorization": auth,
                "Content-Type": "application/json",
            },
            data=payload,
        )

    resp = retry_on_5xx(make_request, "post tweet")
    data = resp.json()
    tweet_id = data.get("data", {}).get("id")

    if tweet_id:
        return f"https://x.com/i/status/{tweet_id}"
    else:
        return f"Tweet posted but could not get ID. Response: {json.dumps(data)}"


if __name__ == "__main__":
    if "--setup" in sys.argv:
        from scripts.shared import ensure_setup
        ensure_setup("x", interactive=True)
        sys.exit(0)

    args = sys.argv[1:]
    dry_run = False
    if "--dry-run" in args:
        dry_run = True
        args.remove("--dry-run")

    if not args:
        print('Usage: python3 post_x.py [--dry-run] "Post text"', file=sys.stderr)
        sys.exit(1)

    text = args[0]
    url = post_to_x(text, dry_run=dry_run)
    print(url)
