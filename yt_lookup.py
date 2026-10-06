#!/usr/bin/env python3
"""Search the authenticated user's scheduled YouTube videos by regex."""

import re
import sys
from yt_service import list_scheduled_videos


def find_videos(pattern: str):
    """All scheduled videos whose title matches `pattern` (case-insensitive).

    Uses re.search, so the pattern can match anywhere in the title
    unless you anchor it yourself (^ for start, $ for end).
    """
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        raise ValueError(f"Invalid regex {pattern!r}: {e}") from e

    return [video for video in list_scheduled_videos() if rx.search(video["title"])]


def find_video(pattern: str):
    """Exactly one match, or raise with a clear message."""
    matches = find_videos(pattern)
    if not matches:
        raise LookupError(f"No scheduled video matching: {pattern!r}")
    if len(matches) > 1:
        lines = "\n".join(f"  - {video['title']}  ({video['publish_at']})" for video in matches)
        raise LookupError(
            f"Multiple scheduled videos match {pattern!r}:\n{lines}\n"
            f"Tighten the pattern (e.g. add $ or more text)."
        )
    return matches[0]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <regex>", file=sys.stderr)
        print(f"Example: {sys.argv[0]} '^4 tetor'", file=sys.stderr)
        sys.exit(1)

    pattern = " ".join(sys.argv[1:])  # allow unquoted multi-word patterns
    try:
        video = find_video(pattern)
    except ValueError as e:      # bad regex
        print(e, file=sys.stderr)
        sys.exit(3)
    except LookupError as e:     # 0 or >1 matches
        print(e, file=sys.stderr)
        sys.exit(2)

    print(f"Title:     {video['title']}")
    print(f"Publishes: {video['publish_at']} (UTC)")
    print(f"URL:       {video['url']}")