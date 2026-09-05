#!/usr/bin/env python
# encoding: utf-8
"""
*Render the categories an `add_id` can hang an ID off*

Deliberately a stub. The filtering and the empty-list row live in
`aardvark_jd.alfred.items.reference_payload`, where pytest reaches them.
"""

import json
import sys

from aardvark_jd.alfred import items

PARENT_TYPE = "category"


def main():
    json.dump(items.reference_payload(json.load(sys.stdin), PARENT_TYPE), sys.stdout)


if __name__ == "__main__":
    main()
