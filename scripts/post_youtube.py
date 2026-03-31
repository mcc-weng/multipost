#!/usr/bin/env python3
"""Upload video to YouTube via Data API v3.

Usage:
  python3 post_youtube.py --media /path/to/video.mp4 --title "Video Title" "Description text"
  python3 post_youtube.py --dry-run --media /path/to/video.mp4 --title "Title" "Description"
  python3 post_youtube.py --media /path/to/short.mp4 --title "Short Title" --short "Description"

Requires env vars:
  YOUTUBE_CLIENT_ID     — OAuth 2.0 client ID
  YOUTUBE_CLIENT_SECRET — OAuth 2.0 client secret
  YOUTUBE_REFRESH_TOKEN — OAuth 2.0 refresh token
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.shared import load_env, ensure_setup, refresh_youtube_token, handle_error, retry_on_5xx
load_env()

YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"


def post_to_youtube(description, video_path, title, is_short=False, dry_run=False):
    """Upload a video to YouTube. Returns the video URL."""
    if not ensure_setup("youtube", interactive=sys.stdin.isatty()):
        print("Error: YouTube not configured. Run: python3 configure.py youtube", file=sys.stderr)
        sys.exit(1)

    video_file = Path(video_path)
    if not video_file.exists():
        print(f"Error: video file not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    video_size = video_file.stat().st_size

    if dry_run:
        vid_type = "Short" if is_short else "Video"
        print(f"[DRY RUN] Would upload YouTube {vid_type}:", file=sys.stderr)
        print(f"  Title: {title}", file=sys.stderr)
        print(f"  Video: {video_path} ({video_size} bytes)", file=sys.stderr)
        print(f"  Description ({len(description)} chars): {description}", file=sys.stderr)
        return "https://youtube.com/dry-run"

    print("Refreshing YouTube access token...", file=sys.stderr)
    access_token = refresh_youtube_token()

    if is_short and "#Shorts" not in title:
        title = f"{title} #Shorts"

    metadata = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    print("Initiating YouTube upload...", file=sys.stderr)
    init_resp = requests.post(
        f"{YOUTUBE_UPLOAD_URL}?uploadType=resumable&part=snippet,status",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Upload-Content-Length": str(video_size),
            "X-Upload-Content-Type": "video/mp4",
        },
        json=metadata,
    )
    handle_error(init_resp, "initiate upload") if not init_resp.ok else None

    upload_url = init_resp.headers.get("Location")
    if not upload_url:
        print("Error: YouTube did not return an upload URL.", file=sys.stderr)
        sys.exit(1)

    print(f"Uploading video ({video_size} bytes)...", file=sys.stderr)
    with open(video_path, "rb") as f:
        upload_resp = requests.put(
            upload_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "video/mp4",
                "Content-Length": str(video_size),
            },
            data=f,
        )
    handle_error(upload_resp, "upload video") if not upload_resp.ok else None

    video_data = upload_resp.json()
    video_id = video_data.get("id")
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"

    return f"Video uploaded but could not get ID. Response: {json.dumps(video_data)}"


if __name__ == "__main__":
    if "--setup" in sys.argv:
        from scripts.shared import ensure_setup
        ensure_setup("youtube", interactive=True)
        sys.exit(0)

    args = sys.argv[1:]
    dry_run = False
    media_path = None
    title = None
    is_short = False

    if "--dry-run" in args:
        dry_run = True
        args.remove("--dry-run")

    if "--short" in args:
        is_short = True
        args.remove("--short")

    if "--media" in args:
        idx = args.index("--media")
        if idx + 1 >= len(args):
            print("Error: --media requires a file path", file=sys.stderr)
            sys.exit(1)
        media_path = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if "--title" in args:
        idx = args.index("--title")
        if idx + 1 >= len(args):
            print("Error: --title requires a value", file=sys.stderr)
            sys.exit(1)
        title = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if not media_path:
        print("Error: YouTube requires a video. Use --media /path/to/video.mp4", file=sys.stderr)
        sys.exit(1)

    if not title:
        print("Error: YouTube requires a title. Use --title \"Video Title\"", file=sys.stderr)
        sys.exit(1)

    if not args:
        print('Usage: python3 post_youtube.py [--dry-run] [--short] --media /path/to/video.mp4 --title "Title" "Description"', file=sys.stderr)
        sys.exit(1)

    url = post_to_youtube(args[0], media_path, title, is_short=is_short, dry_run=dry_run)
    print(url)
