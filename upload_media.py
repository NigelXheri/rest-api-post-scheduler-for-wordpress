#!/usr/bin/env python3
"""Upload an image file to the WordPress media library."""
import os
import mimetypes
from pathlib import Path

import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

load_dotenv()

WP_URL = os.environ["WP_URL"].rstrip("/")
USER = os.environ["WP_USER"]
APP_PASSWORD = os.environ["WP_APP_PASSWORD"]

auth = HTTPBasicAuth(USER, APP_PASSWORD)


def upload_media(path: Path) -> int:
    """POST a local image to /wp-json/wp/v2/media, return its attachment ID.

    WordPress requires the Content-Disposition header with a filename —
    without it the endpoint rejects the upload as a malformed request.
    """
    # Dynamically determine the MIME type (e.g., image/webp or image/jpeg)
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    with open(path, "rb") as f:
        response = requests.post(
            f"{WP_URL}/wp-json/wp/v2/media",
            auth=auth,
            headers={
                "Content-Disposition": f'attachment; filename="{path.name}"',
                "Content-Type": content_type,
            },
            data=f,
            timeout=60,
        )
    response.raise_for_status()
    return response.json()["id"]

def find_existing(filename: str) -> int | None:
    response = requests.get(
        f"{WP_URL}/wp-json/wp/v2/media",
        params={"search": filename, "per_page": 1},
        auth=auth, timeout=10,
    )
    response.raise_for_status()
    items = response.json()
    return items[0]["id"] if items else None


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <image_path>", file=sys.stderr)
        sys.exit(1)

    p = Path(sys.argv[1])
    media_id = upload_media(p)
    print(f"Uploaded: {p}  →  media ID {media_id}")