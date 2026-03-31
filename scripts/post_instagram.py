#!/usr/bin/env python3
"""Post carousel content to Instagram via Graph API.

Usage:
  python3 post_instagram.py --images "url1,url2,url3" "Caption text"
  python3 post_instagram.py --dry-run --images "url1,url2" "Caption text"

Requires env vars:
  INSTAGRAM_BUSINESS_ACCOUNT_ID — numeric Instagram Business Account ID
  INSTAGRAM_ACCESS_TOKEN        — long-lived token (~60 day expiry)
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

BASE_URL = "https://graph.facebook.com/v21.0"

POLL_INTERVAL_SECS = 3
POLL_TIMEOUT_SECS = 30


def post_carousel_to_instagram(image_urls: list[str], caption: str, dry_run: bool = False) -> str:
    """Publish a carousel post to Instagram. Returns permalink URL."""
    if not ensure_setup("instagram", interactive=sys.stdin.isatty()):
        print("Error: Instagram not configured. Run: python3 configure.py instagram", file=sys.stderr)
        sys.exit(1)

    account_id = os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")

    if len(image_urls) < 2:
        print("Error: carousel requires at least 2 images", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        print(f"[DRY RUN] Would post Instagram carousel ({len(image_urls)} images):", file=sys.stderr)
        for i, url in enumerate(image_urls, 1):
            print(f"  Image {i}: {url}", file=sys.stderr)
        print(f"  Caption ({len(caption)} chars): {caption}", file=sys.stderr)
        return "https://www.instagram.com/p/dry-run"

    ensure_fresh_token("instagram")
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")

    # Step 1: Upload each image as a carousel item media object
    media_ids = []
    for i, image_url in enumerate(image_urls, 1):
        print(f"Uploading image {i}/{len(image_urls)}...", file=sys.stderr)
        upload_resp = retry_on_5xx(
            lambda url=image_url: requests.post(
                f"{BASE_URL}/{account_id}/media",
                params={
                    "image_url": url,
                    "is_carousel_item": "true",
                    "access_token": token,
                },
            ),
            f"upload image {i}",
        )
        media_ids.append(upload_resp.json()["id"])

    # Step 2: Create carousel container
    print("Creating carousel container...", file=sys.stderr)
    container_resp = retry_on_5xx(
        lambda: requests.post(
            f"{BASE_URL}/{account_id}/media",
            params={
                "media_type": "CAROUSEL",
                "children": ",".join(media_ids),
                "caption": caption,
                "access_token": token,
            },
        ),
        "create carousel container",
    )
    container_id = container_resp.json()["id"]

    # Step 3: Poll for container status until FINISHED
    print("Waiting for container to finish processing...", file=sys.stderr)
    elapsed = 0
    while elapsed < POLL_TIMEOUT_SECS:
        status_resp = requests.get(
            f"{BASE_URL}/{container_id}",
            params={
                "fields": "status_code",
                "access_token": token,
            },
        )
        status_resp.raise_for_status()
        status_code = status_resp.json().get("status_code", "")
        if status_code == "FINISHED":
            break
        if status_code == "ERROR":
            print(f"Error: container processing failed (status: {status_code})", file=sys.stderr)
            sys.exit(1)
        time.sleep(POLL_INTERVAL_SECS)
        elapsed += POLL_INTERVAL_SECS
    else:
        print(f"Error: container status polling timed out after {POLL_TIMEOUT_SECS}s", file=sys.stderr)
        sys.exit(1)

    # Step 4: Publish
    print("Publishing...", file=sys.stderr)
    publish_resp = retry_on_5xx(
        lambda: requests.post(
            f"{BASE_URL}/{account_id}/media_publish",
            params={
                "creation_id": container_id,
                "access_token": token,
            },
        ),
        "publish",
    )
    post_id = publish_resp.json()["id"]

    # Step 5: Get permalink
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
        ensure_setup("instagram", interactive=True)
        sys.exit(0)

    args = sys.argv[1:]
    dry_run = False
    images_arg = None

    if "--dry-run" in args:
        dry_run = True
        args.remove("--dry-run")

    if "--images" in args:
        idx = args.index("--images")
        if idx + 1 >= len(args):
            print("Error: --images requires a value", file=sys.stderr)
            sys.exit(1)
        images_arg = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if not images_arg:
        print("Usage: python3 post_instagram.py [--dry-run] --images \"url1,url2,...\" \"Caption text\"", file=sys.stderr)
        sys.exit(1)

    if not args:
        print("Error: caption text is required as a positional argument", file=sys.stderr)
        print("Usage: python3 post_instagram.py [--dry-run] --images \"url1,url2,...\" \"Caption text\"", file=sys.stderr)
        sys.exit(1)

    image_urls = [u.strip() for u in images_arg.split(",") if u.strip()]
    caption_text = args[0]

    permalink = post_carousel_to_instagram(image_urls, caption_text, dry_run=dry_run)
    print(permalink)
