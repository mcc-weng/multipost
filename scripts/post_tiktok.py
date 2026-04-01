#!/usr/bin/env python3
"""Post video content to TikTok via Content Posting API v2.

Usage:
  python3 post_tiktok.py --media /path/to/video.mp4 "Caption text"
  python3 post_tiktok.py --dry-run --media /path/to/video.mp4 "Caption text"

Requires env vars:
  TIKTOK_ACCESS_TOKEN — OAuth 2.0 token
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

API_BASE = "https://open.tiktokapis.com/v2"
POLL_INTERVAL_SECS = 5
POLL_TIMEOUT_SECS = 120


def post_to_tiktok(text, video_path, dry_run=False):
    """Upload and publish a video to TikTok. Returns publish ID."""
    if not ensure_setup("tiktok", interactive=sys.stdin.isatty()):
        print("Error: TikTok not configured. Run: python3 configure.py tiktok", file=sys.stderr)
        sys.exit(1)

    token = os.environ.get("TIKTOK_ACCESS_TOKEN")

    video_file = Path(video_path)
    if not video_file.exists():
        print(f"Error: video file not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    video_size = video_file.stat().st_size

    if dry_run:
        print(f"[DRY RUN] Would post to TikTok:", file=sys.stderr)
        print(f"  Video: {video_path} ({video_size} bytes)", file=sys.stderr)
        print(f"  Caption ({len(text)} chars): {text}", file=sys.stderr)
        return "https://tiktok.com/dry-run"

    ensure_fresh_token("tiktok")
    token = os.environ.get("TIKTOK_ACCESS_TOKEN")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    init_payload = {
        "post_info": {
            "title": text,
            "privacy_level": "SELF_ONLY",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": video_size,
            "total_chunk_count": 1,
        },
    }

    print("Initializing TikTok upload...", file=sys.stderr)
    init_resp = retry_on_5xx(
        lambda: requests.post(
            f"{API_BASE}/post/publish/video/init/",
            headers=headers,
            json=init_payload,
        ),
        "init upload",
    )
    init_data = init_resp.json()

    if init_data.get("error", {}).get("code") != "ok":
        print(f"Error initializing upload: {json.dumps(init_data, indent=2)}", file=sys.stderr)
        sys.exit(1)

    upload_url = init_data["data"]["upload_url"]
    publish_id = init_data["data"]["publish_id"]

    print(f"Uploading video ({video_size} bytes)...", file=sys.stderr)
    with open(video_path, "rb") as f:
        video_data = f.read()

    upload_resp = requests.put(
        upload_url,
        headers={
            "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
            "Content-Type": "video/mp4",
        },
        data=video_data,
    )
    if upload_resp.status_code not in (200, 201):
        print(f"Error uploading video: {upload_resp.status_code}", file=sys.stderr)
        print(upload_resp.text, file=sys.stderr)
        sys.exit(1)

    print("Waiting for TikTok to process video...", file=sys.stderr)
    elapsed = 0
    while elapsed < POLL_TIMEOUT_SECS:
        status_resp = requests.post(
            f"{API_BASE}/post/publish/status/fetch/",
            headers=headers,
            json={"publish_id": publish_id},
        )
        if status_resp.status_code == 200:
            status_data = status_resp.json()
            pub_status = status_data.get("data", {}).get("status")
            if pub_status == "PUBLISH_COMPLETE":
                print("Published!", file=sys.stderr)
                return f"TikTok publish ID: {publish_id} (check your profile for the video)"
            if pub_status in ("FAILED", "PUBLISH_FAILED"):
                fail_reason = status_data.get("data", {}).get("fail_reason", "unknown")
                print(f"Error: TikTok publish failed — {fail_reason}", file=sys.stderr)
                sys.exit(1)
        time.sleep(POLL_INTERVAL_SECS)
        elapsed += POLL_INTERVAL_SECS

    print(f"Error: publish status polling timed out after {POLL_TIMEOUT_SECS}s", file=sys.stderr)
    print(f"Publish ID: {publish_id} — check TikTok Creator Portal for status.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    if "--setup" in sys.argv:
        from scripts.shared import ensure_setup
        ensure_setup("tiktok", interactive=True)
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

    if not media_path:
        print("Error: TikTok requires a video. Use --media /path/to/video.mp4", file=sys.stderr)
        sys.exit(1)

    if not args:
        print('Usage: python3 post_tiktok.py [--dry-run] --media /path/to/video.mp4 "Caption text"', file=sys.stderr)
        sys.exit(1)

    url = post_to_tiktok(args[0], media_path, dry_run=dry_run)
    print(url)
