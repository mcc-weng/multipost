#!/usr/bin/env python3
"""Interactive setup wizard for multipost.

Usage:
  python3 configure.py              # Setup all platforms
  python3 configure.py threads      # Setup one platform
  python3 configure.py --status     # Show what's configured
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.shared import load_env, check_setup, check_all, ensure_setup, validate_token, PLATFORM_VARS

ALL_PLATFORMS = ["threads", "instagram", "x", "linkedin", "tiktok", "youtube"]


def show_status():
    """Print configuration status for all platforms."""
    load_env()
    print("\nmultipost — platform status\n")
    for platform in ALL_PLATFORMS:
        if not check_setup(platform):
            if platform == "x":
                print(f"  ⏭️  {platform:12s} not configured (free via Playwright in Claude Code skill)")
            else:
                print(f"  ❌ {platform:12s} not configured")
        else:
            valid = validate_token(platform)
            if valid:
                print(f"  ✅ {platform:12s} configured (token valid)")
            else:
                print(f"  ⚠️  {platform:12s} configured but token may be expired")
    print()


def setup_all():
    """Walk through setup for each unconfigured platform."""
    load_env()
    print("\nmultipost — setup wizard\n")
    for platform in ALL_PLATFORMS:
        if check_setup(platform):
            print(f"  ✅ {platform} — already configured, skipping")
            continue
        choice = input(f"\nSet up {platform}? (y/n): ").strip().lower()
        if choice == "y":
            ensure_setup(platform, interactive=True)
        else:
            print(f"  ⏭️  Skipped {platform}")

    print("\n--- Final Status ---")
    show_status()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if "--status" in sys.argv:
        show_status()
        return

    if args:
        platform = args[0].lower()
        if platform not in ALL_PLATFORMS:
            print(f"Unknown platform: {platform}", file=sys.stderr)
            print(f"Available: {', '.join(ALL_PLATFORMS)}", file=sys.stderr)
            sys.exit(1)
        load_env()
        ensure_setup(platform, interactive=True)
    else:
        setup_all()


if __name__ == "__main__":
    main()
