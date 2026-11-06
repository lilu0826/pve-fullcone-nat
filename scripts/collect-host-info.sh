#!/bin/sh
# Read-only collection. Run in the PVE node Shell, not inside an OpenWrt guest.
set -eu

if ! command -v pveversion >/dev/null 2>&1; then
    printf '%s\n' 'ERROR: run this in the PVE node Shell; pveversion is unavailable.' >&2
    exit 1
fi

release=$(uname -r)
printf '\n== UTC collection time ==\n'
date -u '+%Y-%m-%dT%H:%M:%SZ'
printf '\n== Kernel and PVE packages ==\n'
uname -a
pveversion -v
cat /proc/version
printf '\n== Module ABI ==\n'
for module in nf_conntrack nf_nat nft_masq; do
    printf '\n[%s]\n' "$module"
    if modinfo "$module" >/dev/null 2>&1; then
        modinfo -F filename "$module"
        modinfo -F vermagic "$module"
        modinfo -F signer "$module"
    else
        printf '%s\n' 'Module metadata unavailable (not proof that it is disabled).'
    fi
done
printf '\n== Complete running-release config ==\n'
if [ -r "/boot/config-$release" ]; then
    sha256sum "/boot/config-$release"
    cat "/boot/config-$release"
else
    printf '%s\n' 'ERROR: running-release configuration unavailable.' >&2
    exit 1
fi
printf '\n== Boot information ==\n'
if command -v proxmox-boot-tool >/dev/null 2>&1; then
    proxmox-boot-tool status || printf '%s\n' 'Boot status query failed.'
fi
if command -v mokutil >/dev/null 2>&1; then
    mokutil --sb-state || printf '%s\n' 'Secure Boot status unavailable.'
fi
printf '\n== DKMS ==\n'
if command -v dkms >/dev/null 2>&1; then
    dkms status
else
    printf '%s\n' 'dkms command unavailable.'
fi
