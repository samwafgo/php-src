#!/usr/bin/env python3
"""Read the security revision from PHP's actual source version definitions."""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
PATTERN = r'5\.6\.40-sec[1-9][0-9]*'


def read_version(root=ROOT):
    header = (Path(root) / 'main/php_version.h').read_text(encoding='utf-8')
    match = re.search(r'^#define PHP_VERSION "(' + PATTERN + r')"$', header, re.M)
    if not match:
        raise ValueError('Expected PHP_VERSION 5.6.40-secN (N >= 1)')
    version = match.group(1)
    extra = version[len('5.6.40'):]
    if '#define PHP_EXTRA_VERSION "' + extra + '"' not in header:
        raise ValueError('PHP_EXTRA_VERSION does not match PHP_VERSION')
    if not re.search(r'^#define PHP_VERSION_ID 50640$', header, re.M):
        raise ValueError('PHP_VERSION_ID must remain 50640 for this maintenance line')
    configure = (Path(root) / 'configure.in').read_text(encoding='utf-8')
    for name, value in (('MAJOR', '5'), ('MINOR', '6'), ('RELEASE', '40')):
        if not re.search(r'^#define PHP_' + name + '_VERSION ' + value + '$', header, re.M):
            raise ValueError('Header base version components must remain 5.6.40')
        if not re.search(r'^PHP_' + name + r'_VERSION=' + value + '$', configure, re.M):
            raise ValueError('configure.in base version must remain 5.6.40')
    if 'PHP_EXTRA_VERSION="' + extra + '"' not in configure:
        raise ValueError('configure.in and main/php_version.h disagree')
    return version


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--tag', action='store_true')
    parser.add_argument('--patch', action='store_true')
    args = parser.parse_args()
    version = read_version(args.root)
    if args.patch:
        print(json.loads((args.root / 'ci/release/security.json').read_text())['cumulative_patch'])
    else:
        print(('php-' if args.tag else '') + version)
