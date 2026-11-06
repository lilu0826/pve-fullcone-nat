# 任务规格：PVE Linux 7.0 内核原生 MASQUERADE Full Cone NAT

## 1. 项目目标

将 Broadcom / SONiC Full Cone NAT 实现移植到 Proxmox VE 使用的 Linux 内核：

- 目标内核：Linux 7.0.14-23-pve
- 目标平台：x86_64 / AMD64
- 宿主机：Proxmox VE 9
- 主机名称：com

核心目标：

**只修改 Linux 内核，使原生 IPv4 MASQUERADE 自动具备 Full Cone NAT 能力。**

不修改任何用户态程序，不增加新的 nftables 语法，不增加新的 NAT target，不要求用户修改现有防火墙规则。

原有规则：

```nft
table ip nat {
    chain POSTROUTING {
        type nat hook postrouting priority srcnat;
        oifname "eth1" masquerade
    }
}
```

保持完全不变。

启用修改后的内核后，该规则自动实现 Full Cone NAT。

## 2. 功能范围

### 2.1 必须实现

仅对 IPv4 MASQUERADE 启用 Full Cone NAT。

支持：

- TCP
- UDP

如果对应内核连接跟踪模块支持，也可以扩展：

- UDP-Lite
- SCTP
- DCCP（如果目标内核仍然支持）

不要求实现没有端口概念的 ICMP、GRE 等协议的 Full Cone 行为。

### 2.2 NAT 行为

实现：

- EIM（Endpoint Independent Mapping）
- EIF（Endpoint Independent Filtering）

出站方向：

同一内网源端点访问不同远端 IP、端口时，复用相同的公网映射：

```text
192.168.50.100:5000 -> 8.8.8.8:443
192.168.50.100:5000 -> 1.1.1.1:443

映射为：

PUBLIC_IP:30001 -> 8.8.8.8:443
PUBLIC_IP:30001 -> 1.1.1.1:443
```

入站方向：

不同外部源 IP、源端口访问同一个公网映射端口时，能够通过内核映射查找找到正确的内部设备。

TCP 必须验证完整三次握手及双向数据传输，不能仅根据 STUN 或 UDP 测试结果判断 TCP Full Cone 已实现。

### 2.3 不修改的行为

以下规则必须保持原有语义：

- 显式 SNAT
- 显式 DNAT
- REDIRECT
- 普通非 MASQUERADE NAT
- IPv6 NAT
- 非目标协议的 NAT 行为

不要把 Full Cone 设置为整个 nf_nat 子系统的全局默认行为。

Full Cone 的自动启用范围仅限 IPv4 MASQUERADE。

## 3. 上游实现与参考代码

主要参考：

Broadcom SONiC 官方内核补丁：

https://github.com/sonic-net/sonic-linux-kernel/blob/master/patches-sonic/Support-for-fullcone-nat.patch

移植参考：

https://github.com/mufeng05/openwrt-sonic-fullcone

重点研究：

### 984 补丁

SONiC 原始 Full Cone NAT 内核实现，以及相关上游修复。

重点关注：

- struct nf_conn 扩展
- nat_by_manip_src 辅助哈希表
- 三元组索引
- NAT 映射复用
- 出站 EIM
- 入站 EIF
- RCU 与哈希桶锁
- conntrack 生命周期和释放

### 987 补丁

重点移植以下修复：

- 多核并发时的 NAT 映射竞争
- 不带端口范围时的三元组唯一性检查
- 普通 NAT 误丢包
- masquerade fully-random 等特殊场景兼容性

不要移植 985、986 用户态补丁。

不要修改 iptables、nftables、libnftnl、firewall4、LuCI。

参考项目目前明确测试的内核版本是 6.6、6.12、6.18，并未宣称支持 Linux 7.0。因此必须进行针对性源码适配，不能直接假设补丁可以应用。

## 4. 内核修改方案

### 4.1 自动启用条件

研究 Linux 7.0.14 的 MASQUERADE 实现。

重点检查：

- net/netfilter/nf_nat_masquerade.c
- net/netfilter/nf_nat_core.c
- net/netfilter/nf_nat_proto.c
- include/net/netfilter/nf_conntrack.h
- include/net/netfilter/nf_nat.h

在 IPv4 MASQUERADE 初始化 NAT range 的路径中自动设置 Full Cone 标志。

如果 SONiC 的实现要求 SNAT 端口范围，则在 MASQUERADE 内部为支持 Full Cone 的协议设置适当的端口范围，参考：

```text
1024-65535
```

需要分析低端口源端口映射、端口冲突、端口耗尽和公网本地服务端口冲突问题。

不要通过伪造用户态传入的地址范围来触发 Full Cone。

### 4.2 入站反向查找

这是本项目的关键要求。

原项目通过 POSTROUTING Full Cone 规则和 PREROUTING Full Cone 规则配合工作。

本项目不能依赖用户态额外生成 PREROUTING Full Cone 规则。

必须研究如何在内核 NAT 入站处理路径中自动识别已经建立的 Full Cone MASQUERADE 映射，并执行对应的反向查找。

要求：

- 外部任意源 IP 可以访问已有 Full Cone 映射。
- 正确找到原始内部目标。
- 不允许绕过 conntrack 生命周期管理。
- 不允许破坏 TCP 连接状态跟踪。
- 不允许影响非 Full Cone NAT 规则。
- 不允许绕过现有 FORWARD 防火墙策略。

如果无法在不修改用户态的情况下安全实现上述行为，应先输出技术分析，不得用不完整实现冒充成功。

### 4.3 编译选项

建议增加独立 Kconfig 选项：

```text
CONFIG_NF_NAT_FULLCONE_MASQUERADE
```

要求：

- 默认开启。
- 编译时可以关闭。
- 开启时仅对 IPv4 MASQUERADE 生效。
- 不改变普通 SNAT/DNAT 的行为。

如果目标内核的构建体系不适合增加独立选项，可以使用清晰、可审查的编译宏，但必须说明原因。

## 5. 内核兼容性要求

必须以 PVE 对应的真实源码版本为基础。

不要使用未经验证的 upstream Linux 7.0 源码替代 PVE 内核源码。

首先确认：

- PVE 内核源码仓库
- 对应 7.0.14-23-pve 的源码版本或提交
- PVE 内核配置文件
- Debian 内核打包方式
- CONFIG_MODVERSIONS 配置
- 当前内核模块 vermagic
- PVE 内核补丁和本地修改

必须确保生成的内核包与现有 PVE 环境兼容。

由于修改了 struct nf_conn 等核心结构，不能默认认为只重新编译 nf_nat.ko 和 nft_masq.ko 就足够。

优先采用完整 PVE 内核包构建，确保内核映像和所有受影响的模块使用同一套源码、配置及 ABI。

不得覆盖当前运行内核或自动删除现有可启动内核。

## 6. GitHub Actions 自动编译

创建完整 GitHub Actions 工作流。

要求：

1. 使用固定版本的 PVE 内核源码，不使用不固定的 master。
2. 自动获取或使用仓库中锁定的 PVE 内核配置。
3. 应用 SONiC 984、987 补丁及针对 Linux 7.0 的适配补丁。
4. 执行源码补丁检查。
5. 编译内核及受影响模块。
6. 执行必要的静态检查。
7. 生成 Debian 内核安装包。
8. 上传 GitHub Actions Artifacts。
9. 保存完整编译日志。
10. 输出源码提交号、补丁版本、编译配置及构建时间。

推荐输出：

```text
artifacts/
    linux-image-7.0.14-23-pve-fullcone_amd64.deb
    linux-headers-7.0.14-23-pve-fullcone_amd64.deb
    linux-modules-7.0.14-23-pve-fullcone_amd64.deb
    build-info.txt
    patches/
    build.log
```

实际包名必须以 PVE 打包系统生成的名称为准，不要人为伪造 Debian 包名。

如果需要构建其他关联内核包，应明确列出。

GitHub Actions 不得自动向任何 PVE 主机部署或安装内核。

## 7. 测试与验收

### 7.1 基础测试

确认：

- 内核正常启动。
- conntrack 正常。
- nftables 正常。
- 原有 MASQUERADE 规则正常。
- 普通 SNAT/DNAT 行为不变。
- OpenWrt 虚拟机及其他容器网络不受影响。

### 7.2 UDP Full Cone 测试

使用不同 STUN 服务器验证：

- 同一个内部 UDP 端点访问不同目标时，公网映射保持不变。
- 外部不同源地址能够访问已有映射。
- 内部设备能正确接收数据。
- 端口映射冲突时不会错误转发到其他内部设备。

### 7.3 TCP Full Cone 测试

使用外部独立网络设备进行主动 TCP 连接测试。

验证：

1. 内部设备主动建立 TCP 出站连接。
2. NAT 建立映射。
3. 外部第二台设备从不同源 IP 和源端口主动连接该公网映射。
4. 内部设备正确收到 SYN。
5. SYN-ACK 的源地址和源端口正确转换为公网映射。
6. TCP 三次握手成功。
7. 双向数据正常传输。
8. 连接关闭及 conntrack 清理正常。

不能只通过 TCP 端口扫描或 STUN 结果认定成功。

### 7.4 并发与稳定性

测试：

- 多内网设备使用相同源端口。
- 大量并发连接。
- 不同 CPU 核心同时创建映射。
- NAT 端口耗尽。
- conntrack 超时与删除。
- conntrack flush。
- WAN 断线重连。
- MASQUERADE 接口地址变化。
- 内核日志中无 UAF、NULL dereference、内存泄漏及锁竞争问题。

### 7.5 防火墙安全

Full Cone NAT 不得绕过现有防火墙策略。

必须确认：

- WAN 入站 FORWARD 规则仍然有效。
- 未授权的内部端口不会因为 Full Cone 映射而绕过 FORWARD DROP。
- 已有 conntrack 映射不会错误地授权其他协议。
- 显式端口转发和普通 DNAT 不受影响。

## 8. 交付物

最终提交：

1. 完整的 Linux 7.0.14-23-pve 内核补丁。
2. GitHub Actions 工作流。
3. 补丁应用脚本。
4. PVE 内核编译脚本。
5. Debian 安装包。
6. 构建日志。
7. 补丁移植说明。
8. 测试报告。
9. 安装与回滚说明。

## 9. 开发约束

- 不修改任何用户态 NAT 工具。
- 不修改 nftables 命令语法。
- 不修改 firewall4。
- 不修改 libnftnl。
- 不增加独立 Full Cone NAT 用户态服务。
- 不依赖额外的 nftables PREROUTING Full Cone 规则。
- 不影响 IPv6。
- 不改变显式 SNAT 和 DNAT 的行为。
- 不允许用仅 UDP 的实现冒充 TCP/UDP Full Cone。
- 不允许未经验证直接覆盖宿主机内核。

## 10. 开发执行顺序

请严格按以下顺序执行：

阶段一：源码研究

获取准确的 PVE 7.0.14-23-pve 内核源码，分析 984、987 补丁与目标内核的差异。

阶段二：技术设计

明确出站 EIM 和入站 EIF 的内核调用路径，特别是如何不依赖用户态 PREROUTING 规则实现自动反向查找。

阶段三：补丁移植

实现最小化内核修改，确保普通 MASQUERADE 自动启用 Full Cone。

阶段四：静态检查

检查补丁能否完整应用、代码逻辑、并发锁、生命周期和内核编译兼容性。

阶段五：GitHub Actions

创建可重复执行的自动编译工作流。

阶段六：测试与交付

构建 Debian 内核包，提供测试结果、安装和回滚文档。

如果某个阶段发现设计不可行或存在安全风险，立即停止后续阶段，输出具体原因和替代方案，不得为了完成编译而绕过问题。

最终验收标准：

在完全不修改现有 nftables 用户态规则的前提下：

```nft
oifname "eth1" masquerade
```

能够自动实现 IPv4 TCP/UDP Full Cone NAT，并且显式 SNAT、DNAT 保持原有行为。