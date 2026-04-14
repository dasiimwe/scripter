#!/usr/bin/env python3
"""Remove __pycache__ directories and .pyc files — cross-platform replacement
for the Makefile's old `find | xargs rm` recipe."""
import os
import shutil

removed = 0
for root, dirs, files in os.walk('.'):
    for d in list(dirs):
        if d == '__pycache__':
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)
            dirs.remove(d)
            removed += 1
    for f in files:
        if f.endswith('.pyc'):
            try:
                os.remove(os.path.join(root, f))
                removed += 1
            except OSError:
                pass
print(f'removed {removed} __pycache__ dirs / .pyc files')
