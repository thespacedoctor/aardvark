#!/usr/bin/env python
# encoding: utf-8
"""
*Render `add_project`'s template pick from the category's folder path*

Deliberately a stub. The logic lives in `aardvark_jd.alfred`,
where pytest reaches it.
"""

import json
import os
import sys

from aardvark_jd.alfred import parse, rows


def main():
    names = parse.template_names(os.environ.get("folder_path") or "")
    json.dump({"items": rows.template_items(names)}, sys.stdout)


if __name__ == "__main__":
    main()
