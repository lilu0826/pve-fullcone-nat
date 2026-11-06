# 宿主机基线

记录日期：2026-11-06，Asia/Shanghai。信息来自用户在 PVE 节点 `com` 的 Shell 中提供的输出，并非本工具通过 SSH 现场采集。

| 项目 | 用户提供的值 |
| --- | --- |
| 内核 release | `7.0.14-23-pve` |
| proxmox-ve | `9.2.0` |
| pve-manager | `9.2.21/4f6e0ac86f9e8c7f` |
| 内核系列包 | `proxmox-kernel-7.0: 7.0.14-23` |
| 已安装内核包 | `proxmox-kernel-7.0.14-23-pve-signed: 7.0.14-23` |
| MODVERSIONS | `CONFIG_MODVERSIONS=y` |
| nf_conntrack vermagic | `7.0.14-23-pve SMP preempt mod_unload modversions` |
| 编译器 | GCC Debian `14.2.0-19`，14.2.0 |
| 链接器 | GNU Binutils for Debian 2.44 |
| 编译版本时间 | `PMX 7.0.14-23 (2026-10-07T20:25Z)` |
| zfsutils-linux | `2.4.4-pve1` |

最初在 `openwrt24` 内执行命令时，内核版本相同，但没有 `pveversion`、`/boot/config-*` 和完整的 `modinfo`。这与共享宿主机内核的容器相符，尚未通过 PVE 容器配置确认。不能把该环境的缺失项解释为宿主机缺失。

尚未取得完整 `/boot/config-7.0.14-23-pve`、实际启动方式、Secure Boot 状态、完整模块校验、DKMS 清单，以及本地内核修改情况。已安装官方版本包不等于已经证明所有运行文件未经修改。

也尚未确认 MASQUERADE 实际位于 PVE 主命名空间还是 OpenWrt 容器命名空间。实现必须按 network namespace、conntrack zone 隔离映射，不能按宿主机全局公网端口查找。
