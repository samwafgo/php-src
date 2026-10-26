#!/usr/bin/env python3
"""Create an annotated tag and publish fully uploaded assets without moving tags."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from version import read_version


def api(path, method='GET', payload=None, optional=False):
    headers = {'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
               'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json',
               'X-GitHub-Api-Version': '2022-11-28'}
    request = urllib.request.Request('https://api.github.com/repos/' + os.environ['GITHUB_REPOSITORY'] + '/' + path,
                                     data=json.dumps(payload).encode() if payload is not None else None,
                                     headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if optional and method == 'GET' and error.code == 404:
            return None
        raise RuntimeError('GitHub API failed: ' + str(error.code) + ' ' + method + ' ' + path) from None


def commit_for_ref(ref):
    obj = ref['object']
    while obj['type'] == 'tag':
        obj = api('git/tags/' + obj['sha'])['object']
    if obj['type'] != 'commit':
        raise ValueError('Release tag does not point to a commit')
    return obj['sha']


def find_release(tag):
    release = api('releases/tags/' + urllib.parse.quote(tag, safe=''), optional=True)
    if release:
        return release
    # The by-tag endpoint targets published releases. Authenticated listing
    # also finds a draft left by a previous partial upload.
    page = 1
    while True:
        releases = api('releases?per_page=100&page=' + str(page))
        for item in releases:
            if item['tag_name'] == tag:
                return item
        if len(releases) < 100:
            return None
        page += 1


def publish():
    version = read_version()
    tag = 'php-' + version
    assets = Path('release-assets')
    manifest = json.loads((assets / 'RELEASE-MANIFEST.json').read_text())
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if manifest['source_commit'] != commit or manifest['tag'] != tag:
        raise ValueError('Asset source SHA/tag mismatch')
    checksums = {}
    for line in (assets / 'SHA256SUMS').read_text(encoding='ascii').splitlines():
        digest, name = line.split('  ', 1)
        if Path(name).name != name or name in checksums:
            raise ValueError('Invalid or duplicate release checksum entry')
        checksums[name] = digest
    actual = {p.name for p in assets.iterdir() if p.is_file() and p.name != 'SHA256SUMS'}
    if set(checksums) != actual:
        raise ValueError('Release checksum inventory mismatch')
    for name, digest in checksums.items():
        if hashlib.sha256((assets / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Release file checksum mismatch: ' + name)
    # Inspect release state before any mutation; published assets are never replaced.
    encoded = urllib.parse.quote(tag, safe='')
    release = find_release(tag)
    if release and not release['draft']:
        raise ValueError('Release is already published; do not overwrite a released secN')
    ref = api('git/ref/tags/' + encoded, optional=True)
    if ref and commit_for_ref(ref) != commit:
        raise ValueError('Tag already points to another source commit')
    if not ref:
        annotated = api('git/tags', 'POST', dict(tag=tag, message='PHP ' + version + ' community security backport',
                                               object=commit, type='commit'))
        api('git/refs', 'POST', dict(ref='refs/tags/' + tag, sha=annotated['sha']))
    if not release:
        release = api('releases', 'POST', dict(tag_name=tag, target_commitish=commit,
                      name='PHP ' + version + ' — SamWaf community backport',
                      body=(assets / 'RELEASE-NOTES.md').read_text(), draft=True, prerelease=False))
    files = sorted(path for path in assets.iterdir() if path.is_file())
    # Only a draft may be resumed. This supports retries after partial uploads.
    subprocess.run(['gh', 'release', 'upload', tag, '--repo', os.environ['GITHUB_REPOSITORY'],
                    '--clobber'] + [str(path) for path in files], check=True)
    remote = api('releases/' + str(release['id']))
    uploaded = {asset['name']: asset for asset in remote['assets']}
    if set(uploaded) != {path.name for path in files}:
        raise ValueError('Remote release assets are missing or contain stale unexpected files')
    for path in files:
        item = uploaded[path.name]
        if item['size'] != path.stat().st_size:
            raise ValueError('Uploaded asset size mismatch: ' + path.name)
        digest = item.get('digest')
        if digest and digest != 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError('Uploaded asset digest mismatch: ' + path.name)
    if commit_for_ref(api('git/ref/tags/' + encoded)) != commit:
        raise ValueError('Tag changed during upload')
    published = api('releases/' + str(release['id']), 'PATCH', dict(draft=False, make_latest='true'))
    print('Published ' + published['html_url'])


if __name__ == '__main__':
    publish()
