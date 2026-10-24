#!/usr/bin/env python3
import platform
from pathlib import Path
import shlex
import sys

def verify(target):
    distro,arch=target.rsplit('-',1)
    expected={
        'ubuntu20.04':('ubuntu','20.04'), 'ubuntu22.04':('ubuntu','22.04'),
        'ubuntu24.04':('ubuntu','24.04'), 'debian11':('debian','11'),
        'debian12':('debian','12'), 'almalinux8':('almalinux','8'),
        'almalinux9':('almalinux','9'), 'centos7':('centos','7'),
    }[distro]
    info={}
    for line in Path('/etc/os-release').read_text().splitlines():
        if '=' in line:
            k,v=line.split('=',1)
            info[k]=' '.join(shlex.split(v))
    version=info.get('VERSION_ID','')
    if info.get('ID')!=expected[0] or not (version==expected[1] or version.startswith(expected[1]+'.')):
        raise SystemExit('Wrong distro for '+target+': '+str(info))
    if platform.machine()!=arch:
        raise SystemExit('Wrong CPU for '+target+': '+platform.machine())

if __name__=='__main__': verify(sys.argv[1])
