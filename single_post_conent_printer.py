#!/usr/bin/env python3
"""
Extracts a post from one page using the TFL Devotions Extractor from the PDF.
"""

from tfl_devotions_extractor import extract_pdf_page

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.pdf> <page_number>",
              file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[1]
    page_num = int(sys.argv[2])
    data = extract_pdf_page(pdf_path, page_num)

    print()
    date = str(data.get("date")).lower()
    title = str(data.get("title")).capitalize()
    full_title = date + " - " + title

    content = (
        "<i>"
        + data["quote"]
        + "</i>"
        + " "
        + "<b>"
        + data["quote_ref"]
        + "</b>"
        + "\n" * 2
        + "\n\n".join(data.get("paragraphs"))
    )
    print(full_title)
    print()

    print(content)
    print()
    for fn in data.get("footnotes"):
        print(fn["text"])
    print()

    print(data["closing_verse"])
