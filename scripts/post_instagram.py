#!/usr/bin/env python3
"""Post image content to Instagram via Graph API.

Usage:
  python3 post_instagram.py --images "url1,url2" "Caption text"
  python3 post_instagram.py --images "/path/to/local.jpg" "Caption text"
  python3 post_instagram.py --images "url1,url2,url3" "Caption text"
  python3 post_instagram.py --dry-run --images "/path/to/img.jpg" "Caption text"

Supports:
  - Single image post (1 image — local file or URL)
  - Carousel post (2+ images — local files or URLs, can mix)

Local files are uploaded to a temporary public URL via the Facebook Graph API
before being used in the Instagram post.

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
POLL_TIMEOUT_SECS = 60


def _is_url(s):
    """Check if string is a URL (vs local file path)."""
    return s.startswith("http://") or s.startswith("https://")


def _upload_local_image(file_path, account_id, token):
    """Upload a local image file via the Facebook Graph API. Returns the hosted URL."""
    path = Path(file_path)
    if not path.exists():
        print(f"Error: file not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    # Upload to Facebook as a photo (unpublished) to get a hosted URL
    print(f"  Uploading local file: {path.name}...", file=sys.stderr)
    with open(path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/{account_id}/media",
            data={
                "access_token": token,
                "media_type": "IMAGE",
                "is_carousel_item": "true",
            },
            files={"source": (path.name, f, "image/jpeg")},
        )

    if resp.status_code != 200:
        # Fallback: try using image_url approach with file:// won't work,
        # so we need to upload via the pages photo endpoint first
        print(f"  Direct upload failed ({resp.status_code}), trying photo upload...", file=sys.stderr)

        # Get the Facebook Page ID linked to this Instagram account
        page_resp = requests.get(
            f"{BASE_URL}/{account_id}",
            params={"fields": "id", "access_token": token},
        )

        # Upload as unpublished page photo to get a hosted URL
        with open(path, "rb") as f:
            photo_resp = requests.post(
                f"{BASE_URL}/{account_id}/media",
                params={
                    "access_token": token,
                },
                files={"source": (path.name, f, "image/jpeg")},
            )

        if photo_resp.status_code == 200:
            return photo_resp.json().get("id")
        else:
            print(f"Error uploading {path.name}: {photo_resp.status_code}", file=sys.stderr)
            print(photo_resp.text, file=sys.stderr)
            sys.exit(1)

    return resp.json().get("id")


def _resolve_image(image_ref, account_id, token, is_carousel_item=False):
    """Resolve an image reference (URL or local path) to an IG media container ID."""
    if _is_url(image_ref):
        params = {
            "image_url": image_ref,
            "access_token": token,
        }
        if is_carousel_item:
            params["is_carousel_item"] = "true"

        resp = retry_on_5xx(
            lambda: requests.post(
                f"{BASE_URL}/{account_id}/media",
                params=params,
            ),
            "upload image",
        )
        return resp.json()["id"]
    else:
        # Local file — upload via multipart
        path = Path(image_ref)
        if not path.exists():
            print(f"Error: file not found: {image_ref}", file=sys.stderr)
            sys.exit(1)

        print(f"  Uploading {path.name}...", file=sys.stderr)
        with open(path, "rb") as f:
            data = {
                "access_token": token,
            }
            if is_carousel_item:
                data["is_carousel_item"] = "true"

            resp = requests.post(
                f"{BASE_URL}/{account_id}/media",
                data=data,
                files={"source": (path.name, f, "image/jpeg")},
            )

        if 400 <= resp.status_code < 600:
            handle_error(resp, f"upload {path.name}")

        return resp.json()["id"]


def _poll_container(container_id, token):
    """Poll until container status is FINISHED. Returns True on success."""
    print("Waiting for processing...", file=sys.stderr)
    elapsed = 0
    while elapsed < POLL_TIMEOUT_SECS:
        status_resp = requests.get(
            f"{BASE_URL}/{container_id}",
            params={"fields": "status_code", "access_token": token},
        )
        status_resp.raise_for_status()
        status_code = status_resp.json().get("status_code", "")
        if status_code == "FINISHED":
            return True
        if status_code == "ERROR":
            print(f"Error: container processing failed", file=sys.stderr)
            sys.exit(1)
        time.sleep(POLL_INTERVAL_SECS)
        elapsed += POLL_INTERVAL_SECS
    print(f"Error: processing timed out after {POLL_TIMEOUT_SECS}s", file=sys.stderr)
    sys.exit(1)


def _publish_and_get_permalink(container_id, account_id, token):
    """Publish a container and return the permalink."""
    print("Publishing...", file=sys.stderr)
    publish_resp = retry_on_5xx(
        lambda: requests.post(
            f"{BASE_URL}/{account_id}/media_publish",
            params={"creation_id": container_id, "access_token": token},
        ),
        "publish",
    )
    post_id = publish_resp.json()["id"]

    permalink_resp = requests.get(
        f"{BASE_URL}/{post_id}",
        params={"fields": "permalink", "access_token": token},
    )
    permalink_resp.raise_for_status()
    return permalink_resp.json().get("permalink", f"Post ID: {post_id}")


def post_to_instagram(image_refs: list[str], caption: str, dry_run: bool = False) -> str:
    """Publish a single image or carousel post to Instagram. Returns permalink URL."""
    if not ensure_setup("instagram", interactive=sys.stdin.isatty()):
        print("Error: Instagram not configured. Run: python3 configure.py instagram", file=sys.stderr)
        sys.exit(1)

    account_id = os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")

    if not image_refs:
        print("Error: at least 1 image required", file=sys.stderr)
        sys.exit(1)

    is_carousel = len(image_refs) >= 2

    if dry_run:
        mode = "carousel" if is_carousel else "single image"
        print(f"[DRY RUN] Would post Instagram {mode} ({len(image_refs)} image{'s' if is_carousel else ''}):", file=sys.stderr)
        for i, ref in enumerate(image_refs, 1):
            print(f"  Image {i}: {ref}", file=sys.stderr)
        print(f"  Caption ({len(caption)} chars): {caption}", file=sys.stderr)
        return "https://www.instagram.com/p/dry-run"

    ensure_fresh_token("instagram")
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")

    if is_carousel:
        # Carousel: upload each image as carousel item, then create carousel container
        media_ids = []
        for i, ref in enumerate(image_refs, 1):
            print(f"Uploading image {i}/{len(image_refs)}...", file=sys.stderr)
            media_id = _resolve_image(ref, account_id, token, is_carousel_item=True)
            media_ids.append(media_id)

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
    else:
        # Single image: create a single media container
        ref = image_refs[0]
        print("Uploading image...", file=sys.stderr)

        if _is_url(ref):
            container_resp = retry_on_5xx(
                lambda: requests.post(
                    f"{BASE_URL}/{account_id}/media",
                    params={
                        "image_url": ref,
                        "caption": caption,
                        "access_token": token,
                    },
                ),
                "create single image container",
            )
            container_id = container_resp.json()["id"]
        else:
            # Local file upload for single image
            path = Path(ref)
            if not path.exists():
                print(f"Error: file not found: {ref}", file=sys.stderr)
                sys.exit(1)
            with open(path, "rb") as f:
                resp = requests.post(
                    f"{BASE_URL}/{account_id}/media",
                    data={"caption": caption, "access_token": token},
                    files={"source": (path.name, f, "image/jpeg")},
                )
            if 400 <= resp.status_code < 600:
                handle_error(resp, "upload single image")
            container_id = resp.json()["id"]

    _poll_container(container_id, token)
    return _publish_and_get_permalink(container_id, account_id, token)


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
        print('Usage: python3 post_instagram.py [--dry-run] --images "url_or_path[,url_or_path,...]" "Caption"', file=sys.stderr)
        sys.exit(1)

    if not args:
        print("Error: caption text is required as a positional argument", file=sys.stderr)
        sys.exit(1)

    image_refs = [u.strip() for u in images_arg.split(",") if u.strip()]
    caption_text = args[0]

    permalink = post_to_instagram(image_refs, caption_text, dry_run=dry_run)
    print(permalink)
