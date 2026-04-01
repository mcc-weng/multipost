---
name: multipost
description: Post to 6 platforms (Threads, X, Instagram, LinkedIn, TikTok, YouTube) with one command. Guides setup, handles OAuth, posts via API or Playwright fallback. Use when user says "post to threads", "post everywhere", "set up multipost", "multipost status", "設定 multipost", "發文到", "發到所有平台".
---

# multipost — Multi-Platform Posting Skill

Post content to Threads, X, Instagram, LinkedIn, TikTok, and YouTube from Claude Code.

## Paths

- Scripts: `./scripts/` (relative to repo root)
- Config: `./.env`
- Setup wizard: `./configure.py`

**IMPORTANT:** All paths are relative to the multipost repo root. Before running any command, verify the user is in the multipost directory:
```bash
ls configure.py scripts/shared.py 2>/dev/null && echo "OK" || echo "ERROR: Not in multipost directory. Run: cd ~/Projects/multipost"
```

## Before Posting

Check platform status first:
```bash
python3 configure.py --status
```

If a platform is **not configured**, tell the user:
> "Run `python3 configure.py [platform]` in your terminal to set it up. Let me know if you run into any issues."
> 「在終端機跑 `python3 configure.py [platform]` 來設定。有問題的話跟我說。」

**Do NOT try to guide the user through setup yourself** — the Python script has the exact, up-to-date instructions with bilingual support and handles OAuth flows.

## Posting

Triggered by: "post [text] to [platform]", "post everywhere", "publish to threads", "發文到 [platform]", "發到所有平台"

**Step 1:** Confirm with user before posting:
> Ready to post to **[Platform]**?
>
> ---
> [post text]
> ---
>
> Post this? (y/n)

**Step 2:** Post based on platform:

#### Text platforms (Threads, LinkedIn)

```bash
python3 scripts/post_threads.py "Post text here"
python3 scripts/post_threads.py --topic "Technology" "Post text here"
python3 scripts/post_linkedin.py "Post text here"
```

#### Image platform (Instagram)

Ask for images (1 for single post, 2+ for carousel). Accepts URLs or local file paths:
> "Paste image URLs or local file paths (comma-separated, 1 for single image, 2+ for carousel):"

```bash
# Single image
python3 scripts/post_instagram.py --images "/path/to/photo.jpg" "Caption text"
python3 scripts/post_instagram.py --images "https://example.com/photo.jpg" "Caption text"

# Carousel (2+ images)
python3 scripts/post_instagram.py --images "url1,url2" "Caption text"
python3 scripts/post_instagram.py --images "/path/a.jpg,/path/b.jpg" "Caption text"
```

#### Video platforms (TikTok, YouTube)

Ask for: video path, and for YouTube also ask if it's a **regular video** or a **Short**.

```bash
# TikTok
python3 scripts/post_tiktok.py --media /path/to/video.mp4 "Caption text"

# YouTube — regular video
python3 scripts/post_youtube.py --media /path/to/video.mp4 --title "Title" "Description"

# YouTube — Short (vertical video, <60s)
python3 scripts/post_youtube.py --short --media /path/to/video.mp4 --title "Title" "Description"
```

#### X (Playwright fallback — free, no API needed)

X API uses pay-per-usage pricing. Use Playwright browser automation instead (free):

1. `browser_navigate` to `https://x.com/compose/post`
2. `browser_snapshot` — check if login page appears
   - If login: tell user "Please log in to X in the browser window, then tell me when done."
   - Wait for user confirmation, then `browser_snapshot` again
3. `browser_snapshot` — find the compose text area
4. `browser_click` on the text input area
5. `browser_type` the post text
6. `browser_snapshot` — find the "Post" button
7. Ask user: "Ready to click Post? (y/n)"
8. `browser_click` the "Post" button
9. `browser_wait_for` 3 seconds
10. `browser_snapshot` — verify post was submitted

If Playwright fails, fall back to manual:
```
--- Copy and paste to X ---

[post text]

--- End ---
```

#### RED (manual only — no API)

Present a copy-paste block:
```
--- RED Post ---

Title: [first line or user-specified title]

[body text]

[hashtags]

--- End ---

Paste into the RED creator app. Add a cover image (3:4 vertical) before posting.
```

#### "Post everywhere"

Post to all configured platforms in sequence:
1. Check which platforms are configured: `python3 configure.py --status`
2. For each configured platform, run the appropriate command
3. For X: use Playwright fallback
4. For RED: present copy-paste block
5. Report results for each platform

## Dry Run

For a user's first post, suggest a dry run:
> "Want to do a dry run first? I'll simulate the post without actually publishing."

```bash
python3 scripts/post_threads.py --dry-run "Post text"
```

## Prerequisites

- **ngrok**: Required for Instagram local image uploads. Install: `brew install ngrok && ngrok authtoken YOUR_TOKEN`
  - Get your authtoken at https://dashboard.ngrok.com/get-started/your-authtoken

## Error Handling

- **401 error**: Token expired. Run `python3 scripts/refresh_tokens.py [platform]` or re-setup: `python3 configure.py [platform]`
- **403 error**: API permissions issue. Check platform developer portal.
- **Script not found**: User isn't in the multipost directory. `cd ~/Projects/multipost`
- **Platform not configured**: Tell user to run `python3 configure.py [platform]` in their terminal
- **ngrok tunnel failed**: Make sure ngrok is installed and authenticated. Kill stale sessions: `pkill -f ngrok`
- **Instagram aspect ratio error**: Image must be between 4:5 and 1.91:1 ratio

## Token Refresh

Tokens expire every ~60 days (Meta, LinkedIn) or ~2 hours (TikTok). Scripts auto-refresh before posting. For manual refresh:

```bash
python3 scripts/refresh_tokens.py              # All platforms
python3 scripts/refresh_tokens.py threads      # Specific platform
```

## Rules

- NEVER post without explicit user confirmation
- NEVER modify the post text — post exactly what was approved
- Always check platform status before posting
- Suggest dry-run on first use
- For X: prefer Playwright over API (free vs pay-per-usage)
- For RED: always manual (no API exists)
