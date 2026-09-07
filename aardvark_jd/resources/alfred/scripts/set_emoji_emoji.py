#!/usr/bin/env python
# encoding: utf-8
"""
*Render the emoji step: the offline pick, then the free-text index search*

Deliberately a stub. The logic lives in `aardvark_jd.alfred` and
`aardvark_jd.spell_check`, where pytest reaches it.
"""

import json
import os
import sys

from aardvark_jd import emoji_picker
from aardvark_jd.alfred import rows


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else ""
    title = os.environ.get("title") or os.environ.get("entity_title") or ""
    default = emoji_picker.pick_emoji(title, os.environ.get("description") or "")
    step = rows.emoji_items(query, default, emoji_picker.search_emoji(query))
    json.dump({"items": step}, sys.stdout)


if __name__ == "__main__":
    main()
