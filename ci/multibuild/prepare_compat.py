#!/usr/bin/env python3
"""Apply the narrowly scoped upstream AArch64 asm constraint correction.

Only the temporary build tree changes; the original CVE patch stays intact.
Reference: https://github.com/php/php-src/blob/master/Zend/zend_multiply.h
"""
import argparse
import hashlib
import json
from pathlib import Path

UPSTREAM='https://github.com/php/php-src/blob/master/Zend/zend_multiply.h'
def prepare(source, arch, output):
    file=source/'Zend/zend_multiply.h'
    before=file.read_bytes()
    result=dict(architecture=arch,upstream_reference=UPSTREAM,changed=False,
                file='Zend/zend_multiply.h',before_sha256=hashlib.sha256(before).hexdigest())
    if arch=='aarch64':
        text=before.decode()
        start=text.index('#elif defined(__aarch64__) && defined(__GNUC__)')
        end=text.index('\n#elif ',start+1)
        original=text[start:end]
        old_outputs=': "=X"(__tmpvar), "=X"(usedval)'
        new_outputs=': "=&r"(__tmpvar), "=&r"(usedval)'
        old_inputs=': "X"(a), "X"(b)'
        new_inputs=': "r"(a), "r"(b)'
        if old_outputs in original and old_inputs in original:
            patched=original.replace(old_outputs,new_outputs).replace(old_inputs,new_inputs)
            file.write_text(text[:start]+patched+text[end:])
            result['changed']=True
        elif new_outputs not in original or new_inputs not in original:
            raise ValueError('Unrecognized AArch64 multiply constraints; refusing to patch')
        result['correction']='general registers r with early-clobber outputs =&r'
    elif arch!='x86_64':
        raise ValueError('Unsupported architecture: '+arch)
    result['after_sha256']=hashlib.sha256(file.read_bytes()).hexdigest()
    output.write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('source',type=Path)
    p.add_argument('arch',choices=['aarch64','x86_64'])
    p.add_argument('output',type=Path)
    a=p.parse_args()
    prepare(a.source,a.arch,a.output)
