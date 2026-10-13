# REST API Post Scheduler for WordPress

Turns one page of a devotional PDF into one scheduled WordPress post, timed to go live at the **same moment** the matching YouTube video becomes public. Everything runs over REST APIs, so there is no manual copying, pasting, or scheduling.

- **Input:** a devotional PDF (one page per day) and a set of *scheduled* (private, not yet published) videos on your YouTube channel.
- **Output:** a WordPress post with status `future`, a featured image taken from the video, footnotes, and custom fields, scheduled for the video's publish time.

> **Scope note.** This is a personal project built around one specific book layout (Albanian-language, Brandon + Garamond fonts) and one specific WordPress site setup. The architecture is reusable, but a few parts are site-specific. See [Adapting it to your own site](#adapting-it-to-your-own-site).

---

## Table of contents

1. [How it works](#how-it-works)
2. [Requirements](#requirements)
3. [Setup](#setup)
4. [Running it](#running-it)
5. [Batch scheduling](#batch-scheduling)
6. [Configuration reference](#configuration-reference)
7. [Project layout](#project-layout)
8. [Troubleshooting](#troubleshooting)
9. [Security](#security)
10. [Adapting it to your own site](#adapting-it-to-your-own-site)
11. [Known limitations and TODO](#known-limitations-and-todo)
12. [License and notes](#license-and-notes)

---

## How it works

### The pipeline for one post

```
                    ┌──────────────────┐
  devotional PDF ──▶│  pdf_extractor   │──┐  date, quote, paragraphs,
   (page N)         └──────────────────┘  │  footnotes, closing verse
                                          ▼
  YouTube API ─▶ yt_auth ─▶ yt_service ─▶ yt_lookup ─▶ ┌────────────────┐
  (OAuth 2.0)                  finds the video whose   │ post_packager  │
                               title starts with the   └───────┬────────┘
                               PDF's date                      │ WordPress payload
                                                               ▼
                       ┌──────────────────────────  wp_client_scheduler  ◀── wp_posts (already exists?)
                       │                                      │
        yt_thumbnail ◀─┘ (frame from video)                   ├─▶ upload_media ─▶ media ID
        yt-dlp + ffmpeg + cwebp                               └─▶ POST / PATCH /wp-json/wp/v2/posts
```

Step by step, `python wp_client_scheduler.py tfl.pdf 294` does this:

| # | Step | Module |
|---|------|--------|
| 1 | Extract page 294 of the PDF into a dict (date, title, quote, paragraphs, footnotes, closing verse). | `pdf_extractor.py` |
| 2 | Take the PDF's date (e.g. `13 tetor`) and search your **scheduled** YouTube videos for a title that starts with `13 tetor - `. Exactly one must match. | `yt_lookup.py` → `yt_service.py` → `yt_auth.py` |
| 3 | Build the WordPress payload. The **post title is the YouTube video's title** and `date_gmt` is the video's `publishAt`. | `post_packager.py` |
| 4 | Check whether a post with that slug already exists (idempotency gate). | `wp_posts.py`, `wp_slug.py` |
| 5 | Refuse to continue if the publish time is not in the future. | `wp_client_scheduler.py` |
| 6 | Grab a frame from the video, resize it, convert it to WebP. | `yt_thumbnail.py` |
| 7 | Upload the WebP to the WordPress media library and get its attachment ID. | `upload_media.py` |
| 8 | Create the post (`POST`), or update an existing one (`PATCH`), with `featured_media` set. | `wp_client_scheduler.py` |
| 9 | Verify WordPress actually stored the featured image; fail loudly if not. | `wp_client_scheduler.py` |

### Why the YouTube title matters

The PDF stores titles as letter-spaced capitals (`U N G J I L L I …`), so the extractor cannot recover correct capitalization. The video title on YouTube is typed by a human and is correct, so it becomes the post title. This also means **your video titles must follow a convention**:

```
<day> <month> - <Title>          e.g.   13 tetor - Titulli i devotshmërisë
```

The packager searches with the regex `^<date from PDF, lowercased> - `. The match is case-insensitive, so `13 TETOR - …` also works. If zero or more than one scheduled video matches, nothing is posted. The code refuses to guess.

### Why OAuth 2.0 and not an API key

An API key can only read public data. A scheduled video is **private until its publish time**, so reading it requires your own account's consent. The project requests only the `youtube.readonly` scope, which can read your data but cannot upload, edit, or delete anything.

### Why the "uploads" playlist and not `search.list`

`search.list` only indexes public content, so it never returns scheduled videos. Every channel has a hidden **uploads playlist** containing every video regardless of privacy. `yt_service.py`:

1. Calls `channels.list(mine=True)` to get the uploads playlist ID.
2. Pages through `playlistItems.list` (50 per page).
3. Batches each page's IDs into **one** `videos.list` call to read `status` and `snippet`.
4. Keeps a video only if `privacyStatus == "private"` **and** it has a `publishAt`. That combination is what "scheduled" means.

Batching 50 IDs per `videos.list` call keeps API quota usage tiny (each list call costs 1 unit against the default 10,000 units per day).

> Because only videos that are *still scheduled* are visible to the lookup, a video that has already gone public is treated exactly like a missing one.

### How the PDF extractor works

`pdf_extractor.py` uses **PyMuPDF** and reads per-character data (`get_text("rawdict")`), then classifies every line by **font, size, and position**:

| Element | How it is recognised |
|---|---|
| Title | Brandon font, size ≥ 13. Letter-spacing is undone by measuring the gap between glyph boxes: a small gap is the same word, a gap over 1.5 pt is a word break. |
| Date | First Brandon line, size ≥ 9.5. |
| Quote and reference | Text between the title and the body. The reference is either a separate Brandon line or the all-caps-with-digits tail after the closing `”`. |
| Dropcap | Any span larger than 20 pt. It marks the start of the body and is glued back onto the first paragraph. |
| Footnote markers | Garamond spans smaller than 7 pt, converted to Unicode superscripts (`¹ ² ³`). |
| Footnotes | Lines smaller than 8.5 pt that start with a number. Wrapped lines are appended to the previous footnote. |
| Closing verse | A Brandon line **after** the body has started. |
| Ignored | The page number and the "Plani i leximit…" footer. |

Two details are worth understanding:

- **Paragraph detection is relative, not absolute.** The PDF is a book, so left and right pages have different margins. The extractor anchors to the dropcap's x-position: a line indented 3–12 pt from it starts a new paragraph. Lines indented about 18 pt are the wrap-around next to the dropcap and are not treated as new paragraphs.
- **Verse vs. prose.** Indented, fully italic lines are grouped into one verse block and joined with newlines. Everything else is prose, and wrapped lines are rejoined with hyphenation repair (`Aborigi-` + `nes` → `Aborigines`), covering U+002D, U+00AD and U+2010–U+2013.

### What the payload looks like

`post_packager.py` produces a dict shaped like this (the `_yt_video` key is internal and stripped before sending):

| Field | Value |
|---|---|
| `title` | The YouTube video's title |
| `content` | A centred paragraph with the italic quote and bold reference, then one `<p class="wp-block-paragraph">` per body paragraph, then the footnote list |
| `excerpt` | First 200 characters of the first paragraph, footnote markers removed |
| `status` | `future` |
| `date_gmt` | The video's `publishAt` (UTC) |
| `categories` | `[172, 96]`, **hard-coded IDs for the original site** |
| `acf.referenca` | The closing verse reference |
| `acf.video_url` | The YouTube watch URL |
| `meta.footnotes` | JSON list of `{content, id}` (only sent if the page has footnotes) |
| `featured_media` | Added later by the scheduler once the image is uploaded |

**Why `date_gmt` and not `date`:** `date` is interpreted in the *site's* timezone, while YouTube's `publishAt` is UTC. Sending `date_gmt` is unambiguous, so the post and the video go live in the same second.

**Footnotes.** The extractor turns superscript markers into `<sup>` links and the packager renumbers them 1..N. Each footnote gets a UUID derived from its *original* number and text (UUIDv5), so the same page always produces the same IDs. That is what makes updating an existing post safe. This uses WordPress's built-in footnotes feature.

### How scheduling stays safe to re-run

`wp_client_scheduler.py` slugifies the title (`wp_slug.py` approximates WordPress's `sanitize_title()`: strip accents, lowercase, non-alphanumerics become `-`) and looks the slug up via the REST API with `status=any`, so it also finds `future` and `draft` posts. What happens next is controlled by `SCHEDULE_ON_EXISTING`:

| Value | Behaviour when the post already exists |
|---|---|
| `skip` (default) | Print it and return the existing post. No image work, no changes. |
| `update` | `PATCH` the post in place. Content, categories, ACF fields and the featured image are refreshed; the **existing date and status are kept**. |
| `fail` | Abort with an error. |

For brand-new posts it also checks that `date_gmt` is in the future. WordPress would otherwise publish immediately or reject it.

### How the featured image is made

YouTube's thumbnail CDN does not serve real images for private videos, and the API only returns URLs pointing at that CDN. So `yt_thumbnail.py` takes a real frame instead:

1. `yt-dlp` downloads **only 2 seconds** of the video starting at `THUMB_AT_SECONDS`, authenticating as the channel owner with exported browser cookies (`cookies.txt`).
2. `ffmpeg` extracts one full-resolution JPEG frame.
3. `cwebp` resizes it to `THUMB_WIDTH` pixels (aspect ratio kept) and encodes WebP at `THUMB_QUALITY`.
4. The result is cached as `thumbnails/<slug>.webp`, so repeat runs make no network calls.

If YouTube rotates the session mid-download (error "the page needs to be reloaded"), the call is retried up to 3 times with backoff.

---

## Requirements

**Python 3.10 or newer** (the code uses `X | None` type hints).

**System packages** (used by `yt_thumbnail.py`):

```bash
sudo apt install ffmpeg webp        # webp provides the `cwebp` binary
```

**Python packages**: see `requirements.txt` (`requests`, `python-dotenv`, the Google API client libraries, `pymupdf`, `yt-dlp`, `deno`, `yt-dlp-ejs`). `yt-dlp` needs a JavaScript runtime plus the `yt-dlp-ejs` component to extract from YouTube, which is why `deno` is listed.

**WordPress site** (what the payload assumes):

- REST API enabled, and an **Application Password** for a user who can create posts and upload media. Application Passwords normally require the site to be served over HTTPS (or run as a local environment).
- A **footnotes** feature (core footnotes, WordPress 6.3+) exposed on posts.
- The **Advanced Custom Fields** fields `referenca` and `video_url`, exposed in the REST API.
- Category IDs `172` and `96` (or edit them, see [Adapting it to your own site](#adapting-it-to-your-own-site)).

**Accounts and files you provide yourself:**

- A Google Cloud project with the YouTube Data API v3 enabled.
- The devotional PDF (git-ignored; name it `tfl.pdf` to match `.gitignore`).
- A `cookies.txt` export of your YouTube session (for thumbnails).

---

## Setup

### 1. Python environment

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. WordPress credentials

```bash
cp .env.example .env
```

Fill in `.env`:

```dotenv
WP_URL=https://yoursite.com
WP_USER=your_wp_username
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

Create the Application Password in **WP Admin → Users → Profile → Application Passwords**. It is revocable and separate from your login password. Never reuse your real password here.

### 3. Google Cloud and YouTube OAuth

1. **Create a project** in the [Google Cloud Console](https://console.cloud.google.com) and enable the **YouTube Data API v3**.
2. **Configure the OAuth consent screen.**
   - User type **External** (Internal is Google Workspace only).
   - Add the scope `https://www.googleapis.com/auth/youtube.readonly`.
   - Add the exact Google account that owns the YouTube channel as a **test user**. Skipping this causes `403: access_denied`.
   - Leave the app in **Testing**. Testing-mode refresh tokens **expire after 7 days** (see [Troubleshooting](#troubleshooting)). Moving the app to **In production** (unverified) avoids this.
3. **Create an OAuth client ID** of type **Desktop app**, download the JSON, and save it as `credentials.json` in the project root.
4. **Authorize once.** `yt_auth.py` is a library module with no command line, so the first command that touches YouTube triggers the flow:

   ```bash
   python yt_lookup.py .
   ```

   A browser opens, you approve `youtube.readonly`, and `token.json` is written. Later runs reuse and silently refresh it.

   `run_local_server` needs a browser on the same machine. On a headless server, authorize on your desktop and copy `token.json` over.

### 4. YouTube cookies for thumbnails

`yt-dlp` needs a logged-in session to download frames from private videos. Export your youtube.com cookies in **Netscape format** to `cookies.txt` in the project root (a browser cookie-export extension works, or `yt-dlp --cookies-from-browser <browser> --cookies cookies.txt`). YouTube rotates cookies on open tabs, so exporting from a private or incognito window gives longer-lived cookies. To use a different path, set `YT_COOKIES`.

### 5. Put the PDF in place

Copy the devotional PDF into the project root as `tfl.pdf`.

---

## Running it

> **Run every command from the project root.** `credentials.json`, `token.json`, `cookies.txt`, `thumbnails/` and `.env` are all located by relative path.

### Check each stage on its own (nothing is posted)

Do these in order. Each isolates one concern.

```bash
# 1. YouTube auth + read. Prints the one match (title, publish time, URL),
#    or an error listing the matches if there are several / none.
python yt_lookup.py '^13 tetor'

# 2. PDF extraction as JSON (page numbers are 1-indexed)
python pdf_extractor.py tfl.pdf 294

# 3. Human-readable preview of the extracted page
python pdf_print_single_post.py tfl.pdf 294

# 4. Full payload preview (PDF + YouTube lookup, no WordPress writes)
python post_packager.py tfl.pdf 294
```

To see **all** scheduled videos at once:

```bash
python -c "from yt_service import list_scheduled_videos as l; [print(v['publish_at'], v['title']) for v in l()]"
```

### Schedule one post

```bash
python wp_client_scheduler.py tfl.pdf 294
```

Output (abridged):

```
1. Building the payload from the PDF page
2. Checking if post already exists
[thumb] thumbnails/13-tetor-....webp  (41234 bytes)
[media] attachment ID = 1234
Scheduled! ID: 5678
Status:       future
Link:         https://yoursite.com/?p=5678
```

Re-run behaviour is chosen with an environment variable:

```bash
SCHEDULE_ON_EXISTING=update python wp_client_scheduler.py tfl.pdf 294
```

### Schedule many posts

See [Batch scheduling](#batch-scheduling).

### Standalone helpers

| Command | What it does |
|---|---|
| `python yt_lookup.py '<regex>'` | Find exactly one scheduled video. Exit codes: `0` one match, `1` bad usage, `2` none or several, `3` invalid regex. |
| `python yt_thumbnail.py <video_id> ["title"] [at_seconds] [width]` | Produce a thumbnail WebP only. |
| `python upload_media.py <image>` | Upload one image to the media library and print its ID. **This writes to your site.** |

---

## Batch scheduling

`batch_schedule.py` schedules consecutive pages (one per day) and stops by itself when the videos run out.

```bash
python batch_schedule.py tfl.pdf                                   # start at today's page
python batch_schedule.py tfl.pdf --start-date 2026-10-15           # start at a date
python batch_schedule.py tfl.pdf --start-page 295 --end-page 310   # an explicit range
python batch_schedule.py tfl.pdf --start-page 295 --max-pages 3 --sleep 2
```

| Flag | Meaning |
|---|---|
| `--start-page N` / `--start-date YYYY-MM-DD` | Where to begin (mutually exclusive). Default: today. |
| `--end-page N` | Last PDF page to process. |
| `--max-pages N` | Hard cap on how many posts to process. |
| `--sleep S` | Pause between posts, in seconds (default 0). |

**How pages map to dates.** The script has a hard-coded anchor, `ANCHOR_PAGE = 294` ↔ `ANCHOR_DATE = 2026-10-13`, and every adjacent page is ±1 day. This only holds for the author's PDF. For another book, change those two constants in `batch_schedule.py`.

**When it stops.**

- A page's video cannot be found among the scheduled videos. This is the normal "end of schedule" signal.
- `--end-page`, `--max-pages`, or the end of the PDF is reached.
- Any other error (auth, HTTP, WordPress rejection, a publish time in the past) aborts with a non-zero exit code.

**Practical consequence:** because already-published videos are invisible to the lookup, starting at a page whose video is already live stops the run immediately with "Nothing to schedule". Start from the first date whose video is still scheduled, usually tomorrow.

Re-running is safe: with the default `SCHEDULE_ON_EXISTING=skip`, pages that already have a post are skipped.

---

## Configuration reference

### Environment variables (`.env`)

| Variable | Required | Default | Used by | Meaning |
|---|---|---|---|---|
| `WP_URL` | yes | n/a | WordPress modules | Site base URL, no trailing slash needed |
| `WP_USER` | yes | n/a | WordPress modules | WordPress username |
| `WP_APP_PASSWORD` | yes | n/a | WordPress modules | Application Password |
| `THUMB_AT_SECONDS` | no | `3` | `yt_thumbnail` | Timestamp of the frame to capture |
| `THUMB_WIDTH` | no | `800` | `yt_thumbnail` | Output width in px (height keeps the aspect ratio) |
| `THUMB_QUALITY` | no | `70` | `yt_thumbnail` | WebP quality (0–100) |
| `SCHEDULE_ON_EXISTING` | no | `skip` | `wp_client_scheduler` | `skip`, `update` or `fail` |
| `YT_COOKIES` | no | `cookies.txt` | `yt_thumbnail` | Path to the cookies file |

### Local files (all git-ignored)

| File | What it is | If leaked |
|---|---|---|
| `.env` | WordPress credentials | Revoke the Application Password |
| `credentials.json` | Google OAuth **client** (ID + secret) | Rotate the client in Google Cloud |
| `token.json` | Your cached YouTube access and refresh token | Revoke at <https://myaccount.google.com/permissions> |
| `cookies.txt` | Your logged-in YouTube **session** | Sign out of YouTube everywhere / change your password |
| `tfl.pdf` | The copyrighted source PDF | n/a |
| `thumbnails/` | Cached thumbnail images | n/a |

---

## Project layout

```
rest-api-post-scheduler-for-wordpress/
├── .env.example             # template for .env
├── .gitignore
├── README.md
├── requirements.txt
├── request_example.json     # sanitized sample of a WP REST post response
│
├── pdf_extractor.py         # PDF page -> dict            (CLI: prints JSON)
├── pdf_print_single_post.py # readable preview of a page  (CLI)
│
├── yt_auth.py               # OAuth flow + token caching  (library only)
├── yt_service.py            # list scheduled videos       (library only)
├── yt_lookup.py             # regex search by title       (CLI)
├── yt_thumbnail.py          # video frame -> WebP         (CLI)
│
├── post_packager.py         # PDF dict + video -> payload (CLI: prints payload)
├── wp_slug.py               # title -> WordPress-style slug (library only)
├── wp_posts.py              # find an existing post by slug (library only)
├── upload_media.py          # upload an image to WP       (CLI)
│
├── wp_client_scheduler.py   # the full single-post pipeline (CLI)
└── batch_schedule.py        # run the pipeline over many pages (CLI)
```

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `KeyError: 'WP_URL'` (or `WP_USER`, `WP_APP_PASSWORD`) | `.env` is missing, empty, or you are not in the project root. |
| `403: access_denied` during Google sign-in | Your Google account is not listed as a **test user** on the OAuth consent screen. |
| `invalid_grant` / `RefreshError` after about a week | Testing-mode refresh tokens expire after 7 days, and `yt_auth.py` does not catch this. **Delete `token.json` and run again** to re-authorize. |
| `FileNotFoundError: credentials.json` | Download the Desktop-app OAuth client JSON and save it in the project root. |
| `Cannot schedule post: No scheduled video matching '^13 tetor - '` | The video does not exist, is already public, is not private-with-a-schedule, or its title does not start with `<day> <month> - `. |
| `Multiple scheduled videos match …` | Two scheduled videos share the same prefix. Fix the titles. |
| `date_gmt … is not in the future` | The video's publish time has passed, so WordPress would not schedule it. |
| `Cookie file 'cookies.txt' not found` | Export your YouTube cookies (see Setup step 4). |
| `yt-dlp failed …` | Cookies are stale or rotated. Re-export them. Keep `yt-dlp`, `deno` and `yt-dlp-ejs` up to date. |
| `FileNotFoundError: 'cwebp'` or `'ffmpeg'` | Install the system packages: `sudo apt install ffmpeg webp`. |
| `Featured image rejected: sent X, WP stored None` | The post was written but WordPress dropped `featured_media`. Check that the user may upload media and the theme supports featured images. |
| `401` / `403` from WordPress | Wrong user or Application Password, or a security plugin blocks REST or Basic auth. |
| `SSLError` against a local test site | The scripts use normal certificate verification. A self-signed local HTTPS site must be trusted by your system. |
| Footnote markers stay as plain superscripts | A marker had no matching footnote entry on that page. This is deliberate: it is left untouched rather than guessed. |

---

## Security

| Asset | Risk | Mitigation |
|---|---|---|
| WordPress Application Password | Create and edit posts, upload media | Per-user, revocable, kept only in `.env` |
| `credentials.json` | OAuth client secret | Git-ignored; rotate in Google Cloud if leaked |
| `token.json` | Read-only access to your YouTube data | Git-ignored; revoke in your Google account |
| **`cookies.txt`** | **A full logged-in YouTube session, far more powerful than the read-only OAuth scope** | Git-ignored; never share or upload it; treat it like a password |

Notes:

- The OAuth scope is read-only, but the thumbnail step bypasses that restriction by using your browser cookies. Protect `cookies.txt` accordingly.
- Never commit real credentials, even temporarily. Deleting a secret in a later commit does **not** remove it from Git history. If one is ever pushed, revoke it first, then rewrite history.
- `request_example.json` is a sanitized sample (fake IDs, `example.com`), not real site data.

---

## Adapting it to your own site

Things you must change for a different book or WordPress site:

| What | Where |
|---|---|
| Category IDs `[172, 96]` | `post_packager.py`, in the payload dict |
| ACF field names `referenca`, `video_url` | `post_packager.py` |
| Footnote accessibility label (Albanian text) | `_render_footnote_list` in `post_packager.py` |
| Page ↔ date anchor (`294` ↔ `2026-10-13`) | `batch_schedule.py` |
| Font names (`Brandon`, `Garamond`), font-size thresholds, dropcap size, footer text `Plani i leximit`, indent offsets | `pdf_extractor.py` |
| The YouTube title convention `<day> <month> - …` | `post_packager.py` (`find_video(rf"^{date} - ")`) |
| Character class used to recognise references (`[a-zëç]`) | `_looks_like_ref` in `pdf_extractor.py` |

---

## Known limitations and TODO

- [ ] **Block markup.** Content is plain HTML with block-style classes, not full Gutenberg block comments, so it may need converting later in the editor.
- **Verse line breaks.** Verse lines are joined with newline characters inside a `<p>`; no `<br>` is emitted. Check how your theme renders them.
- **Token expiry is not handled.** An expired Testing-mode token raises an error instead of reopening the browser. Delete `token.json` to recover.
- **`update` mode re-uploads the thumbnail** each time and does not reuse the existing media item (`find_existing` in `upload_media.py` exists but is not called).
- **Hard-coded anchor and categories.** See [Adapting it to your own site](#adapting-it-to-your-own-site).
- **No dry-run flag** on the scheduler. `post_packager.py` is the closest equivalent: it builds and prints the payload without writing to WordPress.
- Done: video lookup by date, featured images, idempotent scheduling, batch posting, auto-generated footnote tags and IDs.

---

## License and notes

   ## License

   The code is released under the [MIT License](LICENSE).

   This license covers the code only. The devotional PDF is copyrighted by
   its publisher and is not included in this repository. Note that PyMuPDF
   (a dependency) is licensed under AGPL-3.0.
