#!/bin/bash
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev 2>/dev/null || true
mount -t tmpfs tmpfs /run
mkdir -p /run/netns /dev/pts
mount -t devpts devpts /dev/pts
touch /run/fullcone-test-vm
mode=disabled
case " $(cat /proc/cmdline) " in
  *' fullcone_mode=enabled '*) mode=enabled ;;
esac
uname -a
zcat /proc/config.gz | grep -E 'NF_NAT_FULLCONE|PROVE_LOCKING|MODVERSIONS'
python3 /opt/fullcone/network.py "$mode"
status=$?
echo '=== FINAL KERNEL LOG ==='
dmesg
if [ "$status" -eq 0 ]; then
  echo "FULLCONE_TEST_PASS $mode"
else
  echo "FULLCONE_TEST_FAIL $mode status=$status"
fi
sync
poweroff -f

