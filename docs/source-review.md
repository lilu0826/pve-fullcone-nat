# 源码研究与阻断报告

> 历史记录：这是首次源码研究的结论。用户随后明确要求继续修正方案、提交 GitHub 并执行 Actions；当前实现见 [design.md](design.md)，当前验证状态以 Actions 和 validation-status.md 为准。

研究日期：2026-11-06。结论仅覆盖固定版本的源码和静态推理；没有运行修改后的内核。

## 1. 阶段结论

已确认目标版本的真实 PVE 打包源码身份；已阅读 SONiC 原始补丁及 OpenWrt 984、987。发现参考实现的映射范围和随机端口分配路径不满足本任务。按 `task.md` 第 10 节“如果某个阶段发现设计不可行或存在安全风险，立即停止后续阶段”的要求，停止补丁移植、构建和安装交付。

这不是“纯内核实现一定不可行”的结论。它意味着不能把 984 + 987 直接套到自动 MASQUERADE/自动入站路径，然后宣称普通 SNAT/DNAT 不受影响。下文列出重新设计所需的不变量。

## 2. 已锁定的真实 PVE 基线

官方仓库：`https://git.proxmox.com/git/pve-kernel.git`。

| 对象 | 固定提交 |
| --- | --- |
| PVE 打包源码 | `c1ca7892dbc5087d01c12ad260bbe03e77c1a296` |
| `submodules/ubuntu-kernel` | `874594fa24531e1ea15fa72709d20047e4a8d77c` |
| `submodules/zfsonlinux` | `dcd0e4345f4253bb9e44cc1ab54c6f73196421aa` |
| OpenWrt 移植参考 | `f87ac2a95b77270af9180a16590cc548617336a1` |
| SONiC 原始补丁所在提交 | `fbe99cecd8035812cba1b67d3c941aafeae8d879` |

PVE 提交标题为 `bump version to 7.0.14-23`，提交时间为 2026-10-07 22:30:14 +0200。该提交的 Makefile 是 `KERNEL_MAJ=7`、`KERNEL_MIN=0`、`KERNEL_PATCHLEVEL=14`、`KREL=23`；changelog 首项是 `proxmox-kernel-7.0 (7.0.14-23) trixie`。它与用户提供的发行包版本一致。

以上从官方 Git 仓库克隆并用 `git show` / `git ls-tree` 检查；[官方 GitHub 镜像提交](https://github.com/proxmox/pve-kernel/commit/c1ca7892dbc5087d01c12ad260bbe03e77c1a296)可交叉核对。内核子模块上一轮升级记录为 `update sources to Ubuntu-7.0.0-39.39`，不能用 kernel.org 的同名版本替代它。

**范围限制：**已获取固定内核提交并稀疏检出 netfilter 相关源码。对所审查的七个文件筛选了全部 PVE kernel patch，实际命中 0155 的头文件修改，并在一次性检查目录应用该文件的对应修改。没有完成整个内核的 PVE 补丁应用或构建，不能把这一范围内的检查称为完整移植成功。

### 参考补丁的实测文本兼容性

在上述范围基线上，GNU patch `--batch --dry-run --fuzz=0 -p1` 检查 984 返回 0（允许行号 offset，未使用 fuzz）。随后只在一次性检查目录应用 984，987 同样以 dry-run、fuzz=0 检查并返回 0。原始输出保存在 [research-checks.log](research-checks.log)。

所以阻断原因**不是已证明补丁文本不能应用到 7.0**，而是应用后的语义不能满足本任务。没有编译，没有应用 985/986。另试 `git apply --check --recount` 时，984 的未加前缀空白上下文行被判为 corrupt patch；GNU patch 可以处理该补丁格式。不能把 Git 的解析错误误报为目标内核代码冲突。

### 配置与打包

已检查上述固定 PVE 提交中的 Makefile、`debian/rules`、`debian/control.in` 和 `debian/rules.d/config-*.opts`：

- Makefile 从内核子模块的 `debian/scripts/misc/annotations --arch amd64 --export` 生成原始配置，再应用 PVE 配置选项，并运行 `olddefconfig`。不能自行拿 upstream defconfig 代替。
- `config-common.opts` 显式启用 `CONFIG_MODVERSIONS`，与宿主机输出一致。
- PVE 将内核源码复制到构建目录，应用 `patches/kernel/*.patch`；本次 Full Cone 修改将来必须基于此最终源码。
- 已识别 PVE 补丁 `0155-net-openvswitch-conntrack-avoid-modifying-shared-unc.patch` 修改 `include/net/netfilter/nf_conntrack.h`，增加 `nf_ct_shared()`。没有因为原补丁可能应用成功就忽略它。
- 正常入口为 `make deb`，内部使用 `dpkg-buildpackage`，同时构建内核、模块、ZFS 和头文件，不能只编译两三个 NAT 模块。
- image 包本身包含内核模块；该打包系统没有本任务示例中的独立 `linux-modules-...` 包。
- 还会生成系列 kernel/headers 元包、linux-tools、tools debug 包和签名模板；kernel debug 包由 build profile 控制。`signed-template` 不是已经由 Proxmox 签名的内核。
- `KREL_EXTRA` 是官方提供的并存内核命名入口。例如 `KREL_EXTRA=-fullcone` 将产生 `7.0.14-23-fullcone-pve`，并非手工重命名为 `7.0.14-23-pve-fullcone`。未来必须检查实际包名、安装路径和维护脚本。
- ABI 检查必须记录真实变化。不得通过忽略所有检查，将改变 `struct nf_conn` 的模块伪装成原 ABI。独立 release、完整重编译和外部 DKMS 验证均必需。

## 3. 阻断 A：入站查找不区分 Full Cone 与普通 SNAT

证据来自固定 OpenWrt 提交的 [984 补丁](https://github.com/mufeng05/openwrt-sonic-fullcone/blob/f87ac2a95b77270af9180a16590cc548617336a1/kernel/984-add-sonic-fullcone-support.patch)及 [987 补丁](https://github.com/mufeng05/openwrt-sonic-fullcone/blob/f87ac2a95b77270af9180a16590cc548617336a1/kernel/987-sonic-fullcone-fix-races-and-drops.patch)：

1. `nf_nat_setup_info()` 在 `maniptype == NF_NAT_MANIP_SRC` 时向 `nf_nat_by_manip_src` 插入 conntrack；插入并未限定为 Full Cone，更没有限定为 IPv4 MASQUERADE。
2. `find_appropriate_dst()` 匹配公网端点、协议、netns 和 zone，没有检查条目是否由本项目的 MASQUERADE 创建。
3. 987 为遍历和发布增加锁，但没有增加这样的来源标记和筛选。
4. 所以，若自动入站路径无条件调用该查找，普通显式 SNAT 也可能被反向转换到内网。

具体静态反例：B 的显式 SNAT 建立 `B:5000 → PUBLIC:40000 → R1:443`。R2 从另一地址主动访问 `PUBLIC:40000`，原先没有匹配的 conntrack，也没有显式 DNAT。自动调用原查找函数会找到 B 的普通 SNAT 条目并建立入站 DNAT。这违反任务对非 Full Cone NAT 的范围约束。是否最终送达 B 仍取决于 FORWARD；不能把此问题夸大为已经实测绕过 FORWARD。

**要求的修正：**只有 IPv4 TCP/UDP MASQUERADE 可以发布带明确资格标记的映射；入站、出站复用和删除都必须检查同一资格与同一生命周期。netns、zone、地址族、协议、WAN 地址和必要的接口身份不能遗漏。不能仅在调用处检查“这是 TCP/UDP”就认为已经隔离。

## 4. 阻断 B：fully-random 下无法保证 EIM

984 的 `get_unique_tuple()` 仅在没有 `NF_NAT_RANGE_PROTO_RANDOM_ALL` 时调用原有映射复用路径。987 串行化同一内部端点的分配，并在竞争重试时设置 `NF_NAT_RANGE_PROTO_RANDOM_FULLY`，但不改变此前的复用条件。

因此 `masquerade fully-random` 下，同一内部端点到不同远端可以获得不同公网端口。增加锁可以防止两个内部端点误用同一个三元组，却不能使两个不同分配自动变成同一个映射。

**要求的修正：**对 Full Cone 模式先查找并复用有效映射，random/fully-random 只影响首次映射的端口选择和冲突重选。端口范围不兼容时，需要明确拒绝还是划分映射域，不能悄悄破坏 EIM。普通 SNAT 的随机语义仍保留。此选择需要明确写入设计和验收。

## 5. 不能靠加一个标志完成的入站设计

以下路径已对照固定内核提交的现有实现，标注 Full Cone 的部分仍是设计草案，不是已经实现的功能：

```text
出站新连接
  现有 nft/iptables MASQUERADE
  → IPv4 masquerade helper
  → Full Cone 资格 + 端点映射复用/首次保留
  → 原有 NAT setup 与 conntrack confirmation

入站新连接
  defrag/conntrack 建立独立连接跟踪条目
  → 现有显式 PREROUTING NAT 规则优先
  → 没有绑定时，查找合格的 Full Cone MASQUERADE 映射
  → 通过 NAT setup 建立该新连接的 DNAT
  → 路由 → 原有 FORWARD → POSTROUTING → confirmation
```

已核实的函数与潜在插入点（行号为未应用 Full Cone 补丁的固定内核源码）：

| 文件/行 | 观察 |
| --- | --- |
| `nf_nat_masquerade.c:28` | `nf_nat_masquerade_ipv4()` 选取出接口地址，记录 masq_index，复制 range，然后调用 `nf_nat_setup_info(..., SRC)` |
| `nf_nat_core.c:771` | `nf_nat_setup_info()` 更新 reply tuple，设置 NAT 状态并发布 bysource 索引 |
| `nf_nat_proto.c:786` | `nf_nat_ipv4_ops` 同时列出 PRE_ROUTING、POST_ROUTING、LOCAL_OUT、LOCAL_IN |
| `nf_nat_core.c:1180` | `nf_nat_register_fn()` 在首个规则注册时注册整组底层 NAT hooks；不需要用户新增 PREROUTING 链才有底层入口 |
| `nf_nat_core.c:904` | `nf_nat_inet_fn()` 遍历该 hook 的 NAT lookup entries；非 ACCEPT 立即返回，已有绑定跳到 do_nat |
| `nf_nat_core.c:949` | 无 lookup entries 或全部未建立绑定时进入 `null_bind`，随后调用 `nf_nat_alloc_null_binding()`；这是候选 fallback 插入点 |
| `nf_nat_proto.c:607` | `nf_nat_ipv4_pre_routing()` 调用 NAT，目的地址改变后清除旧 dst 缓存 |

这使“没有用户态 PREROUTING Full Cone 规则”的方案在调用入口上有可行基础，不需要另造一个抢先改包的 hook。接下来仍须验证：

- 只有 POSTROUTING 规则时也要有入站处理入口，且卸载最后一条 NAT 规则、销毁 netns 时正确注销。
- 不能在每条 NAT 基础链返回时立即 fallback，否则会抢占后续优先级的显式 DNAT/REDIRECT。
- 也不能等 `IPS_DST_NAT_DONE` 的 null binding 已发布后硬改 tuple。必须在最终 null binding 前有正确的 fallback 位置。
- 应尊重既有 drop verdict、已有 NAT 绑定以及明确的“不做 NAT”决策。任意优先级链和同优先级链必须有定义。
- 不能改写 skb 后绕开 `nf_nat_setup_info()`，不能将 R2 的新 TCP SYN 直接附到 R1 的旧连接上。
- 新 TCP 连接继续按 NEW 处理；不标记 ESTABLISHED/RELATED 来获得放行。SYN-ACK 必须通过该新 DNAT 连接的反向 NAT 返回。
- 内部应用必须在同一端口有 TCP listener；一个 connect() 客户端不会自动变成可接受陌生 SYN 的服务器。
- 如果现有 FORWARD 丢弃 WAN NEW，那么新增入站仍应被丢弃。这是保留防火墙语义的正确结果，不能为“测出全锥”修改状态或绕过过滤。

## 6. 映射竞争、端口和生命周期

987 处理了两类值得保留的修正：按 translated-source 桶加锁保护复制；同一内部端点的 setup 串行化，并在发布前重新检查三元组。它还修复无端口范围时的三元组检查，以及普通 NAT 的失败返回行为。移植时应保留这些目的，不能因为函数名相同就机械复制。

仍需验证以下不变量：

- 原始端点锁 → 公网端点锁 → 原有 NAT 索引锁的顺序必须与销毁、错误退出、netns 清理一致；不允许在持有 spinlock 时睡眠。
- conntrack 使用 `SLAB_TYPESAFE_BY_RCU`；“持有 RCU 读锁”本身不能保证对象尚未复用。复制和删除要有一致保护，或取引用后重新验证对象身份。
- 尚未确认、标记 dying、创建失败、超时、flush、接口 down 和地址删除时，不能留下可供入站使用的失效映射。
- 同一个内部端点的多个出站连接需要共享映射；其中一条销毁不能错误删除仍被其他连接使用的映射。
- 入站建立的新连接如何参与映射保活、原出站连接结束后是否仍保持 EIM，必须有明确策略。
- IPv4/IPv6 比较不能只比较地址 union；必须把地址族纳入匹配。
- 普通 SNAT 可合法地与不同远端共享公网端口；Full Cone 需要唯一的公网端点归属。仅在 Full Cone 分配时检查冲突，不能阻止之后的普通 SNAT 抢占同一端点。需要明确混用时的仲裁和回归边界，不能用“给所有 SNAT 都启用 Full Cone”解决。
- 显式端口范围必须被尊重；没有范围时可考虑 1024–65535，但低源端口会被重映射。1024 下限不能保护 8006、51820 等高端口服务。
- 本机 socket 监听和 NAT 分配不共享同一端口分配器。仅在创建映射时扫描监听端口，也不能解决之后 bind()/listen() 的竞争。需要定义本机服务、显式 DNAT 和 Full Cone 映射的优先级，不能承诺“端口范围设为 1024 起就不会冲突”。
- 耗尽时只能使该 Full Cone 映射创建失败，不能回退成共享三元组后仍标称 Full Cone。有限随机尝试失败与整个端口池确实耗尽要区分记录。

## 7. 修正方案与继续条件

建议保留“仅内核修改”的目标，重新设计**仅供 IPv4 MASQUERADE 发布的映射资格和生命周期**，以及位于显式 NAT 决策之后、null binding 之前的入站 fallback。Kconfig 可采用默认 y 的 `CONFIG_NF_NAT_FULLCONE_MASQUERADE`；关闭时应编译掉附加状态和入口。无需增加 nft 语法，也不应把 Full Cone flag 加入允许用户态显式 SNAT 使用的公共默认行为。

开始阶段三之前必须完成：将固定内核子模块展开为完整构建树并应用全部 PVE 补丁；完成上述调用路径的边界设计；写清 ordinary NAT / Full Cone / 本机服务冲突仲裁；审查并发、销毁和错误路径的映射不变量；设计相应负向测试。

另一种可选路线是使用参考项目的显式 Full Cone PRE/POST 规则，但这会改变用户态规则，**不符合当前任务**，不能擅自采用。仅保留现有普通 MASQUERADE 是当前可用的运行基线，不把它称作完成了 TCP/UDP Full Cone。

阶段三至六未启动；没有生成或部署任何新内核。安装与回滚命令应在真实包和启动方式可核验后制定，而不是现在给出假定包名的 `dpkg -i`。
