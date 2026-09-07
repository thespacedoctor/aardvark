#!/usr/bin/env python
# encoding: utf-8
"""
*Render the parse of `add_area`'s `title, description` field*

Deliberately a stub. The logic lives in `aardvark_jd.alfred` and
`aardvark_jd.spell_check`, where pytest reaches it.
"""

import json
import sys

from aardvark_jd.alfred import rows

BACK_LABEL = "Choose a different domain"


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else ""
    json.dump({"items": rows.argument_items(query, BACK_LABEL)}, sys.stdout)


if __name__ == "__main__":
    main()
