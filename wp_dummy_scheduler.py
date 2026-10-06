#!/usr/bin/env python3
# import json
import os

import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

"""This script will schedule posts via
    the REST API to a fresh WordPress installation."""


# Load variables from .env into os.environ
load_dotenv()

# --- config ---
WP_URL = os.environ["WP_URL"].rstrip("/")
USER = os.environ["WP_USER"]
APP_PASSWORD = os.environ["WP_APP_PASSWORD"]

auth = HTTPBasicAuth(USER, APP_PASSWORD)

# --- dummy post ---
payload = {
    "title": "My scheduled post",
    "content": "Hello from Python!\n\nIs this a new paragraph?\nOr no",
    "status": "future",  # 'future' + a future date = scheduled
    "date": "2026-10-09T09:00:00",  # site timezone, or use date_gmt
}

resp = requests.post(
    f"{WP_URL}/wp-json/wp/v2/posts", json=payload, auth=auth, timeout=30, verify=False
)

resp.raise_for_status()
post = resp.json()
print(f"Scheduled! ID: {post['id']}, link: {post['link']}")
