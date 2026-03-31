# multipost

一個指令，發到 6 個平台。

Post to 6 platforms with one command.

## 支援平台 / Supported Platforms

| 平台 Platform | 內容 Content | 認證 Auth | 費用 Cost |
|--------------|-------------|-----------|----------|
| Threads | 文字 Text + topics | Meta token（貼上 paste） | 免費 Free |
| Instagram | 輪播圖 Carousel (images) | Meta token（貼上 paste） | 免費 Free |
| X (Twitter) | 文字 Text | API key 或 Playwright | API: $100/月mo, Playwright: 免費 Free |
| LinkedIn | 文字 Text + 圖片 images | OAuth 瀏覽器授權 browser flow | 免費 Free |
| TikTok | 影片 Video | OAuth 瀏覽器授權 browser flow | 免費 Free（先進沙盒 sandbox first） |
| YouTube | 影片 Video | OAuth 瀏覽器授權 browser flow | 免費 Free |

## 快速開始 / Quick Start

### 用 Claude Code（推薦）/ With Claude Code (recommended)

```bash
git clone https://github.com/mcc-weng/multipost.git
cd multipost
pip install -r requirements.txt
```

安裝 skill：

Install the skill:
```bash
mkdir -p ~/.claude/skills && cp skill/SKILL.md ~/.claude/skills/multipost-SKILL.md
```

然後在 Claude Code 裡面輸入：

Then in Claude Code:
```
> set up multipost
```

Claude 會一步一步帶你設定每個平台

Claude walks you through connecting each platform.

### 不用 Claude Code / Without Claude Code

```bash
git clone https://github.com/mcc-weng/multipost.git
cd multipost
pip install -r requirements.txt
python3 configure.py
```

設定精靈會互動式引導你完成每個平台的設定

The setup wizard guides you through each platform interactively.

## 使用方式 / Usage

### 文字貼文 / Text posts

```bash
# Threads
python3 scripts/post_threads.py "你的貼文 Your post text"
python3 scripts/post_threads.py --topic "Technology" "加話題標籤 With topic tag"

# LinkedIn
python3 scripts/post_linkedin.py "你的貼文 Your post text"
python3 scripts/post_linkedin.py --media /path/to/image.jpg "附圖 With image"

# X（需要設定 API / if API configured）
python3 scripts/post_x.py "你的推文 Your tweet"
```

### 圖片貼文 / Image posts

```bash
# Instagram（輪播圖 carousel，至少 2 張圖片 URL / min 2 image URLs）
python3 scripts/post_instagram.py --images "https://url1.jpg,https://url2.jpg" "圖片說明 Caption"
```

### 影片貼文 / Video posts

```bash
# TikTok
python3 scripts/post_tiktok.py --media /path/to/video.mp4 "影片說明 Caption #hashtag"

# YouTube
python3 scripts/post_youtube.py --media /path/to/video.mp4 --title "影片標題 Title" "影片說明 Description"

# YouTube Shorts
python3 scripts/post_youtube.py --short --media /path/to/short.mp4 --title "標題 Title" "說明 Description"
```

### 測試模式 / Dry run

不會真的發出去

Test without posting:

```bash
python3 scripts/post_threads.py --dry-run "測試貼文 Test post"
```

### 查看狀態 / Check status

```bash
python3 configure.py --status
```

## 設定說明 / Setup Details

### Threads 和 Instagram（Meta）

用 Meta Developer Portal 設定，設定精靈會帶你：建立 App → 加 API 產品 → 產生 token → 貼上

Uses the Meta Developer Portal. The wizard walks you through: Create app → Add API product → Generate token → Paste

不需要 OAuth 流程，直接貼上 token 就好

No OAuth flow needed — you paste the token directly.

### LinkedIn、TikTok、YouTube（OAuth）

設定精靈會：引導你建立開發者 App → 貼上 Client ID 和 Secret → 自動開瀏覽器跑 OAuth → 存 token 到 .env

The wizard: Guides app creation → Asks for Client ID + Secret → Opens browser for OAuth → Saves tokens to .env

### X (Twitter)

X API 需要 Basic 方案（$100/月）才能發文，設定精靈會提醒你費用，可以跳過

X API requires Basic tier ($100/month) for posting. The wizard warns about cost — you can skip.

用 Claude Code skill 的話可以免費透過 Playwright 瀏覽器自動化發文

With the Claude Code skill, you can post to X for free via Playwright browser automation.

### RED（小紅書）

RED 沒有公開 API，Claude Code skill 會產生複製貼上的格式讓你手動貼到 RED creator app

RED has no public API. The Claude Code skill presents a copy-paste block for manual posting.

## Token 更新 / Token Refresh

大部分 token 約 60 天過期，腳本會在發文前自動更新

Most tokens expire every ~60 days. Scripts auto-refresh before posting.

手動更新 / Manual refresh:

```bash
python3 scripts/refresh_tokens.py              # 更新所有平台 / Refresh all
python3 scripts/refresh_tokens.py threads      # 更新特定平台 / Refresh one
```

會自動更新 / Auto-refreshes: Threads, Instagram, TikTok, LinkedIn

不需要更新 / No refresh needed: YouTube（每次自動換 auto per request）, X（token 不會過期 never expires）

## 怎麼做的 / How I Built This

大部分的 code 不是我自己寫的

I didn't write most of this code by hand.

我跟 Claude Code 說我需要什麼——能發文到 6 個平台的 Python 腳本，處理 OAuth，自動更新 token。Claude Code 寫好腳本，我測試、修 auth 問題、反覆調整。全部搞定花了一個 session

I told Claude Code what I needed — Python scripts that post to 6 platforms, handle OAuth, and refresh tokens. Claude Code wrote the scripts. I tested each one, fixed auth issues, and iterated. Total time: one session.

最難的不是寫 code，是搞各平台的 OAuth 和 API 審核。每個平台都有自己的認證流程。6 個平台全部設定好大概要一天

The hardest parts weren't the code — they were the OAuth flows and API approvals. Each platform has its own auth dance. Budget a day for setup if you're doing all 6.

## 疑難排解 / Troubleshooting

| 錯誤 Error | 原因 Cause | 解法 Fix |
|------------|-----------|----------|
| `401 Unauthorized` | Token 過期 expired | `python3 scripts/refresh_tokens.py [platform]` 或 or `python3 configure.py [platform]` |
| `403 Forbidden` | API 權限不足 wrong tier/permissions | 檢查平台開發者後台 Check developer portal |
| `not configured` | 平台未設定 not set up | `python3 configure.py [platform]` |
| Port 8789 busy | OAuth 時 port 被佔用 | 腳本會自動試 8789-8799 / Auto-tries 8789-8799 |
| TikTok 看不到貼文 posts not visible | 沙盒模式 sandbox mode | 到 TikTok 開發者後台送審 Submit app for review |
| YouTube `No refresh token` | 之前已經授權過 already authorized | 到 myaccount.google.com/permissions 撤銷後重新設定 Revoke and re-setup |
| Instagram `carousel requires 2+ images` | 只給了 1 張圖 single image | 至少 2 張圖片 URL / Use at least 2 image URLs |

## 專案結構 / Project Structure

```
multipost/
├── configure.py           # 設定精靈 Setup wizard
├── .env.example           # API token 模板 Template
├── requirements.txt       # Python 套件 Dependencies
├── scripts/
│   ├── shared.py          # 核心：認證、錯誤處理、OAuth Core: auth, errors, OAuth
│   ├── post_threads.py    # 發文到 Threads / Post to Threads
│   ├── post_x.py          # 發文到 X / Post to X
│   ├── post_instagram.py  # 發文到 Instagram / Post to Instagram
│   ├── post_linkedin.py   # 發文到 LinkedIn / Post to LinkedIn
│   ├── post_tiktok.py     # 發文到 TikTok / Post to TikTok
│   ├── post_youtube.py    # 發文到 YouTube / Post to YouTube
│   └── refresh_tokens.py  # 更新 token / Refresh tokens
└── skill/
    └── SKILL.md           # Claude Code skill
```

## License

MIT
