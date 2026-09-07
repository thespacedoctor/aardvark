#!/usr/bin/env python
# encoding: utf-8
"""
*Render `add_project`'s confirmation screen before anything is created*

Deliberately a stub. Detection lives in `aardvark_jd.spell_check` and the
rows in `aardvark_jd.alfred.rows`. `add_project` takes only a title, so
the screen carries no description field and no emoji step ran.
"""

import json
import os
import sys

from aardvark_jd import spell_check
from aardvark_jd.alfred import rows


def main():
    parsed = {"title": os.environ.get("title") or "", "description": ""}
    suggestions = spell_check.detect(
        parsed["title"], rootPath=os.environ.get("root_path") or None,
    )
    screen = rows.confirmation_items(parsed, suggestions, titleOnly=True)
    json.dump({"items": screen}, sys.stdout)


if __name__ == "__main__":
    main()
