#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates git build-essential gcc-14 g++-14 make patch perl \
  asciidoc-base automake bc bindgen bison cpio debhelper dh-python dwarves \
  file flex gawk kmod libdw-dev libelf-dev libiberty-dev libnuma-dev \
  libslang2-dev libssl-dev libtool lintian lz4 python3-dev python3-minimal \
  rsync rustc rust-src rustfmt rust-clippy sphinx-common xmlto zlib1g-dev zstd \
  debootstrap qemu-system-x86 e2fsprogs busybox-static iproute2 nftables \
  python3 conntrack procps iputils-ping xz-utils

