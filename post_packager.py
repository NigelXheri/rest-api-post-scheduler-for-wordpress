#!/usr/bin/env python3
import sys

from pdf_extractor import extract_pdf_page
from yt_lookup import find_video

"""
    Packages post content in a ready to be published format.
"""

def package_specific_post(pdf_path, page_num):
    """Packeges specific post from page number into JSON"""

    data = extract_pdf_page(pdf_path, page_num)

    date = str(data.get("date")).lower()
    # title = str(data.get("title")).lower()

    try:
        video = find_video(rf"^{date} - ")
        youtube_video_title = video["title"]
        youtube_video_url = video["url"]
        youtube_video_publish_at = video["publish_at"]
    except LookupError as e:
        raise SystemExit(f"Cannot schedule post: {e}")


    quote = ("\n<p class=\"has-text-align-center wp-block-paragraph\"><i>"
            + data["quote"]
            + "</i>"
            + " "
            + "<b>"
            + data["quote_ref"]
            + "</b></p>\n")

    paragraphs_html = "\n\n".join(
        f'\n<p class="wp-block-paragraph">{p}</p>\n'
        for p in data.get("paragraphs", [])
    )
    
    content = (
        quote        
        + "\n" * 2
        + paragraphs_html
    )

    excrept = data['paragraphs'][0][:200]

    packaged_post = {
        "title": youtube_video_title,
        "content": content,
        "excerpt": excrept,
        "status": "future",  # 'future' + a future date = scheduled
        "date_gmt": youtube_video_publish_at,  # site timezone, or use date_gmt
        "categories": [172, 96],
        "acf": {
            "referenca": data["closing_verse"],
            "video_url": youtube_video_url
        }
    }

    # Not a WP field. The scheduler pops this, fetches the featured image,
    # and discards it before POSTing.
    packaged_post["_yt_video"] = video

    return packaged_post 

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.pdf> <page_number>",
            file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[1]
    page_num = int(sys.argv[2])
    package = package_specific_post(pdf_path,page_num)
    print(package)