#!/usr/bin/env python3
"""Verify cached source identity only; this is NOT a kernel validation test."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def git(repo, *args):
    return subprocess.check_output(
        ['git', '-C', str(repo), *args], stderr=subprocess.PIPE
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--research-dir', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    cache = args.research_dir or root / '.research'
    lock = json.loads((root / 'sources.lock.json').read_text(encoding='utf-8'))
    checks = []
    for name in ('pve', 'kernel', 'openwrt_reference'):
        entry = lock[name]
        repo = cache / entry['cache_directory']
        commit = entry['commit']
        actual = git(repo, 'rev-parse', 'HEAD').decode().strip()
        if actual != commit:
            raise ValueError(f'{name}: HEAD differs from locked commit')
        paths = [item['path'] for item in entry['files']]
        git(repo, 'diff', '--exit-code', 'HEAD', '--', *paths)
        for item in entry['files']:
            data = git(repo, 'show', f"{commit}:{item['path']}")
            digest = hashlib.sha256(data).hexdigest()
            if digest != item['sha256']:
                raise ValueError(f"{name}: SHA-256 mismatch: {item['path']}")
        checks.append(f'{name}: commit, {len(paths)} locked Git blobs and their working files verified')
    pve = cache / lock['pve']['cache_directory']
    for path, commit in lock['pve']['submodules'].items():
        tree = git(pve, 'ls-tree', lock['pve']['commit'], path).decode().split()
        if tree[:3] != ['160000', 'commit', commit]:
            raise ValueError(f'PVE submodule gitlink mismatch: {path}')
        checks.append(f'{path}: gitlink verified (not a complete submodule audit)')
    sonic = lock['sonic_reference']
    data = (cache / sonic['cache_file']).read_bytes()
    if hashlib.sha256(data).hexdigest() != sonic['sha256']:
        raise ValueError('SONiC cached file SHA-256 mismatch')
    checks.append('SONiC cached patch SHA-256 verified')
    print(json.dumps({
        'reference_integrity': 'pass',
        'checks': checks,
        'project_kernel_patch': 'see patches/manifest.json',
        'reference_patch_probe': 'see docs/research-checks.log',
        'kernel_build': 'not assessed by this reference-only check; see docs/validation-status.md',
        'fullcone_functional_tests': 'not assessed by this reference-only check; see docs/validation-status.md',
    }, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f'Reference verification failed: {exc}', file=sys.stderr)
        sys.exit(1)
