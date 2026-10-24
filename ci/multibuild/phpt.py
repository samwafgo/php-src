#!/usr/bin/env python3
"""Validate legacy PHP counters without confusing FAIL with XFAIL."""
import argparse
import json
from pathlib import Path
import re

RELEASE_XPASS = 'ext/session/tests/bug69111.phpt'
XPASS_REASON = 'XFAIL section but test passes'

def check(log, exit_code, allowlist, profile='debug-test'):
    names = {'total':'Number of tests', 'pass':'Tests passed', 'skip':'Tests skipped',
             'fail':'Tests failed', 'xfail':'Expected fail', 'warn':'Tests warned'}
    counts = {}
    for key, label in names.items():
        matches = re.findall(r'^' + re.escape(label) + r'\s*:\s*(\d+)\b', log, re.M)
        if len(matches) != 1:
            raise ValueError('Missing/duplicate counter: ' + label)
        counts[key] = int(matches[0])
    if counts['total'] < 1000 or sum(v for k,v in counts.items() if k != 'total') != counts['total']:
        raise ValueError('Zero, too few or inconsistent test counts')
    if not re.search(r'^Time taken\s*:', log, re.M):
        raise ValueError('Missing completed timing summary')
    m = re.search(r'(?ms)^FAILED TEST SUMMARY\s*\n-+\n(.*?)(?=^={10,}|\Z)', log)
    actual = re.findall(r'\[((?:Zend|ext|tests)/[^]\r\n]+\.phpt)\]', m[1] if m else '')
    if len(actual) != counts['fail'] or len(set(actual)) != len(actual):
        raise ValueError('Failure list/count mismatch')
    unexpected = sorted(set(actual) - allowlist)
    if unexpected:
        raise ValueError('Unexpected failures: ' + ', '.join(unexpected))
    if re.search(r'^(?:BORKED|LEAKED) TEST SUMMARY\s*$', log, re.M):
        raise ValueError('PHPT borked or leaked tests')
    for label in ('Tests borked', 'Tests leaked'):
        if re.search(r'^' + label + r'\s*:\s*[1-9][0-9]*\b', log, re.M):
            raise ValueError('PHPT ' + label)
    warning_section = re.search(r'(?ms)^WARNED TEST SUMMARY\s*\n-+\n(.*?)(?=^={10,}|\Z)', log)
    lines = [s.strip() for s in warning_section[1].splitlines() if s.strip()] if warning_section else []
    warnings = []
    for line in lines:
        entry = re.fullmatch(r'.+ \[((?:Zend|ext|tests)/[^]\r\n]+\.phpt)\] \(warn: ([^\r\n]+)\)', line)
        if not entry:
            raise ValueError('Unrecognized PHPT warning: ' + line)
        warnings.append(dict(test=entry[1], reason=entry[2]))
    if len(warnings) != counts['warn']:
        raise ValueError('Warning list/count mismatch')
    # PHP 5.6 marks this leak-related XFAIL as WARN when a non-Debug build
    # matches EXPECTF. Preserve WARN in the results; never relabel it PASS/XFAIL.
    if warnings and not (profile == 'web-release' and warnings == [dict(test=RELEASE_XPASS, reason=XPASS_REASON)]):
        raise ValueError('Unexpected PHPT warnings: ' + str(warnings))
    if exit_code not in (0,1) or (exit_code != 0 and not actual):
        raise ValueError('Abnormal runner exit: ' + str(exit_code))
    return dict(counts=counts, exit_code=exit_code, actual_failures=sorted(actual),
                profile=profile, known_release_warnings=warnings,
                allowlisted_now_passing=sorted(allowlist-set(actual)),
                cve_security_validation='not performed')

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('output', type=Path)
    p.add_argument('allowlist', type=Path)
    p.add_argument('--profile', choices=['web-release', 'debug-test'], default='debug-test')
    a = p.parse_args()
    allow = {s.strip().strip('[]') for s in a.allowlist.read_text().splitlines()
             if s.strip() and not s.lstrip().startswith('#')}
    try:
        result = check((a.output/'tests.log').read_text(errors='replace'),
                       int((a.output/'test-exit-code.txt').read_text()), allow, a.profile)
    except (ValueError, OSError) as e:
        raise SystemExit('PHPT validation failed: ' + str(e))
    (a.output/'test-results.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
