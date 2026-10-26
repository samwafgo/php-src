#!/usr/bin/env python3
"""Generate the cumulative source patch from committed changes, using LF bytes."""
import argparse
import json
from pathlib import Path
import subprocess

from version import ROOT

SOURCE_PATHS = ['NEWS', 'configure.in', 'main', 'Zend', 'ext', 'sapi', 'TSRM',
                'win32', 'build', 'buildconf', 'buildconf.bat', 'acinclude.m4',
                'php.ini-development', 'php.ini-production', 'tests']


def update(base, root=ROOT):
    root = Path(root)
    sha = subprocess.check_output(['git', 'rev-parse', '--verify', base + '^{commit}'], cwd=root, text=True).strip()
    data = subprocess.check_output(['git', 'diff', '--binary', sha, 'HEAD', '--'] + SOURCE_PATHS, cwd=root)
    if b'--- a/Zend/zend_alloc.c\n' not in data or b'--- a/main/php_version.h\n' not in data:
        raise ValueError('Base does not produce the expected cumulative PHP 5.6 security diff')
    path = 'security-backports/php-5.6.40-cumulative.patch'
    (root / path).write_bytes(data)
    config = root / 'ci/release/security.json'
    settings = json.loads(config.read_text())
    settings['cumulative_patch'] = path
    config.write_bytes((json.dumps(settings, indent=2) + '\n').encode('utf-8'))
    print('Generated cumulative patch from ' + sha + ' to HEAD; review and commit the patch/config changes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='upstream-php-5.6.40')
    args = parser.parse_args()
    update(args.base)
