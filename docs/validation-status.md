# 验证记录

> 后续进展：已实现三段式补丁和 CI，正在启动 GitHub Actions。下表保留首轮研究时的记录，尚不能视为当前代码的最终验收结果；新运行结果将在本文件更新。

日期：2026-11-06。当前不是功能验收报告的“通过”版本。

| 检查 | 结果 | 证据/限制 |
| --- | --- | --- |
| 目标宿主机版本 | 已核对用户输出 | 见 host-baseline.md |
| 官方 PVE 提交 | 已验证 | 官方仓库存在目标提交，Makefile/changelog 匹配 |
| 内核和 ZFS gitlink | 已验证 | 固定 PVE 提交的 `git ls-tree` |
| 984 / 987 来源 | 已固定 | 本地 clone 的 HEAD + Git blob SHA + SHA-256 |
| SONiC 原始补丁 | 已读取并固定 | GitHub 文件工具，固定提交 |
| 目标内核源码 | 已获取固定提交、稀疏检出 | 已读取 NAT 相关文件，未审阅整个内核 |
| PVE 全量补丁应用 | 未执行 | 已对七个检查文件筛选全量 patch 并应用相关 header 修改；不是完整构建树 |
| 984 文本应用检查 | 范围内通过 | GNU patch dry-run / fuzz=0；有行号 offset，随后仅在一次性检查目录应用 |
| 987 文本应用检查 | 范围内通过 | 在检查目录的 984 基础上 dry-run / fuzz=0；未正式移植 |
| 映射范围静态分析 | 发现阻断 | 普通 SNAT 也被索引且可被原 EIF 查找命中 |
| fully-random EIM 分析 | 发现阻断 | 复用路径受 RANDOM_ALL 条件排除 |
| 并发/UAF/锁验证 | 未执行运行验证 | 仅审阅参考补丁，不等同于 KASAN/lockdep 通过 |
| 编译、Debian 打包 | 未执行 | 阶段停止；没有 Linux 构建环境或 Actions 构建日志 |
| UDP EIM/EIF | 未执行 | 没有测试内核 |
| TCP 三次握手/双向数据 | 未执行 | 没有测试内核和独立外网测试机 |
| FORWARD/SNAT/DNAT/IPv6 回归 | 未执行 | 不以原系统正常代表补丁通过 |
| 安装、重启、回滚 | 未执行 | 未连接或改动 PVE 主机 |

## 后续必须实际执行的验收

1. 在隔离的测试 VM 启动独立 release 的完整内核，记录 uname、配置、模块 vermagic、包文件校验和串口日志。Kconfig 开、关分别编译。
2. 用固定内部 UDP socket 向不同地址/端口发包，由外部端记录实际公网端点；由未参与此前通信的第三端发数据，内部验证内容。STUN 只能作为辅助。
3. TCP 测试程序需有同端口监听和出站连接能力。维持到外部 A 的出站连接，由不同地址/源端口的 B 主动连接映射；抓取 SYN、SYN-ACK、ACK，双向交换随机内容并逐字节校验，记录 FIN/RST 和 conntrack 清理。
4. 只设置原始 POSTROUTING masquerade、没有用户态 PREROUTING NAT 链时完成上述测试；同时验证多条、不同优先级 NAT 基础链、显式 DNAT、REDIRECT 和无 NAT 路径。
5. FORWARD DROP 必须使第三方入站失败；ACCEPT 对照才应通过。不伪造 ESTABLISHED，不从失败测试中删除防火墙来冒充兼容。
6. 多内部主机同源端口、同内部端点跨 CPU 创建、端口池耗尽、fully-random、低端口、显式范围及与普通 SNAT/本机监听端口冲突均单独测试。
7. conntrack 超时/删除/flush、首包未确认即失败、接口地址变化、WAN down/up、netns 和模块卸载必须在并发流量下测试；收集 KASAN、KCSAN、lockdep 等适用的诊断输出。
8. 比较显式 SNAT/DNAT、IPv6、非 TCP/UDP，以及 OpenWrt 容器/其他 VM 的基线行为。所有未执行项目保留“未验证”，不以脚本存在或编译成功替代。

## 构建与安装交付限制

本地为 Windows。稀疏检出 netfilter 时，`xt_DSCP` / `xt_dscp` 等仅大小写不同的 Linux 文件在 Windows 文件系统发生路径碰撞，导致这部分工作树与 Git 对象不一致。研究所用的七个锁定文件无此冲突，检查目录的源码也通过 `git show <固定提交>:<路径>` 从 Git 对象读取。完整构建必须在 Linux 文件系统重新检出；不能直接把这个 Windows 工作树打包当作完整内核源码。参考材料校验脚本仅校验清单列出的文件，明确不代表全树校验。

本次没有生成 `.deb`、`build.log` 或 GitHub Actions 构建运行。[research-checks.log](research-checks.log) 是参考补丁文本检查的真实输出，不是编译日志。未创建占位的“成功”构建工作流。未来只有完整补丁检查和设计门槛通过后，才启动完整 PVE 打包并上传真实产物和失败日志。

未来安装必须保留 `7.0.14-23-pve`，确认 GRUB/systemd-boot、Secure Boot、ZFS 和 DKMS 情况，再用真实包名制定并存安装和一次性试启动流程。当前没有安全可执行的本项目内核安装步骤。
