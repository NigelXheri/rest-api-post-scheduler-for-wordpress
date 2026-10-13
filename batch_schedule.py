#!/usr/bin/env python3
"""Batch-schedule consecutive devotional posts, one PDF page per day.

Pages map 1:1 to calendar dates (the extractor reads the date off each
page). This script schedules pages in sequence, starting from the page
that corresponds to today (or an explicit page/date), and stops the
moment a page's YouTube video cannot be found — i.e. we've run past the
last scheduled video.

Anchor:
    page 294  =  2026-10-13
    page 295  =  2026-10-14
    ...       (one page per day, forwards and backwards)

Usage:
    python batch_schedule.py tfl.pdf                      # start at today
    python batch_schedule.py tfl.pdf --start-page 294
    python batch_schedule.py tfl.pdf --start-date 2026-10-13
    python batch_schedule.py tfl.pdf --start-page 294 --end-page 310
    python batch_schedule.py tfl.pdf --start-page 294 --max-pages 5
    python batch_schedule.py tfl.pdf --start-page 294 --sleep 2

Notes:
- Re-running is safe: wp_client_scheduler honours SCHEDULE_ON_EXISTING
  (skip | update | fail, default skip), so pages that already have a
  post will be skipped rather than duplicated.
- Stops on the first page with no matching scheduled video. Any other
  error (auth, HTTP, WP rejection) aborts the run with a non-zero exit.
"""
import argparse
import sys
import time
from datetime import date, timedelta

import pymupdf

from wp_client_scheduler import schedule_post

# Calendar anchor: page 294 is 2026-10-13; each adjacent page is ±1 day.
ANCHOR_PAGE = 294
ANCHOR_DATE = date(2026, 10, 13)


def page_for_date(d: date) -> int:
    return ANCHOR_PAGE + (d - ANCHOR_DATE).days


def date_for_page(p: int) -> date:
    return ANCHOR_DATE + timedelta(days=p - ANCHOR_PAGE)


def run(pdf_path: str, start_page: int, end_page: int | None,
        max_pages: int | None, sleep: float) -> int:
    with pymupdf.open(pdf_path) as doc:
        total_pages = doc.page_count

    if start_page > total_pages:
        print(f"Start page {start_page} > PDF page count {total_pages}.",
              file=sys.stderr)
        return 1

    page = start_page
    scheduled = 0
    last_page = None

    while True:
        if page > total_pages:
            print(f"\nReached end of PDF (page {total_pages}). Stopping.")
            break
        if end_page is not None and page > end_page:
            print(f"\nReached --end-page {end_page}. Stopping.")
            break
        if max_pages is not None and scheduled >= max_pages:
            print(f"\nReached --max-pages {max_pages}. Stopping.")
            break

        d = date_for_page(page)
        print(f"\n=== Page {page}  ({d.isoformat()}) ===")

        try:
            post = schedule_post(pdf_path, page)
        except SystemExit as e:
            # post_packager wraps a LookupError ("no matching video") in
            # SystemExit. That's our natural end-of-schedule signal.
            if "Cannot schedule post" in str(e):
                print(f"\nNo scheduled video for {d.isoformat()} "
                      f"(page {page}).")
                print("Stopping: reached the end of the uploaded schedule.")
                break
            raise  # e.g. date_gmt in the past — real error, don't swallow
        except Exception as e:
            print(f"\nAborting at page {page} ({d.isoformat()}): {e}",
                  file=sys.stderr)
            return 1

        scheduled += 1
        last_page = page
        action = "Scheduled" if post.get("status") == "future" else "Handled"
        print(f"{action}! ID: {post['id']}")
        print(f"Status:       {post.get('status')}")
        print(f"Link:         {post['link']}")

        page += 1
        if sleep:
            time.sleep(sleep)

    if scheduled:
        print(f"\nDone. {scheduled} post(s) processed, "
              f"last page {last_page}.")
    else:
        print("\nDone. Nothing to schedule.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Schedule a run of consecutive devotional posts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Anchor: page 294 = 2026-10-13, each neighbour page is ±1 day.",
    )
    ap.add_argument("pdf", help="path to the devotional PDF")

    src = ap.add_mutually_exclusive_group()
    src.add_argument("--start-page", type=int,
                     help="first PDF page (1-indexed)")
    src.add_argument("--start-date", metavar="YYYY-MM-DD",
                     help="first date; page derived from the 294=2026-10-13 anchor")

    ap.add_argument("--end-page", type=int,
                    help="stop after this PDF page")
    ap.add_argument("--max-pages", type=int,
                    help="hard cap on how many posts to process")
    ap.add_argument("--sleep", type=float, default=0.0,
                    help="seconds between posts (default: 0)")
    args = ap.parse_args()

    if args.start_page is not None:
        start_page = args.start_page
    elif args.start_date:
        try:
            start_page = page_for_date(date.fromisoformat(args.start_date))
        except ValueError:
            ap.error(f"--start-date must be YYYY-MM-DD, got {args.start_date!r}")
    else:
        today = date.today()
        start_page = page_for_date(today)
        print(f"No start given — using today ({today.isoformat()}) "
              f"→ page {start_page}.")

    return run(args.pdf, start_page, args.end_page, args.max_pages, args.sleep)


if __name__ == "__main__":
    sys.exit(main())