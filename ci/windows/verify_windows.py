#!/usr/bin/env python3
"""Verify the actual staged Windows binaries, then send two benign CGI uploads."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

def pe_architecture(file):
    with file.open('rb') as f:
        header=f.read(64)
        if len(header)!=64 or header[:2]!=b'MZ': raise ValueError('Not a PE file: '+str(file))
        offset=struct.unpack_from('<I',header,0x3c)[0]
        if offset<64 or offset>file.stat().st_size-6: raise ValueError('Invalid PE offset')
        f.seek(offset)
        pe=f.read(6)
    if pe[:4]!=b'PE\0\0': raise ValueError('Missing PE signature')
    machine=struct.unpack_from('<H',pe,4)[0]
    if machine not in (0x14c,0x8664): raise ValueError('Unsupported PE architecture')
    return 'x64' if machine==0x8664 else 'x86'

def run(argv, **kwargs):
    result=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,**kwargs)
    if result.returncode!=0:
        raise ValueError('Process failed: '+str(argv[0])+': '+result.stderr.decode(errors='replace'))
    if result.stderr:
        raise ValueError('Unexpected PHP stderr: '+result.stderr.decode(errors='replace'))
    return result.stdout

def parse_cgi(stdout):
    parts=stdout.split(b'\r\n\r\n',1)
    if len(parts)!=2: parts=stdout.split(b'\n\n',1)
    if len(parts)!=2: raise ValueError('Missing CGI response headers')
    headers,body=parts
    for line in headers.splitlines():
        if line.lower().startswith(b'status:') and not line.lower().startswith(b'status: 200'):
            raise ValueError('CGI HTTP error: '+line.decode(errors='replace'))
    return body.decode().strip()

def verify(package, arch, threading):
    package=package.resolve()
    php=package/'php.exe'
    cgi=package/'php-cgi.exe'
    for file in [php,cgi]+list(package.glob('*.dll')):
        if pe_architecture(file)!=arch: raise ValueError('Wrong architecture: '+file.name)
    if not (package/('php5ts.dll' if threading=='ts' else 'php5.dll')).is_file():
        raise ValueError('Missing matching PHP runtime DLL')
    # PHP 5.6 uses sizeof(long) for PHP_INT_SIZE. Windows keeps long at
    # 32 bits on x64 too (LLP64); executable architecture is checked above
    # using the PE Machine field, independently of PHP integer width.
    integer_bits='32'
    code='echo PHP_VERSION,"|",(PHP_ZTS?"ts":"nts"),"|",PHP_INT_SIZE*8,"|",(extension_loaded("session")?"session":"missing");'
    cli=run([str(php),'-n','-r',code],cwd=str(package)).decode().strip()
    if cli!='5.6.40-sec1|'+threading+'|'+integer_bits+'|session':
        raise ValueError('Version/threading/integer-width/session mismatch: '+cli)
    for binary in [php,cgi]:
        if 'PHP 5.6.40-sec1' not in run([str(binary),'-n','-v'],cwd=str(package)).decode():
            raise ValueError('Wrong PHP version: '+binary.name)
    with tempfile.TemporaryDirectory(prefix='php56-cgi-') as folder:
        root=Path(folder)
        script=root/'upload.php'
        script.write_text('''<?php
session_save_path(dirname(__FILE__));
session_id('php56buildcheck');
session_start();
$_SESSION['counter'] = isset($_SESSION['counter']) ? $_SESSION['counter'] + 1 : 1;
$f=$_FILES['file'];
echo $f['name'],'|',$f['error'],'|',md5_file($f['tmp_name']),'|',$_SESSION['counter'],'|',
    (isset($_SESSION['upload_progress_probe'])?1:0),'|',PHP_VERSION,'|',
    (PHP_ZTS?'ts':'nts'),'|',PHP_INT_SIZE*8;
''')
        payload=b'ordinary-php56-windows-upload\n'
        body=(b'--php56check\r\nContent-Disposition: form-data; name="PHP_SESSION_UPLOAD_PROGRESS"\r\n\r\nprobe\r\n'
              b'--php56check\r\nContent-Disposition: form-data; name="file"; filename="safe.txt"\r\n'
              b'Content-Type: text/plain\r\n\r\n'+payload+b'\r\n--php56check--\r\n')
        env=os.environ.copy()
        env.update(dict(SCRIPT_FILENAME=str(script),SCRIPT_NAME='/upload.php',REQUEST_URI='/upload.php',
            REQUEST_METHOD='POST',SERVER_PROTOCOL='HTTP/1.1',GATEWAY_INTERFACE='CGI/1.1',
            SERVER_NAME='localhost',SERVER_PORT='80',REMOTE_ADDR='127.0.0.1',REDIRECT_STATUS='1',
            CONTENT_TYPE='multipart/form-data; boundary=php56check',CONTENT_LENGTH=str(len(body))))
        for i in (1,2):
            response=parse_cgi(run([str(cgi),'-n'],input=body,env=env,cwd=str(package)))
            expected='|'.join(['safe.txt','0',hashlib.md5(payload).hexdigest(),str(i),'0',
                               '5.6.40-sec1',threading,integer_bits])
            if response!=expected: raise ValueError('CGI upload/session check mismatch: '+response)
    return dict(status='PASS',cli=cli,pe_architecture=arch,threading=threading,
                php_integer_bits=int(integer_bits),
                cgi='two multipart uploads, persisted Session counter 1/2, upload progress absent',
                phpt='not run',iis_apache='not tested',cve_exploit_regression='not run')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--package',required=True,type=Path)
    p.add_argument('--arch',required=True,choices=['x86','x64'])
    p.add_argument('--threading',required=True,choices=['ts','nts'])
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    result=verify(a.package,a.arch,a.threading)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
