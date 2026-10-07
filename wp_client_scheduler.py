#!/usr/bin/env python3
"""Schedules WordPress posts (with YouTube-derived featured images) via REST API.

Flow for one page:
    PDF page  ->  post_packager     ->  payload dict (with _yt_video hint)
    payload   ->  wp_posts          ->  existing post? (idempotency gate)
    YouTube   ->  yt_thumbnail      ->  local .webp
    .webp     ->  upload_media      ->  media_id (integer)
    payload["featured_media"] = media_id
    POST (create) or PATCH (update) /wp-json/wp/v2/posts

Env overrides:
    THUMB_AT_SECONDS        frame timestamp (default 3)
    THUMB_WIDTH             target width in px (default 800)
    THUMB_QUALITY           WebP quality (default 70)
    SCHEDULE_ON_EXISTING    skip | update | fail  (default skip)
"""
import os
import sys
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

# Load .env BEFORE importing local modules: yt_thumbnail.py reads THUMB_*
# at module scope, so .env must be in os.environ by the time it imports.
load_dotenv()

from post_packager import package_specific_post
from upload_media import upload_media
from wp_posts import find_post_by_slug
from yt_thumbnail import (
    fetch_thumbnail,
    DEFAULT_AT_SECONDS    as THUMB_AT_SECONDS,
    DEFAULT_WEBP_QUALITY  as THUMB_QUALITY,
    DEFAULT_WIDTH         as THUMB_WIDTH,
)

# --- config ---
WP_URL = os.environ["WP_URL"].rstrip("/")
USER = os.environ["WP_USER"]
APP_PASSWORD = os.environ["WP_APP_PASSWORD"]

auth = HTTPBasicAuth(USER, APP_PASSWORD)

# How to react when a post with the same slug already exists.
ON_EXISTING = os.getenv("SCHEDULE_ON_EXISTING", "skip").lower()
if ON_EXISTING not in {"skip", "update", "fail"}:
    raise SystemExit(
        f"SCHEDULE_ON_EXISTING must be one of skip|update|fail, got {ON_EXISTING!r}"
    )


def _assert_future(date_gmt: str) -> None:
    """WordPress silently publishes (or rejects) `status: future` posts whose
    date is in the past. Fail loudly instead."""
    try:
        pub = datetime.fromisoformat(date_gmt.replace("Z", "+00:00"))
    except ValueError as e:
        raise SystemExit(f"Unparseable date_gmt {date_gmt!r}: {e}") from e
    if pub <= datetime.now(timezone.utc):
        raise SystemExit(
            f"date_gmt {date_gmt} is not in the future — "
            f"WP will not schedule this as a future post."
        )


def schedule_post(pdf_path: str, page_num: int) -> dict:
    """Package a PDF page, attach a YouTube frame as the featured image,
    and create (or update) the scheduled WordPress post.

    Returns the WP response JSON. In 'skip' mode, returns the *existing*
    post untouched if one is already present.
    """
    # 1. Build the payload from the PDF page.
    print("1. Building the payload from the PDF page")
    payload = package_specific_post(pdf_path, page_num)

    # 2. Idempotency gate — check by slug before doing any expensive work.
    print("2. Idempotency gate — check by slug before doing any expensive work")
    existing  = find_post_by_slug(payload["title"])
    is_update = bool(existing) and ON_EXISTING == "update"

    if existing:
        if ON_EXISTING == "fail":
            raise SystemExit(
                f"Post already exists (ID {existing['id']}, "
                f"status {existing['status']}): {existing['link']}"
            )
        if ON_EXISTING == "skip":
            print(
                f"[skip] post already exists: ID {existing['id']} "
                f"({existing['status']}) -> {existing['link']}"
            )
            return existing
        # ON_EXISTING == "update" -> fall through and PATCH later.
        print(f"[update] post exists: ID {existing['id']} — will update in place.")

    # 3. Refuse to schedule something in the past — but only for new posts.
    #    In update mode we may legitimately be refreshing an already-published
    #    post whose YouTube video has since gone live, so the guard doesn't apply.
    if not is_update:
        _assert_future(payload["date_gmt"])

    # 4. In update mode, preserve the existing post's date and status; only
    #    refresh content, categories, ACF, and the featured image.
    if is_update:
        payload.pop("status", None)
        payload.pop("date_gmt", None)

    # 5. Pop the YouTube hint — WordPress would reject the extra field.
    yt = payload.pop("_yt_video", None)
    if yt is None:
        raise SystemExit("Payload has no _yt_video; cannot build a featured image.")

    # 6. Extract a frame and encode it as an 800px WebP (cached on repeat runs).
    thumb_path = fetch_thumbnail(
        video_id=yt["id"],
        video_title=yt["title"],
        at_seconds=THUMB_AT_SECONDS,
        quality=THUMB_QUALITY,
        width=THUMB_WIDTH,
    )
    print(f"[thumb] {thumb_path}  ({thumb_path.stat().st_size} bytes)")

    # 7. Upload it to the WP media library -> attachment ID.
    media_id = upload_media(thumb_path)
    print(f"[media] attachment ID = {media_id}")

    # 8. Attach as the featured image (ID, not URL).
    payload["featured_media"] = media_id

    # 9. Create OR update.
    if is_update:
        resp = requests.patch(
            f"{WP_URL}/wp-json/wp/v2/posts/{existing['id']}",
            json=payload,
            auth=auth,
            timeout=30,
        )
    else:
        resp = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts",
            json=payload,
            auth=auth,
            timeout=30,
        )
    resp.raise_for_status()
    post = resp.json()

    # 10. Sanity-check that WordPress actually stored the featured image.
    stored = post.get("featured_media")
    if stored != media_id:
        action = "updated" if is_update else "created"
        raise SystemExit(
            f"Featured image rejected: sent {media_id}, WP stored {stored!r}. "
            f"Post ID {post.get('id')} was {action} — fix before retrying."
        )

    return post


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.pdf> <page_number>", file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[1]
    page_num = int(sys.argv[2])

    post = schedule_post(pdf_path, page_num)
    action = "Scheduled" if post.get("status") == "future" else "Handled"
    print(f"{action}! ID: {post['id']}")
    print(f"Status:       {post.get('status')}")
    print(f"Link:         {post['link']}")

    fm_link = post.get("_links", {}).get("wp:featuredmedia", [{}])[0].get("href")
    if fm_link:
        print(f"Featured media: {fm_link}")