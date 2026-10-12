#!/usr/bin/env python3
import json
import re
import sys
import uuid

from pdf_extractor import extract_pdf_page
from yt_lookup import find_video

"""
    Packages post content in a ready-to-be-published format.
"""

# --- footnote plumbing ------------------------------------------------------
# Unicode superscripts emitted by pdf_extractor for footnote markers.
_SUP_TO_DIGIT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_SUP_RE       = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+")

# Fixed namespace so footnote UUIDs stay stable across runs (idempotent PATCHes).
# Replace with a project-unique UUIDv4 if you'd rather not share the DNS namespace.
_FOOTNOTE_NS  = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def _renumber(footnotes):
    """(orig_n -> new_n, orig_n -> uuid). Footnotes are sorted by book number
    and renumbered 1..N; UUIDs are hashed from the ORIGINAL number + text so
    they survive renumbering."""
    ordered = sorted(footnotes, key=lambda fn: int(fn["n"]))
    new_n = {fn["n"]: str(i + 1) for i, fn in enumerate(ordered)}
    ids = {
        fn["n"]: str(uuid.uuid5(_FOOTNOTE_NS, f"{fn['n']}|{fn['text']}"))
        for fn in ordered
    }
    return new_n, ids


def _sub_footnote_refs(text, new_n, ids):
    """Turn raw superscript digits into WP footnote <sup> refs. Markers with
    no matching footnote entry are left as their original superscript."""
    def repl(m):
        orig = m.group().translate(_SUP_TO_DIGIT)
        fid  = ids.get(orig)
        if fid is None:
            return m.group()
        display = new_n[orig]
        return (
            f'<sup data-fn="{fid}" class="fn">'
            f'<a href="#{fid}" id="{fid}-link">{display}</a></sup>'
        )
    return _SUP_RE.sub(repl, text)


def _render_footnote_list(footnotes, new_n, ids):
    if not footnotes:
        return ""
    items = "".join(
        f'<li id="{ids[fn["n"]]}">{fn["text"]} '
        f'<a href="#{ids[fn["n"]]}-link" '
        f'aria-label="Kaloni te referencë fundfaqeje {new_n[fn["n"]]}">↩︎</a></li>'
        for fn in sorted(footnotes, key=lambda fn: int(fn["n"]))
    )
    return f'<ol class="wp-block-footnotes">{items}</ol>'


# --- main packager ----------------------------------------------------------

def package_specific_post(pdf_path, page_num):
    """Packages a specific post from a page number into a WP payload dict."""

    data      = extract_pdf_page(pdf_path, page_num)
    footnotes = data.get("footnotes", [])
    new_n, ids = _renumber(footnotes)          # (3) fixed: names now exist

    date = str(data.get("date")).lower()

    try:
        video = find_video(rf"^{date} - ")
        youtube_video_title      = video["title"]
        youtube_video_url        = video["url"]
        youtube_video_publish_at = video["publish_at"]
    except LookupError as e:
        raise SystemExit(f"Cannot schedule post: {e}")

    quote = (
        '\n<p class="has-text-align-center wp-block-paragraph"><i>'
        + _sub_footnote_refs(data["quote"], new_n, ids)   # (4) fixed
        + "</i> "
        + (f' <b class="quote-ref">{data["quote_ref"]}</b>') + "</p>\n"  
    )

    paragraphs_html = "\n\n".join(
        f'\n<p class="wp-block-paragraph">{_sub_footnote_refs(p, new_n, ids)}</p>\n'
        for p in data.get("paragraphs", [])
    )

    footnotes_html = _render_footnote_list(footnotes, new_n, ids)   # (5) fixed

    content = quote + "\n\n" + paragraphs_html
    if footnotes_html:
        content += "\n\n" + footnotes_html

    excrept = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]", "", data["paragraphs"][0])[:200]

    packaged_post = {
        "title":      youtube_video_title,
        "content":    content,
        "excerpt":    excrept,
        "status":     "future",
        "date_gmt":   youtube_video_publish_at,
        "categories": [172, 96],
        "acf": {
            "referenca": data["closing_verse"],
            "video_url": youtube_video_url,
        },
    }

    # (6) fixed: only send meta when there are footnotes — an empty "[]"
    # would blank the field on update and confuse the block editor.
    if footnotes:
        packaged_post["meta"] = {
            "footnotes": json.dumps([
                {"content": fn["text"], "id": ids[fn["n"]]}
                for fn in sorted(footnotes, key=lambda fn: int(fn["n"]))
            ])
        }

    # Not a WP field. The scheduler pops this, fetches the featured image,
    # and discards it before POSTing.
    packaged_post["_yt_video"] = video

    return packaged_post


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.pdf> <page_number>", file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[1]
    page_num = int(sys.argv[2])
    package = package_specific_post(pdf_path, page_num)
    print(json.dumps(package, indent=2))