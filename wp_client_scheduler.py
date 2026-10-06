#!/usr/bin/env python3
# import argparse
import os
import sys

import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from post_packager import package_specific_post

"""Schedules WordPress Posts via REST API"""

# Load variables from .env into os.environ
load_dotenv()

# --- config ---
WP_URL = os.environ["WP_URL"].rstrip("/")
USER = os.environ["WP_USER"]
APP_PASSWORD = os.environ["WP_APP_PASSWORD"]

auth = HTTPBasicAuth(USER, APP_PASSWORD)

if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.pdf> <page_number>",
            file=sys.stderr)
        sys.exit(1)

pdf_path = sys.argv[1]
page_num = int(sys.argv[2])

payload = package_specific_post(pdf_path, page_num)

resp = requests.post(
    f"{WP_URL}/wp-json/wp/v2/posts",
    json=payload,
    auth=auth,
    timeout=10,
)
resp.raise_for_status()
post = resp.json()
print(f"Scheduled! ID: {post['id']}, link: {post['link']}")
