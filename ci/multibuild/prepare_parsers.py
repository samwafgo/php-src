#!/usr/bin/env python3
"""Reuse upstream release parser output only when both grammars are identical.

Bison 3.8 changes PHP 5.6 syntax-error diagnostics. No PHP grammar or runtime
patch is altered here. The upstream release already carries generated parsers.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

SHA256='1369a51eee3995d7fbd1c5342e5cc917760e276d561595b6052b21ace2656d1c'
URL='https://museum.php.net/php5/php-5.6.40.tar.xz'

def prepare(archive, source, output):
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=SHA256:
        raise ValueError('Official PHP 5.6.40 archive SHA256 mismatch')
    files={}
    with tarfile.open(str(archive),'r:xz') as tar:
        for stem in ('zend_language_parser','zend_ini_parser'):
            grammar='Zend/'+stem+'.y'
            expected=tar.extractfile('php-5.6.40/'+grammar).read()
            if (source/grammar).read_bytes()!=expected:
                raise ValueError('Grammar changed; cannot reuse release parser: '+grammar)
            for suffix in ('.c','.h'):
                rel='Zend/'+stem+suffix
                data=tar.extractfile('php-5.6.40/'+rel).read()
                (source/rel).write_bytes(data)
                files[rel]=hashlib.sha256(data).hexdigest()
    output.write_text(json.dumps(dict(source_url=URL,archive_sha256=SHA256,
        verified_identical_grammars=['Zend/zend_language_parser.y','Zend/zend_ini_parser.y'],
        generated_files=files),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('archive',type=Path)
    p.add_argument('source',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    prepare(a.archive,a.source,a.output)
