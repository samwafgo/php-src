#!/usr/bin/env python3
"""Accept exactly 15 Linux and four Windows candidates from one commit."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile

from version import ROOT, read_version

sys.path.insert(0, str(ROOT / 'ci/multibuild'))
from matrix import TARGETS


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory():
    result = {}
    for target in TARGETS:
        result['php56-' + target + '-web-release-candidate'] = dict(target=target, profile='web-release')
    for arch in ('x86', 'x64'):
        for threading in ('nts', 'ts'):
            result['php56-windows-vc11-' + arch + '-' + threading + '-core-candidate'] = dict(
                platform='Windows', arch=arch, threading=threading, profile='core')
    return result


def validate_candidates(download, version, commit):
    download = Path(download)
    expected = inventory()
    if {p.name for p in download.iterdir()} != set(expected):
        raise ValueError('Candidate inventory mismatch: exactly 15 Linux and 4 Windows required')
    accepted = []
    for artifact, fields in expected.items():
        folder = download / artifact
        manifest = json.loads((folder / 'MANIFEST.json').read_text(encoding='utf-8-sig'))
        required = dict(version=version, source_commit=commit, **fields)
        if any(manifest.get(key) != value for key, value in required.items()):
            raise ValueError('Manifest version/commit/target mismatch: ' + artifact)
        archives = list(folder.glob('*.zip')) + list(folder.glob('*.tar.gz'))
        if len(archives) != 1:
            raise ValueError('Expected one binary archive: ' + artifact)
        archive = archives[0]
        if not archive.name.startswith('php-' + version + '-'):
            raise ValueError('Archive version name mismatch: ' + archive.name)
        sums = (folder / 'SHA256SUMS').read_text(encoding='ascii').strip()
        if sums != sha256(archive) + '  ' + archive.name:
            raise ValueError('Archive SHA256 mismatch: ' + artifact)
        if 'platform' in fields:
            with zipfile.ZipFile(archive) as zipped:
                if zipped.testzip() is not None:
                    raise ValueError('Damaged ZIP: ' + archive.name)
                inside = json.loads(zipped.read('MANIFEST.json').decode('utf-8-sig'))
            if inside.get('verification', {}).get('status') != 'PASS':
                raise ValueError('Windows package did not pass runtime validation')
        else:
            with tarfile.open(archive, 'r:gz') as tar:
                name = archive.name[:-len('.tar.gz')]
                stream = tar.extractfile(name + '/MANIFEST.json')
                if stream is None:
                    raise ValueError('Missing embedded manifest')
                inside = json.load(stream)
            if not inside.get('fpm_smoke', '').startswith('PASS:') or not isinstance(inside.get('phpt'), dict):
                raise ValueError('Linux package lacks validation evidence')
        if inside != manifest:
            raise ValueError('Embedded and outer manifests disagree: ' + artifact)
        accepted.append((artifact, archive, manifest))
    return accepted


def assemble(download, output, commit):
    version = read_version()
    current = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if current != commit or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Release checkout does not match selected source SHA')
    accepted = validate_candidates(download, version, commit)
    output = Path(output)
    if output.exists():
        raise ValueError('Use a fresh release asset directory')
    output.mkdir(parents=True)
    entries = []
    for artifact, archive, manifest in accepted:
        shutil.copyfile(archive, output / archive.name)
        entries.append(dict(artifact=artifact, file=archive.name, sha256=sha256(archive),
                            source_commit=manifest['source_commit'], profile=manifest['profile']))
    prefix = 'php-' + version + '-source/'
    for format_, suffix in (('tar.gz', '.tar.gz'), ('zip', '.zip')):
        subprocess.run(['git', 'archive', '--format=' + format_, '--prefix=' + prefix,
                        '--output=' + str((output / (prefix[:-1] + suffix)).resolve()), commit], cwd=ROOT, check=True)
    config = json.loads((ROOT / 'ci/release/security.json').read_text())
    patch = ROOT / config['cumulative_patch']
    shutil.copyfile(patch, output / ('php-' + version + '-security.patch'))
    shutil.copyfile(ROOT / 'releases' / (version + '.md'), output / 'RELEASE-NOTES.md')
    (output / 'RELEASE-MANIFEST.json').write_text(json.dumps(dict(
        version=version, tag='php-' + version, source_commit=commit,
        repository='https://github.com/samwafgo/php-src', binaries=entries,
        security_patch_source=config['cumulative_patch'],
        limits='Community limited-extension candidates; full production/CVE acceptance not implied'), indent=2) + '\n')
    with zipfile.ZipFile(output / ('php-' + version + '-build-manifests.zip'), 'w', zipfile.ZIP_DEFLATED) as zipped:
        for artifact, archive, manifest in accepted:
            for name in ('MANIFEST.json', 'SHA256SUMS'):
                zipped.write(archive.parent / name, artifact + '/' + name)
    sums = ''.join(sha256(path) + '  ' + path.name + '\n' for path in sorted(output.iterdir()))
    (output / 'SHA256SUMS').write_text(sums, encoding='ascii')
    print('Prepared ' + str(len(accepted)) + ' binary assets plus source, patch, manifests and SHA256SUMS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    assemble(args.download, args.output, args.commit)
