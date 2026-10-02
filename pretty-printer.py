#!./.venv/bin/python3
"""This is a pretty-printer that exports the contents of the pages extracted with the tfl_devotions_extractor"""

import json
import sys

from tfl_devotions_extractor import extract_pdf


def view_contents(contents: list[str]):
    """This function will display the contents extracted from the PDF"""
    for page in contents:
        print(json.dumps(page, ensure_ascii=False, indent=2))
    print("\n", contents)


if __name__ == "__main__":
    view_contents(extract_pdf(sys.argv[1] if len(sys.argv) > 1 else "input.pdf"))
