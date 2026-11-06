#!/bin/bash
set -euo pipefail
project=$(cd "$(dirname "$0")/.." && pwd)
build_root=${1:?usage: build-kernel.sh BUILD_ROOT}
mkdir -p "$project/artifacts"
exec > >(tee "$project/artifacts/build.log") 2>&1
export CC=gcc-14 HOSTCC=gcc-14
python3 "$project/scripts/prepare-source.py" "$build_root/pve"
pve="$build_root/pve"
kernel="$pve/proxmox-kernel-7.0.14/ubuntu-kernel"
{
  date -u '+build-start=%Y-%m-%dT%H:%M:%SZ'
  printf 'project-commit=%s\n' "$(git -C "$project" rev-parse HEAD)"
  printf 'pve-commit=%s\n' "$(git -C "$pve" rev-parse HEAD)"
  git -C "$pve" submodule status --recursive
  gcc-14 --version
  ld --version
  dpkg-query -W
} > "$project/artifacts/build-info.txt"
cp "$project/sources.lock.json" "$project/artifacts/"
cp -a "$project/patches" "$project/artifacts/patches"
# olddefconfig uses the PVE-generated Ubuntu annotations and PVE option list.
make -C "$pve" KREL_EXTRA=-fullcone PKG_REV_EXTRA=+fullcone1 deb
test "$(make -s -C "$kernel" kernelrelease)" = 7.0.14-23-fullcone-pve
grep -qx CONFIG_NF_NAT_FULLCONE_MASQUERADE=y "$kernel/.config"
grep -qx CONFIG_MODVERSIONS=y "$kernel/.config"
cp "$kernel/.config" "$project/artifacts/config-7.0.14-23-fullcone-pve"
cp "$kernel/Module.symvers" "$project/artifacts/"
find "$pve" -maxdepth 1 -type f \( -name '*.deb' -o -name '*.buildinfo' -o -name '*.changes' \) \
  -exec cp -t "$project/artifacts/" {} +
find "$pve/proxmox-kernel-7.0.14" -maxdepth 1 -name 'abi-*' -type f \
  -exec cp -t "$project/artifacts/" {} +
for package in "$project"/artifacts/*.deb; do
  dpkg-deb -f "$package" Package Version Architecture >> "$project/artifacts/build-info.txt"
done
date -u '+build-end=%Y-%m-%dT%H:%M:%SZ' >> "$project/artifacts/build-info.txt"
(cd "$project/artifacts" && sha256sum *.deb > SHA256SUMS)

