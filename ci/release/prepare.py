#!/usr/bin/env python3
"""Validate the exact revision selected for a tag/manual release."""
import json
import os
from pathlib import Path
import subprocess

from version import ROOT, read_version


def prepare():
    version = read_version()
    tag = 'php-' + version
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    config = json.loads((ROOT / 'ci/release/security.json').read_text())
    ref = os.environ['GITHUB_REF_NAME']
    if os.environ['GITHUB_REF_TYPE'] == 'tag':
        if ref != tag:
            raise ValueError('Tag does not match source version: ' + ref + ' != ' + tag)
    elif ref not in (config['maintenance_branch'], 'PHP-5.6-CVE-2026-109618-109619'):
        raise ValueError('Run release from the maintenance branch or its version tag')
    existing = subprocess.run(['git', 'rev-parse', '--verify', 'refs/tags/' + tag + '^{commit}'],
                              cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if existing.returncode == 0 and existing.stdout.strip() != sha:
        raise ValueError('Existing tag points to another commit; publish a new secN instead')
    notes = ROOT / 'releases' / (version + '.md')
    if not notes.is_file() or 'TODO' in notes.read_text(encoding='utf-8'):
        raise ValueError('Complete releases/' + version + '.md before publishing')
    subprocess.run(['python3', str(ROOT / 'ci/release/check_source.py')], cwd=ROOT, check=True)
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as out:
        for key, value in dict(version=version, tag=tag, sha=sha).items():
            out.write(key + '=' + value + '\n')
    print('Release source: ' + tag + ' at ' + sha)


if __name__ == '__main__':
    prepare()
