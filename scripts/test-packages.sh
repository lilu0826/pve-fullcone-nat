#!/bin/bash
# Boot the actual generated PVE image/modules in an isolated QEMU guest.
set -euo pipefail
project=$(cd "$(dirname "$0")/.." && pwd)
build_root=${1:?usage: test-packages.sh BUILD_ROOT}
release=7.0.14-23-fullcone-pve
rootfs="$build_root/package-rootfs"
mapfile -t images < <(find "$project/artifacts" -maxdepth 1 -name "proxmox-kernel-${release}_*_amd64.deb")
test "${#images[@]}" -eq 1
test "$(dpkg-deb -f "${images[0]}" Package)" = "proxmox-kernel-$release"
debootstrap --variant=minbase \
  --include=iproute2,nftables,python3,conntrack,procps,iputils-ping,busybox,kmod,initramfs-tools \
  trixie "$rootfs" https://deb.debian.org/debian
# Extract only into the disposable rootfs; never install on the runner host.
dpkg-deb -x "${images[0]}" "$rootfs"
mkdir -p "$rootfs/opt/fullcone"
cp "$project"/tests/* "$rootfs/opt/fullcone/"
chmod +x "$rootfs/opt/fullcone/init.sh"
printf 'virtio_pci\nvirtio_blk\next4\n' >> "$rootfs/etc/initramfs-tools/modules"
mount -t proc proc "$rootfs/proc"
mount -t sysfs sysfs "$rootfs/sys"
trap 'umount "$rootfs/sys" 2>/dev/null || true; umount "$rootfs/proc" 2>/dev/null || true' EXIT
chroot "$rootfs" depmod "$release"
chroot "$rootfs" update-initramfs -c -k "$release"
umount "$rootfs/sys"
umount "$rootfs/proc"
trap - EXIT
truncate -s 4G "$build_root/package-root.img"
mkfs.ext4 -q -F -d "$rootfs" "$build_root/package-root.img"
acceleration=(-accel tcg -cpu max)
if [ -r /dev/kvm ]; then
  acceleration=(-accel kvm -cpu host)
fi
timeout 600 qemu-system-x86_64 "${acceleration[@]}" -m 3072 -smp 4 \
  -nographic -no-reboot -nic none \
  -kernel "$rootfs/boot/vmlinuz-$release" \
  -initrd "$rootfs/boot/initrd.img-$release" \
  -drive "file=$build_root/package-root.img,format=raw,if=virtio,snapshot=on" \
  -append 'root=/dev/vda rw console=ttyS0 init=/opt/fullcone/init.sh fullcone_mode=enabled panic=-1 oops=panic' \
  2>&1 | tee "$project/artifacts/qemu-package.log"
grep -q 'FULLCONE_TEST_PASS enabled' "$project/artifacts/qemu-package.log"
if grep -E 'BUG:|WARNING:|possible circular locking|KASAN:|kernel panic|Kernel panic' "$project/artifacts/qemu-package.log"; then
  echo 'Kernel diagnostic failure' >&2
  exit 1
fi

