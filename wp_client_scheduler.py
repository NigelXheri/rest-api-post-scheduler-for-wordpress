import argparse
import os

import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

"""Schedules WordPress Posts via REST API"""

# Load variables from .env into os.environ
load_dotenv()

# --- config ---
WP_URL = os.environ["WP_URL"].rstrip("/")
USER = os.environ["WP_USER"]
APP_PASSWORD = os.environ["WP_APP_PASSWORD"]

auth = HTTPBasicAuth(USER, APP_PASSWORD)

payload = {
    "title": "My scheduled post",
    "content": "<p>Hello from Python!</p>",
    "status": "future",
    "date": "2026-10-05T09:00:00",
}

resp = requests.post(
    f"{WP_URL}/wp-json/wp/v2/posts",
    json=payload,
    auth=auth,
    timeout=30,
)
resp.raise_for_status()
post = resp.json()
print(f"Scheduled! ID: {post['id']}, link: {post['link']}")
