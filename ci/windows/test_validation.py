#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('verify_windows',BASE/'verify_windows.py')
v=importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

def pe(path,machine):
    data=bytearray(256)
    data[:2]=b'MZ'
    struct.pack_into('<I',data,0x3c,128)
    data[128:132]=b'PE\0\0'
    struct.pack_into('<H',data,132,machine)
    path.write_bytes(data)

class VerificationTests(unittest.TestCase):
    def test_both_pe_architectures(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'binary'
            for machine,arch in [(0x14c,'x86'),(0x8664,'x64')]:
                pe(p,machine)
                self.assertEqual(v.pe_architecture(p),arch)
    def test_truncated_pe_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'binary';p.write_bytes(b'MZ')
            with self.assertRaises(ValueError):v.pe_architecture(p)
    def test_bad_pe_offset_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'binary';pe(p,0x14c)
            data=bytearray(p.read_bytes());struct.pack_into('<I',data,0x3c,100000);p.write_bytes(data)
            with self.assertRaises(ValueError):v.pe_architecture(p)
    def test_arm_package_not_mislabeled_x64(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'binary';pe(p,0xaa64)
            with self.assertRaises(ValueError):v.pe_architecture(p)
    def test_cgi_response(self):
        self.assertEqual(v.parse_cgi(b'Content-Type: text/plain\r\n\r\nok'),'ok')
    def test_cgi_error_not_accepted(self):
        with self.assertRaises(ValueError):v.parse_cgi(b'Status: 500 Error\r\n\r\nok')
    def test_missing_cgi_headers(self):
        with self.assertRaises(ValueError):v.parse_cgi(b'ok')
    def test_wrong_runtime_version_rejected_before_upload(self):
        with tempfile.TemporaryDirectory() as d:
            package=Path(d)
            for file in ('php.exe','php-cgi.exe','php5.dll'):pe(package/file,0x8664)
            with patch.object(v,'run',return_value=b'5.6.40|nts|64|session'):
                with self.assertRaisesRegex(ValueError,'mismatch'):v.verify(package,'x64','nts')
    def test_wrong_runtime_threading_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            package=Path(d)
            for file in ('php.exe','php-cgi.exe','php5ts.dll'):pe(package/file,0x8664)
            with patch.object(v,'run',return_value=b'5.6.40-sec1|nts|64|session'):
                with self.assertRaisesRegex(ValueError,'mismatch'):v.verify(package,'x64','ts')
    def test_missing_php_dll_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            package=Path(d)
            for file in ('php.exe','php-cgi.exe'):pe(package/file,0x8664)
            with self.assertRaisesRegex(ValueError,'runtime DLL'):v.verify(package,'x64','nts')
    def test_lock_only_pins_original_vendor_files(self):
        lock=json.loads((BASE/'downloads.json').read_text())
        self.assertEqual({a['id'] for a in lock['assets']},{'vc11_iso','php_sdk','deps_x86','deps_x64'})
        for a in lock['assets']:
            self.assertRegex(a['url'],r'^https://(?:download\.microsoft\.com|downloads\.php\.net)/')
            self.assertRegex(a['sha256'],r'^[0-9a-f]{64}$')
            self.assertEqual(Path(a['filename']).name,a['filename'])

if __name__=='__main__':unittest.main()
