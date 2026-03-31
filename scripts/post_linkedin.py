#!/usr/bin/env python3
"""Post text content to LinkedIn via Community Management API.

Usage:
  python3 post_linkedin.py "Post text here"
  python3 post_linkedin.py --media /path/to/image.jpg "Post text here"
  python3 post_linkedin.py --dry-run "Post text here"

Requires env vars:
  LINKEDIN_ACCESS_TOKEN — OAuth 2.0 token (~60 day expiry)
  LINKEDIN_PERSON_ID    — URN like urn:li:person:xxxxx
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.shared import load_env, ensure_setup, ensure_fresh_token, handle_error, retry_on_5xx
load_env()

API_BASE = "https://api.linkedin.com/v2"


def _upload_image(image_path, token, person_id):
    """Upload an image to LinkedIn. Returns the image URN."""
    register_payload = {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "owner": person_id,
            "serviceRelationships": [
                {
                    "relationshipType": "OWNER",
                    "identifier": "urn:li:userGeneratedContent",
                }
            ],
        }
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    register_resp = retry_on_5xx(
        lambda: requests.post(
            f"{API_BASE}/assets?action=registerUpload",
            headers=headers,
            json=register_payload,
        ),
        "register image upload",
    )
    register_data = register_resp.json()
    upload_url = register_data["value"]["uploadMechanism"][
        "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
    ]["uploadUrl"]
    asset = register_data["value"]["asset"]

    with open(image_path, "rb") as f:
        image_data = f.read()
    upload_resp = requests.put(
        upload_url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
        },
        data=image_data,
    )
    if upload_resp.status_code not in (200, 201):
        print(f"Error uploading image: {upload_resp.status_code}", file=sys.stderr)
        print(upload_resp.text, file=sys.stderr)
        sys.exit(1)

    return asset


def post_to_linkedin(text, media_path=None, dry_run=False):
    """Publish a post to LinkedIn. Returns the post URL."""
    if not ensure_setup("linkedin", interactive=sys.stdin.isatty()):
        print("Error: LinkedIn not configured. Run: python3 configure.py linkedin", file=sys.stderr)
        sys.exit(1)

    token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    person_id = os.environ.get("LINKEDIN_PERSON_ID")

    if dry_run:
        print(f"[DRY RUN] Would post to LinkedIn ({len(text)} chars):", file=sys.stderr)
        print(text, file=sys.stderr)
        if media_path:
            print(f"  With image: {media_path}", file=sys.stderr)
        return "https://linkedin.com/feed/dry-run"

    ensure_fresh_token("linkedin")
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    payload = {
        "author": person_id,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    if media_path:
        print(f"Uploading image: {media_path}...", file=sys.stderr)
        asset_urn = _upload_image(media_path, token, person_id)
        share_content = payload["specificContent"]["com.linkedin.ugc.ShareContent"]
        share_content["shareMediaCategory"] = "IMAGE"
        share_content["media"] = [
            {
                "status": "READY",
                "media": asset_urn,
            }
        ]

    resp = retry_on_5xx(
        lambda: requests.post(
            f"{API_BASE}/ugcPosts", headers=headers, json=payload
        ),
        "create post",
    )

    post_urn = resp.headers.get("X-RestLi-Id", resp.json().get("id", ""))
    if post_urn:
        return f"https://www.linkedin.com/feed/update/{post_urn}"
    return "Post published but could not get URL."


if __name__ == "__main__":
    if "--setup" in sys.argv:
        from scripts.shared import ensure_setup
        ensure_setup("linkedin", interactive=True)
        sys.exit(0)

    args = sys.argv[1:]
    dry_run = False
    media_path = None

    if "--dry-run" in args:
        dry_run = True
        args.remove("--dry-run")

    if "--media" in args:
        idx = args.index("--media")
        if idx + 1 >= len(args):
            print("Error: --media requires a file path", file=sys.stderr)
            sys.exit(1)
        media_path = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if not args:
        print('Usage: python3 post_linkedin.py [--dry-run] [--media /path/to/image] "Post text"', file=sys.stderr)
        sys.exit(1)

    url = post_to_linkedin(args[0], media_path=media_path, dry_run=dry_run)
    print(url)
