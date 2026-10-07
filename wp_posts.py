#!/usr/bin/env python3
"""Look up existing WordPress posts by slug (exact, indexed match)."""
import os

import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

from wp_slug import wp_slug

load_dotenv()

WP_URL = os.environ["WP_URL"].rstrip("/")
USER = os.environ["WP_USER"]
APP_PASSWORD = os.environ["WP_APP_PASSWORD"]

auth = HTTPBasicAuth(USER, APP_PASSWORD)


def find_post_by_slug(title: str) -> dict | None:
    """Return the post whose slug matches `wp_slug(title)`, or None.

    Uses the indexed `slug` query param, so this is a strict equality
    lookup — no fuzzy full-text search, no client-side filtering needed.

    `status=any` requires an authenticated user with edit_posts (which the
    Application Password provides) and is required to see `future` and
    `draft` posts, not just published ones.
    """
    slug = wp_slug(title)
    if not slug:
        # wp_slug() returns "" for a title with no alphanumerics; there's
        # nothing meaningful to look up, and an empty slug query would
        # return every post.
        return None

    r = requests.get(
        f"{WP_URL}/wp-json/wp/v2/posts",
        auth=auth,
        params={
            "slug": slug,
            "status": "any",   # include future + draft + publish
            "context": "edit", # so we get title.raw, not title.rendered
            "_fields": "id,slug,title,status,date_gmt,link",
        },
        timeout=15,
    )
    r.raise_for_status()

    items = r.json()
    return items[0] if items else None