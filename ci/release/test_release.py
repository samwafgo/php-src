#!/usr/bin/env python3
"""Release integrity regressions. No GitHub mutation or native compiler needed."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from version import ROOT, read_version
from bump import bump
from check_source import check
from assemble import inventory, validate_candidates
import publish

SHA = 'a' * 40
VERSION = read_version()


def make_candidates(root):
    for artifact, fields in inventory().items():
        directory = root / artifact
        directory.mkdir()
        manifest = dict(version=VERSION, source_commit=SHA, **fields)
        manifest.update(verification={'status': 'PASS'}, phpt={'counts': {}}, fpm_smoke='PASS: fixture')
        name = 'php-' + VERSION + '-' + artifact[len('php56-'):]
        if fields.get('platform') == 'Windows':
            archive = directory / (name + '.zip')
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('MANIFEST.json', json.dumps(manifest))
        else:
            archive = directory / (name + '.tar.gz')
            data = json.dumps(manifest).encode()
            info = tarfile.TarInfo(name + '/MANIFEST.json')
            info.size = len(data)
            with tarfile.open(archive, 'w:gz') as tar:
                tar.addfile(info, io.BytesIO(data))
        (directory / 'MANIFEST.json').write_text(json.dumps(manifest))
        (directory / 'SHA256SUMS').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')


class ReleaseTests(unittest.TestCase):
    def source_copy(self, root):
        config = json.loads((ROOT / 'ci/release/security.json').read_text())
        text = (ROOT / config['cumulative_patch']).read_text()
        names = set(re.findall(r'^\+\+\+ b/(.+)$', text, re.M)) - {'configure'}
        names |= {'ci/prepare-git-patch.py', config['cumulative_patch'], 'ci/release/security.json'}
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def test_current_source_security_check(self):
        check()

    def test_sec2_bump_keeps_security_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.source_copy(root)
            next_ = '5.6.40-sec' + str(int(VERSION.split('-sec')[1]) + 1)
            bump(root, next_)
            self.assertEqual(read_version(root), next_)
            check(root)
            self.assertIn('TODO', (root / 'releases' / (next_ + '.md')).read_text())

    def test_version_header_configure_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.source_copy(root)
            file = root / 'configure.in'
            file.write_text(file.read_text().replace('PHP_EXTRA_VERSION="-' + VERSION.split('-')[1] + '"',
                                                     'PHP_EXTRA_VERSION="-sec999999"'))
            with self.assertRaisesRegex(ValueError, 'disagree'):
                read_version(root)

    def test_revision_cannot_be_reused_or_skipped(self):
        for invalid in (VERSION, '5.6.40-sec0', '5.6.40-sec999999', 'sec2'):
            with self.subTest(version=invalid), self.assertRaises(ValueError):
                bump(ROOT, invalid)

    def test_removed_security_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.source_copy(root)
            file = root / 'ext/session/session.c'
            text = file.read_text()
            self.assertIn('if (!PS(rfc1867_enabled) || 1)', text)
            file.write_text(text.replace('if (!PS(rfc1867_enabled) || 1)', 'if (!PS(rfc1867_enabled))'))
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(subprocess.CalledProcessError):
                check(root, quiet=True)

    def test_all_19_configurations_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_candidates(root)
            self.assertEqual(len(validate_candidates(root, VERSION, SHA)), 19)

    def test_mismatched_source_commit_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_candidates(root)
            with self.assertRaisesRegex(ValueError, 'commit/target mismatch'):
                validate_candidates(root, VERSION, 'b' * 40)

    def test_missing_candidate_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_candidates(root)
            shutil.rmtree(root / next(iter(inventory())))
            with self.assertRaisesRegex(ValueError, 'inventory mismatch'):
                validate_candidates(root, VERSION, SHA)

    def test_wrong_profile_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_candidates(root)
            file = root / next(iter(inventory())) / 'MANIFEST.json'
            data = json.loads(file.read_text())
            data['profile'] = 'debug-test'
            file.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'target mismatch'):
                validate_candidates(root, VERSION, SHA)

    def test_corrupt_binary_archive_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_candidates(root)
            archive = next(root.rglob('*.zip'))
            archive.write_bytes(archive.read_bytes() + b'tampered')
            with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
                validate_candidates(root, VERSION, SHA)

    def test_outer_manifest_cannot_override_embedded_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_candidates(root)
            file = root / next(iter(inventory())) / 'MANIFEST.json'
            data = json.loads(file.read_text())
            data['forged_extra'] = True
            file.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'manifests disagree'):
                validate_candidates(root, VERSION, SHA)

    def test_annotated_tag_resolves_to_exact_commit(self):
        ref = {'object': {'type': 'tag', 'sha': 'c' * 40}}
        with patch.object(publish, 'api', return_value={'object': {'type': 'commit', 'sha': SHA}}):
            self.assertEqual(publish.commit_for_ref(ref), SHA)

    def test_interrupted_draft_is_found_for_resume(self):
        draft = {'tag_name': 'php-' + VERSION, 'draft': True, 'id': 42}
        with patch.object(publish, 'api', side_effect=[None, [draft]]):
            self.assertEqual(publish.find_release('php-' + VERSION), draft)

    def test_published_release_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            assets = root / 'release-assets'
            assets.mkdir()
            data = json.dumps({'source_commit': SHA, 'tag': 'php-' + VERSION}).encode()
            (assets / 'RELEASE-MANIFEST.json').write_bytes(data)
            (assets / 'SHA256SUMS').write_text(hashlib.sha256(data).hexdigest() + '  RELEASE-MANIFEST.json\n')
            before = Path.cwd()
            try:
                os.chdir(root)
                with patch.object(publish.subprocess, 'check_output', return_value=SHA), \
                     patch.object(publish.subprocess, 'run') as process, \
                     patch.object(publish, 'api', return_value={'draft': False}) as api:
                    with self.assertRaisesRegex(ValueError, 'already published'):
                        publish.publish()
                    process.assert_not_called()
                    self.assertEqual(api.call_count, 1)
            finally:
                os.chdir(before)


if __name__ == '__main__':
    unittest.main()
