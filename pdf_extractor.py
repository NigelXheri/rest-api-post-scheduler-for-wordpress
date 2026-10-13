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

# Characters that may appear as a line-break hyphen in a PDF.
HYPHENS = "-\u00ad\u2010\u2011\u2012\u2013"
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
        stripped = out.rstrip()
        if stripped and stripped[-1] in HYPHENS:
            out = stripped[:-1] + t   # previous line ended in a hyphen -> join
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
        for line in b["lines"]:
            spans = [s for s in line["spans"] if span_text(s).strip()]
            if not spans:
                continue
            real = [s for s in spans if s["size"] >= 7]  # ignore superscripts
            main = max(real or spans, key=lambda s: s["size"] * len(span_text(s)))
            lines.append(
                {
                    "raw": line,
                    "text": line_text(line),
                    "size": main["size"],
                    "font": main["font"],
                    "x": min(s["bbox"][0] for s in spans),
                    "y": min(s["bbox"][1] for s in spans),
                    "all_italic": bool(real)
                    and all("Italic" in s["font"] for s in real),
                    "dropcap": any(s["size"] > 20 for s in spans),
                }
            )
    lines.sort(key=lambda line: (line["y"], line["x"]))

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
    for line in lines:
        t, brandon = line["text"], "Brandon" in line["font"]
        # skip footer: page number + "Plani i leximit..."
        if "Plani i leximit" in t or re.fullmatch(r"\d+", t):
            continue
        if line["dropcap"]:
            body_lines.append(line)
            body_started = True
        elif brandon and line["size"] >= 13:  # title
            title_part = despace_letters(line["raw"])
            result["title"] = (result["title"] + " " + title_part
                            if result["title"] else title_part)
        elif brandon and line["size"] >= 9.5 and result["date"] is None:  # date
            result["date"] = t
        elif brandon and not body_started and result["quote_ref"] is None:  # quote ref
            result["quote_ref"] = t
        elif brandon and body_started:  # closing verse
            result["closing_verse"] = t.strip()
        elif line["size"] < 8.5:  # footnotes
            t = re.sub(r"[\x00-\x1f]+", " ", t).strip()
            m = re.match(r"^(\d+)\s+(.*)", t)
            if m:
                result["footnotes"].append({"n": m.group(1), "text": m.group(2)})
            elif result["footnotes"]:
                fn = result["footnotes"][-1]
                fn["text"] = join_lines([fn["text"], t])
        elif (
            result["title"]
            and result["quote_ref"] is None
            and not body_started
            and not (result["quote"] or "").rstrip().endswith("”")
        ):  # still inside the quote
            q = t.strip()
            close_idx = q.rfind("”")
            if close_idx >= 0:
                quote_part = q[: close_idx + 1]
                tail       = q[close_idx + 1:].strip()
                result["quote"] = (
                    join_lines([result["quote"], quote_part]) if result["quote"] else quote_part
                )
                if _looks_like_ref(tail):
                    result["quote_ref"] = tail
            else:
                result["quote"] = join_lines([result["quote"], q]) if result["quote"] else q
        else:  # body text
            body_lines.append(line)
            body_started = True

    # --- body -> paragraphs (indented first line = new paragraph;
    #     consecutive indented all-italic lines = one verse block) ---
    # The PDF is a book: left and right pages have different absolute left
    # margins. Anchor the indent check to the dropcap's x-position (the body
    # text's left edge) so it works on both sides.
    dropcap_x = next((l["x"] for l in body_lines if l["dropcap"]), None)
    if dropcap_x is None:
        # No dropcap on this page — fall back to the leftmost body line.
        dropcap_x = min((l["x"] for l in body_lines), default=0)

    # Offsets relative to the dropcap / body left edge:
    #   wrapped lines      ≈ dropcap_x + 0
    #   indented paragraph ≈ dropcap_x + 5
    #   dropcap-wrap lines ≈ dropcap_x + 18  (NOT treated as an indent)
    indent_lo = dropcap_x + 3
    indent_hi = dropcap_x + 12

    paragraphs, dropcap = [], ""
    for line in body_lines:
        if line["dropcap"]:
            dropcap = "".join(
                span_text(s).strip() for s in line["raw"]["spans"] if s["size"] > 20
            )
            after_dropcap = True
            continue

        if after_dropcap:
            # The line right after a dropcap is the continuation of the
            # dropcap's own row
            paragraphs.append(([line["text"]], "prose"))
            after_dropcap = False
            continue

        indented = indent_lo < line["x"] < indent_hi
        if (
            indented
            and line["all_italic"]
            and paragraphs
            and paragraphs[-1][1] == "verse"
        ):
            paragraphs[-1][0].append(line["text"])  # verse continues
        elif indented or not paragraphs:
            kind = "verse" if (indented and line["all_italic"]) else "prose"
            paragraphs.append(([line["text"]], kind))
        else:
            paragraphs[-1][0].append(line["text"])  # wrapped line

    out = [join_lines(t) if k == "prose" else "\n".join(t) for t, k in paragraphs]
    if dropcap and out:
        out[0] = dropcap + out[0]
    result["paragraphs"] = out
    return result


def extract_pdf(path):
    """Return one dict per page, ready to become one WordPress post each."""
    with pymupdf.open(path) as doc:
        return [extract_page(p) for p in doc]


def extract_pdf_page(path, page_number):
    """Extract a single page (1-indexed) from a PDF into post data."""
    with pymupdf.open(path) as doc:
        if not 1 <= page_number <= doc.page_count:
            raise ValueError(
                f"Page {page_number} out of range (document has {doc.page_count} pages)"
            )
        return extract_page(doc[page_number - 1])

def _looks_like_ref(s: str) -> bool:
    """True if `s` looks like a scripture reference, e.g. 'RUTHI 3:1-3'."""
    return bool(s) and bool(re.search(r"\d", s)) and not re.search(r"[a-zëç]", s)

if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.pdf> <page_number>", file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[1]
    page_num = int(sys.argv[2])
    data = extract_pdf_page(pdf_path, page_num)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print("Number of paragraphs: ", len(data['paragraphs']))
