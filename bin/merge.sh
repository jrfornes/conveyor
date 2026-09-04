#!/usr/bin/env python3
"""merge.sh <commit> — protocol §7. cwd is the tree to merge into.
Exit 0: merged or already an ancestor. Exit 1: conflict (merge aborted)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from conveyor import queue  # noqa: E402

if len(sys.argv) != 2:
    print("usage: merge.sh <commit>", file=sys.stderr)
    sys.exit(2)
role = os.environ.get("CONVEYOR_ROLE") or "operator"
sys.exit(0 if queue.merge(sys.argv[1], os.getcwd(), role) else 1)
