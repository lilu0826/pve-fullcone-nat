#!/usr/bin/env python3
"""Require the guest result and reject kernel diagnostics, with one named platform notice."""
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
mode = sys.argv[2]
lines = path.read_text(errors='replace').splitlines()
if not any(line.strip() == f'FULLCONE_TEST_PASS {mode}' for line in lines):
    raise SystemExit(f'Missing successful guest completion: {path}')

# This is the virtual CPU/host mitigation notice, not a WARN_ON stack trace.
# Keep it in the full log and list it explicitly; all other warnings still fail.
platform_notice = ('Speculative Return Stack Overflow: WARNING: See '
                   'https://kernel.org/doc/html/latest/admin-guide/hw-vuln/srso.html '
                   'for mitigation options.')
diagnostic = re.compile(r'BUG:|WARNING:|possible circular locking|KASAN:|[Kk]ernel panic')
failures = []
for line in lines:
    if diagnostic.search(line):
        if line.endswith(platform_notice):
            print('Recorded platform notice: ' + line)
        else:
            failures.append(line)
if failures:
    raise SystemExit('Kernel diagnostic failure:\n' + '\n'.join(failures))
print(f'Guest completion and kernel diagnostics verified: {path.name} ({mode})')
