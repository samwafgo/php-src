#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

p=argparse.ArgumentParser()
p.add_argument('output',type=Path)
p.add_argument('target')
p.add_argument('profile')
p.add_argument('source_commit')
p.add_argument('image_digest')
p.add_argument('patch',type=Path)
a=p.parse_args()
out=a.output.resolve()
name='php-5.6.40-sec1-'+a.target+'-'+a.profile+'-candidate'
package=out/'package'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def text(name): return (out/name).read_text().strip()
results=json.loads(text('test-results.json'))
manifest=dict(version='5.6.40-sec1',upstream_base='5.6.40',target=a.target,
    profile=a.profile,status='candidate',source_commit=a.source_commit,
    source_repository='https://github.com/samwafgo/php-src',
    patch_sha256=sha(a.patch),container_image_digest=a.image_digest,
    build_time_utc=datetime.now(timezone.utc).isoformat(),
    workflow_run=os.environ.get('GITHUB_SERVER_URL','https://github.com')+'/'+
        os.environ.get('GITHUB_REPOSITORY','samwafgo/php-src')+'/actions/runs/'+os.environ.get('GITHUB_RUN_ID','local'),
    os_release=text('os-release'),architecture=text('architecture.txt'),
    glibc=text('glibc.txt'),compiler=text('compiler.txt'),cflags=text('cflags.txt'),
    configure_args=text('configure-args.txt').splitlines(),modules=text('modules.txt').splitlines(),
    generated_parser_provenance=json.loads(text('parser-provenance.json')),
    build_compatibility_provenance=json.loads(text('compat-provenance.json')),
    phpt=results,fpm_smoke='PASS: normal multipart upload, one worker, two sessions requests',
    limitations=['session.upload_progress disabled in C, regardless of INI',
      'limited PHPT scope; allowlisted FAIL is separate from XFAIL',
      'CVE exploit regression and general production approval not performed',
      'web-release omits openssl, curl, gd, zip and third-party loaders',
      'not a drop-in replacement for an existing Baota PHP installation'],
    binaries={f:sha(package/f) for f in ['bin/php','bin/php-cgi','sbin/php-fpm']})
(package/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
(package/'README.txt').write_text('PHP 5.6.40-sec1 unofficial candidate\n'
    'Target: '+a.target+'; profile: '+a.profile+'\n'
    'Install prefix compiled in: /opt/samwaf/php56/5.6.40-sec1\n'
    'This package is staged, not installed. Existing services were not changed.\n'
    'Use bin/php -c /absolute/path/etc/php.ini to select your reviewed config.\n'
    'See MANIFEST.json for extensions, hashes, test failures and limitations.\n'
    'Do not copy into /www/server/php/56 or reuse existing binary extensions.\n')
evidence=package/'build-evidence'
evidence.mkdir(exist_ok=True)
import shutil
for file in ['test-results.json','fpm-smoke.log','version.txt','modules.txt','ldd.txt','configure-args.txt','parser-provenance.json','compat-provenance.json','multiply-smoke.txt']:
    shutil.copyfile(out/file,evidence/file)
dest=out/'binaries'
dest.mkdir(exist_ok=True)
archive=dest/(name+'.tar.gz')
with tarfile.open(str(archive),'w:gz') as t:
    t.add(str(package),arcname=name)
with tarfile.open(str(archive),'r:gz') as t:
    members={m.name for m in t.getmembers()}
    for binary in manifest['binaries']:
        if name+'/'+binary not in members: raise SystemExit('Missing archive entry '+binary)
    for m in t.getmembers():
        if m.isfile():
            with t.extractfile(m) as f:
                while f.read(1024*1024): pass
(dest/'SHA256SUMS').write_text(sha(archive)+'  '+archive.name+'\n')
shutil.copyfile(package/'MANIFEST.json',dest/'MANIFEST.json')
print(archive)
