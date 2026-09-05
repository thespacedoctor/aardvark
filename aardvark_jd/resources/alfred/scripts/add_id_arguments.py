#!/usr/bin/env python
# encoding: utf-8
"""
*Render the parse of the `title, description` field back as Alfred items*

Deliberately a stub. The split lives in `aardvark_jd.alfred.parse` and
the rows in `aardvark_jd.alfred.rows`, where pytest reaches both.
"""

import json
import sys

from aardvark_jd.alfred import rows

BACK_LABEL = "Choose a different category"


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else ""
    json.dump({"items": rows.argument_items(query, BACK_LABEL)}, sys.stdout)


if __name__ == "__main__":
    main()
