#!/bin/bash
set -euo pipefail
project=$(cd "$(dirname "$0")/.." && pwd)
build_root=${1:?usage: ci-network-tests.sh BUILD_ROOT}
mkdir -p "$project/artifacts" "$build_root"
export CC=gcc-14 HOSTCC=gcc-14
python3 "$project/scripts/prepare-source.py" "$build_root/pve"
kernel="$build_root/pve/proxmox-kernel-7.0.14/ubuntu-kernel"
perl "$kernel/scripts/checkpatch.pl" --no-tree --no-signoff --terse \
  "$project/patches/0003-pve-native-fullcone.patch" \
  2>&1 | tee "$project/artifacts/checkpatch.log"
cp "$kernel/.config" "$project/artifacts/pve-config-before-smoke"
# The smoke image uses the exact PVE-patched source, with a smaller VM config.
# The separate package job retains and builds the full PVE configuration.
make -C "$kernel" x86_64_defconfig
"$kernel/scripts/config" --file "$kernel/.config" \
  -d MODULES -d DRM -d SOUND -d MEDIA_SUPPORT -d WIRELESS -d WLAN -d BT \
  -d USB_SUPPORT -d INFINIBAND -d DEBUG_INFO_DWARF_TOOLCHAIN_DEFAULT \
  -d LOCALVERSION_AUTO --set-str LOCALVERSION '-fullcone-test' \
  -e NET -e INET -e IPV6 -e NETFILTER -e NETFILTER_ADVANCED \
  -e NF_CONNTRACK -e NF_CONNTRACK_MARK -e NF_CONNTRACK_ZONES -e NF_CT_NETLINK \
  -e NF_NAT -e NF_NAT_MASQUERADE -e NF_NAT_REDIRECT -e NF_SOCKET_IPV4 \
  -e NF_TABLES -e NF_TABLES_INET -e NF_TABLES_IPV4 -e NF_TABLES_IPV6 \
  -e NFT_CT -e NFT_NAT -e NFT_MASQ -e NFT_REDIR -e NFT_COUNTER \
  -e NET_NS -e VETH -e BRIDGE -e UNIX -e PACKET -e PROC_FS -e SYSFS \
  -e TMPFS -e EXT4_FS -e VIRTIO_BLK -e VIRTIO_PCI -e VIRTIO_NET \
  -e DEVTMPFS -e DEVTMPFS_MOUNT -e BLK_DEV_INITRD \
  -e SERIAL_8250 -e SERIAL_8250_CONSOLE -e IKCONFIG -e IKCONFIG_PROC \
  -e DEBUG_KERNEL -e PROVE_LOCKING -e DEBUG_LOCK_ALLOC -e DEBUG_SPINLOCK
rootfs="$build_root/rootfs"
debootstrap --variant=minbase \
  --include=iproute2,nftables,python3,conntrack,procps,iputils-ping,busybox,kmod \
  trixie "$rootfs" https://deb.debian.org/debian
mkdir -p "$rootfs/opt/fullcone"
cp "$project"/tests/* "$rootfs/opt/fullcone/"
chmod +x "$rootfs/opt/fullcone/init.sh"
truncate -s 2G "$build_root/root.img"
mkfs.ext4 -q -F -d "$rootfs" "$build_root/root.img"
acceleration=(-accel tcg -cpu max)
if [ -r /dev/kvm ]; then
  acceleration=(-accel kvm -cpu host)
fi
for mode in enabled disabled; do
  if [ "$mode" = enabled ]; then
    "$kernel/scripts/config" --file "$kernel/.config" -e NF_NAT_FULLCONE_MASQUERADE
  else
    "$kernel/scripts/config" --file "$kernel/.config" -d NF_NAT_FULLCONE_MASQUERADE
  fi
  make -C "$kernel" olddefconfig
  for option in NF_NAT NFT_MASQ NFT_NAT NET_NS VETH BRIDGE EXT4_FS VIRTIO_BLK; do
    grep -qx "CONFIG_$option=y" "$kernel/.config"
  done
  if [ "$mode" = enabled ]; then
    grep -qx CONFIG_NF_NAT_FULLCONE_MASQUERADE=y "$kernel/.config"
  else
    grep -qx '# CONFIG_NF_NAT_FULLCONE_MASQUERADE is not set' "$kernel/.config"
  fi
  cp "$kernel/.config" "$project/artifacts/test-config-$mode"
  make -C "$kernel" -j"$(nproc)" bzImage 2>&1 | tee "$project/artifacts/compile-$mode.log"
  timeout 300 qemu-system-x86_64 "${acceleration[@]}" -m 2048 -smp 4 \
    -nographic -no-reboot -nic none \
    -kernel "$kernel/arch/x86/boot/bzImage" \
    -drive "file=$build_root/root.img,format=raw,if=virtio,snapshot=on" \
    -append "root=/dev/vda rw console=ttyS0 init=/opt/fullcone/init.sh fullcone_mode=$mode panic=-1 oops=panic" \
    2>&1 | tee "$project/artifacts/qemu-$mode.log"
  grep -q "FULLCONE_TEST_PASS $mode" "$project/artifacts/qemu-$mode.log"
  if grep -E 'BUG:|WARNING:|possible circular locking|KASAN:|kernel panic|Kernel panic' "$project/artifacts/qemu-$mode.log"; then
    echo 'Kernel diagnostic failure' >&2
    exit 1
  fi
done
