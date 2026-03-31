---
name: multipost
description: Post to 6 platforms (Threads, X, Instagram, LinkedIn, TikTok, YouTube) with one command. Guides setup, handles OAuth, posts via API or Playwright fallback. Use when user says "post to threads", "post everywhere", "set up multipost", or "multipost status".
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

## Two Modes

### Mode 1: Setup

Triggered by: "set up multipost", "configure platforms", "multipost status"

**Step 1:** Check status:
```bash
python3 configure.py --status
```

**Step 2:** For each unconfigured platform, ask the user:
> "[Platform] isn't configured yet. Want to set it up now?"

**Step 3:** If yes, run the interactive setup:
```bash
python3 scripts/post_[platform].py --setup
```

The script will guide the user through creating a developer app and getting tokens. Relay the prompts to the user and pass their responses.

**Step 4:** Show final status:
```bash
python3 configure.py --status
```

### Mode 2: Post

Triggered by: "post [text] to [platform]", "post everywhere", "publish to threads"

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

Ask for image URLs first:
> "Instagram requires at least 2 images for a carousel. Paste the URLs (comma-separated):"

```bash
python3 scripts/post_instagram.py --images "url1,url2" "Caption text"
```

#### Video platforms (TikTok, YouTube)

Ask for video path first:
> "Paste the path to your video file:"

```bash
python3 scripts/post_tiktok.py --media /path/to/video.mp4 "Caption text"
python3 scripts/post_youtube.py --media /path/to/video.mp4 --title "Title" "Description"
python3 scripts/post_youtube.py --short --media /path/to/video.mp4 --title "Title" "Description"
```

#### X (Playwright fallback — free, no API needed)

X API costs $100/month. Use Playwright browser automation instead:

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

## Error Handling

- **401 error**: Token expired. Run `python3 scripts/refresh_tokens.py [platform]` or re-setup: `python3 configure.py [platform]`
- **403 error**: API permissions issue. Check platform developer portal.
- **Script not found**: User isn't in the multipost directory. `cd ~/Projects/multipost`
- **Platform not configured**: Offer to run setup: `python3 scripts/post_[platform].py --setup`

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
- For X: prefer Playwright over API (free vs $100/month)
- For RED: always manual (no API exists)
