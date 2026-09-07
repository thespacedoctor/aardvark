#!/usr/bin/env python
# encoding: utf-8
"""
*Render `archive`'s one-row confirmation screen*

Deliberately a stub. The logic lives in `aardvark_jd.alfred`,
where pytest reaches it.
"""

import json
import os
import sys

from aardvark_jd.alfred import rows


def main():
    ref = os.environ.get("ref") or ""
    label = os.environ.get("entity_title") or ref
    json.dump({"items": rows.archive_confirm_items(ref, label)}, sys.stdout)


if __name__ == "__main__":
    main()
