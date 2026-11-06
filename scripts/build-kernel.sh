#!/bin/bash
set -euo pipefail
project=$(cd "$(dirname "$0")/.." && pwd)
build_root=${1:?usage: build-kernel.sh BUILD_ROOT}
mkdir -p "$project/artifacts"
exec > >(tee "$project/artifacts/build.log") 2>&1
export CC=gcc-14 HOSTCC=gcc-14
pve="$build_root/pve"
kernel="$pve/proxmox-kernel-7.0.14/ubuntu-kernel"
# Preserve completed outputs for diagnosis even if a later packaging check fails.
# The workflow result and package boot gate still determine whether they are usable.
preserve_outputs() {
  local status=$?
  trap - EXIT
  if [ "$status" -eq 0 ]; then
    printf 'build-script-exit=0\n' > "$project/artifacts/build-status.txt" || exit 1
    exit 0
  fi
  set +e
  if [ -d "$pve" ]; then
    find "$pve" -maxdepth 1 -type f \( -name '*.deb' -o -name '*.buildinfo' -o -name '*.changes' \) \
      -exec cp -t "$project/artifacts/" {} +
  fi
  if [ -f "$kernel/.config" ]; then
    cp "$kernel/.config" "$project/artifacts/config-7.0.14-23-fullcone-pve"
  fi
  if [ -f "$kernel/Module.symvers" ]; then
    cp "$kernel/Module.symvers" "$project/artifacts/"
  fi
  if compgen -G "$project/artifacts/*.deb" >/dev/null; then
    (cd "$project/artifacts" && sha256sum *.deb > SHA256SUMS)
  fi
  printf 'build-script-exit=%s\n' "$status" > "$project/artifacts/build-status.txt"
  exit "$status"
}
trap preserve_outputs EXIT
python3 "$project/scripts/prepare-source.py" "$pve"
{
  date -u '+build-start=%Y-%m-%dT%H:%M:%SZ'
  printf 'project-commit=%s\n' "$(git -c safe.directory="$project" -C "$project" rev-parse HEAD)"
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
bash "$project/scripts/test-packages.sh" "$build_root"

