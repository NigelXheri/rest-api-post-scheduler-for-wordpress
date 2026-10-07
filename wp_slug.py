#!/usr/bin/env python3
import re
import unicodedata

def wp_slug(title: str) -> str:
    """Reproduce WordPress's sanitize_title() for a post title."""
    # Strip accents: ë -> e, ç -> c, Ë -> E -> e
    nfkd = unicodedata.normalize("NFKD", title)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    # Lowercase and replace anything non-alphanumeric with a hyphen
    s = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower())
    return s.strip("-")
