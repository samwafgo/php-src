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
parser.add_argument('--allow-missing-configure', action='store_true',
                    help='Also accept a cumulative Git diff without generated configure')
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
if len(removed) != 1 and not (a.allow_missing_configure and len(removed) == 0):
    parser.error('Expected exactly one generated configure diff; found %d' % len(removed))
result = ''.join(kept)
orig_paths = re.findall(r'^--- a/(.+)$', original, re.M)
new_paths = re.findall(r'^--- a/(.+)$', result, re.M)
if len(orig_paths) < 10 or new_paths != [p for p in orig_paths if p != 'configure']:
    parser.error('Unexpected patch structure; refusing to modify')
if not all(p in new_paths for p in ('configure.in', 'main/php_version.h', 'Zend/zend_alloc.c')):
    parser.error('Critical source diffs are missing')
# read_text() above normalizes source line endings. Binary output preserves
# those LF bytes on Windows too; write_text(newline=None) would emit CRLF.
Path(a.output).write_bytes(result.encode('utf-8'))
print('Original:', len(orig_paths), 'files; Git compatible:', len(new_paths), 'files')
print('Removed generated-file diff: configure (and nothing else)' if removed else 'No generated configure diff present')
print('Git patch encoding: UTF-8 / LF (platform-independent)')
