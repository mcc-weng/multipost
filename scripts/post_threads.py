#!/usr/bin/env python3
"""Post text content to Threads via Graph API.

Usage:
  python3 post_threads.py "Post text here"
  python3 post_threads.py --topic "Technology" "Post text here"
  python3 post_threads.py --dry-run "Post text here"

Requires env vars:
  THREADS_ACCESS_TOKEN — long-lived token (~60 day expiry)
  THREADS_USER_ID — numeric Threads user ID
"""

import json
import os
import sys
import time
import requests
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.shared import load_env, ensure_setup, ensure_fresh_token, handle_error, retry_on_5xx
load_env()

BASE_URL = "https://graph.threads.net/v1.0"


def post_to_threads(text: str, topic: str = None, dry_run: bool = False) -> str:
    """Publish a text post to Threads. Returns permalink URL."""
    if not ensure_setup("threads", interactive=sys.stdin.isatty()):
        print("Error: Threads not configured. Run: python3 configure.py threads", file=sys.stderr)
        sys.exit(1)

    token = os.environ.get("THREADS_ACCESS_TOKEN")
    user_id = os.environ.get("THREADS_USER_ID")

    if dry_run:
        topic_str = f" [topic: {topic}]" if topic else ""
        print(f"[DRY RUN] Would post to Threads ({len(text)} chars){topic_str}:", file=sys.stderr)
        print(text, file=sys.stderr)
        return "https://threads.net/dry-run"

    ensure_fresh_token("threads")
    token = os.environ.get("THREADS_ACCESS_TOKEN")

    # Step 1: Create container
    create_params = {
        "media_type": "TEXT",
        "text": text,
        "access_token": token,
    }
    if topic:
        create_params["topic_tag"] = topic

    create_resp = retry_on_5xx(
        lambda: requests.post(
            f"{BASE_URL}/{user_id}/threads",
            params=create_params,
        ),
        "create container",
    )
    creation_id = create_resp.json()["id"]

    # Wait for container to finish processing
    time.sleep(3)

    # Step 2: Publish
    publish_resp = retry_on_5xx(
        lambda: requests.post(
            f"{BASE_URL}/{user_id}/threads_publish",
            params={
                "creation_id": creation_id,
                "access_token": token,
            },
        ),
        "publish",
    )
    post_id = publish_resp.json()["id"]

    # Step 3: Get permalink
    permalink_resp = requests.get(
        f"{BASE_URL}/{post_id}",
        params={
            "fields": "permalink",
            "access_token": token,
        },
    )
    permalink_resp.raise_for_status()
    return permalink_resp.json().get("permalink", f"Post ID: {post_id}")


if __name__ == "__main__":
    if "--setup" in sys.argv:
        from scripts.shared import ensure_setup
        ensure_setup("threads", interactive=True)
        sys.exit(0)

    args = sys.argv[1:]
    dry_run = False
    topic = None
    if "--dry-run" in args:
        dry_run = True
        args.remove("--dry-run")
    if "--topic" in args:
        idx = args.index("--topic")
        topic = args[idx + 1]
        args.pop(idx)  # remove --topic
        args.pop(idx)  # remove topic value

    if not args:
        print("Usage: python3 post_threads.py [--dry-run] [--topic \"Topic\"] \"Post text\"", file=sys.stderr)
        sys.exit(1)

    text = args[0]
    permalink = post_to_threads(text, topic=topic, dry_run=dry_run)
    print(permalink)
