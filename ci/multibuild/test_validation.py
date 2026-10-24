#!/usr/bin/env python3
"""Tests for accepting/rejecting security-build evidence, no PHP required."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

BASE=Path(__file__).resolve().parent
def module(name):
    spec=importlib.util.spec_from_file_location(name,BASE/(name+'.py'))
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
phpt=module('phpt')
matrix=module('matrix')
parsers=module('prepare_parsers')
compat=module('prepare_compat')
ALLOW={
 'ext/session/tests/rfc1867.phpt','ext/session/tests/rfc1867_inter.phpt',
 'ext/session/tests/rfc1867_sid_cookie.phpt','ext/session/tests/rfc1867_sid_get.phpt',
 'ext/session/tests/rfc1867_sid_get_2.phpt','ext/session/tests/rfc1867_sid_invalid.phpt',
 'ext/session/tests/rfc1867_sid_only_cookie.phpt','ext/session/tests/rfc1867_sid_post.phpt',
}
LOG='''Number of tests : 1863              1818
Tests skipped   :   45 (  2.4%) --------
Tests warned    :    0 (  0.0%) (  0.0%)
Tests failed    :    8 (  0.4%) (  0.4%)
Expected fail   :    8 (  0.4%) (  0.4%)
Tests passed    : 1802 ( 96.7%) ( 99.1%)
Time taken      :   15 seconds
=====================================================================
EXPECTED FAILED TEST SUMMARY
---------------------------------------------------------------------
Expected failure [Zend/tests/bug69111.phpt]
=====================================================================
FAILED TEST SUMMARY
---------------------------------------------------------------------
'''+''.join('session rfc1867 ['+f+']\n' for f in sorted(ALLOW))+'=====================================================================\n'
RELEASE_LOG=(LOG.replace('45 (  2.4%)','34 (  2.4%)')
    .replace('Tests warned    :    0','Tests warned    :    1')
    .replace('Expected fail   :    8','Expected fail   :    7')
    .replace('1802','1813') + '''WARNED TEST SUMMARY
---------------------------------------------------------------------
Bug #69111 Crash in SessionHandler::read() [ext/session/tests/bug69111.phpt] (warn: XFAIL section but test passes)
=====================================================================
''')

class ValidationTests(unittest.TestCase):
    def test_real_php56_counter_format_separates_xfail(self):
        result=phpt.check(LOG,1,ALLOW)
        self.assertEqual(result['counts']['fail'],8)
        self.assertEqual(result['counts']['xfail'],8)
        self.assertEqual(set(result['actual_failures']),ALLOW)
    def test_incomplete_counter_section(self):
        with self.assertRaises(ValueError): phpt.check(LOG.split('Tests passed')[0],1,ALLOW)
    def test_inconsistent_counts(self):
        with self.assertRaises(ValueError): phpt.check(LOG.replace('1802','1803'),1,ALLOW)
    def test_unknown_failure(self):
        with self.assertRaises(ValueError): phpt.check(LOG.replace('rfc1867.phpt','new-regression.phpt'),1,ALLOW)
    def test_killed_process_cannot_be_allowlisted(self):
        with self.assertRaises(ValueError): phpt.check(LOG,137,ALLOW)
    def test_missing_failed_summary(self):
        with self.assertRaises(ValueError): phpt.check(LOG.split('\nFAILED TEST SUMMARY')[0],1,ALLOW)
    def test_no_widening_allowlist_for_new_platforms(self):
        actual={s.strip().strip('[]') for s in (BASE.parent.parent/'tests/expected-failures.txt').read_text().splitlines() if s.strip() and not s.startswith('#')}
        self.assertEqual(actual,ALLOW)
    def test_inventory_native_architecture_and_unique_artifact_names(self):
        rows=matrix.select('all')
        self.assertEqual(len(rows),15)
        self.assertEqual(len({r['target'] for r in rows}),15)
        for row in rows:
            self.assertEqual(row['runner'].endswith('-arm'),row['arch']=='aarch64')
            self.assertEqual(row['platform'],'linux/arm64' if row['arch']=='aarch64' else 'linux/amd64')
    def test_wrong_parser_archive_hash_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'archive').write_bytes(b'not the verified archive')
            with self.assertRaisesRegex(ValueError,'SHA256'):
                parsers.prepare(root/'archive',root,root/'result.json')
    def test_known_release_xpass_preserves_warning(self):
        result=phpt.check(RELEASE_LOG,1,ALLOW,'web-release')
        self.assertEqual(result['counts']['warn'],1)
        self.assertEqual(result['counts']['pass'],1813)
        self.assertEqual(result['known_release_warnings'][0]['test'],phpt.RELEASE_XPASS)
    def test_release_xpass_not_accepted_in_debug(self):
        with self.assertRaises(ValueError):phpt.check(RELEASE_LOG,1,ALLOW,'debug-test')
    def test_unknown_warning_still_fails(self):
        with self.assertRaises(ValueError):
            phpt.check(RELEASE_LOG.replace('ext/session/tests/bug69111.phpt','ext/session/tests/unknown.phpt'),1,ALLOW,'web-release')
    def test_wrong_warning_reason_still_fails(self):
        with self.assertRaises(ValueError):
            phpt.check(RELEASE_LOG.replace('XFAIL section but test passes','test crashes'),1,ALLOW,'web-release')
    def test_warning_counter_without_warning_summary_fails(self):
        with self.assertRaises(ValueError):phpt.check(RELEASE_LOG.split('WARNED TEST SUMMARY')[0],1,ALLOW,'web-release')
    def test_borked_still_fails_with_known_xpass(self):
        with self.assertRaises(ValueError):phpt.check(RELEASE_LOG+'BORKED TEST SUMMARY\n',1,ALLOW,'web-release')
    def test_arm_compat_changes_only_two_constraint_lines_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'Zend').mkdir()
            original=(BASE.parent.parent/'Zend/zend_multiply.h').read_bytes()
            file=root/'Zend/zend_multiply.h'
            file.write_bytes(original)
            compat.prepare(root,'x86_64',root/'result.json')
            self.assertEqual(file.read_bytes(),original)
            result=compat.prepare(root,'aarch64',root/'result.json')
            self.assertTrue(result['changed'])
            modified=file.read_bytes()
            differences=[(a,b) for a,b in zip(original.splitlines(),modified.splitlines()) if a!=b]
            self.assertEqual(len(differences),2)
            self.assertIn(b'"=&r"',differences[0][1])
            self.assertFalse(compat.prepare(root,'aarch64',root/'result.json')['changed'])
            self.assertEqual(file.read_bytes(),modified)

if __name__=='__main__': unittest.main()
