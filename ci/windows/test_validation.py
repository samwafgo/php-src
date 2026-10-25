#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import contextlib
import io
import runpy
import subprocess
import sys

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
    def runtime_output(self, threading, integer_bits=32, cgi_integer_bits=32):
        counter=0
        def output(argv, **kwargs):
            nonlocal counter
            if '-r' in argv:
                return ('5.6.40-sec1|'+threading+'|'+str(integer_bits)+'|session').encode()
            if '-v' in argv:
                return b'PHP 5.6.40-sec1'
            counter+=1
            self.assertEqual(Path(argv[0]).name,'php-cgi.exe')
            self.assertIn(b'filename="safe.txt"',kwargs['input'])
            body='|'.join(['safe.txt','0',v.hashlib.md5(b'ordinary-php56-windows-upload\n').hexdigest(),
                           str(counter),'0','5.6.40-sec1',threading,str(cgi_integer_bits)])
            return b'Content-Type: text/plain\r\n\r\n'+body.encode()
        return output
    def windows_package(self, package, arch, threading):
        for name in ('php.exe','php-cgi.exe','php5ts.dll' if threading=='ts' else 'php5.dll'):
            pe(package/name,0x8664 if arch=='x64' else 0x14c)
    def test_all_windows_php56_configurations_use_32bit_integers(self):
        for arch in ('x86','x64'):
            for threading in ('nts','ts'):
                with self.subTest(arch=arch,threading=threading), tempfile.TemporaryDirectory() as d:
                    package=Path(d)
                    self.windows_package(package,arch,threading)
                    with patch.object(v,'run',side_effect=self.runtime_output(threading)) as runtime:
                        result=v.verify(package,arch,threading)
                    self.assertEqual(result['status'],'PASS')
                    self.assertEqual(result['pe_architecture'],arch)
                    self.assertEqual(result['cli'],'5.6.40-sec1|'+threading+'|32|session')
                    self.assertEqual(runtime.call_count,5) # CLI, two versions, two CGI uploads
    def test_mixed_x86_binaries_still_rejected_in_x64_package(self):
        for name in ('php.exe','php-cgi.exe','php5.dll'):
            with self.subTest(file=name), tempfile.TemporaryDirectory() as d:
                package=Path(d)
                self.windows_package(package,'x64','nts')
                pe(package/name,0x14c)
                with patch.object(v,'run') as runtime:
                    with self.assertRaisesRegex(ValueError,'Wrong architecture'):
                        v.verify(package,'x64','nts')
                    runtime.assert_not_called()
    def test_unexpected_64bit_integer_model_rejected_in_cli_and_cgi(self):
        for cli_bits,cgi_bits in ((64,32),(32,64)):
            with self.subTest(cli=cli_bits,cgi=cgi_bits), tempfile.TemporaryDirectory() as d:
                package=Path(d)
                self.windows_package(package,'x64','nts')
                with patch.object(v,'run',side_effect=self.runtime_output('nts',cli_bits,cgi_bits)):
                    with self.assertRaisesRegex(ValueError,'mismatch'):
                        v.verify(package,'x64','nts')
    def generate_patch(self, destination, simulate_windows=False):
        root=BASE.parent.parent
        helper=root/'ci/prepare-git-patch.py'
        args=[str(helper),'--source',str(root/'security-backports/php-5.6.40-CVE-2026-109618-109619.patch'),
              '--output',str(destination)]
        original_write_text=Path.write_text
        def windows_text_write(path,data,*positional,**kwargs):
            # Reproduce Windows text-mode translation even when tests run on Linux.
            newline=kwargs.pop('newline',None)
            if newline is None:data=data.replace('\n','\r\n')
            return original_write_text(path,data,*positional,newline='',**kwargs)
        with patch.object(sys,'argv',args), contextlib.redirect_stdout(io.StringIO()):
            if simulate_windows:
                with patch.object(Path,'write_text',windows_text_write):
                    runpy.run_path(str(helper),run_name='__main__')
            else:runpy.run_path(str(helper),run_name='__main__')
    def test_patch_writer_preserves_lf_under_windows_translation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'git.patch'
            self.generate_patch(p,simulate_windows=True)
            data=p.read_bytes()
            self.assertNotIn(b'\r',data)
            self.assertFalse(data.startswith(b'\xef\xbb\xbf'))
            self.assertEqual(data.count(b'--- a/'),16)
            self.assertNotIn(b'--- a/configure\n',data)
    def test_generated_patch_passes_original_strict_reverse_check(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'git.patch'
            self.generate_patch(p)
            result=subprocess.run(['git','apply','--reverse','--check',str(p)],
                cwd=BASE.parent.parent,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
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
