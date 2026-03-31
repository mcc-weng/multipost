#!/usr/bin/env python3
"""Refresh expiring OAuth tokens for all configured platforms.

Usage:
  python3 scripts/refresh_tokens.py              # Refresh all
  python3 scripts/refresh_tokens.py threads      # Refresh specific platform
  python3 scripts/refresh_tokens.py --dry-run    # Show what would refresh
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.shared import load_env, check_setup, ensure_fresh_token

REFRESHABLE = ["threads", "instagram", "tiktok", "linkedin"]


def main():
    load_env()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv

    platforms = args if args else REFRESHABLE

    for platform in platforms:
        if platform not in REFRESHABLE:
            print(f"⏭️  {platform} — no refresh needed")
            continue
        if not check_setup(platform):
            print(f"⏭️  {platform} — not configured")
            continue
        if dry_run:
            print(f"🔄 {platform} — would refresh")
            continue
        print(f"🔄 {platform} — refreshing...", end=" ")
        try:
            ensure_fresh_token(platform)
            print("done")
        except Exception as e:
            print(f"failed: {e}")


if __name__ == "__main__":
    main()
