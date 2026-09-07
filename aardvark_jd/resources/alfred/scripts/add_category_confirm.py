#!/usr/bin/env python
# encoding: utf-8
"""
*Render `add_category`'s confirmation screen before anything is created*

Deliberately a stub. Detection lives in `aardvark_jd.spell_check` and the
rows in `aardvark_jd.alfred.rows`, where pytest reaches both. Detection
runs here rather than reading the mutating result's `suggestions`,
because this screen is shown before anything exists.
"""

import json
import os
import sys

from aardvark_jd import spell_check
from aardvark_jd.alfred import rows


def main():
    parsed = {
        "title": os.environ.get("title") or "",
        "description": os.environ.get("description") or "",
    }
    suggestions = spell_check.detect(
        parsed["title"], rootPath=os.environ.get("root_path") or None,
    )
    screen = rows.confirmation_items(
        parsed, suggestions, emoji=os.environ.get("emoji") or None,
    )
    json.dump({"items": screen}, sys.stdout)


if __name__ == "__main__":
    main()
