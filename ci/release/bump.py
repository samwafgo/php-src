#!/usr/bin/env python3
"""Advance secN to sec(N+1); never modify existing Git tags."""
import argparse
from pathlib import Path
import re

from version import ROOT, PATTERN, read_version


def bump(root, new):
    root = Path(root)
    old = read_version(root)
    if not re.fullmatch(PATTERN, new):
        raise ValueError('Expected 5.6.40-secN')
    if int(new.split('-sec')[1]) != int(old.split('-sec')[1]) + 1:
        raise ValueError('Advance exactly one revision; current=' + old)
    notes = root / 'releases' / (new + '.md')
    if notes.exists():
        raise ValueError('Release notes already exist: ' + str(notes))
    old_extra, new_extra = old[len('5.6.40'):], new[len('5.6.40'):]
    changes = {}
    for name in ('main/php_version.h', 'configure.in'):
        path = root / name
        changes[path] = path.read_text().replace(old, new).replace(old_extra, new_extra)
    news = root / 'NEWS'
    changes[news] = new + '\n\n- Security: describe the cumulative fixes in releases/' + new + '.md.\n\n' + news.read_text()
    changes[notes] = ('# PHP ' + new + '\n\nTODO: describe new fixes, references, behavior changes and validation.\n\n'
                      'Includes all changes from ' + old + '.\n')
    notes.parent.mkdir(exist_ok=True)
    for path, text in changes.items():
        path.write_bytes(text.encode('utf-8'))
    read_version(root)
    print('Advanced ' + old + ' -> ' + new + '; complete release notes and cumulative patch before publishing')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('version')
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    bump(args.root, args.version)
