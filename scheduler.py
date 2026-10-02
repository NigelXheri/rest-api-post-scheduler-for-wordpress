import requests
from requests.auth import HTTPBasicAuth

# --- config ---
WP_URL = "https://yoursite.com"
USER = "your_wp_username"
APP_PASSWORD = "xxxx xxxx xxxx xxxx"  # the Application Password

auth = HTTPBasicAuth(USER, APP_PASSWORD)

# --- dummy post ---
payload = {
    "title": "My scheduled post",
    "content": "<p>Hello from Python!</p>",
    "status": "future",  # 'future' + a future date = scheduled
    "date": "2026-10-05T09:00:00",  # site timezone, or use date_gmt
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
