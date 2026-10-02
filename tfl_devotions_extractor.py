#!/usr/bin/env python3
"""
TFL devotional PDF -> structured post data (one page = one post).

Extracts per page: date, title, daily quote + reference, body paragraphs
(with line breaks preserved for verse), footnotes, and closing verse.
Skips the page number and "Plani i leximit..." footer.

Requires: pip install pymupdf
"""

import re

import pymupdf

SUPERSCRIPTS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def span_text(span):
    return "".join(c["c"] for c in span["chars"]) if "chars" in span else span["text"]


def despace_letters(line):
    """Rebuild a letter-spaced title ('U N G J I L L I ...') from real glyph
    gaps: small gap = same word, big gap = word boundary."""
    out, prev_end = [], None
    for span in line["spans"]:
        for ch in span["chars"]:
            # letter space: gap to previous glyph ~= 0; word gap is larger
            if (
                prev_end is not None
                and ch["bbox"][0] - prev_end > 1.5
                and out
                and out[-1] != " "
            ):
                out.append(" ")
            if ch["c"].strip():
                out.append(ch["c"])
            prev_end = ch["bbox"][2]  # track every glyph, incl. space chars
    return "".join(out)


def line_text(line):
    """Plain text of a line; tiny in-text spans -> unicode superscripts."""
    parts = []
    for s in line["spans"]:
        if s["size"] < 7 and "Garamond" in s["font"]:  # footnote marker
            parts.append(span_text(s).strip().translate(SUPERSCRIPTS))
        else:
            parts.append(span_text(s))
    return "".join(parts).strip()


def join_lines(lines):
    """Join wrapped lines into one paragraph, fixing hyphenation:
    'Aborigi-' + 'nes' -> 'Aborigines'."""
    out = ""
    for t in lines:
        if out.endswith("\u00ad"):
            out = out[:-1] + t  # de-hyphenate
        elif out:
            out += " " + t
        else:
            out = t
    return re.sub(r"\s+", " ", out).strip()


def extract_page(page):
    lines = []
    for b in page.get_text("rawdict")["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            spans = [s for s in l["spans"] if span_text(s).strip()]
            if not spans:
                continue
            real = [s for s in spans if s["size"] >= 7]  # ignore superscripts
            main = max(real or spans, key=lambda s: s["size"] * len(span_text(s)))
            lines.append(
                {
                    "raw": l,
                    "text": line_text(l),
                    "size": main["size"],
                    "font": main["font"],
                    "x": min(s["bbox"][0] for s in spans),
                    "y": min(s["bbox"][1] for s in spans),
                    "all_italic": bool(real)
                    and all("Italic" in s["font"] for s in real),
                    "dropcap": any(s["size"] > 20 for s in spans),
                }
            )
    lines.sort(key=lambda l: (l["y"], l["x"]))

    result = {
        "date": None,
        "title": None,
        "quote": None,
        "quote_ref": None,
        "paragraphs": [],
        "footnotes": [],
        "closing_verse": None,
    }

    body_lines, body_started = [], False
    for l in lines:
        t, brandon = l["text"], "Brandon" in l["font"]
        # skip footer: page number + "Plani i leximit..."
        if "Plani i leximit" in t or re.fullmatch(r"\d+", t):
            continue
        if l["dropcap"]:
            body_lines.append(l)
            body_started = True
        elif brandon and l["size"] >= 13:  # title
            result["title"] = despace_letters(l["raw"])
        elif brandon and l["size"] >= 9.5:  # date
            result["date"] = t
        elif brandon and not body_started:  # quote reference
            result["quote_ref"] = t
        elif brandon and body_started:  # closing verse
            result["closing_verse"] = t.strip()
        elif l["size"] < 8.5:  # footnotes
            t = re.sub(r"[\x00-\x1f]+", " ", t).strip()
            m = re.match(r"^(\d+)\s+(.*)", t)
            if m:
                result["footnotes"].append({"n": m.group(1), "text": m.group(2)})
            elif result["footnotes"]:
                fn = result["footnotes"][-1]
                fn["text"] = join_lines([fn["text"], t])
        elif result["title"] and result["quote_ref"] is None:  # quote lines
            q = t.strip("“” ")
            result["quote"] = join_lines([result["quote"], q]) if result["quote"] else q
        else:  # body text
            body_lines.append(l)
            body_started = True

    # --- body -> paragraphs (indented first line = new paragraph;
    #     consecutive indented all-italic lines = one verse block) ---
    paragraphs, dropcap = [], ""
    for l in body_lines:
        if l["dropcap"]:
            dropcap = "".join(
                span_text(s).strip() for s in l["raw"]["spans"] if s["size"] > 20
            )
            continue
        indented = 63 < l["x"] < 75  # 68 = indent; 81.5 = drop-cap wrap
        if indented and l["all_italic"] and paragraphs and paragraphs[-1][1] == "verse":
            paragraphs[-1][0].append(l["text"])  # verse continues
        elif indented or not paragraphs:
            kind = "verse" if (indented and l["all_italic"]) else "prose"
            paragraphs.append(([l["text"]], kind))
        else:
            paragraphs[-1][0].append(l["text"])  # wrapped line

    out = [join_lines(t) if k == "prose" else "\n".join(t) for t, k in paragraphs]
    if dropcap and out:
        out[0] = dropcap + out[0]
    result["paragraphs"] = out
    return result


def extract_pdf(path):
    """Return one dict per page, ready to become one WordPress post each."""
    with pymupdf.open(path) as doc:
        return [extract_page(p) for p in doc]


if __name__ == "__main__":
    import json
    import sys

    data = extract_pdf(sys.argv[1] if len(sys.argv) > 1 else "input.pdf")
    print(json.dumps(data, ensure_ascii=False, indent=2))
