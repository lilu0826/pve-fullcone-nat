# 验证记录

最终复核：2026-11-07（Asia/Shanghai）；Actions 构建于 2026-11-06 UTC。[Actions 42227692753](https://github.com/lilu0826/pve-fullcone-nat/actions/runs/42227692753) **完整通过**，验证提交为 `47b140071d029a86ba15d6d75a54ec77ac27a8b0`。精简配置启用 17/17、关闭 13/13；实际 PVE 安装包内核再次启动并通过 17/17。下载工件、包校验和及元数据、源码/补丁记录、配置、模块 vermagic、guest 完成标记和逐项结果均已本地复核。

交付 release 为 `7.0.14-23-fullcone-pve`，8 个 Debian 包的版本均为 `7.0.14-23+fullcone1`。本轮完整 PVE 配置构建、打包目标中的 lintian 检查以及实际包启动复测均成功。没有向 PVE 节点部署；实机、独立公网和长期压力验收的边界见下文。

## 已核实的启动测试结果

| 检查 | 结果 |
| --- | --- |
| 固定 PVE 源码及完整 PVE 补丁应用 | 通过 |
| 三段式补丁哈希、零 fuzz 应用、结果哈希 | 通过 |
| 自有适配补丁 checkpatch | 通过，无输出 |
| Full Cone 启用配置 | 17/17，通过 |
| Full Cone 关闭配置 | 13/13，通过；第三方新入站应被阻止 |
| lockdep 配置和 guest 完成标记 | 已核对，两种配置均启动并完成 |
| 本轮内核日志 | 未发现检查范围内的 WARNING、BUG、锁依赖错误或 panic |
| 下载产物及两套测试镜像校验和 | 本地复核通过 |
| 完整 PVE 配置、内核、模块及 ZFS 构建 | 通过，使用锁定 PVE 打包目标 |
| Debian 包及打包检查 | 8 个包已生成，PVE 打包目标中的 lintian 检查通过 |
| 实际包内核启动及网络复测 | 17/17，通过；使用包内 vmlinuz、模块和生成的 initramfs |
| 实际包 ABI 配置及模块信息 | `MODVERSIONS=y`、完整 `Module.symvers`；模块 vermagic 为独立 release |
| 下载包及源码/补丁记录 | 8 个包的 SHA-256、元数据和工件中的源码/补丁文件复核通过 |

逐项结果见 [ci-network-results.json](ci-network-results.json)。网络测试工件为 [network-validation-47b1400](https://github.com/lilu0826/pve-fullcone-nat/actions/runs/42227692753/artifacts/13507137278)，ZIP SHA-256 为 `6c247e9cdf49d5a3b9c2fc3df78ccaaa4316e9626fbe5f1d35834efa7980b19c`。启用镜像复用了上一轮按源码、补丁、构建脚本、配置及镜像校验和检查的缓存；关闭镜像本轮编译。每次均实际启动并重跑测试，测试内核不作为 PVE 安装包使用。

## 完整包及下载证据

安装包工件：[pve-fullcone-packages-47b1400](https://github.com/lilu0826/pve-fullcone-nat/actions/runs/42227692753/artifacts/13521608636)，大小 156,554,482 字节，保留至 2026-11-20 16:42:16 UTC。ZIP SHA-256 为 `e1a1f47aac756788eb30e4e946e9de969e9bbbf1a7a463d348c0a5ef498e17cd`。完整包名、各包摘要、配置和 17 项包启动测试结果见 [ci-package-results.json](ci-package-results.json)。

试启动需要的配套包为：

- `proxmox-kernel-7.0.14-23-fullcone-pve_7.0.14-23+fullcone1_amd64.deb`
- `proxmox-headers-7.0.14-23-fullcone-pve_7.0.14-23+fullcone1_amd64.deb`

工件同时保存 `build.log`、`ci-package.log`、`build-info.txt`、`build-status.txt`、`qemu-package.log`、完整配置、`Module.symvers`、ABI 清单、`.buildinfo`、`.changes`、`SHA256SUMS` 和源码/补丁记录。`build-script-exit=0` 已复核；源码和补丁文件与仓库一致。实际启动模块的 vermagic 为 `7.0.14-23-fullcone-pve SMP preempt mod_unload modversions`。

构建日志保留了 linux-tools 的 perf 手册 groff 警告，以及测试 rootfs 缺少 zstd 时 initramfs 改用 gzip 的提示；两者未阻止打包和实际启动。内核日志中的已知 SRSO 平台提示按下述规则单独记录，不能将本报告理解为所有构建输出均无警告。

## 源码和实现检查

| 检查 | 结果 | 证据/范围 |
| --- | --- | --- |
| 宿主机版本 | 已核对用户输出 | `com`：PVE 9.2、`7.0.14-23-pve`、`CONFIG_MODVERSIONS=y`；见 [host-baseline.md](host-baseline.md) |
| 官方 PVE 打包版本 | 已固定 | `c1ca7892dbc5087d01c12ad260bbe03e77c1a296` |
| 内核子模块 | 已固定 | `874594fa24531e1ea15fa72709d20047e4a8d77c` |
| ZFS 子模块 | 已固定 | `dcd0e4345f4253bb9e44cc1ab54c6f73196421aa` |
| 984、987 参考补丁 | 已固定并移植 | 原文件和 Git blob 摘要见 `sources.lock.json`，交付补丁见 `patches/manifest.json` |
| 本地补丁链 | 通过 | 对固定 PVE 基线文件逐一验证 SHA-256，GNU patch 零 fuzz 应用，再核对结果摘要；不代表内核编译 |
| 修改范围和生命周期 | 已进行代码审阅 | 见 [design.md](design.md)；不把代码审阅等同于并发稳定性证明 |

三段式补丁不包含 985/986。仅 IPv4 TCP/UDP MASQUERADE 设置内核私有资格位；入站自动查找发生在所有显式 NAT lookup 之后，仍走标准 conntrack、NAT 和 FORWARD。没有用户态程序修改，也没有额外 PREROUTING Full Cone 规则。

## CI 证据规则

运行必须同时满足：补丁校验成功、编译成功、QEMU 启动成功、全部测试通过标记存在、内核日志没有检查范围内的 BUG/WARNING/lockdep/panic，才能记为通过。完整包作业还必须生成真实 Debian 包，并使用包内的 vmlinuz、模块和新生成的 initramfs 再启动复测。

早期运行 `42202195204` 的 network-tests 曾被 Actions 显示为成功，但下载日志发现实际编译失败，外层 `tee` 管道未传播失败退出码。**该运行不能证明任何功能通过。** 已在 `65616db` 中修复编译错误，并为工作流显式设置 `bash` 和 `set -euo pipefail`。取消、失败和误报成功运行的工件均只作诊断，不能安装。

运行 `42210585402` 曾完成完整内核、模块、ZFS 和 8 个 Debian 包的编译，但 lintian 因 changelog 中的 `build@localhost` 邮箱失败，该轮没有保留安装包。后续改用项目 GitHub noreply 地址，并增加保留失败产物且保持原退出码的处理；本轮完整打包及包启动复测已通过。

运行 `42204353520` 已真实完成启用配置的编译和启动，前七项功能用例通过，随后因有端口范围的测试规则缺少传输协议上下文而失败，未执行完整打包。后续已修正测试规则。`check-kernel-log.py` 只豁免完整匹配的 SRSO 虚拟 CPU/宿主机缓解提示，并在日志中记录；其他 WARNING、BUG、lockdep、KASAN 或 panic 仍判失败。日志检查器的五项正反例已在本地通过。

运行 `42226105395` 中启用配置的 17 项用例全部通过，但最终 `dmesg` 的 ANSI 颜色码破坏了上述提示的精确匹配，因此作业判失败。`47b1400` 将输出固定为 `dmesg --color=never`，没有放宽日志检查器。本轮两种配置已通过同一检查器，平台提示保留在原始日志中。

## 测试设计及边界

精简测试内核与完整安装包使用同一套固定 PVE 源码和补丁。精简配置分别编译 Full Cone 开/关并启用 lockdep；完整包保留 PVE 配置。测试 VM 使用路由器、两个内网设备和三个外网设备的独立 network namespace。内网先访问 A/B 验证 EIM，再由从未联系过的 C 发起新入站验证 EIF，避免把地址受限过滤误判为 Full Cone。没有连接或修改 PVE 节点。

已通过的启用测试覆盖 UDP EIM/EIF、fully-random、TCP 实际 connect/accept 和 32768 字节双向校验、TCP 关闭、FORWARD DROP、显式 SNAT/DNAT/REDIRECT、本机 socket 优先、低源端口、IPv6、协议隔离、ICMP、普通 SNAT 公网端点冲突、conntrack 超时/删除/flush、并发映射与端口唯一性、端口耗尽、WAN down/up 和地址变化、conntrack zone 隔离。并发用例为两个内部设备、48 个源端点、96 次探测和 32 个控制线程；这是短时并发测试，不是长期压力测试。

以下项目仍需要实际环境，不能用 CI 替代：

- PVE `com` 实机启动、引导器、Secure Boot、自有 DKMS、ZFS 存储读写，以及 OpenWrt/LXC/VM 网络回归。
- 独立公网设备和真实链路上的 UDP/STUN、TCP 主动连接验收；CI 的“外网”是隔离测试拓扑。
- 长时间高负载、KASAN/KCSAN、内存泄漏检测，以及并发流量下的模块卸载和命名空间反复销毁。

本地 Windows 稀疏检出存在 Linux 大小写路径碰撞，因此本地只从固定 Git 对象读取并验证清单文件。CI 在 Linux 文件系统重新获取源码、应用完整 PVE 补丁并编译；没有把 Windows 工作树当作完整构建树。

安装与回滚见 [install-and-rollback.md](install-and-rollback.md)。本轮已通过完整工作流和实际包启动测试；独立 release `7.0.14-23-fullcone-pve` 用于与原内核并存。实机验收应在维护窗口按该文档执行。
