#!/usr/bin/env python
# encoding: utf-8
"""
*Record one token in the learned vocabulary, so it is never flagged again*

Deliberately a stub. The vocabulary file is `aardvark_jd.vocabulary`'s
business, where pytest reaches it.
"""

import os
import sys

from aardvark_jd import vocabulary


def main():
    token = sys.argv[1] if len(sys.argv) > 1 else ""
    rootPath = os.environ.get("root_path") or ""

    if not token or not rootPath:
        print("nothing to teach - no token or no system root")
        return 1

    vocabulary.remember(rootPath, token)
    print(f"aardvark will not flag '{token}' again")
    return 0


if __name__ == "__main__":
    sys.exit(main())
