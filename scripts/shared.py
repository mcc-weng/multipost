"""Shared utilities for multipost scripts.

Provides: error handling, retry logic, env management, token refresh, OAuth flows.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

# ---------------------------------------------------------------------------
# Env management
# ---------------------------------------------------------------------------

def load_env() -> None:
    """Load .env from project root. If missing, create from .env.example."""
    if not ENV_PATH.exists():
        example = PROJECT_ROOT / ".env.example"
        if example.exists():
            ENV_PATH.write_text(example.read_text())
            print(
                f"Created {ENV_PATH} from .env.example — fill in your tokens.",
                file=sys.stderr,
            )
        else:
            ENV_PATH.touch()
            print(f"Created empty {ENV_PATH}.", file=sys.stderr)
    load_dotenv(ENV_PATH, override=True)


def update_env(key: str, value: str) -> None:
    """Update a single key in .env and os.environ in-place.

    If the key exists, replaces the value on that line.
    If the key is absent, appends it.
    """
    text = ENV_PATH.read_text() if ENV_PATH.exists() else ""
    pattern = re.compile(rf"^({re.escape(key)}\s*=).*$", re.MULTILINE)
    replacement = rf"\g<1>{value}"
    if pattern.search(text):
        new_text = pattern.sub(replacement, text)
    else:
        sep = "\n" if text and not text.endswith("\n") else ""
        new_text = text + sep + f"{key}={value}\n"
    ENV_PATH.write_text(new_text)
    os.environ[key] = value


PLATFORM_VARS: dict[str, list[str]] = {
    "threads": ["THREADS_ACCESS_TOKEN", "THREADS_USER_ID"],
    "instagram": ["INSTAGRAM_BUSINESS_ACCOUNT_ID", "INSTAGRAM_ACCESS_TOKEN"],
    "x": ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"],
    "linkedin": ["LINKEDIN_ACCESS_TOKEN", "LINKEDIN_PERSON_ID"],
    "tiktok": ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_ACCESS_TOKEN"],
    "youtube": ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"],
}


def check_setup(platform: str) -> bool:
    """Return True if all required env vars for *platform* are set and non-empty."""
    vars_ = PLATFORM_VARS.get(platform, [])
    return all(os.environ.get(v) for v in vars_)


def check_all() -> dict[str, bool]:
    """Return a dict of {platform: bool} for every platform in PLATFORM_VARS."""
    return {platform: check_setup(platform) for platform in PLATFORM_VARS}


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def handle_error(resp: requests.Response, step_name: str) -> None:
    """Handle an HTTP error response and exit with code 1.

    - 401: token expired hint + suggest configure.py
    - 403: permissions hint
    - 4xx: show response body detail
    All paths are fatal (sys.exit(1)).
    """
    status = resp.status_code
    if status == 401:
        print(
            f"[{step_name}] 401 Unauthorized — your access token has expired or is invalid.\n"
            "Run `python scripts/configure.py` (or the relevant platform refresh) to get a fresh token.",
            file=sys.stderr,
        )
    elif status == 403:
        print(
            f"[{step_name}] 403 Forbidden — the token lacks the required permissions for this action.\n"
            "Check your app's permission scopes on the platform's developer portal.",
            file=sys.stderr,
        )
    elif 400 <= status < 500:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        print(
            f"[{step_name}] {status} Client Error: {detail}",
            file=sys.stderr,
        )
    else:
        # Caller should only pass non-2xx responses, but handle the unexpected
        print(
            f"[{step_name}] Unexpected error {status}: {resp.text}",
            file=sys.stderr,
        )
    sys.exit(1)


def retry_on_5xx(make_request, step_name: str) -> requests.Response:
    """Execute *make_request()*, retry once on 5xx after 2 s, then call handle_error.

    Args:
        make_request: zero-argument callable that returns a requests.Response.
        step_name: human-readable label used in error messages.

    Returns:
        The successful response (2xx).
    """
    resp = make_request()
    if resp.status_code >= 500:
        print(
            f"[{step_name}] {resp.status_code} Server Error — retrying in 2 s…",
            file=sys.stderr,
        )
        time.sleep(2)
        resp = make_request()
    if not resp.ok:
        handle_error(resp, step_name)
    return resp


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

def _refresh_threads() -> None:
    """Refresh the Threads long-lived access token."""
    token = os.environ.get("THREADS_ACCESS_TOKEN")
    if not token:
        return
    resp = requests.get(
        "https://graph.threads.net/refresh_access_token",
        params={"grant_type": "th_refresh_token", "access_token": token},
    )
    if not resp.ok:
        print(f"[refresh_threads] {resp.status_code}: {resp.text}", file=sys.stderr)
        return
    data = resp.json()
    new_token = data.get("access_token")
    expires_in = data.get("expires_in", "unknown")
    if new_token:
        update_env("THREADS_ACCESS_TOKEN", new_token)
        print(f"[refresh_threads] Token refreshed. Expires in {expires_in}s.", file=sys.stderr)


def _refresh_instagram() -> None:
    """Refresh the Instagram long-lived access token."""
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        return
    resp = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token},
    )
    if not resp.ok:
        print(f"[refresh_instagram] {resp.status_code}: {resp.text}", file=sys.stderr)
        return
    data = resp.json()
    new_token = data.get("access_token")
    expires_in = data.get("expires_in", "unknown")
    if new_token:
        update_env("INSTAGRAM_ACCESS_TOKEN", new_token)
        print(f"[refresh_instagram] Token refreshed. Expires in {expires_in}s.", file=sys.stderr)


def _refresh_tiktok() -> None:
    """Refresh the TikTok access token using the refresh token."""
    client_key = os.environ.get("TIKTOK_CLIENT_KEY")
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET")
    refresh_token = os.environ.get("TIKTOK_REFRESH_TOKEN")
    if not all([client_key, client_secret, refresh_token]):
        return
    resp = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if not resp.ok:
        print(f"[refresh_tiktok] {resp.status_code}: {resp.text}", file=sys.stderr)
        return
    data = resp.json()
    new_token = data.get("access_token")
    new_refresh = data.get("refresh_token")
    expires_in = data.get("expires_in", "unknown")
    if new_token:
        update_env("TIKTOK_ACCESS_TOKEN", new_token)
    if new_refresh:
        update_env("TIKTOK_REFRESH_TOKEN", new_refresh)
    print(f"[refresh_tiktok] Token refreshed. Expires in {expires_in}s.", file=sys.stderr)


def _refresh_linkedin() -> None:
    """Refresh the LinkedIn access token using the refresh token."""
    client_id = os.environ.get("LINKEDIN_CLIENT_ID")
    client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET")
    refresh_token = os.environ.get("LINKEDIN_REFRESH_TOKEN")
    if not all([client_id, client_secret, refresh_token]):
        return
    resp = requests.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if not resp.ok:
        print(f"[refresh_linkedin] {resp.status_code}: {resp.text}", file=sys.stderr)
        return
    data = resp.json()
    new_token = data.get("access_token")
    expires_in = data.get("expires_in", "unknown")
    if new_token:
        update_env("LINKEDIN_ACCESS_TOKEN", new_token)
        print(f"[refresh_linkedin] Token refreshed. Expires in {expires_in}s.", file=sys.stderr)


def refresh_youtube_token() -> str:
    """Exchange the YouTube refresh token for a short-lived access token.

    YouTube tokens are short-lived (~1 hour) and cannot be stored long-term,
    so this function returns the access token string for immediate use rather
    than persisting it to .env.

    Returns:
        The access token string.

    Raises:
        RuntimeError: if required env vars are missing or the request fails.
    """
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")
    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError(
            "Missing one or more YouTube env vars: "
            "YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN"
        )
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    if not resp.ok:
        raise RuntimeError(
            f"[refresh_youtube] {resp.status_code}: {resp.text}"
        )
    data = resp.json()
    access_token = data.get("access_token")
    expires_in = data.get("expires_in", "unknown")
    print(f"[refresh_youtube] Access token obtained. Expires in {expires_in}s.", file=sys.stderr)
    if not access_token:
        raise RuntimeError(f"[refresh_youtube] No access_token in response: {data}")
    return access_token


# Map platform name → refresh function (YouTube and X handled separately)
_REFRESHERS: dict[str, object] = {
    "threads": _refresh_threads,
    "instagram": _refresh_instagram,
    "tiktok": _refresh_tiktok,
    "linkedin": _refresh_linkedin,
}


def ensure_fresh_token(platform: str) -> None:
    """Attempt to refresh the token for *platform*, failing silently on any error.

    YouTube is excluded (use refresh_youtube_token() directly).
    X is excluded (uses OAuth 1.0a — no refresh flow).
    """
    refresher = _REFRESHERS.get(platform)
    if refresher is None:
        return
    try:
        refresher()
    except Exception:
        pass
