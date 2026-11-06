#!/usr/bin/env python3
"""Fetch exact PVE gitlinks and let the PVE Makefile prepare its source tree."""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
LOCK = json.loads((ROOT / 'sources.lock.json').read_text())


def run(*args, cwd=None):
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=cwd, check=True)


def prepare(destination):
    destination = destination.resolve()
    if destination.exists():
        raise SystemExit(f'Refusing to overwrite existing source directory: {destination}')
    destination.mkdir(parents=True)
    run('git', 'init', destination)
    run('git', 'remote', 'add', 'origin', LOCK['pve']['repository'], cwd=destination)
    run('git', 'fetch', '--depth=1', 'origin', LOCK['pve']['commit'], cwd=destination)
    run('git', 'checkout', '--detach', LOCK['pve']['commit'], cwd=destination)
    run('git', 'submodule', 'init', cwd=destination)
    run('git', 'config', 'submodule.submodules/ubuntu-kernel.url', LOCK['kernel']['repository'], cwd=destination)
    run('git', 'config', 'submodule.submodules/zfsonlinux.url', 'https://git.proxmox.com/git/zfsonlinux.git', cwd=destination)
    run('git', 'submodule', 'update', '--init', '--recursive', '--depth=1', cwd=destination)
    for path, expected in LOCK['pve']['submodules'].items():
        actual = subprocess.check_output(['git', '-C', str(destination / path), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != expected:
            raise SystemExit(f'gitlink mismatch: {path}')
    # Use the packaging system's supported separate-release mechanism.
    changelog = destination / 'debian/changelog'
    original = changelog.read_text()
    changelog.write_text('proxmox-kernel-7.0 (7.0.14-23+fullcone1) trixie; urgency=medium\n\n'
                         '  * Native IPv4 MASQUERADE Full Cone NAT, experimental validation build.\n\n'
                         ' -- PVE Fullcone Build <build@localhost>  Fri, 06 Nov 2026 12:00:00 +0000\n\n' + original)
    run('make', 'KREL_EXTRA=-fullcone', 'PKG_REV_EXTRA=+fullcone1', 'build-dir-fresh', cwd=destination)
    kernel = destination / 'proxmox-kernel-7.0.14/ubuntu-kernel'
    run('python3', ROOT / 'scripts/apply-patches.py', kernel)
    return kernel


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(prepare(args.destination))

