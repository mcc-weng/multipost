"""Shared utilities for multipost scripts.

Provides: error handling, retry logic, env management, token refresh, OAuth flows.
"""

import base64
import hashlib
import json
import os
import re
import secrets as _secrets
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
    "instagram": ["INSTAGRAM_ACCESS_TOKEN"],
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


def oauth_browser_flow(auth_url_base, token_url, client_id, client_secret, scopes, redirect_port=8789, pkce=False, client_id_param="client_id", extra_auth_params=None):
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
        client_id_param: client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes if isinstance(scopes, str) else " ".join(scopes),
    }
    if extra_auth_params:
        auth_params.update(extra_auth_params)

    # PKCE support
    code_verifier = None
    if pkce:
        # Use [A-Za-z0-9_.\-~] characters, 43-128 length (RFC 7636 + TikTok compat)
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
        code_verifier = "".join(_secrets.choice(alphabet) for _ in range(64))
        if pkce == "hex":
            # TikTok uses hex-encoded SHA256
            code_challenge = hashlib.sha256(code_verifier.encode("ascii")).hexdigest()
        else:
            # Standard PKCE (base64url-encoded SHA256)
            code_challenge = base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode("ascii")).digest()
            ).rstrip(b"=").decode("ascii")
        auth_params["code_challenge"] = code_challenge
        auth_params["code_challenge_method"] = "S256"

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
    token_data = {
        "grant_type": "authorization_code",
        "code": _OAuthCallbackHandler.auth_code,
        "redirect_uri": redirect_uri,
        client_id_param: client_id,
        "client_secret": client_secret,
    }
    if code_verifier:
        token_data["code_verifier"] = code_verifier
    token_resp = requests.post(token_url, data=token_data)
    if token_resp.status_code != 200:
        print(f"Error exchanging code: {token_resp.status_code}", file=sys.stderr)
        print(token_resp.text, file=sys.stderr)
        sys.exit(1)
    result = token_resp.json()
    # TikTok nests tokens under "data"
    if "data" in result and "access_token" in result["data"]:
        return result["data"]
    return result


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
            resp = requests.get("https://graph.instagram.com/v21.0/me",
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
            return bool(token)
        elif platform == "youtube":
            access_token = refresh_youtube_token()
            return bool(access_token)
    except Exception:
        return False
    return False


# --- Interactive Setup Helpers ---

def _prompt_and_validate(env_key, prompt_zh, prompt_en, platform, zh):
    """Prompt user for a token, validate it, and offer retry/skip on failure.
    Returns True if token is valid and saved, False if skipped.
    """
    while True:
        current = os.environ.get(env_key, "")
        if current:
            if zh:
                print(f"\n{env_key} 已設定。")
                choice = input("要重新輸入嗎？(y/n): ").strip().lower()
            else:
                print(f"\n{env_key} is already set.")
                choice = input("Re-enter? (y/n): ").strip().lower()
            if choice != "y":
                print("驗證中..." if zh else "Validating...", file=sys.stderr)
                if validate_token(platform):
                    print("✅ " + ("驗證成功！" if zh else "Valid!"))
                    return True
                if zh:
                    print("❌ 驗證失敗。")
                    choice = input("重新輸入 (r) / 跳過 (s)? ").strip().lower()
                else:
                    print("❌ Validation failed.")
                    choice = input("Retry (r) / Skip (s)? ").strip().lower()
                if choice == "s":
                    return False
                continue

        token = input(prompt_zh if zh else prompt_en).strip()
        if not token:
            print("已取消。" if zh else "Aborted.", file=sys.stderr)
            return False
        update_env(env_key, token)
        print("驗證中..." if zh else "Validating...", file=sys.stderr)
        if validate_token(platform):
            print("✅ " + ("驗證成功！" if zh else "Valid!"))
            return True
        if zh:
            print("❌ 驗證失敗 — 請檢查 token。")
            choice = input("重新輸入 (r) / 跳過 (s)? ").strip().lower()
        else:
            print("❌ Validation failed — check your token.")
            choice = input("Retry (r) / Skip (s)? ").strip().lower()
        if choice == "s":
            return False


# --- Interactive Setup ---

def _detect_lang():
    """Detect UI language. Returns 'zh' or 'en'.
    Priority: MULTIPOST_LANG env var > system locale.
    """
    override = os.environ.get("MULTIPOST_LANG", "").lower()
    if override in ("zh", "en"):
        return override
    import locale
    lang = os.environ.get("LANG", "") or os.environ.get("LANGUAGE", "") or locale.getdefaultlocale()[0] or ""
    return "zh" if "zh" in lang.lower() else "en"


def _setup_threads():
    """Guide user through Threads setup (Meta Developer Portal)."""
    zh = _detect_lang() == "zh"
    if zh:
        print("\n=== Threads 設定 ===\n")
        print("需要 Meta 開發者帳號和 Threads 帳號。\n")
        print("1. 建立 Meta App")
        print("   - 去 https://developers.facebook.com/apps/")
        print("   - 點「建立應用程式」（或用現有的 app）")
        print("   - 使用案例加「存取 Threads API」")
        print("   - 商家選「我還不想連結商家資產管理組合」")
        print("   - 「下一步」→「下一步」→「建立應用程式」")
        print()
        print("2. 開啟發文權限")
        print("   - 側欄選「使用案例」→ 點「存取 Threads API」的 Edit")
        print("   - 加 threads_content_publish")
        print()
        print("3. 加自己為測試人員")
        print("   - 去「設定」，在「用戶權杖產生器」點「新增或移除Threads測試人員」")
        print("   - 點「新增用戶」→ 選「Threads 測試人員」→ 輸入帳號 → 點「新增」")
        print()
        print("4. 接受邀請")
        print("   - 點「網站權限」連結（會跳到 Threads），或")
        print("   - Threads app →「設定」→「帳戶」→「網站權限」")
        print("   - 去「邀請」→ 接受")
        print()
        print("5. 產生 token")
        print("   - 回到「使用案例」→「存取 Threads API」→「設定」→ 點「產生存取權杖」")
        print("   - 複製權杖")
    else:
        print("\n=== Threads Setup ===\n")
        print("You need a Meta Developer account and a Threads account.\n")
        print("1. Create a Meta App")
        print("   - Go to https://developers.facebook.com/apps/")
        print("   - Click 'Create App' (or use existing app)")
        print("   - For Use cases, add 'Access Threads API'")
        print("   - For Business, select 'I don't want to connect a business portfolio yet'")
        print("   - 'Next' -> 'Next' -> 'Create App'")
        print()
        print("2. Enable content publish permission")
        print("   - Select 'Use cases' (side panel) -> Click Edit on 'Access the Threads API'")
        print("   - Add 'threads_content_publish'")
        print()
        print("3. Add yourself as a Threads Tester")
        print("   - Go to 'Settings', in 'User Token Generator'")
        print("     click 'Add or Remove Threads Testers'")
        print("   - Click 'Add People' -> Select 'Threads Tester'")
        print("     -> Enter username -> Click 'Add'")
        print()
        print("4. Accept the tester invite")
        print("   - Click 'Website permissions' link (takes you to Threads), OR")
        print("   - In Threads app: 'Settings' -> 'Account' -> 'Website permissions'")
        print("   - Go to 'Invitations' -> Accept")
        print()
        print("5. Generate the access token")
        print("   - Go back to 'Use cases' -> 'Access Threads API'")
        print("     -> 'Settings' -> Click 'Generate'")
        print("   - Copy the access token")
    print()
    webbrowser.open("https://developers.facebook.com/apps/")
    print(("正在開啟 Meta 開發者後台..." if zh else "(Opening Meta Developer Portal in your browser...)") + "\n")
    if _prompt_and_validate("THREADS_ACCESS_TOKEN",
                            "貼上你的 Threads access token: ",
                            "Paste your Threads access token: ",
                            "threads", zh):
        print("✅ Threads 設定完成！" if zh else "✅ Threads configured successfully!")
        return True
    return False


def _setup_instagram():
    """Guide user through Instagram setup (Meta Developer Portal)."""
    zh = _detect_lang() == "zh"
    if zh:
        print("\n=== Instagram 設定 ===\n")
        print("前置條件：需要 Instagram 商業帳號（非個人帳號）\n")
        print("1. 建立 Meta App")
        print("   - 去 https://developers.facebook.com/apps/")
        print("   - 點「建立應用程式」（或用現有的 app）")
        print("   - 使用案例加「管理Instagram的訊息或內容」")
        print("   - 商家選「我還不想連結商家資產管理組合」")
        print("   - 「下一步」→「下一步」→「建立應用程式」")
        print()
        print("2. 設定權限")
        print("   - 側欄選「使用案例」→ 點「管理Instagram的訊息或內容」的 Customize")
        print("   - 加所有需要的權限")
        print()
        print("3. 加自己為測試人員")
        print("   - 點「角色」連結，或左下角去 App Roles → Roles")
        print("   - 點「新增用戶」→ 選「Instagram 測試人員」→ 輸入帳號 → 點「新增」")
        print()
        print("4. 接受邀請")
        print("   - 點「應用程式和網站」連結，或")
        print("   - IG →「設定」→「應用程式網站權限」→「應用程式和網站」→「測試員邀請」→「接受」")
        print()
        print("5. 產生 token")
        print("   - 回到「使用案例」→「管理Instagram的訊息或內容」→「設定」")
        print("   - 點「新增帳號」→ 登入帳號同意權限")
        print("   - 點「產生權杖」")
        print("   - 複製 access token")
    else:
        print("\n=== Instagram Setup ===\n")
        print("Prerequisite: You need an Instagram Business or Creator account (not personal).\n")
        print("1. Create a Meta App")
        print("   - Go to https://developers.facebook.com/apps/")
        print("   - Click 'Create App' (or use existing app)")
        print("   - For Use cases, add 'Manage messaging & content on Instagram'")
        print("   - For Business, select 'I don't want to connect a business portfolio yet'")
        print("   - 'Next' -> 'Next' -> 'Create App'")
        print()
        print("2. Configure permissions")
        print("   - Select 'Use cases' (side panel)")
        print("   - Click 'Customize' on 'Manage messaging & content on Instagram'")
        print("   - Add all required permissions")
        print()
        print("3. Add yourself as an Instagram Tester")
        print("   - Click 'Roles' link, or go to 'App Roles' -> 'Roles' (bottom left)")
        print("   - Click 'Add People' -> Select 'Instagram Tester'")
        print("     -> Enter username -> Click 'Add'")
        print()
        print("4. Accept the tester invite")
        print("   - Click 'Apps and Websites' link, OR")
        print("   - In Instagram: 'Settings' -> 'App Website permissions'")
        print("     -> 'Apps and websites' -> 'Tester Invitations' -> 'Accept'")
        print()
        print("5. Generate the access token")
        print("   - Go back to 'Use cases' -> 'Manage messaging & content on Instagram' -> 'Settings'")
        print("   - Click 'Add account' -> Log in and grant permissions")
        print("   - Click 'Generate access token'")
        print("   - Copy the access token")
    print()
    webbrowser.open("https://developers.facebook.com/apps/")
    print(("正在開啟 Meta 開發者後台..." if zh else "(Opening Meta Developer Portal in your browser...)") + "\n")
    if not _prompt_and_validate("INSTAGRAM_ACCESS_TOKEN",
                                "貼上你的 Instagram access token: ",
                                "Paste your Instagram access token: ",
                                "instagram", zh):
        return False

    # Check ngrok setup for local image uploads
    ngrok_token = os.environ.get("NGROK_AUTHTOKEN", "")
    print()
    if ngrok_token:
        print("✅ ngrok " + ("已設定。" if zh else "already configured."))
        choice = input("重新輸入嗎？(y/n): " if zh else "Re-enter? (y/n): ").strip().lower()
        if choice != "y":
            pass  # keep existing
        else:
            ngrok_token = ""  # fall through to setup below

    if not ngrok_token:
        if zh:
            print("--- ngrok 設定（本機圖片上傳需要）---\n")
            print("Instagram API 需要公開 URL 來上傳圖片。")
            print("我們用 ngrok 建立臨時通道來處理本機檔案上傳。\n")
            print("1. 去 https://dashboard.ngrok.com/signup 註冊免費帳號")
            print("2. 去 https://dashboard.ngrok.com/get-started/your-authtoken 複製 token")
            print("3. 貼上 token\n")
        else:
            print("--- ngrok Setup (required for local image uploads) ---\n")
            print("Instagram API requires a public URL to upload images.")
            print("We use ngrok to create a temporary tunnel for local file uploads.\n")
            print("1. Sign up for a free account at https://dashboard.ngrok.com/signup")
            print("2. Copy your token from https://dashboard.ngrok.com/get-started/your-authtoken")
            print("3. Paste it below\n")
        webbrowser.open("https://dashboard.ngrok.com/get-started/your-authtoken")
        ngrok_input = input("貼上 ngrok authtoken（跳過請按 Enter）: " if zh else "Paste ngrok authtoken (press Enter to skip): ").strip()
        if ngrok_input:
            update_env("NGROK_AUTHTOKEN", ngrok_input)
            print("✅ ngrok " + ("設定完成！" if zh else "configured!"))
        else:
            if zh:
                print("⏭️  已跳過 ngrok。之後可以在 .env 加 NGROK_AUTHTOKEN=your_token")
                print("   沒有 ngrok 的話只能用 URL 上傳圖片，不能用本機檔案。")
            else:
                print("⏭️  Skipped ngrok. You can add NGROK_AUTHTOKEN=your_token to .env later.")
                print("   Without ngrok, you can only upload images via URL, not local files.")

    print("\n✅ Instagram 設定完成！" if zh else "\n✅ Instagram configured successfully!")
    return True


def _setup_x():
    """Guide user through X setup."""
    zh = _detect_lang() == "zh"
    if zh:
        print("\n=== X (Twitter) 設定 ===\n")
        print("X API 採用按量付費模式。")
        print("用 Claude Code skill 可以免費透過瀏覽器自動化發文。\n")
        choice = input("要設定 X API 嗎？(y/n): ").strip().lower()
    else:
        print("\n=== X (Twitter) Setup ===\n")
        print("X API uses a pay-per-usage model.")
        print("If you use the Claude Code skill, you can post to X for FREE via browser automation.\n")
        choice = input("Set up X API? (y/n): ").strip().lower()
    if choice != "y":
        print("已跳過 X 設定。" if zh else "Skipped X setup. Use the Claude Code skill for free X posting.")
        return False
    if zh:
        print("\n1. 建立 X 開發者 App")
        print("   - 去 https://developer.x.com/en/portal/dashboard")
        print("   - 建立 Project + App")
        print("   - App 權限設為 'Read and Write'")
        print()
        print("2. 產生 token")
        print("   - 去 'Keys and Tokens' 分頁")
        print("   - 產生全部 4 個 token\n")
    else:
        print("\n1. Create an X Developer App")
        print("   - Go to https://developer.x.com/en/portal/dashboard")
        print("   - Create a Project + App")
        print("   - Set app permissions to 'Read and Write'")
        print()
        print("2. Generate tokens")
        print("   - Go to 'Keys and Tokens' tab")
        print("   - Generate all 4 tokens\n")
    webbrowser.open("https://developer.x.com/en/portal/dashboard")
    print(("正在開啟 X 開發者後台..." if zh else "(Opening X Developer Portal in your browser...)") + "\n")
    api_key = input(("貼上 API Key: " if zh else "Paste API Key: ")).strip()
    api_secret = input(("貼上 API Secret: " if zh else "Paste API Secret: ")).strip()
    access_token = input(("貼上 Access Token: " if zh else "Paste Access Token: ")).strip()
    access_token_secret = input(("貼上 Access Token Secret: " if zh else "Paste Access Token Secret: ")).strip()
    if not all([api_key, api_secret, access_token, access_token_secret]):
        print("已取消 — 缺少值。" if zh else "Aborted — missing values.", file=sys.stderr)
        return False
    update_env("X_API_KEY", api_key)
    update_env("X_API_SECRET", api_secret)
    update_env("X_ACCESS_TOKEN", access_token)
    update_env("X_ACCESS_TOKEN_SECRET", access_token_secret)
    print("✅ X 設定完成！" if zh else "✅ X configured! (Token validation skipped — X uses OAuth 1.0a)")
    return True


def _setup_linkedin():
    """Guide user through LinkedIn OAuth setup."""
    zh = _detect_lang() == "zh"
    if zh:
        print("\n=== LinkedIn 設定 ===\n")
        print("1. 建立 LinkedIn App")
        print("   - 去 https://www.linkedin.com/developers/apps")
        print("   - 點「Create App」")
        print("   - LinkedIn Page：用你自己的專頁，或輸入「Default Company Page for Individual Developer」")
        print("   - 上傳一張 App logo 圖片")
        print()
        print("2. 申請產品權限")
        print("   - 在「Products」分頁，申請「Share on LinkedIn」")
        print("   - 申請「Sign In with LinkedIn using OpenID Connect」")
        print()
        print("3. 設定 OAuth")
        print("   - 在「Auth」分頁，加 redirect URL: http://localhost:8789/callback")
        print()
        print("4. 複製憑證")
        print("   - 在「Auth」分頁複製 Client ID 和 Client Secret\n")
    else:
        print("\n=== LinkedIn Setup ===\n")
        print("1. Create a LinkedIn App")
        print("   - Go to https://www.linkedin.com/developers/apps")
        print("   - Click 'Create App'")
        print("   - LinkedIn Page: use your own page if you have one,")
        print("     otherwise type 'Default Company Page for Individual Developer'")
        print("   - Upload a photo for the App logo")
        print()
        print("2. Request product access")
        print("   - Under 'Products' tab, request 'Share on LinkedIn'")
        print("   - Request 'Sign In with LinkedIn using OpenID Connect'")
        print()
        print("3. Configure OAuth")
        print("   - Under 'Auth' tab, add redirect URL: http://localhost:8789/callback")
        print()
        print("4. Copy credentials")
        print("   - Copy your Client ID and Client Secret from the 'Auth' tab\n")
    webbrowser.open("https://www.linkedin.com/developers/apps")
    print(("正在開啟 LinkedIn 開發者後台..." if zh else "(Opening LinkedIn Developer Portal in your browser...)") + "\n")
    client_id = input(("貼上 Client ID: " if zh else "Paste Client ID: ")).strip()
    client_secret = input(("貼上 Client Secret: " if zh else "Paste Client Secret: ")).strip()
    if not client_id or not client_secret:
        print("已取消。" if zh else "Aborted.", file=sys.stderr)
        return False
    update_env("LINKEDIN_CLIENT_ID", client_id)
    update_env("LINKEDIN_CLIENT_SECRET", client_secret)
    print("\n正在啟動 OAuth 授權流程..." if zh else "\nStarting OAuth flow to get your access token...")
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
    print("正在取得 LinkedIn person ID..." if zh else "Getting your LinkedIn person ID...", file=sys.stderr)
    resp = requests.get("https://api.linkedin.com/v2/userinfo",
                        headers={"Authorization": f"Bearer {tokens['access_token']}"})
    if resp.status_code == 200:
        sub = resp.json().get("sub", "")
        person_id = f"urn:li:person:{sub}"
        update_env("LINKEDIN_PERSON_ID", person_id)
        print(f"✅ LinkedIn 設定完成！Person ID: {person_id}" if zh else f"✅ LinkedIn configured! Person ID: {person_id}")
        return True
    print("❌ 無法取得 LinkedIn person ID。" if zh else "❌ Could not get LinkedIn person ID.", file=sys.stderr)
    return False


def _setup_tiktok():
    """Guide user through TikTok OAuth setup."""
    zh = _detect_lang() == "zh"
    if zh:
        print("\n=== TikTok 設定 ===\n")
        print("注意：目前只支援 Sandbox 模式。Sandbox 模式下貼文只會發到私人帳號，")
        print("別人看不到。如果需要公開發文，需要用公開網域驗證 URL 並送審。\n")
        print("1. 建立 TikTok App")
        print("   - 去 https://developers.tiktok.com/apps/")
        print("   - 點「Connect an app」→ 選「Individual」")
        print("   - 選擇 Sandbox 模式")
        print()
        print("2. 填寫 App 資訊")
        print("   - 填寫 App Icon、App name、Category、Description")
        print("   - 填寫 Terms of Service URL 和 Privacy Policy URL")
        print()
        print("3. 設定平台")
        print("   - Platforms 只選「Desktop」")
        print("   - Desktop URL 填 http://localhost:8789")
        print()
        print("4. 新增產品")
        print("   - 新增「Login Kit」")
        print("   - 在 Login Kit 加 redirect URL: http://localhost:8789/callback")
        print("   - 新增「Content Posting API」")
        print()
        print("5. 新增帳號")
        print("   - 加你的 TikTok 帳號")
        print()
        print("6. 複製憑證")
        print("   - 複製 Client Key 和 Client Secret\n")
    else:
        print("\n=== TikTok Setup ===\n")
        print("Note: Currently only Sandbox mode is supported. In Sandbox mode, posts")
        print("are only visible on your private account. To post publicly, you need to")
        print("verify your URL with a public domain and submit for review.\n")
        print("1. Create a TikTok App")
        print("   - Go to https://developers.tiktok.com/apps/")
        print("   - Click 'Connect an app' -> select 'Individual'")
        print("   - Select Sandbox mode")
        print()
        print("2. Fill in App details")
        print("   - Fill in App Icon, App name, Category, Description")
        print("   - Fill in Terms of Service URL and Privacy Policy URL")
        print()
        print("3. Configure platform")
        print("   - For Platforms, only select 'Desktop'")
        print("   - Set Desktop URL to http://localhost:8789")
        print()
        print("4. Add products")
        print("   - Add 'Login Kit'")
        print("   - In Login Kit, add redirect URL: http://localhost:8789/callback")
        print("   - Add 'Content Posting API'")
        print()
        print("5. Add account")
        print("   - Add your TikTok account")
        print()
        print("6. Copy credentials")
        print("   - Copy Client Key and Client Secret\n")
    webbrowser.open("https://developers.tiktok.com/apps/")
    print(("正在開啟 TikTok 開發者後台..." if zh else "(Opening TikTok Developer Portal in your browser...)") + "\n")
    client_key = input(("貼上 Client Key: " if zh else "Paste Client Key: ")).strip()
    client_secret = input(("貼上 Client Secret: " if zh else "Paste Client Secret: ")).strip()
    if not client_key or not client_secret:
        print("已取消。" if zh else "Aborted.", file=sys.stderr)
        return False
    update_env("TIKTOK_CLIENT_KEY", client_key)
    update_env("TIKTOK_CLIENT_SECRET", client_secret)
    print("\n正在啟動 OAuth 授權流程..." if zh else "\nStarting OAuth flow...")
    tokens = oauth_browser_flow(
        auth_url_base="https://www.tiktok.com/v2/auth/authorize/",
        token_url="https://open.tiktokapis.com/v2/oauth/token/",
        client_id=client_key, client_secret=client_secret,
        scopes="user.info.basic,video.publish",
        pkce="hex",
        client_id_param="client_key",
    )
    if tokens.get("access_token"):
        update_env("TIKTOK_ACCESS_TOKEN", tokens["access_token"])
    if tokens.get("refresh_token"):
        update_env("TIKTOK_REFRESH_TOKEN", tokens["refresh_token"])
    print("驗證中..." if zh else "Validating...", file=sys.stderr)
    if validate_token("tiktok"):
        print("✅ TikTok 設定完成！" if zh else "✅ TikTok configured!")
        return True
    print("❌ 驗證失敗。" if zh else "❌ Validation failed.", file=sys.stderr)
    return False


def _setup_youtube():
    """Guide user through YouTube/Google OAuth setup."""
    zh = _detect_lang() == "zh"
    if zh:
        print("\n=== YouTube 設定 ===\n")
        print("1. 建立 Google Cloud 專案")
        print("   - 去 https://console.cloud.google.com/")
        print("   - 建立新專案（或用現有的）")
        print()
        print("2. 啟用 YouTube Data API v3")
        print("   - 在專案中去 APIs & Services → Library")
        print("   - 搜尋「YouTube Data API v3」→ 點啟用")
        print()
        print("3. 設定 OAuth consent screen")
        print("   - 去 APIs & Services → OAuth consent screen")
        print("   - App name 填你的 app 名稱，User support email 填你的 email")
        print("   - 去「Audience」→ 點「+Add Users」→ 加你的 email 為測試使用者")
        print("   - 去「Data Access」→ 點「Add or Remove Scopes」")
        print("     → 加 scope: https://www.googleapis.com/auth/youtube.upload")
        print()
        print("4. 建立 OAuth 2.0 憑證")
        print("   - 去 APIs & Services → Credentials")
        print("   - 點 Create Credentials → OAuth client ID")
        print("   - Application type 選 Web application")
        print("   - 加 http://localhost:8789/callback 為 Authorized redirect URI")
        print("   - 複製 Client ID 和 Client Secret\n")
    else:
        print("\n=== YouTube Setup ===\n")
        print("1. Create a Google Cloud project")
        print("   - Go to https://console.cloud.google.com/")
        print("   - Create a new project (or use existing)")
        print()
        print("2. Enable the YouTube Data API v3")
        print("   - In your project, go to APIs & Services → Library")
        print("   - Search for 'YouTube Data API v3' → click Enable")
        print()
        print("3. Configure OAuth consent screen")
        print("   - Go to APIs & Services → OAuth consent screen")
        print("   - Fill in App name and User support email")
        print("   - Go to 'Audience' → click '+Add Users' → add your email as a test user")
        print("   - Go to 'Data Access' → click 'Add or Remove Scopes'")
        print("     → add scope: https://www.googleapis.com/auth/youtube.upload")
        print()
        print("4. Create OAuth 2.0 credentials")
        print("   - Go to APIs & Services → Credentials")
        print("   - Click Create Credentials → OAuth client ID")
        print("   - For Application type, select Web application")
        print("   - Add http://localhost:8789/callback as an Authorized redirect URI")
        print("   - Copy the Client ID and Client Secret\n")
    webbrowser.open("https://console.cloud.google.com/apis/credentials")
    print(("正在開啟 Google Cloud Console..." if zh else "(Opening Google Cloud Console in your browser...)") + "\n")
    client_id = input(("貼上 Client ID: " if zh else "Paste Client ID: ")).strip()
    client_secret = input(("貼上 Client Secret: " if zh else "Paste Client Secret: ")).strip()
    if not client_id or not client_secret:
        print("已取消。" if zh else "Aborted.", file=sys.stderr)
        return False
    update_env("YOUTUBE_CLIENT_ID", client_id)
    update_env("YOUTUBE_CLIENT_SECRET", client_secret)
    print("\n正在啟動 OAuth 授權流程取得 refresh token..." if zh else "\nStarting OAuth flow to get refresh token...")
    tokens = oauth_browser_flow(
        auth_url_base="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        client_id=client_id, client_secret=client_secret,
        scopes="https://www.googleapis.com/auth/youtube.upload",
        extra_auth_params={"access_type": "offline", "prompt": "consent"},
    )
    if tokens.get("refresh_token"):
        update_env("YOUTUBE_REFRESH_TOKEN", tokens["refresh_token"])
    else:
        print("警告：沒有收到 refresh token。可能需要撤銷權限後重新授權。" if zh else
              "Warning: No refresh token received. You may need to revoke access and re-authorize.", file=sys.stderr)
        print("前往：https://myaccount.google.com/permissions" if zh else
              "Visit: https://myaccount.google.com/permissions", file=sys.stderr)
    print("驗證中..." if zh else "Validating...", file=sys.stderr)
    if validate_token("youtube"):
        print("✅ YouTube 設定完成！" if zh else "✅ YouTube configured!")
        return True
    print("❌ 驗證失敗。" if zh else "❌ Validation failed.", file=sys.stderr)
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
