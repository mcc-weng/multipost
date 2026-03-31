"""Shared utilities for multipost scripts.

Provides: error handling, retry logic, env management, token refresh, OAuth flows.
"""

import json
import os
import re
import sys
import time
import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
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
    "threads": ["THREADS_ACCESS_TOKEN"],
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


# --- OAuth Browser Flow ---

class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures OAuth callback and stores the auth code."""
    auth_code = None
    error = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            _OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Success!</h1><p>You can close this tab and return to the terminal.</p></body></html>")
        elif "error" in params:
            _OAuthCallbackHandler.error = params.get("error_description", params["error"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"<html><body><h1>Error</h1><p>{_OAuthCallbackHandler.error}</p></body></html>".encode())
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress request logging


def oauth_browser_flow(auth_url_base, token_url, client_id, client_secret, scopes, redirect_port=8789):
    """Open browser for OAuth consent, capture callback, exchange for tokens."""
    port = None
    server = None
    for p in range(redirect_port, redirect_port + 10):
        try:
            server = HTTPServer(("localhost", p), _OAuthCallbackHandler)
            port = p
            break
        except OSError:
            continue
    if not server:
        print("Error: Could not find an available port (tried 8789-8799).", file=sys.stderr)
        sys.exit(1)

    redirect_uri = f"http://localhost:{port}/callback"
    auth_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes if isinstance(scopes, str) else " ".join(scopes),
    }
    auth_url = f"{auth_url_base}?{urllib.parse.urlencode(auth_params)}"

    _OAuthCallbackHandler.auth_code = None
    _OAuthCallbackHandler.error = None

    print(f"\nOpening browser for authorization...", file=sys.stderr)
    print(f"If the browser doesn't open, visit: {auth_url}\n", file=sys.stderr)
    webbrowser.open(auth_url)

    server.timeout = 120
    print("Waiting for authorization (timeout: 120s)...", file=sys.stderr)
    while _OAuthCallbackHandler.auth_code is None and _OAuthCallbackHandler.error is None:
        server.handle_request()
    server.server_close()

    if _OAuthCallbackHandler.error:
        print(f"OAuth error: {_OAuthCallbackHandler.error}", file=sys.stderr)
        sys.exit(1)
    if not _OAuthCallbackHandler.auth_code:
        print("Error: No authorization code received (timeout?).", file=sys.stderr)
        sys.exit(1)

    print("Exchanging authorization code for tokens...", file=sys.stderr)
    token_resp = requests.post(token_url, data={
        "grant_type": "authorization_code",
        "code": _OAuthCallbackHandler.auth_code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    })
    if token_resp.status_code != 200:
        print(f"Error exchanging code: {token_resp.status_code}", file=sys.stderr)
        print(token_resp.text, file=sys.stderr)
        sys.exit(1)
    return token_resp.json()


# --- Token Validation ---

def validate_token(platform):
    """Test API call to check if token works. Returns True/False."""
    load_env()
    try:
        if platform == "threads":
            token = os.environ.get("THREADS_ACCESS_TOKEN", "")
            resp = requests.get("https://graph.threads.net/v1.0/me",
                                params={"fields": "id,username", "access_token": token})
            return resp.status_code == 200
        elif platform == "instagram":
            token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
            account_id = os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
            resp = requests.get(f"https://graph.facebook.com/v21.0/{account_id}",
                                params={"fields": "id,username", "access_token": token})
            return resp.status_code == 200
        elif platform == "x":
            return check_setup("x")
        elif platform == "linkedin":
            token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
            resp = requests.get("https://api.linkedin.com/v2/userinfo",
                                headers={"Authorization": f"Bearer {token}"})
            return resp.status_code == 200
        elif platform == "tiktok":
            token = os.environ.get("TIKTOK_ACCESS_TOKEN", "")
            resp = requests.get("https://open.tiktokapis.com/v2/user/info/",
                                headers={"Authorization": f"Bearer {token}"})
            return resp.status_code == 200
        elif platform == "youtube":
            access_token = refresh_youtube_token()
            resp = requests.get("https://www.googleapis.com/youtube/v3/channels",
                                params={"part": "id", "mine": "true"},
                                headers={"Authorization": f"Bearer {access_token}"})
            return resp.status_code == 200
    except Exception:
        return False
    return False


# --- Interactive Setup ---

def _setup_threads():
    """Guide user through Threads setup (Meta Developer Portal)."""
    print("\n=== Threads Setup ===\n")
    print("You need a Meta Developer account and app with Threads API enabled.\n")
    print("Steps:")
    print("  1. Go to https://developers.facebook.com/apps/")
    print("  2. Click 'Create App' -> select 'Business' type")
    print("  3. Add the 'Threads API' product to your app")
    print("  4. Go to Threads API -> API Explorer")
    print("  5. Generate a long-lived access token\n")
    webbrowser.open("https://developers.facebook.com/apps/")
    print("(Opening Meta Developer Portal in your browser...)\n")
    token = input("Paste your Threads access token: ").strip()
    if not token:
        print("Aborted — no token provided.", file=sys.stderr)
        return False
    update_env("THREADS_ACCESS_TOKEN", token)
    print("Validating...", file=sys.stderr)
    if validate_token("threads"):
        print("✅ Threads configured successfully!")
        return True
    print("❌ Validation failed — check your token.", file=sys.stderr)
    return False


def _setup_instagram():
    """Guide user through Instagram setup (Meta Developer Portal)."""
    print("\n=== Instagram Setup ===\n")
    print("You need a Meta Developer app with Instagram Graph API,")
    print("and an Instagram Business or Creator account (not personal).\n")
    print("Steps:")
    print("  1. Go to https://developers.facebook.com/apps/")
    print("  2. Use the same app as Threads (or create a new one)")
    print("  3. Add the 'Instagram Graph API' product")
    print("  4. Go to API Explorer -> generate a long-lived token")
    print("  5. Get your Business Account ID from:")
    print("     curl 'https://graph.facebook.com/v21.0/me/accounts?access_token=YOUR_TOKEN'")
    print("     Then: curl 'https://graph.facebook.com/v21.0/PAGE_ID?fields=instagram_business_account&access_token=YOUR_TOKEN'\n")
    webbrowser.open("https://developers.facebook.com/apps/")
    print("(Opening Meta Developer Portal in your browser...)\n")
    token = input("Paste your Instagram access token: ").strip()
    if not token:
        print("Aborted.", file=sys.stderr)
        return False
    update_env("INSTAGRAM_ACCESS_TOKEN", token)
    account_id = input("Paste your Instagram Business Account ID: ").strip()
    if not account_id:
        print("Aborted.", file=sys.stderr)
        return False
    update_env("INSTAGRAM_BUSINESS_ACCOUNT_ID", account_id)
    print("Validating...", file=sys.stderr)
    if validate_token("instagram"):
        print("✅ Instagram configured successfully!")
        return True
    print("❌ Validation failed — check your token and account ID.", file=sys.stderr)
    return False


def _setup_x():
    """Guide user through X setup. Warns about $100/month cost."""
    print("\n=== X (Twitter) Setup ===\n")
    print("X API requires the Basic tier ($100/month) for posting.")
    print("If you use the Claude Code skill, you can post to X for FREE via browser automation.\n")
    choice = input("Set up X API anyway? (y/n): ").strip().lower()
    if choice != "y":
        print("Skipped X setup. Use the Claude Code skill for free X posting.")
        return False
    print("\nSteps:")
    print("  1. Go to https://developer.x.com/en/portal/dashboard")
    print("  2. Create a Project + App")
    print("  3. Set app permissions to 'Read and Write'")
    print("  4. Go to 'Keys and Tokens' tab")
    print("  5. Generate all 4 tokens\n")
    webbrowser.open("https://developer.x.com/en/portal/dashboard")
    print("(Opening X Developer Portal in your browser...)\n")
    api_key = input("Paste API Key: ").strip()
    api_secret = input("Paste API Secret: ").strip()
    access_token = input("Paste Access Token: ").strip()
    access_token_secret = input("Paste Access Token Secret: ").strip()
    if not all([api_key, api_secret, access_token, access_token_secret]):
        print("Aborted — missing values.", file=sys.stderr)
        return False
    update_env("X_API_KEY", api_key)
    update_env("X_API_SECRET", api_secret)
    update_env("X_ACCESS_TOKEN", access_token)
    update_env("X_ACCESS_TOKEN_SECRET", access_token_secret)
    print("✅ X configured! (Token validation skipped — X uses OAuth 1.0a)")
    return True


def _setup_linkedin():
    """Guide user through LinkedIn OAuth setup."""
    print("\n=== LinkedIn Setup ===\n")
    print("Steps to create a LinkedIn app:")
    print("  1. Go to https://www.linkedin.com/developers/apps")
    print("  2. Click 'Create App'")
    print("  3. Fill in company name (can be your own name)")
    print("  4. Under 'Auth' tab, add redirect URL: http://localhost:8789/callback")
    print("  5. Under 'Products' tab, request 'Community Management API'")
    print("  6. Copy your Client ID and Client Secret from the 'Auth' tab\n")
    webbrowser.open("https://www.linkedin.com/developers/apps")
    print("(Opening LinkedIn Developer Portal in your browser...)\n")
    client_id = input("Paste Client ID: ").strip()
    client_secret = input("Paste Client Secret: ").strip()
    if not client_id or not client_secret:
        print("Aborted.", file=sys.stderr)
        return False
    update_env("LINKEDIN_CLIENT_ID", client_id)
    update_env("LINKEDIN_CLIENT_SECRET", client_secret)
    print("\nStarting OAuth flow to get your access token...")
    tokens = oauth_browser_flow(
        auth_url_base="https://www.linkedin.com/oauth/v2/authorization",
        token_url="https://www.linkedin.com/oauth/v2/accessToken",
        client_id=client_id, client_secret=client_secret,
        scopes="openid profile w_member_social",
    )
    if tokens.get("access_token"):
        update_env("LINKEDIN_ACCESS_TOKEN", tokens["access_token"])
    if tokens.get("refresh_token"):
        update_env("LINKEDIN_REFRESH_TOKEN", tokens["refresh_token"])
    print("Getting your LinkedIn person ID...", file=sys.stderr)
    resp = requests.get("https://api.linkedin.com/v2/userinfo",
                        headers={"Authorization": f"Bearer {tokens['access_token']}"})
    if resp.status_code == 200:
        sub = resp.json().get("sub", "")
        person_id = f"urn:li:person:{sub}"
        update_env("LINKEDIN_PERSON_ID", person_id)
        print(f"✅ LinkedIn configured! Person ID: {person_id}")
        return True
    print("❌ Could not get LinkedIn person ID.", file=sys.stderr)
    return False


def _setup_tiktok():
    """Guide user through TikTok OAuth setup."""
    print("\n=== TikTok Setup ===\n")
    print("Steps to create a TikTok app:")
    print("  1. Go to https://developers.tiktok.com/apps/")
    print("  2. Click 'Create App' -> select 'Web' platform")
    print("  3. Add redirect URL: http://localhost:8789/callback")
    print("  4. Request 'Content Posting API' scope")
    print("  5. Copy Client Key and Client Secret\n")
    print("Note: New apps start in sandbox mode (posts only visible to you).")
    print("Submit your app for review to go live.\n")
    webbrowser.open("https://developers.tiktok.com/apps/")
    print("(Opening TikTok Developer Portal in your browser...)\n")
    client_key = input("Paste Client Key: ").strip()
    client_secret = input("Paste Client Secret: ").strip()
    if not client_key or not client_secret:
        print("Aborted.", file=sys.stderr)
        return False
    update_env("TIKTOK_CLIENT_KEY", client_key)
    update_env("TIKTOK_CLIENT_SECRET", client_secret)
    print("\nStarting OAuth flow...")
    tokens = oauth_browser_flow(
        auth_url_base="https://www.tiktok.com/v2/auth/authorize/",
        token_url="https://open.tiktokapis.com/v2/oauth/token/",
        client_id=client_key, client_secret=client_secret,
        scopes="user.info.basic,video.publish",
    )
    if tokens.get("access_token"):
        update_env("TIKTOK_ACCESS_TOKEN", tokens["access_token"])
    if tokens.get("refresh_token"):
        update_env("TIKTOK_REFRESH_TOKEN", tokens["refresh_token"])
    print("Validating...", file=sys.stderr)
    if validate_token("tiktok"):
        print("✅ TikTok configured!")
        return True
    print("❌ Validation failed.", file=sys.stderr)
    return False


def _setup_youtube():
    """Guide user through YouTube/Google OAuth setup."""
    print("\n=== YouTube Setup ===\n")
    print("Steps to create Google OAuth credentials:")
    print("  1. Go to https://console.cloud.google.com/apis/credentials")
    print("  2. Create a project (or select existing)")
    print("  3. Enable 'YouTube Data API v3' in the API Library")
    print("  4. Go to Credentials -> Create Credentials -> OAuth 2.0 Client ID")
    print("  5. Application type: 'Web application'")
    print("  6. Add redirect URI: http://localhost:8789/callback")
    print("  7. Copy Client ID and Client Secret\n")
    webbrowser.open("https://console.cloud.google.com/apis/credentials")
    print("(Opening Google Cloud Console in your browser...)\n")
    client_id = input("Paste Client ID: ").strip()
    client_secret = input("Paste Client Secret: ").strip()
    if not client_id or not client_secret:
        print("Aborted.", file=sys.stderr)
        return False
    update_env("YOUTUBE_CLIENT_ID", client_id)
    update_env("YOUTUBE_CLIENT_SECRET", client_secret)
    print("\nStarting OAuth flow to get refresh token...")
    tokens = oauth_browser_flow(
        auth_url_base="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        client_id=client_id, client_secret=client_secret,
        scopes="https://www.googleapis.com/auth/youtube.upload",
    )
    if tokens.get("refresh_token"):
        update_env("YOUTUBE_REFRESH_TOKEN", tokens["refresh_token"])
    else:
        print("Warning: No refresh token received. You may need to revoke access and re-authorize.", file=sys.stderr)
        print("Visit: https://myaccount.google.com/permissions", file=sys.stderr)
    print("Validating...", file=sys.stderr)
    if validate_token("youtube"):
        print("✅ YouTube configured!")
        return True
    print("❌ Validation failed.", file=sys.stderr)
    return False


_SETUP_FUNCTIONS = {
    "threads": _setup_threads,
    "instagram": _setup_instagram,
    "x": _setup_x,
    "linkedin": _setup_linkedin,
    "tiktok": _setup_tiktok,
    "youtube": _setup_youtube,
}


def ensure_setup(platform, interactive=True):
    """Check if platform is configured. If not and interactive, guide through setup.
    Returns True if platform is ready to use, False otherwise.
    """
    if check_setup(platform):
        return True
    if not interactive:
        return False
    setup_fn = _SETUP_FUNCTIONS.get(platform)
    if not setup_fn:
        print(f"Error: Unknown platform '{platform}'", file=sys.stderr)
        return False
    return setup_fn()
