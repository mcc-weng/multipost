# multipost

一個指令，發到 6 個平台。

Post to 6 platforms with one command.

## Supported Platforms

| Platform | Content Type | Auth Method | Cost |
|----------|-------------|-------------|------|
| Threads | Text + topics | Meta token (paste) | Free |
| Instagram | Carousel (images) | Meta token (paste) | Free |
| X (Twitter) | Text | API key (paste) or Playwright | API: $100/mo, Playwright: Free |
| LinkedIn | Text + images | OAuth browser flow | Free |
| TikTok | Video | OAuth browser flow | Free (sandbox mode first) |
| YouTube | Video | OAuth browser flow | Free |

## Quick Start

### With Claude Code (recommended)

```bash
git clone https://github.com/mikeweng/multipost.git
cd multipost
pip install -r requirements.txt
```

Then in Claude Code:
```
> set up multipost
```

Claude walks you through connecting each platform.

### Without Claude Code

```bash
git clone https://github.com/mikeweng/multipost.git
cd multipost
pip install -r requirements.txt
python3 configure.py
```

The setup wizard guides you through each platform interactively.

## Usage

### Text posts

```bash
# Threads
python3 scripts/post_threads.py "Your post text here"
python3 scripts/post_threads.py --topic "Technology" "With a topic tag"

# LinkedIn
python3 scripts/post_linkedin.py "Your post text here"
python3 scripts/post_linkedin.py --media /path/to/image.jpg "With an image"

# X (if API configured)
python3 scripts/post_x.py "Your tweet here"
```

### Image posts

```bash
# Instagram (carousel, min 2 images as URLs)
python3 scripts/post_instagram.py --images "https://url1.jpg,https://url2.jpg" "Caption"
```

### Video posts

```bash
# TikTok
python3 scripts/post_tiktok.py --media /path/to/video.mp4 "Caption #hashtag"

# YouTube
python3 scripts/post_youtube.py --media /path/to/video.mp4 --title "Video Title" "Description"

# YouTube Shorts
python3 scripts/post_youtube.py --short --media /path/to/short.mp4 --title "Short Title" "Description"
```

### Dry run (test without posting)

Every script supports `--dry-run`:

```bash
python3 scripts/post_threads.py --dry-run "Test post"
```

### Check status

```bash
python3 configure.py --status
```

## Setup Details

### Threads & Instagram (Meta)

These use the Meta Developer Portal. The setup wizard walks you through:
1. Creating a Meta Developer app
2. Adding the Threads API / Instagram Graph API product
3. Generating a long-lived access token
4. Copying your User ID / Business Account ID

No OAuth flow needed — you paste the token directly.

### LinkedIn, TikTok, YouTube (OAuth)

These use OAuth 2.0. The setup wizard:
1. Guides you through creating a developer app on each platform
2. Asks you to paste your Client ID and Client Secret
3. Opens your browser for the OAuth consent screen
4. Captures the callback automatically on `localhost:8789`
5. Saves all tokens to `.env`

### X (Twitter)

X API requires the Basic tier ($100/month) for write access. The setup wizard warns you about the cost and offers to skip.

If you use the Claude Code skill, you can post to X for free via browser automation (Playwright).

### RED (小紅書)

RED has no public API. The Claude Code skill presents a copy-paste block for manual posting via the RED creator app.

## Token Refresh

Most tokens expire every ~60 days. Scripts auto-refresh before posting. For manual refresh:

```bash
python3 scripts/refresh_tokens.py              # Refresh all platforms
python3 scripts/refresh_tokens.py threads      # Refresh one platform
```

Platforms that refresh: Threads, Instagram, TikTok, LinkedIn.
No refresh needed: YouTube (auto per request), X (tokens don't expire).

## How I Built This

I didn't write most of this code by hand.

I told Claude Code what I needed — Python scripts that post to 6 platforms, handle OAuth, and refresh tokens. Claude Code wrote the scripts. I tested each one, fixed auth issues, and iterated. Total time: one session.

The hardest parts weren't the code — they were the OAuth flows and API approvals. Each platform has its own auth dance. Budget a day for setup if you're doing all 6.

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `401 Unauthorized` | Token expired | `python3 scripts/refresh_tokens.py [platform]` or re-run `python3 configure.py [platform]` |
| `403 Forbidden` | Wrong API tier or missing permissions | Check platform developer portal |
| `THREADS_ACCESS_TOKEN not set` | Platform not configured | Run `python3 configure.py threads` |
| Port 8789 busy during OAuth | Another process on that port | Script auto-tries ports 8789-8799 |
| TikTok posts not visible | Sandbox mode | Submit app for review on TikTok developer portal |
| YouTube `No refresh token` | Already authorized before | Revoke at myaccount.google.com/permissions, re-run setup |
| Instagram `carousel requires 2+ images` | Single image passed | Use at least 2 image URLs |

## Project Structure

```
multipost/
├── configure.py           # Setup wizard
├── .env.example           # Template for API tokens
├── requirements.txt       # Python dependencies
├── scripts/
│   ├── shared.py          # Core: auth, errors, OAuth, setup
│   ├── post_threads.py    # Post to Threads
│   ├── post_x.py          # Post to X
│   ├── post_instagram.py  # Post to Instagram
│   ├── post_linkedin.py   # Post to LinkedIn
│   ├── post_tiktok.py     # Post to TikTok
│   ├── post_youtube.py    # Post to YouTube
│   └── refresh_tokens.py  # Refresh expiring tokens
└── skill/
    └── SKILL.md           # Claude Code skill
```

## License

MIT
