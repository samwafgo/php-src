#!/usr/bin/env python3
"""One allowlisted inventory for the workflow and local Docker driver."""
import argparse
import json

TARGETS = {}
for distro, image in [
    ('ubuntu20.04', 'ubuntu:20.04'), ('ubuntu22.04', 'ubuntu:22.04'),
    ('ubuntu24.04', 'ubuntu:24.04'), ('debian11', 'debian:11'),
    ('debian12', 'debian:12'), ('almalinux8', 'almalinux:8'),
    ('almalinux9', 'almalinux:9'),
]:
    for arch, platform, runner in [
        ('x86_64', 'linux/amd64', 'ubuntu-24.04'),
        ('aarch64', 'linux/arm64', 'ubuntu-24.04-arm'),
    ]:
        key = distro + '-' + arch
        TARGETS[key] = dict(target=key, image=image, arch=arch,
                            platform=platform, runner=runner)
TARGETS['centos7-x86_64'] = dict(target='centos7-x86_64', image='centos:7.9.2009',
                               arch='x86_64', platform='linux/amd64', runner='ubuntu-24.04')

def select(scope):
    if scope == 'all':
        return list(TARGETS.values())
    if scope == 'smoke':
        return [TARGETS[k] for k in ('ubuntu20.04-x86_64', 'ubuntu24.04-x86_64',
                                    'debian12-x86_64', 'almalinux9-x86_64')]
    return [TARGETS[scope]]

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('scope', choices=['all', 'smoke'] + list(TARGETS))
    p.add_argument('--field', choices=['image', 'arch', 'platform', 'runner'])
    a = p.parse_args()
    rows = select(a.scope)
    if a.field:
        if len(rows) != 1:
            p.error('--field requires a single target')
        print(rows[0][a.field])
    else:
        print(json.dumps({'include': rows}, separators=(',', ':')))
