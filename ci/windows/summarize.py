#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

root=Path(sys.argv[1])
lines=['### Windows PHP 5.6.40-sec1 core candidates','',
       '| Configuration | Actual result |','|---|---|']
for key in ['x86-nts','x86-ts','x64-nts','x64-ts']:
    file=root/key/'evidence/status.json'
    result=json.loads(file.read_text(encoding='utf-8-sig'))['status'] if file.exists() else 'NOT RUN'
    lines.append('| '+key+' | '+result+' |')
lines+=['','PASS means version/PE/threading/session/normal CGI upload checks passed. '
        'Full PHPT, IIS/Apache integration and CVE exploit validation were not performed.']
report='\n'.join(lines)+'\n'
print(report)
if os.environ.get('GITHUB_STEP_SUMMARY'):
    with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as f:f.write(report)
