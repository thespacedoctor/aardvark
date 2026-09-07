#!/usr/bin/env python
# encoding: utf-8
"""
*Render the `projects` categories an `add_project` can hang a project off*

Deliberately a stub. The logic lives in `aardvark_jd.alfred`,
where pytest reaches it.
"""

import json
import sys

from aardvark_jd.alfred import items


def main():
    json.dump(
        items.reference_payload(json.load(sys.stdin), "category", domain="projects"), sys.stdout,
    )


if __name__ == "__main__":
    main()
