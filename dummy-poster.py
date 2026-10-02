#!/usr/bin/env python3
"""This script will schedule posts via the REST API to a fresh WordPress installation."""

import json

import requests
from requests.auth import HTTPBasicAuth

# --- config ---
WP_URL = "https://example.local"
USER = "admin"
APP_PASSWORD = "REMOVED"  # the Application Password

auth = HTTPBasicAuth(USER, APP_PASSWORD)

# --- dummy post ---
payload = {
    "title": "My scheduled post",
    "content": "Hello from Python!\nOr no\n\nIs this a new paragraph?",
    "status": "future",  # 'future' + a future date = scheduled
    "date": "2026-10-05T09:00:00",  # site timezone, or use date_gmt
}

# resp = requests.post(
#     f"{WP_URL}/wp-json/wp/v2/posts",
#     json=payload,
#     auth=auth,
#     timeout=30,
# )

# resp.raise_for_status()
# post = resp.json()
# print(f"Scheduled! ID: {post['id']}, link: {post['link']}")

resp = requests.get(
    f"{WP_URL}/wp-json/wp/v2/posts?status=future", auth=auth, timeout=5, verify=False
)

# resp.raise_for_status()
post = resp.json()
print(post)
