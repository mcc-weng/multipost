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

Local files are served via a temporary ngrok tunnel so Instagram can fetch them.

Requires env vars:
  INSTAGRAM_ACCESS_TOKEN — long-lived token (~60 day expiry)
"""

import http.server
import json
import os
import subprocess
import sys
import threading
import time
import requests
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.shared import load_env, ensure_setup, ensure_fresh_token, handle_error, retry_on_5xx
load_env()

BASE_URL = "https://graph.instagram.com/v21.0"

POLL_INTERVAL_SECS = 3
POLL_TIMEOUT_SECS = 60


def _is_url(s):
    """Check if string is a URL (vs local file path)."""
    return s.startswith("http://") or s.startswith("https://")


# ---------------------------------------------------------------------------
# Ngrok tunnel for serving local files
# ---------------------------------------------------------------------------

class _LocalFileServer:
    """Serves local files via ngrok tunnel for Instagram to fetch."""

    def __init__(self, file_paths):
        self.file_paths = file_paths  # list of Path objects
        self.port = 19876
        self.ngrok_process = None
        self.server = None
        self.tunnel_url = None

    def start(self):
        """Start local HTTP server and ngrok tunnel. Returns base tunnel URL."""
        file_map = {}
        for p in self.file_paths:
            file_map[f"/{p.name}"] = p

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                path = file_map.get(self.path)
                if path and path.exists():
                    self.send_response(200)
                    suffix = path.suffix.lower()
                    ct = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                          "gif": "image/gif", "webp": "image/webp", "mp4": "video/mp4",
                          "mov": "video/quicktime"}.get(suffix.lstrip("."), "application/octet-stream")
                    self.send_header("Content-Type", ct)
                    self.send_header("Content-Length", str(path.stat().st_size))
                    self.end_headers()
                    with open(path, "rb") as f:
                        self.wfile.write(f.read())
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", self.port), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

        # Kill any existing ngrok sessions
        subprocess.run(["pkill", "-f", "ngrok"], capture_output=True)
        time.sleep(1)

        # Start ngrok
        self.ngrok_process = subprocess.Popen(
            ["ngrok", "http", str(self.port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        # Wait for tunnel URL via ngrok local API
        deadline = time.time() + 10
        while time.time() < deadline:
            time.sleep(1)
            try:
                resp = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=2)
                if resp.ok:
                    tunnels = resp.json().get("tunnels", [])
                    for t in tunnels:
                        url = t.get("public_url", "")
                        if url.startswith("https://"):
                            self.tunnel_url = url
                            return url
            except requests.ConnectionError:
                continue

        self.stop()
        raise RuntimeError("Failed to start ngrok tunnel. Is ngrok installed and authenticated?")

    def get_url(self, file_path):
        """Get the public URL for a local file."""
        return f"{self.tunnel_url}/{Path(file_path).name}"

    def stop(self):
        """Shut down ngrok and local server."""
        if self.ngrok_process:
            self.ngrok_process.terminate()
            self.ngrok_process.wait()
        if self.server:
            self.server.shutdown()


def _resolve_image(image_ref, account_id, token, is_carousel_item=False, tunnel=None):
    """Resolve an image reference (URL or local path) to an IG media container ID."""
    if _is_url(image_ref):
        image_url = image_ref
    else:
        if not tunnel:
            raise RuntimeError("Local file requires ngrok tunnel but none provided")
        image_url = tunnel.get_url(image_ref)

    params = {
        "image_url": image_url,
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

    account_id = "me"
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

    # Check if any refs are local files — if so, start ngrok tunnel
    local_files = [Path(r) for r in image_refs if not _is_url(r)]
    tunnel = None
    if local_files:
        for f in local_files:
            if not f.exists():
                print(f"Error: file not found: {f}", file=sys.stderr)
                sys.exit(1)
        print("Starting ngrok tunnel for local files...", file=sys.stderr)
        tunnel = _LocalFileServer(local_files)
        tunnel.start()
        print(f"Tunnel ready: {tunnel.tunnel_url}", file=sys.stderr)

    try:
        if is_carousel:
            media_ids = []
            for i, ref in enumerate(image_refs, 1):
                print(f"Uploading image {i}/{len(image_refs)}...", file=sys.stderr)
                media_id = _resolve_image(ref, account_id, token, is_carousel_item=True, tunnel=tunnel)
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
            ref = image_refs[0]
            print("Uploading image...", file=sys.stderr)
            if _is_url(ref):
                image_url = ref
            else:
                image_url = tunnel.get_url(ref)
            container_resp = retry_on_5xx(
                lambda: requests.post(
                    f"{BASE_URL}/{account_id}/media",
                    params={
                        "image_url": image_url,
                        "caption": caption,
                        "access_token": token,
                    },
                ),
                "create single image container",
            )
            container_id = container_resp.json()["id"]

        _poll_container(container_id, token)
        permalink = _publish_and_get_permalink(container_id, account_id, token)
    finally:
        if tunnel:
            print("Shutting down tunnel...", file=sys.stderr)
            tunnel.stop()

    return permalink


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
