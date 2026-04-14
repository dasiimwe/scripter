#!/usr/bin/env python3
"""Exit 0 iff every env var named on the command line is set and non-empty.
Used by the Makefile's `prod` target for cross-platform env checks."""
import os
import sys

missing = [k for k in sys.argv[1:] if not os.environ.get(k)]
if missing:
    sys.stderr.write(f"ERROR: missing required env var(s): {', '.join(missing)}\n")
    sys.exit(1)
