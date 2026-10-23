#!/usr/bin/env python3
"""Create a Git-checkout-safe PHP 5.6 patch by dropping only generated ./configure.

The original patch stays unchanged and remains usable with php-5.6.40.tar.xz.
"""
import argparse
from pathlib import Path
import re

parser = argparse.ArgumentParser()
parser.add_argument('--source', required=True)
parser.add_argument('--output', required=True)
a = parser.parse_args()
original = Path(a.source).read_text(encoding='utf-8')
parts = re.split(r'(?=^--- a/)', original, flags=re.MULTILINE)
removed = []
kept = []
for part in parts:
    if part.startswith('--- a/configure\n+++ b/configure\n'):
        removed.append(part)
    else:
        kept.append(part)
if len(removed) != 1:
    parser.error('Expected exactly one generated configure diff; found %d' % len(removed))
result = ''.join(kept)
orig_paths = re.findall(r'^--- a/(.+)$', original, re.M)
new_paths = re.findall(r'^--- a/(.+)$', result, re.M)
if len(orig_paths) < 10 or new_paths != [p for p in orig_paths if p != 'configure']:
    parser.error('Unexpected patch structure; refusing to modify')
if not all(p in new_paths for p in ('configure.in', 'main/php_version.h', 'Zend/zend_alloc.c')):
    parser.error('Critical source diffs are missing')
Path(a.output).write_text(result, encoding='utf-8')
print('Original:', len(orig_paths), 'files; Git compatible:', len(new_paths), 'files')
print('Removed generated-file diff: configure (and nothing else)')
