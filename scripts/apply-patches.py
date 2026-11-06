#!/usr/bin/env python3
"""Apply locked patches to an already PVE-patched, otherwise pristine kernel."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    args = parser.parse_args()
    kernel = args.kernel.resolve()
    lock = json.loads((ROOT / 'patches/manifest.json').read_text())
    for path, expected in lock['pve_baseline_files'].items():
        actual = hashlib.sha256((kernel / path).read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f'Unexpected prepared PVE source: {path}; refusing to patch')
    for item in lock['patches']:
        patch = ROOT / 'patches' / item['file']
        data = patch.read_bytes()
        if hashlib.sha256(data).hexdigest() != item['sha256']:
            raise SystemExit(f'Patch digest mismatch: {patch.name}')
        for dry_run in (True, False):
            command = ['patch', '--batch', '--forward', '--fuzz=0', '-p1']
            if dry_run:
                command.append('--dry-run')
            print(f'{patch.name}: {"check" if dry_run else "apply"}', flush=True)
            subprocess.run(command, cwd=kernel, input=data, check=True)
    for path, expected in lock['result_files'].items():
        if hashlib.sha256((kernel / path).read_bytes()).hexdigest() != expected:
            raise SystemExit(f'Patched result mismatch: {path}')
    print('All patches applied and final source hashes verified. No compilation performed.')


if __name__ == '__main__':
    main()

