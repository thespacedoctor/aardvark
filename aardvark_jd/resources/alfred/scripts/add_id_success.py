#!/usr/bin/env python
# encoding: utf-8
"""
*Render the post-create success surface from the mutating result on stdin*

Deliberately a stub. The rows live in `aardvark_jd.alfred.rows`, where
pytest reaches them.
"""

import json
import sys

from aardvark_jd.alfred import items, rows


def main():
    payload = json.load(sys.stdin)

    if payload.get("error"):
        json.dump({"items": [items.error_row(payload["error"])]}, sys.stdout)
        return

    json.dump(
        {"items": rows.success_items(payload["result"]["entity"])}, sys.stdout,
    )


if __name__ == "__main__":
    main()
