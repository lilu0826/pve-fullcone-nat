# 原生 MASQUERADE 实现设计

本版基于 `sources.lock.json` 和 `patches/manifest.json` 中的固定源码。实现已经写入补丁，运行结果尚须以 CI 记录为准。

## 范围与调用路径

- 默认开启 `CONFIG_NF_NAT_FULLCONE_MASQUERADE`，可编译关闭。
- 只在 `nf_nat_masquerade_ipv4()` 对 TCP/UDP 设置私有内核标志和接口字段。UAPI 的 NAT flag mask 不增加 Full Cone 位；setup 还检查内部接口字段、地址族、协议和 zone。旧 xtables 路径即使传入未知标志位也不能单凭该位启用扩展；既有 nft/iptables 工具和规则不变。
- 不带端口范围时在 helper 内部使用 1024–65535；明确提供的范围仍受尊重。低源端口因此可能被转换到高端口。
- 普通显式 SNAT、DNAT、REDIRECT、IPv6 和非 TCP/UDP 不启用 Full Cone。方向不对称的 conntrack zone 保持原 MASQUERADE 行为，本版只对双向一致的 zone 启用扩展。

出站：IPv4 MASQUERADE → 端点 setup 锁 → 带资格标记的映射复用 → 三元组端口选择 → 公网桶锁下重新检查并发布 → 既有 conntrack 确认。

入站：既有 conntrack → 原 NAT lookup 规则全部处理 → `nf_nat_inet_fn()` 最终 `null_bind` 点 → 查找有资格的确认映射 → 标准 `nf_nat_setup_info(DST)` → 路由和原 FORWARD → 标准 reply NAT。

首次 IPv4 NAT 规则注册就会注册底层整组 NAT hooks，因此不要求添加用户态 PREROUTING 链。已有显式 NAT 绑定直接跳过 fallback；规则的非 ACCEPT verdict 保留。新外部 TCP 连接使用独立 conntrack，保持 NEW，绝不伪装为旧连接的 ESTABLISHED/RELATED。

## 对 984 / 987 的调整

1. 保留 SONiC translated-source 三元组索引和 987 的桶锁、同源 setup 锁及分配后原子复查。
2. `fullcone_masq` 资格位位于 `nf_conn` 的 memset 初始化区域，避免 slab 复用时继承资格。只有本项目的 MASQUERADE 发布映射时设置。
   出接口索引也保存在初始化区域，并在索引发布前写入；查找不读取其他未确认 conntrack 的扩展区，因为该扩展区随后可能被 `krealloc()` 移动。持有哈希桶锁只保护 conntrack 本体，不自动保护扩展区。
3. EIF 仅使用确认、未 dying、未超时、同协议/地址族/netns/zone、同 WAN 接口的合格映射。所有 conntrack tuple 的复制都在对应的删除锁下完成，不把查找到的裸指针传出临界区。
4. EIM 在 random/fully-random 端口选择前执行。随机标志影响首次分配，不能使后续连接换映射。同端点随后提供不兼容端口范围时丢弃该新建映射，避免悄悄拆分 EIM。
5. 修正 987 三元组复查中的提前返回：找到同内部端点不能掩盖同桶中其他冲突绑定。
6. 入站新连接记录 masquerade 接口以参与 WAN 清理；它的 original 方向是 WAN→LAN，所以跳过原来面向出站 MASQUERADE 的 oif-change 判断。地址删除检查使用该连接 original 的公网目的地址。

辅助索引仍记录普通 source NAT，目的是识别公网端点冲突，不能因此授权入站。Kconfig 关闭时不设置资格、不做自动入站；当前版本仍保留辅助索引和新增结构成员，所以关闭构建也必须用完整、匹配 ABI 的模块。

## 明确的优先级和生命周期

显式 DNAT/REDIRECT 优先。本机 socket 优先：在自动入站之前使用内核 IPv4 socket lookup，保护包括高端口在内的本机服务。已有 listener 或后续新 listener 都在新流量的 lookup 时检查；已经建立的 conntrack 继续既有 NAT。它不是对所有未来 bind() 的端口预留协议。

普通 SNAT 的分配语义保留。如果显式 SNAT 后来合法占用同一个公网端点但对应另一内部端点，自动 EIF 对该歧义端点停止，而不把流量发错主机，也不改写显式 SNAT。这是冲突时的失败关闭规则。显式端口转发/本机服务与 Full Cone 同时要求占用同一公网端口时，不可能都获得独占访问，优先级必须明确。

映射寿命由使用该出站映射的 conntrack 条目决定。至少一个合格出站条目仍有效时可以建立新的入站连接；最后一个出站条目失效后，不再接受新的自动反向映射。已经建立的入站 TCP/UDP 连接使用自己的 conntrack，仍可完成通信，但不会单独维持一个永久监听映射。flush/接口变化遵循 conntrack 与 masquerade 清理机制。

没有独立守护服务、周期 GC 或用户态 Full Cone target。普通 FORWARD DROP 仍会拦截新入站；只有 NAT 能力变化不等于防火墙自动允许 WAN NEW。

## 构建和验证边界

release 使用 PVE 的 `KREL_EXTRA=-fullcone`，得到 `7.0.14-23-fullcone-pve`；包版本为 `7.0.14-23+fullcone1`。完整构建包含 ZFS、内核模块和 headers，并保留原有 ABI 检查输出。新的 release 允许与 `7.0.14-23-pve` 并存，不应混装两套模块。

CI 的外部 A/B/C 是测试 VM 中独立网络命名空间和 IP，不是公网实机。先访问 A/B 检查 EIM，再由未联系过的 C 检查 EIF。TCP 测试真正执行 connect/accept、三次握手和 32768 字节双向传输；UDP 测试实际核对公网端点和新来源回包。独立公网设备、PVE 实机启动、长时间负载、KASAN/KCSAN 仍不能靠 CI 短测声称通过。
