#!/usr/bin/env python
# encoding: utf-8
"""
*Render the areas an `add_category` can hang a category off*

Deliberately a stub. The logic lives in `aardvark_jd.alfred`,
where pytest reaches it.
"""

import json
import sys

from aardvark_jd.alfred import items


def main():
    json.dump(
        items.reference_payload(json.load(sys.stdin), "area"), sys.stdout,
    )


if __name__ == "__main__":
    main()
