#!/usr/bin/env python3
"""Verify cumulative security changes independently of release metadata."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from version import ROOT, read_version


def check(root=ROOT, quiet=False):
    root = Path(root).resolve()
    version = read_version(root)
    config = json.loads((root / 'ci/release/security.json').read_text())
    patch = (root / config['cumulative_patch']).resolve()
    if not patch.is_relative_to(root / 'security-backports') or not patch.is_file():
        raise ValueError('Cumulative patch must be an existing security-backports file')
    with tempfile.TemporaryDirectory(prefix='php56-security-') as temp:
        generated = Path(temp) / 'git.patch'
        capture = dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE) if quiet else {}
        subprocess.run([sys.executable, str(root / 'ci/prepare-git-patch.py'),
                        '--source', str(patch), '--output', str(generated),
                        '--allow-missing-configure'], check=True, **capture)
        # These three files only hold the original patch's version/NEWS changes.
        # Current version definitions are independently checked by read_version.
        # All C, header and INI security hunks still undergo strict reverse check.
        subprocess.run(['git', 'apply', '--reverse', '--check',
                        '--exclude=NEWS', '--exclude=configure.in',
                        '--exclude=main/php_version.h', str(generated)], cwd=root, check=True, **capture)
    print('Security source check PASS; version=' + version)


if __name__ == '__main__':
    check()
