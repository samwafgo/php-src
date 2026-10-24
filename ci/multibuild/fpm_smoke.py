#!/usr/bin/env python3
"""Real FastCGI upload and session reuse checks; no exploit payloads."""
import argparse
import hashlib
import os
from pathlib import Path
import pwd
import socket
import struct
import subprocess
import tempfile
import time

def record(kind, data=b''):
    return struct.pack('!BBHHBB',1,kind,1,len(data),0,0)+data

def length(n):
    return bytes([n]) if n < 128 else struct.pack('!I', n | 0x80000000)

def request(sockfile, script, body):
    env = dict(SCRIPT_FILENAME=str(script), SCRIPT_NAME='/test.php',
               REQUEST_METHOD='POST', REQUEST_URI='/test.php', SERVER_PROTOCOL='HTTP/1.1',
               GATEWAY_INTERFACE='CGI/1.1', SERVER_NAME='localhost', SERVER_PORT='80',
               REMOTE_ADDR='127.0.0.1', CONTENT_TYPE='multipart/form-data; boundary=php56check',
               CONTENT_LENGTH=str(len(body)), HTTP_COOKIE='PHPSESSID=php56buildcheck')
    params=b''
    for key, value in env.items():
        k,v=key.encode(),value.encode()
        params += length(len(k))+length(len(v))+k+v
    def readn(sock,n):
        b=b''
        while len(b)<n:
            part=sock.recv(n-len(b))
            if not part: raise RuntimeError('FPM connection closed early')
            b+=part
        return b
    stdout=b''
    stderr=b''
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(15)
        s.connect(str(sockfile))
        s.sendall(record(1,struct.pack('!HB5x',1,0))+record(4,params)+record(4)
                  +record(5,body)+record(5))
        while True:
            version,kind,rid,size,padding,_=struct.unpack('!BBHHBB',readn(s,8))
            data=readn(s,size)
            readn(s,padding)
            if version!=1 or rid!=1: raise RuntimeError('Invalid FastCGI response')
            if kind==6: stdout+=data
            elif kind==7: stderr+=data
            elif kind==3:
                if len(data)!=8 or struct.unpack('!IB3x',data)!=(0,0):
                    raise RuntimeError('Nonzero FastCGI application/protocol status')
                break
    if stderr: raise RuntimeError('FastCGI stderr: '+stderr.decode(errors='replace'))
    if b'\r\n\r\n' not in stdout: raise RuntimeError('Missing CGI headers')
    headers,response=stdout.split(b'\r\n\r\n',1)
    if b'Status:' in headers and b'Status: 200' not in headers:
        raise RuntimeError('HTTP error: '+headers.decode(errors='replace'))
    return response.decode().strip().split('|')

def smoke(binary, output):
    with tempfile.TemporaryDirectory(prefix='php56-fpm-') as d:
        root=Path(d)
        sockfile=root/'fpm.sock'
        script=root/'test.php'
        script.write_text('''<?php
session_start();
$_SESSION['counter'] = isset($_SESSION['counter']) ? $_SESSION['counter'] + 1 : 1;
$progress = isset($_SESSION['upload_progress_probe']) ? 1 : 0;
$f=$_FILES['file'];
echo getmypid(),'|',$f['name'],'|',$f['error'],'|',md5_file($f['tmp_name']),'|',$_SESSION['counter'],'|',$progress;
''')
        conf=root/'fpm.conf'
        conf.write_text('''[global]
daemonize = no
error_log = {root}/error.log
[check]
user = {user}
group = {group}
listen = {sockfile}
pm = static
pm.max_children = 1
pm.max_requests = 0
catch_workers_output = yes
php_admin_value[session.save_path] = {root}
php_admin_value[session.upload_progress.enabled] = 1
'''.format(root=root, sockfile=sockfile, user=pwd.getpwuid(os.getuid()).pw_name,
           group=__import__('grp').getgrgid(os.getgid()).gr_name))
        logpath=Path(output)
        with logpath.open('w') as log:
            cmd=[str(Path(binary).resolve()),'-n','-F','-y',str(conf),'-p',str(root)]
            if os.getuid()==0: cmd.append('-R')
            proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
            try:
                for _ in range(150):
                    if proc.poll() is not None: raise RuntimeError('FPM exited early; see '+str(logpath))
                    if sockfile.exists(): break
                    time.sleep(0.1)
                else: raise RuntimeError('FPM socket did not appear')
                payload=b'ordinary-upload-php56\n'
                body=(b'--php56check\r\nContent-Disposition: form-data; name="PHP_SESSION_UPLOAD_PROGRESS"\r\n\r\nprobe\r\n'
                      b'--php56check\r\nContent-Disposition: form-data; name="file"; filename="safe.txt"\r\n'
                      b'Content-Type: text/plain\r\n\r\n'+payload+b'\r\n--php56check--\r\n')
                replies=[request(sockfile,script,body) for _ in range(2)]
                for i,r in enumerate(replies,1):
                    assert len(r)==6 and r[1:]==['safe.txt','0',hashlib.md5(payload).hexdigest(),str(i),'0'],r
                assert replies[0][0]==replies[1][0], 'Requests did not reuse one worker'
                log.write('\nPASS: two normal multipart uploads; same FPM worker; session counter 1/2.\n')
                log.write('Upload progress remains absent; this is not a CVE exploit regression.\n')
            finally:
                proc.terminate()
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('binary')
    p.add_argument('output')
    a=p.parse_args()
    smoke(a.binary,a.output)
    print('FPM smoke PASS')
