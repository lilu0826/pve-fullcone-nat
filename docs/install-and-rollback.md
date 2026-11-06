# 安装与回滚

这些步骤供后续在维护窗口人工执行；Actions 不连接、安装或重启 PVE 主机。**只有对应提交的完整 workflow 成功、生成实际包，并核对测试报告后才能使用其安装包。** 取消或失败运行中的工件仅供诊断。

## 选择和核对产物

从成功运行的 `pve-fullcone-packages-<commit>` 下载工件；`network-validation-*` 是测试记录，不是安装包。阅读 `build-info.txt`、`build.log`、`qemu-package.log` 和配置文件，检查 SHA256SUMS：

```bash
sha256sum -c SHA256SUMS
dpkg-deb -f ./proxmox-kernel-7.0.14-23-fullcone-pve_*_amd64.deb Package Version Architecture
dpkg-deb -f ./proxmox-headers-7.0.14-23-fullcone-pve_*_amd64.deb Package Version Architecture
```

预期 release 为 `7.0.14-23-fullcone-pve`，amd64，包版本 `7.0.14-23+fullcone1`。实际文件名必须来自打包产物。kernel 包已包含模块和 ZFS，不另造 `linux-modules` 包。不要批量安装所有 `.deb`：系列元包、tools、签名模板不属于这次试启动所需的 image/headers 对。

自编译包没有 Proxmox 官方 UEFI 签名。现有宿主机安装的是官方 signed 包，但这不能证明 Secure Boot 是否开启。用 `mokutil --sb-state` 核对；若开启，需要先完成自己的受信任签名流程，不能把文件改名为 signed 包来代替。模块签名与 UEFI 内核签名是两回事。

## 保留原内核并并存安装

在 **PVE 节点 com 的 Shell** 执行，不在 OpenWrt 容器执行。先确认有可用的控制台、旧内核和空间，记录 `proxmox-boot-tool status`、`proxmox-boot-tool kernel list`、`dkms status`。

```bash
test -f /boot/vmlinuz-7.0.14-23-pve
apt-mark manual proxmox-kernel-7.0.14-23-pve-signed
proxmox-boot-tool kernel pin 7.0.14-23-pve
```

只安装完整匹配的一对 image/headers，安装过程会生成 initramfs 和启动菜单，不会由本项目自动重启：

```bash
apt install ./proxmox-kernel-7.0.14-23-fullcone-pve_*_amd64.deb \
            ./proxmox-headers-7.0.14-23-fullcone-pve_*_amd64.deb
test -f /boot/vmlinuz-7.0.14-23-fullcone-pve
test -f /boot/initrd.img-7.0.14-23-fullcone-pve
modinfo -k 7.0.14-23-fullcone-pve -F vermagic nf_conntrack
modinfo -k 7.0.14-23-fullcone-pve -F vermagic nf_nat
dkms status
```

若 DKMS、initramfs 或 ESP 同步失败，不应继续试启动。不要覆盖当前内核的 `.ko`，不要删除旧内核，不要运行 autoremove。

准备好维护窗口后设置一次试启动，再人工重启：

```bash
proxmox-boot-tool kernel pin 7.0.14-23-fullcone-pve --next-boot
proxmox-boot-tool refresh
```

pin/next-boot 命令参照 [Proxmox 官方启动文档](https://github.com/proxmox/pve-docs/blob/master/system-booting.adoc)，并对照了官方 `proxmox-kernel-helper` 提交 `3b801dcd7bcc2b61f86f19b3b94679e26a07df7b`。`--next-boot` 依赖启动后的清理机制，**不保证早期启动失败时自动恢复**；必要时通过控制台在启动菜单选择旧内核。

启动后检查 `uname -r`、`dmesg`、ZFS、存储、VM/LXC 和网络，再执行 task.md 的真实外网 TCP/UDP 验收。保留原 nft 规则；如果 FORWARD 拒绝 WAN NEW，自动 DNAT 后仍会被拒绝，这是预期行为。

## 回滚

若新内核无法正常启动，从控制台选择 `7.0.14-23-pve`。若已经正常进入系统但测试失败，取消一次试启动设置并重新固定旧内核：

```bash
proxmox-boot-tool kernel unpin --next-boot
proxmox-boot-tool kernel pin 7.0.14-23-pve
proxmox-boot-tool refresh
```

在维护窗口人工重启并核对 `uname -r`。回滚无需卸载新包；先保持两套内核和日志，避免误删当前运行模块。不要在新内核仍运行时删除它的 image/headers。

当前文档是交付流程，不能替代宿主机实测；运行结果见 validation-status.md。
