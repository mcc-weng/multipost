# multipost

一個指令，發到 6 個平台。

Post to 6 platforms with one command.

## 支援平台 / Supported Platforms

| 平台 Platform | 內容 Content | 認證 Auth | 費用 Cost |
|--------------|-------------|-----------|----------|
| Threads | 文字 Text + topics | Meta token（貼上 paste） | 免費 Free |
| Instagram | 圖片 Images (single or carousel) | Meta token（貼上 paste） | 免費 Free |
| X (Twitter) | 文字 Text | API key 或 Playwright | API: 按量付費 pay-per-use, Playwright: 免費 Free |
| LinkedIn | 文字 Text + 圖片 images | OAuth 瀏覽器授權 browser flow | 免費 Free |
| TikTok | 影片 Video | OAuth 瀏覽器授權 browser flow | 免費 Free（先進沙盒 sandbox first） |
| YouTube | 影片 Video | OAuth 瀏覽器授權 browser flow | 免費 Free |

## 快速開始 / Quick Start

```bash
git clone https://github.com/mcc-weng/multipost.git
cd multipost
pip install -r requirements.txt
python3 configure.py
```

設定精靈會互動式引導你完成每個平台的設定，支援中英文

The setup wizard guides you through each platform interactively, with bilingual support.

```bash
python3 configure.py                    # 自動偵測語言 / Auto-detect language
python3 configure.py --lang zh          # 強制中文 / Force Chinese
python3 configure.py --lang en          # 強制英文 / Force English
python3 configure.py --lang zh threads  # 中文，只設定 Threads / Chinese, Threads only
python3 configure.py --status           # 查看狀態 / Check status
```

### 搭配 Claude Code / With Claude Code

安裝 skill 讓 Claude 幫你發文：

Install the skill so Claude can post for you:
```bash
mkdir -p ~/.claude/skills/multipost && cp skill/SKILL.md ~/.claude/skills/multipost/SKILL.md
```

然後在 Claude Code 裡面說「post to threads」或「發文到 Instagram」，Claude 會用腳本帶你完成發文流程

Then tell Claude "post to threads" or "post everywhere" — Claude will use the scripts and take you through posting.

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
# Instagram 單張圖 single image（URL 或本機檔案 or local file）
python3 scripts/post_instagram.py --images "https://url.jpg" "圖片說明 Caption"
python3 scripts/post_instagram.py --images "/path/to/photo.jpg" "圖片說明 Caption"

# Instagram 輪播圖 carousel（2+ 張圖片 images）
python3 scripts/post_instagram.py --images "https://url1.jpg,https://url2.jpg" "圖片說明 Caption"
python3 scripts/post_instagram.py --images "/path/to/a.jpg,/path/to/b.jpg" "圖片說明 Caption"
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

### Threads

1. **建立 Meta App / Create a Meta App**
   - 去 https://developers.facebook.com/apps/
   - 點「建立應用程式」/ Click "Create App"（或用現有的 app / or use existing app）
   - 使用案例加「存取 Threads API」/ For Use cases add "Access Threads API"
   - 商家選「我還不想連結商家資產管理組合」/ For Business select "I don't want to connect a business portfolio yet"
   - 「下一步」→「下一步」→「建立應用程式」/ "Next" → "Next" → "Create App"

2. **開啟發文權限 / Enable content publish permission**
   - Dashboard 側欄選「使用案例」/ Select "Use cases" on the side panel
   - 點「存取 Threads API」的 Edit / Click edit on "Access the Threads API"
   - 加 `threads_content_publish`

3. **加自己為測試人員 / Add yourself as a Threads Tester**
   - 去「設定」，在「用戶權杖產生器」點「新增或移除Threads測試人員」/ Go to "Settings", in "User Token Generator" click "Add or Remove Threads Testers"
   - 點「新增用戶」→ 選「Threads 測試人員」→ 輸入帳號 → 點「新增」/ Click "Add People" → Select "Threads Tester" → Enter username → Click "Add"

4. **接受邀請 / Accept the tester invite**
   - 點「網站權限」連結（會跳到 Threads），或在 Threads app →「設定」→「帳戶」→「網站權限」/ Click "Website permissions" link, or in Threads app → "Settings" → "Account" → "Website permissions"
   - 去「邀請」→ 接受 / Go to "Invitations" → Accept

5. **產生並儲存 token / Generate and save the access token**
   - 回到開發者後台 →「使用案例」→「存取 Threads API」→「設定」→ 點「產生存取權杖」/ Go back to developer console → "Use cases" → "Access Threads API" → "Settings" → Click "Generate"
   - 複製權杖 / Copy the access token
   - 打開 `.env`，加上 / Open `.env` and add：`THREADS_ACCESS_TOKEN=your_token_here`

### Instagram

前置條件：需要 Instagram 商業帳號（非個人帳號）

Prerequisite: You need an Instagram Business or Creator account (not personal).

1. **建立 Meta App / Create a Meta App**
   - 去 https://developers.facebook.com/apps/
   - 點「建立應用程式」/ Click "Create App"（或用現有的 app / or use existing app）
   - 使用案例加「管理Instagram的訊息或內容」/ For Use cases add "Manage messaging & content on Instagram"
   - 商家選「我還不想連結商家資產管理組合」/ For Business select "I don't want to connect a business portfolio yet"
   - 「下一步」→「下一步」→「建立應用程式」/ "Next" → "Next" → "Create App"

2. **設定權限 / Configure permissions**
   - Dashboard 側欄選「使用案例」/ Select "Use cases" on the side panel
   - 點「管理Instagram的訊息或內容」的 Customize / Click "Customize" on "Manage messaging & content on Instagram"
   - 加所有需要的權限 / Add all required permissions

3. **加自己為測試人員 / Add yourself as an Instagram Tester**
   - 點「角色」連結，或左下角去 App Roles → Roles / Click "Roles" link, or go to "App Roles" → "Roles" (bottom left)
   - 點「新增用戶」→ 選「Instagram 測試人員」→ 輸入帳號 → 點「新增」/ Click "Add People" → Select "Instagram Tester" → Enter username → Click "Add"

4. **接受邀請 / Accept the tester invite**
   - 點「應用程式和網站」連結，或在 IG →「設定」→「應用程式網站權限」→「應用程式和網站」→「測試員邀請」→「接受」/ Click "Apps and Websites" link, or in Instagram → "Settings" → "App Website permissions" → "Apps and websites" → "Tester Invitations" → "Accept"

5. **產生並儲存 token / Generate and save the access token**
   - 回到開發者後台 →「使用案例」→「管理Instagram的訊息或內容」→「設定」/ Go back to developer console → "Use cases" → "Manage messaging & content on Instagram" → "Settings"
   - 點「新增帳號」→ 登入帳號同意權限 / Click "Add account" → Log in and grant permissions
   - 點「產生權杖」/ Click "Generate access token"
   - 複製 access token / Copy access token
   - 打開 `.env`，加上 / Open `.env` and add：`INSTAGRAM_ACCESS_TOKEN=your_token_here`

**注意 / Note:** 本機圖片上傳需要 ngrok token（已包含在 pip install 中）。去 https://dashboard.ngrok.com/get-started/your-authtoken 取得免費 token，加到 `.env`：`NGROK_AUTHTOKEN=your_token`

Local image uploads require an ngrok token (pyngrok is included in pip install). Get your free token at https://dashboard.ngrok.com/get-started/your-authtoken and add to `.env`: `NGROK_AUTHTOKEN=your_token`

### LinkedIn

1. **建立 LinkedIn App / Create a LinkedIn App**
   - 去 https://www.linkedin.com/developers/apps → 點「Create App」/ Go to https://www.linkedin.com/developers/apps → Click "Create App"
   - LinkedIn Page：用你自己的專頁，或輸入「Default Company Page for Individual Developer」/ Use your own page, or type "Default Company Page for Individual Developer"
   - 上傳一張 App logo 圖片 / Upload a photo for the App logo

2. **申請產品權限 / Request product access**
   - 在「Products」分頁，申請「Share on LinkedIn」/ Under "Products" tab, request "Share on LinkedIn"
   - 申請「Sign In with LinkedIn using OpenID Connect」/ Request "Sign In with LinkedIn using OpenID Connect"

3. **設定 OAuth / Configure OAuth**
   - 在「Auth」分頁，加 redirect URL: `http://localhost:8789/callback` / Under "Auth" tab, add redirect URL

4. **複製憑證 / Copy credentials**
   - 在「Auth」分頁複製 Client ID 和 Client Secret / Copy Client ID and Client Secret from the "Auth" tab
   - 打開 `.env`，加上 / Open `.env` and add：
     `LINKEDIN_CLIENT_ID=your_client_id`
     `LINKEDIN_CLIENT_SECRET=your_client_secret`

5. **跑 OAuth 流程 / Run OAuth flow**
   - 跑 `python3 configure.py linkedin`，會自動開瀏覽器授權並存 token 到 `.env`
   - Run `python3 configure.py linkedin` — it opens a browser for OAuth and auto-saves tokens to `.env`

### TikTok

注意：目前只支援 Sandbox 模式。Sandbox 模式下貼文只會發到私人帳號，別人看不到。如果需要公開發文，需要用公開網域驗證 URL 並送審。

Note: Currently only Sandbox mode is supported. In Sandbox mode, posts are only visible on your private account. To post publicly, you need to verify your URL with a public domain and submit for review.

1. **建立 TikTok App / Create a TikTok App**
   - 去 https://developers.tiktok.com/apps/ → 點「Connect an app」→ 選「Individual」/ Go to https://developers.tiktok.com/apps/ → Click "Connect an app" → select "Individual"
   - 選擇 Sandbox 模式 / Select Sandbox mode

2. **填寫 App 資訊 / Fill in App details**
   - 填寫 App Icon、App name、Category、Description / Fill in App Icon, App name, Category, Description
   - 填寫 Terms of Service URL 和 Privacy Policy URL / Fill in Terms of Service URL and Privacy Policy URL

3. **設定平台 / Configure platform**
   - Platforms 只選「Desktop」/ For Platforms, only select "Desktop"
   - Desktop URL 填 `http://localhost:8789` / Set Desktop URL to `http://localhost:8789`

4. **新增產品 / Add products**
   - 新增「Login Kit」/ Add "Login Kit"
   - 在 Login Kit 加 redirect URL: `http://localhost:8789/callback` / In Login Kit, add redirect URL
   - 新增「Content Posting API」/ Add "Content Posting API"

5. **新增帳號並複製憑證 / Add account and copy credentials**
   - 加你的 TikTok 帳號 / Add your TikTok account
   - 複製 Client Key 和 Client Secret / Copy Client Key and Client Secret
   - 打開 `.env`，加上 / Open `.env` and add：
     `TIKTOK_CLIENT_KEY=your_client_key`
     `TIKTOK_CLIENT_SECRET=your_client_secret`

6. **跑 OAuth 流程 / Run OAuth flow**
   - 跑 `python3 configure.py tiktok`，會自動開瀏覽器授權並存 token 到 `.env`
   - Run `python3 configure.py tiktok` — it opens a browser for OAuth and auto-saves tokens to `.env`

### YouTube

1. **建立 Google Cloud 專案 / Create a Google Cloud project**
   - 去 https://console.cloud.google.com/ → 建立新專案（或用現有的）/ Go to https://console.cloud.google.com/ → Create a new project (or use existing)

2. **啟用 YouTube Data API v3 / Enable the YouTube Data API v3**
   - 在專案中去 APIs & Services → Library / In your project, go to APIs & Services → Library
   - 搜尋「YouTube Data API v3」→ 點啟用 / Search for "YouTube Data API v3" → click Enable

3. **設定 OAuth consent screen / Configure OAuth consent screen**
   - 去 APIs & Services → OAuth consent screen / Go to APIs & Services → OAuth consent screen
   - 填 App name 和 User support email / Fill in App name and User support email
   - 去「Audience」→ 點「+Add Users」→ 加你的 email 為測試使用者 / Go to "Audience" → click "+Add Users" → add your email as a test user
   - 去「Data Access」→ 點「Add or Remove Scopes」→ 加 scope: `https://www.googleapis.com/auth/youtube.upload` / Go to "Data Access" → click "Add or Remove Scopes" → add scope

4. **建立 OAuth 2.0 憑證 / Create OAuth 2.0 credentials**
   - 去 APIs & Services → Credentials / Go to APIs & Services → Credentials
   - 點 Create Credentials → OAuth client ID / Click Create Credentials → OAuth client ID
   - Application type 選 Web application / Select Web application
   - 加 `http://localhost:8789/callback` 為 Authorized redirect URI（必須是 8789）/ Add as Authorized redirect URI (must be 8789)
   - 複製 Client ID 和 Client Secret / Copy Client ID and Client Secret
   - 打開 `.env`，加上 / Open `.env` and add：
     `YOUTUBE_CLIENT_ID=your_client_id`
     `YOUTUBE_CLIENT_SECRET=your_client_secret`

5. **跑 OAuth 流程 / Run OAuth flow**
   - 跑 `python3 configure.py youtube`，會自動開瀏覽器授權並存 refresh token 到 `.env`
   - Run `python3 configure.py youtube` — it opens a browser for OAuth and auto-saves the refresh token to `.env`

### X (Twitter)

X API 採用按量付費模式，設定精靈會引導你建立開發者 App

X API uses a pay-per-usage model. The wizard guides you through creating a developer app.

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

## 疑難排解 / Troubleshooting

| 錯誤 Error | 原因 Cause | 解法 Fix |
|------------|-----------|----------|
| `401 Unauthorized` | Token 過期 expired | `python3 scripts/refresh_tokens.py [platform]` 或 or `python3 configure.py [platform]` |
| `403 Forbidden` | API 權限不足 wrong tier/permissions | 檢查平台開發者後台 Check developer portal |
| `not configured` | 平台未設定 not set up | `python3 configure.py [platform]` |
| Port 8789 busy | OAuth 時 port 被佔用 | 腳本會自動試 8789-8799 / Auto-tries 8789-8799 |
| TikTok 看不到貼文 posts not visible | 沙盒模式 sandbox mode | 到 TikTok 開發者後台送審 Submit app for review |
| YouTube `No refresh token` | 之前已經授權過 already authorized | 到 myaccount.google.com/permissions 撤銷後重新設定 Revoke and re-setup |
| Instagram `at least 1 image required` | 沒給圖片 no images | 用 --images 指定至少 1 張 / Use --images with at least 1 image |

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
