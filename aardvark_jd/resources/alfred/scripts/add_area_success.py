#!/usr/bin/env python
# encoding: utf-8
"""
*Render the post-create success surface for `add_area` from the result on stdin*

Deliberately a stub. The logic lives in `aardvark_jd.alfred`,
where pytest reaches it.
"""

import json
import sys

from aardvark_jd.alfred import items, rows


def main():
    payload = json.load(sys.stdin)

    if payload.get("error"):
        json.dump({"items": [items.error_row(payload["error"])]}, sys.stdout)
        return

    entity = payload["result"].get("entity") or {}
    json.dump({"items": rows.success_items(entity)}, sys.stdout)


if __name__ == "__main__":
    main()
